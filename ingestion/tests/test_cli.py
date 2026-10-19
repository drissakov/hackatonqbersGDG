"""Synthetic, temporary-file importer checks; no fixture enters the city corpus."""

import asyncio
import copy
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.app.schemas import POIRecord, UpsertResult
from ingestion import cli
from ingestion.categories import CATEGORY_FILTERS
from ingestion.osm import OSMError


@pytest.fixture
def snapshot():
    fetched = "2026-10-19T00:00:00Z"
    return {
        "format": "qadam-osm-snapshot-v1",
        "provider": "osm",
        "city": "astana",
        "license": "ODbL-1.0",
        "rights_basis_url": "https://www.openstreetmap.org/copyright",
        "fetched_at": fetched,
        "source_timestamp": fetched,
        "complete": True,
        "boundary": {
            "type": "Feature",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[71.0, 50.0], [72.0, 50.0], [72.0, 52.0], [71.0, 52.0], [71.0, 50.0]]]
                ],
            },
            "properties": {
                "osm_type": "relation",
                "osm_id": 91,
                "source_timestamp": fetched,
                "url": "https://www.openstreetmap.org/relation/91",
                "fetched_at": fetched,
                "tags": {
                    "boundary": "administrative",
                    "admin_level": "4",
                    "wikidata": "Q1520",
                    "name": "Synthetic test boundary",
                },
            },
        },
        "queries": [
            {
                "category": name,
                "status": "ok",
                "count": int(name == "food"),
                "error_code": None,
                "source_timestamp": fetched,
                "element_ids": ["node/1"] if name == "food" else [],
            }
            for name in CATEGORY_FILTERS
        ],
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 51.0,
                "lon": 71.5,
                "tags": {"name": "Synthetic test cafe", "name:kk": "Сынақ", "amenity": "cafe"},
            }
        ],
    }


def run_snapshot(tmp_path, snapshot, *options):
    path = tmp_path / "synthetic-snapshot.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "data"
    code = cli.main(
        [
            "import-osm",
            "--city",
            "astana",
            "--from-snapshot",
            str(path),
            "--data-dir",
            str(output),
            *options,
        ]
    )
    return code, output


def test_export_is_canonical_reproducible_and_does_not_touch_db(tmp_path, snapshot, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("export-only must not initialize the database")

    monkeypatch.setattr(cli, "database_upsert", forbidden)
    code, output = run_snapshot(tmp_path, snapshot, "--export-only")
    assert code == 0
    payload = (output / "normalized/pois.jsonl").read_bytes()
    manifest = json.loads((output / "normalized/manifest.json").read_text("utf-8"))
    rows = [json.loads(line) for line in payload.splitlines()]
    assert len(rows) == manifest["records_count"] == 1
    assert manifest["sha256"] == hashlib.sha256(payload).hexdigest()
    schema = json.loads((cli.ROOT / "contracts/poi.schema.json").read_text("utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for row in rows:
        validator.validate(row)
        POIRecord.model_validate(row)
    assert manifest["sidecar_required"]
    assert manifest["normalization"]["records"][rows[0]["id"]]["names"]["kk"] == "Сынақ"
    assert len((output / "normalized/first-10.jsonl").read_text("utf-8").splitlines()) == 1
    assert (output / "raw" / f"{manifest['import_id']}.json").exists()
    code, _ = run_snapshot(tmp_path, snapshot, "--export-only")
    assert code == 0
    assert payload == (output / "normalized/pois.jsonl").read_bytes()


def test_failure_preserves_previous_export_and_reports_unavailable(tmp_path, snapshot, monkeypatch):
    _, output = run_snapshot(tmp_path, snapshot, "--export-only")
    previous = [
        (output / "normalized" / name).read_bytes() for name in ("pois.jsonl", "manifest.json")
    ]

    def fail(_):
        raise OSMError("http_forbidden")

    monkeypatch.setattr(cli, "fetch_astana", fail)
    assert (
        cli.main(["import-osm", "--city", "astana", "--export-only", "--data-dir", str(output)])
        == 1
    )
    assert previous == [
        (output / "normalized" / name).read_bytes() for name in ("pois.jsonl", "manifest.json")
    ]
    report = json.loads((output / "source-report.json").read_text("utf-8"))
    assert report["status"] == "failed"
    assert report["error_code"] == "http_forbidden"
    assert report["upsert"]["status"] == "not_run"


def test_partial_query_export_is_not_a_success_or_empty_database(tmp_path, snapshot):
    snapshot["complete"] = False
    query = next(q for q in snapshot["queries"] if q["category"] == "museum")
    query.update(status="failed", error_code="http_rate_limited")
    code, output = run_snapshot(tmp_path, snapshot, "--export-only")
    assert code == 2
    report = json.loads((output / "source-report.json").read_text("utf-8"))
    assert report["status"] == "partial"
    assert report["records_count"] == 1
    assert report["coverage"]["city_coverage"] == "unknown"


def test_empty_or_unlicensed_snapshot_never_replaces_corpus(tmp_path, snapshot):
    _, output = run_snapshot(tmp_path, snapshot, "--export-only")
    previous = (output / "normalized/pois.jsonl").read_bytes()
    for field, value in (("provider", "twogis"), ("elements", [])):
        broken = copy.deepcopy(snapshot)
        broken[field] = value
        code, _ = run_snapshot(tmp_path, broken, "--export-only")
        assert code == 1
        assert (output / "normalized/pois.jsonl").read_bytes() == previous


def test_upsert_uses_s01_protocol_and_validates_counts():
    class Repository:
        async def upsert_pois(self, records):
            self.received = records
            return UpsertResult(inserted=1, updated=0, rejected=0, rejections=[])

    repo = Repository()
    result = asyncio.run(cli.upsert_records(repo, [{"id": "synthetic"}]))
    assert repo.received == [{"id": "synthetic"}]
    assert result == {"inserted": 1, "updated": 0, "rejected": 0, "rejections": []}
    with pytest.raises(OSMError, match="invalid_upsert_counts"):
        asyncio.run(cli.upsert_records(Repository(), [{"id": "synthetic"}, {"id": "other"}]))


def test_database_not_configured_returns_not_run(monkeypatch):
    from backend.app import settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        settings,
        "Settings",
        lambda: type(
            "Settings",
            (),
            {"database_url": type("Secret", (), {"get_secret_value": lambda _: ""})()},
        )(),
    )
    assert cli.database_upsert([]) == {"status": "not_run", "reason": "database_not_configured"}


def test_database_errors_are_sanitized(monkeypatch):
    from backend.app import settings

    def fail():
        raise ValueError("synthetic-sensitive-dsn-must-never-be-reported")

    monkeypatch.setattr(settings, "Settings", fail)
    result = cli.database_upsert([])
    assert result == {"status": "failed", "reason": "database_import_failed"}


def test_database_unavailable_keeps_valid_export(tmp_path, snapshot, monkeypatch):
    monkeypatch.setattr(
        cli,
        "database_upsert",
        lambda *args: {"status": "not_run", "reason": "database_not_configured"},
    )
    code, output = run_snapshot(tmp_path, snapshot)
    assert code == 2
    assert (output / "normalized/pois.jsonl").exists()
    assert json.loads((output / "source-report.json").read_text("utf-8"))["status"] == "partial"


def test_concurrent_import_cannot_publish_or_replace_active_report(tmp_path, snapshot, capsys):
    _, output = run_snapshot(tmp_path, snapshot, "--export-only")
    before = (output / "source-report.json").read_bytes()
    with cli.data_lock(output):
        code = cli.main(
            ["import-osm", "--city", "astana", "--export-only", "--data-dir", str(output)]
        )
    assert code == 1
    assert "import_already_running" in capsys.readouterr().out
    assert (output / "source-report.json").read_bytes() == before
    # The kernel releases the lock; a subsequent normal import still works.
    assert run_snapshot(tmp_path, snapshot, "--export-only")[0] == 0


def test_full_outage_reports_individual_failed_categories(tmp_path, monkeypatch):
    error = OSMError("empty_corpus")
    error.queries = [
        {
            "category": "museum",
            "status": "failed",
            "count": 0,
            "error_code": "http_forbidden",
            "element_ids": [],
        }
    ]

    def fail(_):
        raise error

    monkeypatch.setattr(cli, "fetch_astana", fail)
    assert (
        cli.main(["import-osm", "--city", "astana", "--export-only", "--data-dir", str(tmp_path)])
        == 1
    )
    report = json.loads((tmp_path / "source-report.json").read_text("utf-8"))
    assert report["queries"][0]["error_code"] == "http_forbidden"
    assert not (tmp_path / "normalized/pois.jsonl").exists()


def test_batches_preserve_global_rejection_indexes_and_bound_concurrency():
    class Repository:
        active = 0
        maximum = 0

        async def upsert_pois(self, records):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0)
            self.active -= 1
            return UpsertResult(
                inserted=len(records) - 1,
                updated=0,
                rejected=1,
                rejections=[{"index": len(records) - 1, "code": "invalid_record"}],
            )

    repository = Repository()
    result = asyncio.run(cli.upsert_batches(repository, list(range(5)), batch_size=2))
    assert result["status"] == "completed"
    assert result["inserted"] == 2
    assert result["rejected"] == 3
    assert [row["index"] for row in result["rejections"]] == [1, 3, 4]
    assert repository.maximum == 2


def test_failed_batch_is_unknown_and_does_not_hide_other_committed_batches():
    class Repository:
        async def upsert_pois(self, records):
            if records[0] == 2:
                raise RuntimeError("synthetic-sensitive-provider-body")
            return UpsertResult(inserted=len(records), updated=0, rejected=0, rejections=[])

    result = asyncio.run(cli.upsert_batches(Repository(), list(range(5)), batch_size=2))
    assert result["status"] == "partial"
    assert result["inserted"] == 3
    assert result["rejected"] == 0
    assert result["failed_batch_records_unknown"] == 2
    assert "sensitive" not in json.dumps(result)


def test_broken_progress_output_does_not_discard_committed_counts():
    class Repository:
        async def upsert_pois(self, records):
            return UpsertResult(inserted=len(records), updated=0, rejected=0, rejections=[])

    def progress(_):
        raise BrokenPipeError("synthetic closed output")

    result = asyncio.run(
        cli.upsert_batches(Repository(), list(range(5)), batch_size=2, progress=progress)
    )
    assert result["status"] == "completed"
    assert result["inserted"] == 5
    assert len(result["batches"]) == 3


@pytest.mark.parametrize(("configured", "expected"), [(1, 1), (3, 2), (5, 2)])
def test_import_respects_existing_connection_budget(configured, expected, monkeypatch):
    from backend.app import database, repository, settings

    class Pool:
        def __init__(self, url, max_size):
            assert max_size == expected

        def close(self):
            pass

    class Repository:
        def __init__(self, pool):
            pass

        async def upsert_pois(self, records):
            return UpsertResult(inserted=len(records), updated=0, rejected=0, rejections=[])

    class Settings:
        database_pool_size = configured
        database_url = type("Secret", (), {"get_secret_value": lambda _: "synthetic"})()

    monkeypatch.setattr(settings, "Settings", Settings)
    monkeypatch.setattr(database, "DatabasePool", Pool)
    monkeypatch.setattr(repository, "PostgresPOIRepository", Repository)
    result = cli.database_upsert([{"id": "synthetic"}])
    assert result["status"] == "completed"
    assert result["concurrency"] == expected
