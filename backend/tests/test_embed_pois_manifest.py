"""Current synthetic OSM exports retain checksum and indexing-rights enforcement."""

import hashlib
import json

import pytest

from backend.app.indexing import build_document
from backend.tests.test_indexing import export_pair
from scripts.embed_pois import load_corpus


def current_export(tmp_path):
    jsonl, sidecar, manifest = export_pair(tmp_path)
    manifest["contract_version"] = "1.3.0"
    sidecar.write_text(json.dumps(manifest), "utf-8")
    return jsonl, sidecar, manifest


def test_current_contract_export_can_be_loaded_for_embedding(tmp_path):
    jsonl, sidecar, _ = current_export(tmp_path)

    records, sidecars, evidence = load_corpus(jsonl, sidecar)

    assert evidence["contract_version"] == "1.3.0"
    assert evidence["records_count"] == len(records) == 1
    record = next(iter(records.values()))
    assert build_document(record, sidecars[record.id]) is not None


@pytest.mark.parametrize("version", ["1.4.0", "2.0.0"])
def test_unknown_contract_versions_remain_rejected(tmp_path, version):
    jsonl, sidecar, manifest = current_export(tmp_path)
    manifest["contract_version"] = version
    sidecar.write_text(json.dumps(manifest), "utf-8")

    with pytest.raises(ValueError, match="invalid_corpus_manifest_or_checksum"):
        load_corpus(jsonl, sidecar)


def test_current_contract_does_not_bypass_checksum_validation(tmp_path):
    jsonl, sidecar, _ = current_export(tmp_path)
    jsonl.write_bytes(jsonl.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="invalid_corpus_manifest_or_checksum"):
        load_corpus(jsonl, sidecar)


def test_current_contract_does_not_grant_indexing_rights(tmp_path):
    jsonl, sidecar, manifest = current_export(tmp_path)
    row = json.loads(jsonl.read_text("utf-8"))
    row["sources"][0]["indexing_allowed"] = False
    payload = (json.dumps(row) + "\n").encode("utf-8")
    jsonl.write_bytes(payload)
    manifest["sha256"] = hashlib.sha256(payload).hexdigest()
    sidecar.write_text(json.dumps(manifest), "utf-8")

    records, sidecars, _ = load_corpus(jsonl, sidecar)

    record = next(iter(records.values()))
    assert build_document(record, sidecars[record.id]) is None
