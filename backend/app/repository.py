"""Validated, atomic POI persistence for ingestion; no import-time connections."""

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from backend.app.database import DatabasePool, DatabaseUnavailable, schema_name
from backend.app.schemas import Coordinates, POIRecord, RejectedPOI, Source, UpsertResult


class POIRepository(Protocol):
    async def upsert_pois(self, records: Sequence[Mapping[str, object]]) -> UpsertResult:
        """Validate each record, enforce rights, and report inserted/updated/rejected.

        Stable key: (primary source provider, external_id). Rejected indexes refer
        to the original batch. Infrastructure failures raise and roll back the
        batch; they must not be reported as successful per-record rejections.
        """
        ...

    async def coverage(self) -> dict: ...

    async def geo_search(
        self, origin: Coordinates, radius_m: int = 5000, limit: int = 20
    ) -> list[POIRecord]: ...


@dataclass(frozen=True)
class PreparedPOI:
    index: int
    record: POIRecord
    identity: tuple[str, str]
    observed_at: datetime | None
    indexed_text: str
    text_hash: str
    indexing_allowed: bool


def validate_storage_text(value: object) -> None:
    """PostgreSQL text/jsonb cannot represent NUL or invalid UTF-8 text."""
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("PostgreSQL text cannot contain NUL")
        value.encode("utf-8")
    elif isinstance(value, dict):
        for item in value.values():
            validate_storage_text(item)
    elif isinstance(value, list):
        for item in value:
            validate_storage_text(item)


def prepare_records(records, allow_test=False):
    """Reject unsafe records before SQL. No raw values escape this boundary."""
    prepared, rejections, seen = [], [], set()
    for index, raw in enumerate(records):
        try:
            sources = [Source.model_validate(row) for row in raw.get("sources", [])]
            if any(not s.storage_allowed or s.provider == "twogis" for s in sources):
                rejections.append(RejectedPOI(index=index, code="storage_not_permitted"))
                continue
            record = POIRecord.model_validate(raw)
            validate_storage_text(record.model_dump(mode="json"))
        except (ValidationError, ValueError, TypeError, AttributeError):
            rejections.append(RejectedPOI(index=index, code="invalid_record"))
            continue
        if record.is_test and not allow_test:
            rejections.append(RejectedPOI(index=index, code="storage_not_permitted"))
            continue
        primary = next(s for s in record.sources if s.source_id == record.primary_source_id)
        identity = (primary.provider.value, record.external_id)
        if identity in seen:
            rejections.append(RejectedPOI(index=index, code="duplicate_in_batch"))
            continue
        seen.add(identity)
        observations = [
            p.observed_at
            for p in record.provenance
            if p.source_id == record.primary_source_id and p.external_id == record.external_id
        ]
        # Use the oldest matching fact; any unknown observation stays unknown.
        observed_at = (
            min(observations) if observations and all(t is not None for t in observations) else None
        )
        text = json.dumps(
            [
                record.name,
                record.description,
                record.address,
                record.activity_code.value,
                record.opening_hours_text,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        prepared.append(
            PreparedPOI(
                index,
                record,
                identity,
                observed_at,
                text,
                hashlib.sha256(text.encode("utf-8")).hexdigest(),
                all(s.indexing_allowed for s in record.sources),
            )
        )
    return prepared, rejections


class PostgresPOIRepository:
    def __init__(self, pool: DatabasePool, *, schema="app", allow_test=False):
        self.pool = pool
        self.schema = schema_name(schema)
        self.allow_test = allow_test

    def table(self, name):
        return sql.Identifier(self.schema, name)

    @staticmethod
    def extension_schemas(connection):
        rows = connection.execute(
            "SELECT e.extname, n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid=e.extnamespace "
            "WHERE e.extname IN ('postgis', 'vector', 'pg_trgm')"
        ).fetchall()
        found = {r["extname"]: r["nspname"] for r in rows}
        if set(found) != {"postgis", "vector", "pg_trgm"}:
            raise DatabaseUnavailable("database_migration_required")
        # Operators (including <=>) and PostGIS internals resolve actual schemas.
        path = sql.SQL(",").join(
            sql.Identifier(s) for s in dict.fromkeys(["pg_catalog", *found.values()])
        )
        connection.execute(
            "SELECT set_config('search_path', %s, true)", (path.as_string(connection),)
        )
        return found

    async def upsert_pois(self, records: Sequence[Mapping[str, object]]) -> UpsertResult:
        return await asyncio.to_thread(self._upsert, list(records))

    def _upsert(self, records):
        prepared, rejections = prepare_records(records, self.allow_test)
        inserted = updated = 0
        try:
            with self.pool.connection() as connection:
                extensions = self.extension_schemas(connection)
                # Sorted identity locks serialize concurrent inserts and stale checks.
                for item in sorted(prepared, key=lambda p: p.identity):
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (json.dumps([self.schema, *item.identity]),),
                    )
                # Acquire locks in a stable order, then retain original batch order
                # so canonical-ID collisions are attributed to the later record.
                for item in prepared:
                    existing = connection.execute(
                        sql.SQL(
                            "SELECT id, primary_observed_at, is_test FROM {} "
                            "WHERE source=%s AND source_item_id=%s FOR UPDATE"
                        ).format(self.table("pois")),
                        item.identity,
                    ).fetchone()
                    if existing and existing["is_test"] != item.record.is_test:
                        rejections.append(RejectedPOI(index=item.index, code="invalid_record"))
                        continue
                    old_time = existing["primary_observed_at"] if existing else None
                    if old_time is not None and (
                        item.observed_at is None or item.observed_at < old_time
                    ):
                        rejections.append(RejectedPOI(index=item.index, code="stale_record"))
                        continue
                    canonical_id = existing["id"] if existing else item.record.id
                    try:
                        with connection.transaction():
                            self._write(connection, extensions, item, canonical_id, bool(existing))
                    except psycopg.errors.UniqueViolation:
                        rejections.append(RejectedPOI(index=item.index, code="invalid_record"))
                        continue
                    if existing:
                        updated += 1
                    else:
                        inserted += 1
                result = UpsertResult(
                    inserted=inserted,
                    updated=updated,
                    rejected=len(rejections),
                    rejections=sorted(rejections, key=lambda r: r.index),
                )
                connection.execute(
                    sql.SQL(
                        "INSERT INTO {} (status, attempted, inserted, updated, rejected) "
                        "VALUES ('completed', %s, %s, %s, %s)"
                    ).format(self.table("import_runs")),
                    (len(records), result.inserted, result.updated, result.rejected),
                )
            return result
        except DatabaseUnavailable:
            # Best effort separate audit transaction; never mask the original failure.
            try:
                with self.pool.connection() as connection:
                    connection.execute(
                        sql.SQL(
                            "INSERT INTO {} (status, attempted, inserted, updated, "
                            "rejected, error_code) "
                            "VALUES ('failed', %s, 0, 0, 0, 'database_operation_failed')"
                        ).format(self.table("import_runs")),
                        (len(records),),
                    )
            except DatabaseUnavailable:
                pass
            raise

    def _write(self, connection, extensions, item, canonical_id, exists):
        record = item.record.model_copy(update={"id": canonical_id})
        location = record.location
        point = (
            sql.SQL("{}.ST_SetSRID({}.ST_MakePoint(%s,%s),4326)::{}.geography").format(
                *[sql.Identifier(extensions["postgis"])] * 3
            )
            if location
            else sql.SQL("NULL")
        )
        values = [item.identity[0], item.identity[1], Jsonb(record.model_dump(mode="json"))]
        if location:
            values.extend([location.longitude, location.latitude])
        values.extend(
            [
                item.indexed_text,
                item.text_hash,
                item.indexing_allowed,
                item.observed_at,
                record.is_test,
                canonical_id,
            ]
        )
        if exists:
            # Unchanged permitted text keeps its embedding. Any rights change or
            # text change invalidates it before the composite FK is updated.
            connection.execute(
                sql.SQL(
                    "DELETE FROM {} WHERE poi_id=%s AND (indexed_text_hash <> %s OR NOT %s)"
                ).format(self.table("embeddings")),
                (canonical_id, item.text_hash, item.indexing_allowed),
            )
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET source=%s, source_item_id=%s, document=%s, location={}, "
                    "indexed_text=%s, indexed_text_hash=%s, indexing_allowed=%s, "
                    "primary_observed_at=%s, is_test=%s, updated_at=now() WHERE id=%s"
                ).format(self.table("pois"), point),
                values,
            )
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE poi_id=%s").format(self.table("poi_sources")),
                (canonical_id,),
            )
        else:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {} (source,source_item_id,document,location,indexed_text,"
                    "indexed_text_hash,indexing_allowed,primary_observed_at,is_test,id) "
                    "VALUES (%s,%s,%s,{},%s,%s,%s,%s,%s,%s)"
                ).format(self.table("pois"), point),
                values,
            )
        for source in record.sources:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {} (poi_id,source_id,provider,retrieved_at,storage_allowed,"
                    "indexing_allowed,document) VALUES (%s,%s,%s,%s,%s,%s,%s)"
                ).format(self.table("poi_sources")),
                (
                    canonical_id,
                    source.source_id,
                    source.provider.value,
                    source.retrieved_at,
                    source.storage_allowed,
                    source.indexing_allowed,
                    Jsonb(source.model_dump(mode="json")),
                ),
            )
        for ordinal, fact in enumerate(record.provenance):
            connection.execute(
                sql.SQL(
                    "INSERT INTO {} (poi_id,ordinal,source_id,source_item_id,fields,observed_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s)"
                ).format(self.table("poi_facts")),
                (
                    canonical_id,
                    ordinal,
                    fact.source_id,
                    fact.external_id,
                    fact.fields,
                    fact.observed_at,
                ),
            )

    async def coverage(self) -> dict:
        return await asyncio.to_thread(self._coverage)

    def _coverage(self):
        with self.pool.connection() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            counts = connection.execute(
                sql.SQL(
                    "SELECT count(*) FILTER (WHERE NOT is_test) AS production_pois, "
                    "count(*) FILTER (WHERE is_test) AS test_pois, "
                    "count(*) FILTER (WHERE NOT is_test AND location IS NOT NULL) AS located_pois, "
                    "count(*) FILTER (WHERE NOT is_test AND location IS NULL) "
                    "AS missing_location_pois "
                    "FROM {}"
                ).format(self.table("pois"))
            ).fetchone()
            sources = connection.execute(
                sql.SQL(
                    "SELECT source, count(*) AS count FROM {} WHERE NOT is_test "
                    "GROUP BY source ORDER BY source"
                ).format(self.table("pois"))
            ).fetchall()
            runs = connection.execute(
                sql.SQL(
                    "SELECT count(*) AS total, count(*) FILTER (WHERE status='failed') AS failed, "
                    "coalesce(sum(rejected),0)::bigint AS rejected_records FROM {}"
                ).format(self.table("import_runs"))
            ).fetchone()
            embedded = connection.execute(
                sql.SQL(
                    "SELECT count(*) AS count FROM {} e JOIN {} p ON p.id=e.poi_id "
                    "WHERE NOT p.is_test"
                ).format(self.table("embeddings"), self.table("pois"))
            ).fetchone()["count"]
        return {
            "status": "ok",
            **counts,
            "embedded_pois": embedded,
            "by_source": {row["source"]: row["count"] for row in sources},
            "import_runs": runs,
            "city_coverage": "unknown",
            "is_production_dataset": counts["production_pois"] > 0,
        }

    async def geo_search(self, origin: Coordinates, radius_m=5000, limit=20) -> list[POIRecord]:
        if not isinstance(origin, Coordinates):
            raise ValueError("origin must be validated Coordinates")
        if type(radius_m) is not int or not 1 <= radius_m <= 100000:
            raise ValueError("radius_m must be between 1 and 100000")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return await asyncio.to_thread(self._geo_search, origin, radius_m, limit)

    def _geo_search(self, origin, radius_m, limit):
        with self.pool.connection() as connection:
            geo = sql.Identifier(self.extension_schemas(connection)["postgis"])
            point = sql.SQL("{}.ST_SetSRID({}.ST_MakePoint(%s,%s),4326)::{}.geography").format(
                geo, geo, geo
            )
            rows = connection.execute(
                sql.SQL(
                    "WITH origin AS (SELECT {} AS point) "
                    "SELECT p.document FROM {} p CROSS JOIN origin o "
                    "WHERE p.indexing_allowed AND p.location IS NOT NULL AND (NOT p.is_test OR %s) "
                    "AND {}.ST_DWithin(p.location,o.point,%s) "
                    "ORDER BY {}.ST_Distance(p.location,o.point), p.id LIMIT %s"
                ).format(point, self.table("pois"), geo, geo),
                (origin.longitude, origin.latitude, self.allow_test, radius_m, limit),
            ).fetchall()
        return [POIRecord.model_validate(row["document"]) for row in rows]
