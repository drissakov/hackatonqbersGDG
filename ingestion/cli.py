"""Run from the repository root: python -m ingestion.cli import-osm --city astana."""

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ingestion.categories import CATEGORY_FILTERS
from ingestion.normalize import normalize_elements
from ingestion.osm import OSMError, OverpassClient, fetch_astana, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"


@contextmanager
def data_lock(data_dir: Path):
    """OS lock survives neither a crashed process nor an interpreter shutdown."""
    data_dir.mkdir(parents=True, exist_ok=True)
    # Keep a stable inode: unlinking a lock file lets new processes lock a new file.
    with (data_dir / ".import-osm.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise OSMError("import_already_running") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def atomic_write(path: Path, content: bytes):
    """Replace one artifact; manifest is published last as the checksum commit marker."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def coverage(records, boundary):
    """Observed counts and spatial cells; the number of all real city POIs is unknown."""
    rings = boundary["geometry"]["coordinates"]
    points = [point for polygon in rings for ring in polygon for point in ring]
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    cells = Counter()
    for row in records:
        point = row["location"]
        x = min(3, max(0, int(4 * (point["longitude"] - west) / (east - west))))
        y = min(3, max(0, int(4 * (point["latitude"] - south) / (north - south))))
        cells[f"{x},{y}"] += 1
    return {
        "city_coverage": "unknown",
        "scope": "OSM allowed categories within fetched Astana administrative boundary",
        "by_category": dict(sorted(Counter(r["activity_code"] for r in records).items())),
        "by_osm_type": dict(
            sorted(Counter(r["external_id"].split("/")[0] for r in records).items())
        ),
        "grid": {
            "bbox": [west, south, east, north],
            "columns": 4,
            "rows": 4,
            "counts": dict(sorted(cells.items())),
            "meaning": "Occupied bbox cells are not an estimate of city completeness.",
        },
        "missing_hours": sum(r["opening_hours_text"] is None for r in records),
        "missing_price": sum(r["price_kzt_per_person"] is None for r in records),
        "duplicate_identities": len(records) - len({r["external_id"] for r in records}),
    }


def export_snapshot(snapshot, data_dir: Path, import_id: str):
    validate_snapshot(snapshot)
    records, metadata = normalize_elements(
        snapshot["elements"], fetched_at=snapshot["fetched_at"], boundary=snapshot["boundary"]
    )
    if not records:
        raise OSMError("no_valid_records")
    payload = b"".join(
        (
            json.dumps(
                row, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")
        for row in records
    )
    raw = json_bytes(snapshot)
    contract_version = json.loads((ROOT / "contracts/codes.json").read_text("utf-8"))[
        "contract_version"
    ]
    manifest = {
        "format": "qadam-poi-export-v1",
        "contract_version": contract_version,
        "import_id": import_id,
        "city": "astana",
        "provider": "osm",
        "fetched_at": snapshot["fetched_at"],
        "source_timestamp": snapshot["source_timestamp"],
        "endpoint": snapshot.get("endpoint"),
        "complete": snapshot["complete"],
        "attribution": ATTRIBUTION,
        "license": "ODbL-1.0",
        "license_url": LICENSE_URL,
        "rights_basis_url": "https://www.openstreetmap.org/copyright",
        "records_count": len(records),
        "sha256": digest(payload),
        "snapshot_sha256": digest(raw),
        "boundary": snapshot["boundary"],
        "queries": snapshot["queries"],
        "normalization": metadata,
        "coverage": coverage(records, snapshot["boundary"]),
        "sidecar_required": True,
        "sidecar_reason": "Contract 1.1.0 has no language names, aliases, fact verification, "
        "derived markers or coordinate accuracy fields. Keep this manifest.",
    }
    atomic_write(data_dir / "raw" / f"{import_id}.json", raw)
    generation = data_dir / "normalized" / "runs" / import_id
    atomic_write(generation / "pois.jsonl", payload)
    atomic_write(generation / "manifest.json", json_bytes(manifest))
    atomic_write(data_dir / "normalized" / "pois.jsonl", payload)
    atomic_write(data_dir / "normalized" / "manifest.json", json_bytes(manifest))
    atomic_write(
        data_dir / "source-registry.json",
        json_bytes(
            {
                "provider": "osm",
                "url": "https://www.openstreetmap.org/copyright",
                "license": "ODbL-1.0",
                "license_url": LICENSE_URL,
                "rights_basis_url": "https://www.openstreetmap.org/copyright",
                "storage_allowed": True,
                "indexing_allowed": True,
                "attribution": ATTRIBUTION,
                "fetched_at": snapshot["fetched_at"],
                "verified_at": None,
                "source_timestamp": snapshot["source_timestamp"],
                "endpoint": snapshot.get("endpoint"),
                "boundary_source_id": f"relation/{snapshot['boundary']['properties']['osm_id']}",
                "boundary_url": snapshot["boundary"]["properties"]["url"],
                "categories": CATEGORY_FILTERS,
                "permission_scope": "OSM only. No 2GIS payloads or other providers.",
            }
        ),
    )
    # Include each observed category before filling the ten-record review sample.
    sample = list({row["activity_code"]: row for row in reversed(records)}.values())
    sample.extend(row for row in records if row not in sample)
    sample = sample[:10]
    atomic_write(
        data_dir / "normalized" / "first-10.jsonl",
        b"".join(
            (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            for row in sample
        ),
    )
    return records, manifest


async def upsert_records(repository, records):
    """Only S01 owns SQL, transactions, stable identity and deletion policy."""
    from backend.app.schemas import UpsertResult

    result = UpsertResult.model_validate(await repository.upsert_pois(records))
    if result.inserted + result.updated + result.rejected != len(records):
        raise OSMError("invalid_upsert_counts")
    if any(item.index >= len(records) for item in result.rejections):
        raise OSMError("invalid_upsert_indexes")
    return result.model_dump(mode="json")


async def upsert_batches(repository, records, *, batch_size=100, concurrency=2, progress=None):
    """S01 is atomic per batch. Failed batches stay unknown, never fake rejections."""
    if type(batch_size) is not int or not 1 <= batch_size <= 1000 or concurrency not in (1, 2):
        raise ValueError("batch_size=1..1000 and concurrency=1..2 required")
    slots = asyncio.Semaphore(concurrency)

    async def persist(start):
        batch = records[start : start + batch_size]
        async with slots:
            try:
                result = await upsert_records(repository, batch)
                outcome = {
                    "status": "completed",
                    "start_index": start,
                    "attempted": len(batch),
                    **result,
                }
            except Exception:
                outcome = {
                    "status": "failed",
                    "start_index": start,
                    "attempted": len(batch),
                    "reason": "database_batch_failed",
                }
            if progress is not None:
                try:
                    progress(outcome)
                except Exception:
                    # A closed console must not discard already committed counters.
                    pass
            return outcome

    batches = await asyncio.gather(
        *(persist(start) for start in range(0, len(records), batch_size))
    )
    completed = [batch for batch in batches if batch["status"] == "completed"]
    failed = [batch for batch in batches if batch["status"] == "failed"]
    return {
        "status": "partial" if failed else "completed",
        "attempted": len(records),
        "inserted": sum(batch["inserted"] for batch in completed),
        "updated": sum(batch["updated"] for batch in completed),
        "rejected": sum(batch["rejected"] for batch in completed),
        "rejections": [
            {"index": batch["start_index"] + row["index"], "code": row["code"]}
            for batch in completed
            for row in batch["rejections"]
        ],
        "failed_batch_records_unknown": sum(batch["attempted"] for batch in failed),
        "batch_size": batch_size,
        "concurrency": concurrency,
        "batches": batches,
    }


def database_upsert(records, env_file=None):
    # Export-only never imports settings, driver or repository implementation.
    from backend.app.database import DatabasePool, DatabaseUnavailable
    from backend.app.repository import PostgresPOIRepository
    from backend.app.settings import Settings

    try:
        settings = Settings(_env_file=env_file) if env_file else Settings()
        if not settings.database_url.get_secret_value():
            return {"status": "not_run", "reason": "database_not_configured"}
        concurrency = min(2, settings.database_pool_size)
        pool = DatabasePool(settings.database_url.get_secret_value(), max_size=concurrency)
        try:
            repository = PostgresPOIRepository(pool)
            return asyncio.run(
                upsert_batches(
                    repository,
                    records,
                    concurrency=concurrency,
                    progress=lambda batch: print(
                        json.dumps({"stage": "upsert", **batch}), flush=True
                    ),
                )
            )
        finally:
            pool.close()
    except DatabaseUnavailable:
        return {"status": "failed", "reason": "database_unavailable"}
    except OSMError:
        raise
    except Exception:
        # Settings/driver/provider messages may contain credentials; never echo them.
        return {"status": "failed", "reason": "database_import_failed"}


def import_osm(args):
    import_id = "osm-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:12]
    report = {
        "import_id": import_id,
        "city": "astana",
        "provider": "osm",
        "started_at": datetime.now(UTC).isoformat(),
        "status": "failed",
        "upsert": {"status": "not_run"},
    }
    exit_code = 1
    try:
        if args.from_snapshot:
            snapshot = json.loads(args.from_snapshot.read_text(encoding="utf-8"))
        else:
            client = OverpassClient(
                timeout=args.timeout, retries=args.retries, concurrency=args.concurrency
            )
            snapshot = fetch_astana(client)
        records, manifest = export_snapshot(snapshot, args.data_dir, import_id)
        upsert = (
            {"status": "not_run", "reason": "export_only"}
            if args.export_only
            else database_upsert(records, args.env_file)
        )
        report.update(
            records_count=len(records),
            sha256=manifest["sha256"],
            snapshot_sha256=manifest["snapshot_sha256"],
            contract_version=manifest["contract_version"],
            complete=manifest["complete"],
            queries=[
                {k: v for k, v in query.items() if k != "element_ids"}
                for query in manifest["queries"]
            ],
            fetched_at=manifest["fetched_at"],
            source_timestamp=manifest["source_timestamp"],
            endpoint=manifest["endpoint"],
            normalization_stats=manifest["normalization"]["stats"],
            coverage=manifest["coverage"],
            boundary=manifest["boundary"]["properties"],
            upsert=upsert,
            attribution=ATTRIBUTION,
            license_url=LICENSE_URL,
            artifacts={
                "jsonl": str((args.data_dir / "normalized/pois.jsonl").resolve()),
                "manifest": str((args.data_dir / "normalized/manifest.json").resolve()),
                "sample": str((args.data_dir / "normalized/first-10.jsonl").resolve()),
            },
        )
        database_ok = args.export_only or upsert["status"] == "completed"
        no_rejections = upsert.get("rejected", 0) == 0
        report["status"] = (
            "completed" if manifest["complete"] and database_ok and no_rejections else "partial"
        )
        exit_code = 0 if report["status"] == "completed" else 2
    except OSMError as error:
        report["error_code"] = error.code
        if getattr(error, "queries", None):
            report["queries"] = [
                {k: v for k, v in query.items() if k != "element_ids"} for query in error.queries
            ]
    except (OSError, ValueError, TypeError, KeyError):
        report["error_code"] = "invalid_snapshot_or_artifact"
    report["finished_at"] = datetime.now(UTC).isoformat()
    if "records_count" in report:
        atomic_write(
            args.data_dir / "normalized" / "upsert-summary.json",
            json_bytes(
                {
                    "import_id": import_id,
                    "import_id_scope": "D02 local run",
                    "database_import_run_id": None,
                    "database_import_run_id_reason": "S01 upsert_pois returns counters only",
                    "records_count": report["records_count"],
                    "sha256": report["sha256"],
                    "upsert": report["upsert"],
                }
            ),
        )
    atomic_write(args.data_dir / "reports" / f"{import_id}.json", json_bytes(report))
    atomic_write(args.data_dir / "source-report.json", json_bytes(report))
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "import_id",
                    "status",
                    "records_count",
                    "sha256",
                    "error_code",
                    "upsert",
                )
                if key in report
            },
            ensure_ascii=False,
        )
    )
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("import-osm")
    command.add_argument("--city", choices=["astana"], required=True)
    command.add_argument("--export-only", action="store_true")
    command.add_argument("--from-snapshot", type=Path)
    command.add_argument("--data-dir", type=Path, default=ROOT / "data")
    command.add_argument(
        "--env-file", type=Path, help="Optional existing backend env file; never copied or printed"
    )
    command.add_argument(
        "--timeout", type=int, default=60, choices=range(10, 121), metavar="10..120"
    )
    command.add_argument("--retries", type=int, default=2, choices=range(4))
    command.add_argument("--concurrency", type=int, choices=[1, 2], default=1)
    args = parser.parse_args(argv)
    try:
        with data_lock(args.data_dir):
            return import_osm(args)
    except OSMError as error:
        print(json.dumps({"status": "failed", "error_code": error.code}))
        return 1
    except OSError:
        print(json.dumps({"status": "failed", "error_code": "artifact_write_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
