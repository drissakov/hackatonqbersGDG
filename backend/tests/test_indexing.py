"""Source text, skip hashes, rights and batch API behavior without network access."""

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.database import DatabaseUnavailable
from backend.app.indexing import build_document, normalize_name
from backend.app.repository import PostgresPOIRepository
from backend.app.schemas import POIRecord
from backend.tests.test_repository import poi
from scripts.embed_pois import index_corpus, load_corpus


def test_nfc_kazakh_and_names_keep_their_alphabet():
    assert normalize_name("  ӘЛЕМ—Қазақ ІҢ ӨҮҰҺ  ") == "әлем қазақ ің өүұһ"
    assert normalize_name("Cafe\u0301") == normalize_name("Café")


def test_only_attributed_fields_enter_text_and_source_times_do_not_change_hash():
    row = poi()
    row["description"] = "Unattributed generated sentence"
    row["provenance"][0]["fields"] = ["name", "activity_code"]
    original = build_document(POIRecord.model_validate(row))
    assert row["description"] not in original.text
    assert row["primary_source_id"] in original.text
    row["sources"][0]["retrieved_at"] = "2031-01-01T00:00:00Z"
    assert build_document(POIRecord.model_validate(row)).text_hash == original.text_hash
    row["name"] = "Changed synthetic source name"
    assert build_document(POIRecord.model_validate(row)).text_hash != original.text_hash
    row["sources"][0]["indexing_allowed"] = False
    assert build_document(POIRecord.model_validate(row)) is None


def test_aliases_and_source_tags_affect_hash_but_not_unknown_facts():
    record = POIRecord.model_validate(poi())
    details = {
        "source_id": record.primary_source_id,
        "names": {"kk": "Әлем"},
        "aliases": ["World"],
        "facts": {},
        "unknown": {"quiet": None},
    }
    original = build_document(record, details)
    assert "әлем" in original.names and "world" in original.names
    details["unknown"]["quiet"] = "a generated claim"
    assert build_document(record, details).text_hash == original.text_hash
    details["aliases"].append("Synthetic alias")
    assert build_document(record, details).text_hash != original.text_hash
    details["source_id"] = "unrelated-source"
    with pytest.raises(ValueError, match="sidecar_source_mismatch"):
        build_document(record, details)


class MemoryRepository:
    def __init__(self):
        self.row = {"document": poi(), "indexing_allowed": True}
        self.saved = []

    async def index_records(self, after):
        return [self.row] if not after else []

    async def save_search_document(self, document, vector=None):
        self.staged_hash = document.text_hash
        self.saved.append(document)
        self.row.update(
            source_document=document.record.model_dump(mode="json"), metadata=document.metadata
        )
        if vector is not None:
            self.row.update(
                model="text-embedding-3-large",
                dimensions=1536,
                text_version="poi-source-v1",
                document_text_hash=document.text_hash,
            )
        return "saved"

    async def save_search_documents(self, documents, vectors=None, *, require_staged=False):
        vectors = vectors if vectors is not None else [None] * len(documents)
        return [
            "stale"
            if require_staged and self.staged_hash != d.text_hash
            else await self.save_search_document(d, v)
            for d, v in zip(documents, vectors, strict=True)
        ]


def test_repeated_indexing_never_calls_provider_for_unchanged_text():
    repository, client = MemoryRepository(), AsyncMock()
    client.embed_many.return_value = [[1.0] + [0.0] * 1535]
    first = asyncio.run(index_corpus(repository, client))
    assert first["embedded_written"] == 1 and first["api_requests"] == 1
    second = asyncio.run(index_corpus(repository, client))
    assert second["skipped_unchanged"] == 1 and second["api_requests"] == 0
    assert client.embed_many.call_count == 1
    repository.row["document"]["name"] = "Changed synthetic source"
    third = asyncio.run(index_corpus(repository, client))
    assert third["embedded_written"] == 1 and client.embed_many.call_count == 2


def test_wrong_model_or_version_does_not_skip_and_missing_access_is_lexical_only():
    repository = MemoryRepository()
    doc = build_document(POIRecord.model_validate(repository.row["document"]))
    repository.row.update(
        document_text_hash=doc.text_hash,
        dimensions=1536,
        model="different-space",
        text_version="poi-source-v1",
    )
    report = asyncio.run(index_corpus(repository, None))
    assert report["status"] == "lexical_only" and report["skipped_unchanged"] == 0
    assert report["embedded_written"] == 0 and report["lexical_written"] == 1


def test_snapshot_mismatch_stops_before_writes_or_api_calls():
    repository, client = MemoryRepository(), AsyncMock()
    record = POIRecord.model_validate(poi())
    different = copy.deepcopy(repository.row["document"])
    different["name"] = "Changed"
    repository.row["document"] = different
    with pytest.raises(ValueError, match="database_corpus_snapshot_mismatch"):
        asyncio.run(index_corpus(repository, client, corpus=({record.id: record}, {}, {})))
    assert repository.saved == []
    client.embed_many.assert_not_called()


def test_dry_run_does_not_write_or_call_api():
    repository, client = MemoryRepository(), AsyncMock()
    report = asyncio.run(index_corpus(repository, client, dry_run=True))
    assert report["would_embed"] == 1 and report["api_requests"] == 0
    assert json.dumps(report) and repository.saved == []
    client.embed_many.assert_not_called()


def test_database_write_failure_reports_unknown_outcome_without_fabricated_counts():
    repository = MemoryRepository()
    repository.save_search_documents = AsyncMock(side_effect=DatabaseUnavailable("synthetic"))
    report = asyncio.run(index_corpus(repository, None))
    assert report["status"] == "unavailable" and report["unknown_write_outcome_records"] == 1
    assert report["lexical_written"] == report["embedded_written"] == 0


def export_pair(tmp_path):
    """Synthetic OSM-shaped export, never used by a real import or database."""
    import hashlib

    row = poi()
    identity = "osm:node:123"
    row.update(id=identity, external_id="node/123", primary_source_id=identity, is_test=False)
    row["sources"][0].update(
        source_id=identity,
        provider="osm",
        is_test=False,
        url="https://www.openstreetmap.org/node/123",
    )
    row["provenance"][0].update(source_id=identity, external_id="node/123")
    details = {
        "source_id": identity,
        "url": row["sources"][0]["url"],
        "names": {"kk": "Әлем"},
        "name_fields": {},
        "aliases_by_tag": {},
        "aliases": [],
        "facts": {},
    }
    payload = (json.dumps(row) + "\n").encode()
    manifest = {
        "format": "qadam-poi-export-v1",
        "provider": "osm",
        "city": "astana",
        "contract_version": "1.1.0",
        "sidecar_required": True,
        "complete": True,
        "import_id": "synthetic-test-import",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "records_count": 1,
        "normalization": {"records": {identity: details}},
    }
    jsonl, sidecar = tmp_path / "pois.jsonl", tmp_path / "manifest.json"
    jsonl.write_bytes(payload)
    sidecar.write_text(json.dumps(manifest), "utf-8")
    return jsonl, sidecar, manifest


def test_delivered_legacy_contract_is_accepted_but_corruption_is_rejected(tmp_path):
    jsonl, sidecar, manifest = export_pair(tmp_path)
    records, _, evidence = load_corpus(jsonl, sidecar)
    assert len(records) == 1 and evidence["contract_version"] == "1.1.0"
    jsonl.write_bytes(jsonl.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="invalid_corpus_manifest_or_checksum"):
        load_corpus(jsonl, sidecar)


def test_manifest_source_identity_mismatch_is_rejected(tmp_path):
    jsonl, sidecar, manifest = export_pair(tmp_path)
    manifest["normalization"]["records"]["osm:node:123"]["source_id"] = "unrelated"
    sidecar.write_text(json.dumps(manifest), "utf-8")
    with pytest.raises(ValueError, match="corpus_source_identity_mismatch"):
        load_corpus(jsonl, sidecar)


def test_slow_embedding_does_not_overwrite_a_newer_staged_text():
    repository, client = MemoryRepository(), AsyncMock()

    async def embed_many(_):
        repository.staged_hash = "a-newer-alias-document"
        return [[1.0] + [0.0] * 1535]

    client.embed_many.side_effect = embed_many
    report = asyncio.run(index_corpus(repository, client))
    assert report["stale"] == 1 and report["embedded_written"] == 0
    assert repository.staged_hash == "a-newer-alias-document"


@pytest.mark.parametrize("staged_hash,expected", [("different-text", "stale"), (None, "saved")])
def test_repository_checks_staged_hash_and_only_writes_the_matching_embedding(
    staged_hash, expected
):
    document = build_document(POIRecord.model_validate(poi()))
    connection, pool = MagicMock(), MagicMock()
    pool.connection.return_value.__enter__.return_value = connection
    repo = PostgresPOIRepository(pool)
    repo.extension_schemas = lambda _: {"vector": "extensions"}
    connection.execute.return_value.fetchall.side_effect = [
        [
            {
                "id": document.record.id,
                "document": document.record.model_dump(mode="json"),
                "indexing_allowed": True,
                "indexed_text_hash": "0" * 64,
            }
        ],
        [
            {
                "poi_id": document.record.id,
                "text_hash": staged_hash or document.text_hash,
                "text_version": "poi-source-v1",
            }
        ],
    ]
    cursor = connection.cursor.return_value.__enter__.return_value
    events = []
    cursor.executemany.side_effect = lambda *args: events.append("advisory_or_write")
    connection.execute.side_effect = lambda *args: (
        events.append("row_read") or connection.execute.return_value
    )
    assert repo._save_search_documents([document], [[1.0] + [0.0] * 1535], True) == [expected]
    assert events[:2] == ["advisory_or_write", "row_read"]
    lock = cursor.executemany.call_args_list[0]
    assert "pg_advisory_xact_lock" in lock.args[0]
    primary = next(
        s for s in document.record.sources if s.source_id == document.record.primary_source_id
    )
    assert lock.args[1] == [
        (json.dumps(["app", primary.provider.value, document.record.external_id]),)
    ]
    writes = cursor.executemany.call_args_list[1:]
    assert len(writes) == (1 if expected == "saved" else 0)
    if writes:
        assert '"embeddings"' in writes[0].args[0].as_string()
