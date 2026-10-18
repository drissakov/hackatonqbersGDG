"""Batch validation, TLS/pooling and deterministic source text without a database."""

import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import psycopg
import pytest

from backend.app.database import DatabasePool, DatabaseUnavailable, connection_options, schema_name
from backend.app.repository import PostgresPOIRepository, prepare_records
from backend.app.schemas import Coordinates


def poi():
    path = Path(__file__).resolve().parents[2] / "contracts/examples/poi.test.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_validation_rights_fixture_gate_and_duplicate_indexes():
    denied = poi()
    denied["sources"][0].update(storage_allowed=False, indexing_allowed=False)
    rows, errors = prepare_records([{}, denied, poi(), poi()], allow_test=True)
    assert len(rows) == 1
    assert [(r.index, r.code) for r in errors] == [
        (0, "invalid_record"),
        (1, "storage_not_permitted"),
        (3, "duplicate_in_batch"),
    ]
    assert prepare_records([poi()])[1][0].code == "storage_not_permitted"
    twogis = poi()
    twogis["sources"][0]["provider"] = "twogis"
    assert prepare_records([twogis], True)[1][0].code == "storage_not_permitted"


@pytest.mark.parametrize("field", ["name", "id", "license"])
@pytest.mark.parametrize("invalid_text", ["invalid\x00text", "invalid\ud800text"])
def test_unstorable_text_rejects_one_record_before_identity_deduplication(field, invalid_text):
    invalid = poi()
    if field == "license":
        invalid["sources"][0][field] = invalid_text
    else:
        invalid[field] = invalid_text
    prepared, rejections = prepare_records([invalid, poi()], allow_test=True)
    assert [row.index for row in prepared] == [1]
    assert [(row.index, row.code) for row in rejections] == [(0, "invalid_record")]


def test_source_text_hash_ignores_ids_timestamps_and_generated_content():
    original = prepare_records([poi()], True)[0][0]
    changed = poi()
    changed["id"] = "changed-id"
    changed["sources"][0]["retrieved_at"] = "2031-01-01T00:00:00Z"
    assert prepare_records([changed], True)[0][0].text_hash == original.text_hash
    changed["description"] = "Different sourced text"
    assert prepare_records([changed], True)[0][0].text_hash != original.text_hash


def test_matching_primary_provenance_has_conservative_null_and_oldest_semantics():
    row = poi()
    row["provenance"].append(copy.deepcopy(row["provenance"][0]))
    row["provenance"][1]["observed_at"] = "2029-01-01T00:00:00Z"
    assert prepare_records([row], True)[0][0].observed_at.year == 2029
    row["provenance"][1]["observed_at"] = None
    assert prepare_records([row], True)[0][0].observed_at is None
    row["provenance"][1]["external_id"] = "another-object"
    assert prepare_records([row], True)[0][0].observed_at.year == 2030


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:synthetic@localhost/db?sslmode=disable",
        "postgresql://u:synthetic@localhost/db?sslmode=prefer",
        "postgresql://u:synthetic@aws-0-example.pooler.supabase.com:6543/db",
        "postgresql://u:synthetic@db.example.supabase.co:5432/db",
    ],
)
def test_tls_and_supabase_session_mode_are_required(url):
    with pytest.raises(DatabaseUnavailable):
        connection_options(url)


def test_pool_is_lazy_reuses_connections_commits_rolls_back_and_closes(monkeypatch):
    connection = MagicMock(closed=False, broken=False)
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr("backend.app.database.psycopg.connect", connect)
    pool = DatabasePool("postgresql://u:synthetic@localhost/db", 1)
    connect.assert_not_called()
    with pool.connection() as actual:
        assert actual is connection
    assert connect.call_args.kwargs["sslmode"] == "require"
    connection.commit.assert_called_once()
    with pytest.raises(ValueError), pool.connection():
        raise ValueError("synthetic")
    connection.rollback.assert_called_once()
    assert connect.call_count == 1
    pool.close()
    connection.close.assert_called_once()
    with pytest.raises(DatabaseUnavailable), pool.connection():
        pass


def test_driver_errors_are_sanitized_and_broken_connections_discarded(monkeypatch):
    connection = MagicMock(closed=False, broken=True)
    monkeypatch.setattr("backend.app.database.psycopg.connect", lambda **kw: connection)
    pool = DatabasePool("postgresql://u:synthetic@localhost/db", 1)
    with pytest.raises(DatabaseUnavailable, match="^database_operation_failed$"), pool.connection():
        raise psycopg.OperationalError("synthetic secret and provider payload")
    assert connection.close.called
    pool.close()


def test_pool_rejects_a_connection_without_actual_tls(monkeypatch):
    connection = MagicMock(closed=False, broken=False)
    connection.pgconn.ssl_in_use = False
    monkeypatch.setattr("backend.app.database.psycopg.connect", lambda **kw: connection)
    pool = DatabasePool("postgresql://u:synthetic@localhost/db", 1)
    with pytest.raises(DatabaseUnavailable, match="^database_tls_required$"), pool.connection():
        pytest.fail("An unencrypted connection must never reach repository code")
    assert connection.close.called
    pool.close()


def test_schema_and_geo_parameters_cannot_inject_sql():
    with pytest.raises(ValueError):
        schema_name("app; DROP SCHEMA app")
    repo = PostgresPOIRepository(DatabasePool(""))
    for radius, limit in [(0, 1), (100001, 1), (5, 101), (True, 1)]:
        with pytest.raises(ValueError):
            asyncio.run(repo.geo_search(Coordinates(latitude=51, longitude=71), radius, limit))
