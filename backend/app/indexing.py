"""Versioned, provenance-marked search text; never include runtime provider data."""

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass

from backend.app.schemas import POIRecord

EMBEDDING_MODEL = "text-embedding-3-large"
DIMENSIONS = 1536
TEXT_VERSION = "poi-source-v1"


def normalize_name(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def valid_vector(vector) -> bool:
    return (
        isinstance(vector, list)
        and len(vector) == DIMENSIONS
        and all(type(value) in (int, float) and math.isfinite(value) for value in vector)
        and any(value != 0 for value in vector)
    )


@dataclass(frozen=True)
class SearchDocument:
    record: POIRecord
    text: str
    text_hash: str
    names: str
    metadata: dict


def build_document(record: POIRecord, sidecar: dict | None = None) -> SearchDocument | None:
    if not all(s.storage_allowed and s.indexing_allowed for s in record.sources):
        return None
    sources = {s.source_id: s for s in record.sources}
    lines, names = [], []
    # Only facts attributed to an included, permitted source enter the index.
    for fact in record.provenance:
        for field in sorted(set(fact.fields)):
            if field not in {
                "name",
                "description",
                "activity_code",
                "address",
                "indoor",
                "opening_hours_text",
                "price_kzt_per_person",
                "visit_minutes_estimate",
            }:
                continue
            value = getattr(record, field)
            if value is not None:
                lines.append(
                    {
                        "source_id": fact.source_id,
                        "external_id": fact.external_id,
                        "field": field,
                        "value": value,
                        "kind": "source_assertion",
                    }
                )
                if field == "name":
                    names.append(value)
    if sidecar is not None:
        source_id = sidecar.get("source_id")
        if source_id not in sources:
            raise ValueError("sidecar_source_mismatch")
        for field in ("names", "name_fields", "aliases_by_tag"):
            for key, value in sorted(sidecar.get(field, {}).items()):
                for name in value if isinstance(value, list) else [value]:
                    if name:
                        names.append(name)
                        lines.append(
                            {
                                "source_id": source_id,
                                "field": f"{field}.{key}",
                                "value": name,
                                "kind": "source_assertion",
                            }
                        )
        for name in sidecar.get("aliases", []):
            names.append(name)
            lines.append(
                {
                    "source_id": source_id,
                    "field": "alias",
                    "value": name,
                    "kind": "source_assertion",
                }
            )
        for key, fact in sorted(sidecar.get("facts", {}).items()):
            if fact.get("source_id") not in sources:
                raise ValueError("sidecar_fact_source_mismatch")
            lines.append(
                {
                    "source_id": fact["source_id"],
                    "field": key,
                    "value": fact["value"],
                    "kind": "unverified_source_tag",
                }
            )
    if not names:
        return None
    text = unicodedata.normalize(
        "NFC",
        json.dumps(
            {"version": TEXT_VERSION, "facts": lines},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    # Bound each input conservatively below the embedding token limit, without truncation.
    if len(text.encode("utf-8")) > 8000:
        raise ValueError("index_document_too_large")
    return SearchDocument(
        record,
        text,
        hashlib.sha256(text.encode()).hexdigest(),
        "\n".join(dict.fromkeys(normalize_name(n) for n in names)),
        {
            "sidecar_available": sidecar is not None,
            "sidecar": sidecar,
            "sources": [s.model_dump(mode="json") for s in record.sources],
        },
    )
