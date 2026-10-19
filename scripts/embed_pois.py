"""Index the database corpus: python -m scripts.embed_pois (from repository root)."""

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path

from pydantic import ValidationError

from backend.app.database import DatabasePool, DatabaseUnavailable
from backend.app.indexing import DIMENSIONS, EMBEDDING_MODEL, TEXT_VERSION, build_document
from backend.app.openai_client import OpenAIClient, ProviderError
from backend.app.repository import PostgresPOIRepository
from backend.app.schemas import POIRecord
from backend.app.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def load_corpus(jsonl: Path, manifest_path: Path) -> tuple[dict, dict, dict]:
    """Read the separately delivered pair. Do not execute anything from its archive."""
    payload = jsonl.read_bytes()
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("invalid_corpus_manifest_or_checksum")
    digest = hashlib.sha256(payload).hexdigest()
    if (
        manifest.get("format") != "qadam-poi-export-v1"
        or manifest.get("contract_version") not in {"1.1.0", "1.2.0", "1.3.0"}
        or manifest.get("provider") != "osm"
        or manifest.get("city") != "astana"
        or manifest.get("sidecar_required") is not True
        or type(manifest.get("complete")) is not bool
        or not isinstance(manifest.get("import_id"), str)
        or manifest.get("sha256") != digest
    ):
        raise ValueError("invalid_corpus_manifest_or_checksum")
    rows = [POIRecord.model_validate_json(line) for line in payload.decode("utf-8").splitlines()]
    records = {row.id: row for row in rows}
    normalization = manifest.get("normalization")
    sidecars = normalization.get("records") if isinstance(normalization, dict) else None
    if (
        not rows
        or len(records) != len(rows)
        or manifest.get("records_count") != len(rows)
        or not isinstance(sidecars, dict)
        or set(sidecars) != set(records)
    ):
        raise ValueError("corpus_counts_or_sidecars_mismatch")
    for record in rows:
        details = sidecars[record.id]
        if not isinstance(details, dict):
            raise ValueError("invalid_record_sidecar")
        if (
            record.is_test
            or re.fullmatch(r"(node|way|relation)/[1-9][0-9]*", record.external_id) is None
            or not record.id.startswith("osm:")
            or record.id != "osm:" + record.external_id.replace("/", ":")
            or record.primary_source_id != record.id
            or len(record.sources) != 1
            or record.sources[0].source_id != record.id
            or record.sources[0].provider != "osm"
            or str(record.sources[0].url) != f"https://www.openstreetmap.org/{record.external_id}"
            or record.sources[0].is_test
            or details.get("source_id") != record.id
            or details.get("url") != str(record.sources[0].url)
        ):
            raise ValueError("corpus_source_identity_mismatch")
        for field in ("names", "name_fields", "aliases_by_tag"):
            if not isinstance(details.get(field), dict):
                raise ValueError("invalid_sidecar_names")
            for value in details[field].values():
                values = value if isinstance(value, list) else [value]
                if any(
                    v is not None
                    and (not isinstance(v, str) or not v.strip() or len(v) > 4000 or "\x00" in v)
                    for v in values
                ):
                    raise ValueError("invalid_sidecar_names")
        if (
            not isinstance(details.get("aliases"), list)
            or any(
                not isinstance(n, str) or not n.strip() or len(n) > 4000 or "\x00" in n
                for n in details["aliases"]
            )
            or not isinstance(details.get("facts"), dict)
        ):
            raise ValueError("invalid_sidecar_facts_or_aliases")
        for fact in details["facts"].values():
            if (
                not isinstance(fact, dict)
                or fact.get("source_id") != record.id
                or not isinstance(fact.get("value"), str)
                or "\x00" in fact["value"]
            ):
                raise ValueError("sidecar_fact_source_mismatch")
        build_document(record, details)
    return (
        records,
        sidecars,
        {
            "import_id": manifest["import_id"],
            "contract_version": manifest["contract_version"],
            "records_count": len(rows),
            "jsonl_sha256": digest,
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "source_complete": manifest["complete"],
        },
    )


async def index_corpus(repository, client, *, corpus=None, limit=None, dry_run=False):
    report = {
        "model": EMBEDDING_MODEL,
        "dimensions": DIMENSIONS,
        "text_version": TEXT_VERSION,
        "database_records": 0,
        "eligible": 0,
        "lexical_written": 0,
        "embedded_written": 0,
        "skipped_unchanged": 0,
        "skipped_rights_or_facts": 0,
        "stale": 0,
        "deferred": 0,
        "api_requests": 0,
        "dry_run": dry_run,
        "sidecar_missing": 0,
        "status": "ok",
    }
    records, sidecars, evidence = corpus if corpus else ({}, {}, None)
    report["corpus"] = evidence
    after, rows = "", []
    while page := await repository.index_records(after):
        rows.extend(page)
        after = page[-1]["document"]["id"]
    report["database_records"] = len(rows)
    if not rows:
        report.update(status="failed", reason="database_corpus_empty")
        return report
    if records:
        actual = {row["document"]["id"]: row["document"] for row in rows}
        if any(
            actual.get(key) != record.model_dump(mode="json") for key, record in records.items()
        ):
            raise ValueError("database_corpus_snapshot_mismatch")
        report["corpus"]["database_matched_records"] = len(records)
    prepared = []
    for row in rows:
        record = POIRecord.model_validate(row["document"])
        details = sidecars.get(record.id)
        if details is None and row.get("source_document") == row["document"]:
            details = (row.get("metadata") or {}).get("sidecar")
        document = build_document(record, details) if row["indexing_allowed"] else None
        if document is None:
            report["skipped_rights_or_facts"] += 1
            continue
        report["eligible"] += 1
        report["sidecar_missing"] += details is None
        unchanged = (
            row.get("model") == EMBEDDING_MODEL
            and row.get("dimensions") == DIMENSIONS
            and row.get("text_version") == TEXT_VERSION
            and row.get("document_text_hash") == document.text_hash
        )
        if limit is not None and len(prepared) >= limit:
            report["deferred"] += 1
            continue
        prepared.append((document, unchanged))
    if dry_run:
        report["would_embed"] = sum(not unchanged for _, unchanged in prepared)
        return report
    pending = []
    for start in range(0, len(prepared), 100):
        batch = prepared[start : start + 100]
        try:
            statuses = await repository.save_search_documents([doc for doc, _ in batch])
        except DatabaseUnavailable:
            report.update(
                status="unavailable",
                reason="database_write_failed",
                unknown_write_outcome_records=len(batch),
            )
            return report
        for (document, unchanged), saved in zip(batch, statuses, strict=True):
            if saved == "stale":
                report["stale"] += 1
                continue
            report["lexical_written"] += 1
            if unchanged:
                report["skipped_unchanged"] += 1
            else:
                pending.append(document)
    if pending and client is None:
        report.update(status="lexical_only", reason="embedding_not_run")
        return report
    for start in range(0, len(pending), 32):
        batch = pending[start : start + 32]
        report["api_requests"] += 1
        try:
            vectors = await client.embed_many([document.text for document in batch])
        except ProviderError as exc:
            report.update(status="lexical_only", reason=exc.code)
            break
        try:
            statuses = await repository.save_search_documents(batch, vectors, require_staged=True)
        except DatabaseUnavailable:
            report.update(
                status="unavailable",
                reason="database_write_failed",
                unknown_write_outcome_records=len(batch),
            )
            return report
        for saved in statuses:
            report["stale" if saved == "stale" else "embedded_written"] += 1
    if report["stale"] or report["deferred"]:
        report["status"] = "partial"
    return report


async def run(args):
    corpus = None
    if args.jsonl.exists() or args.manifest.exists():
        corpus = load_corpus(args.jsonl, args.manifest)
    settings = Settings()
    pool = DatabasePool(settings.database_url.get_secret_value(), max_size=1)
    try:
        repository = PostgresPOIRepository(pool)
        options = dict(corpus=corpus, limit=args.limit, dry_run=args.dry_run)
        if args.lexical_only or args.dry_run or not settings.openai_api_key.get_secret_value():
            return await index_corpus(repository, None, **options)
        async with OpenAIClient(settings) as client:
            return await index_corpus(repository, client, **options)
    finally:
        pool.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=ROOT / "data/normalized/pois.jsonl")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/normalized/manifest.json")
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.limit is not None and args.limit < 1:
            raise ValueError("limit must be positive")
        report = asyncio.run(run(args))
    except DatabaseUnavailable:
        report = {"status": "unavailable", "reason": "database_unavailable_or_migration_required"}
    except (ValueError, OSError, KeyError, TypeError, ValidationError):
        report = {"status": "failed", "reason": "invalid_corpus_or_configuration"}
    output = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, "utf-8")
    print(output, end="")
    return 0 if report["status"] == "ok" else 2 if report["status"] == "lexical_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
