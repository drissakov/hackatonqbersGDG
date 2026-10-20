"""Small permitted source-checked supplement, separate from the indexed city corpus."""

import math
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StrictBool, ValidationError, model_validator

from backend.app.indexing import normalize_name
from backend.app.intent import ResolvedIntent
from backend.app.schemas import (
    ContractModel,
    FeatureEvidence,
    FeatureField,
    POIRecord,
    validate_feature_evidence,
)

Evidence = FeatureEvidence
CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "curated" / "poi-features.json"


class CuratedPOI(ContractModel):
    poi: POIRecord
    name_is_derived: StrictBool
    coordinate_precision: Literal["node", "area_representative"]
    evidence: Annotated[list[FeatureEvidence], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def evidence_is_attributed(self) -> Self:
        validate_feature_evidence(self.poi, self.evidence)
        if self.poi.location is None:
            raise ValueError("Curated records need source-backed coordinates")
        if not any("location" in item.fields for item in self.poi.provenance):
            raise ValueError("Curated coordinates need provenance")
        if self.name_is_derived and any("name" in item.fields for item in self.poi.provenance):
            raise ValueError("A derived display name cannot be attributed as a source name")
        return self

    def fact(self, field: FeatureField | str) -> bool | None:
        return next((item.value for item in self.evidence if item.field == field), None)


def distance_metres(first, second) -> float:
    """Geographic retrieval distance only; never a route or travel-time estimate."""
    lat1, lat2 = math.radians(first.latitude), math.radians(second.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(second.longitude - first.longitude)
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))


class FeatureCatalog(ContractModel):
    format_version: Literal["qadam-poi-features-v1"]
    checked_at: AwareDatetime
    records: Annotated[list[CuratedPOI], Field(max_length=30)]

    @model_validator(mode="after")
    def records_are_unique(self) -> Self:
        ids = [item.poi.id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Curated identities must be unique")
        for record in self.records:
            if any(item.checked_at > self.checked_at for item in record.evidence):
                raise ValueError("Catalog check must follow record checks")
        return self

    def supports(self, requirement: str) -> bool:
        field = {
            "child_suitability": FeatureField.FAMILY_PLAYGROUND,
            "power_outlets": FeatureField.POWER_OUTLETS,
        }.get(requirement)
        return field is not None and any(row.fact(field) is True for row in self.records)

    def select(self, intent: ResolvedIntent, requirements, *, radius_m=5000) -> list[CuratedPOI]:
        fields = [
            FeatureField.FAMILY_PLAYGROUND
            if item == "child_suitability"
            else FeatureField.POWER_OUTLETS
            for item in requirements
            if item in {"child_suitability", "power_outlets"}
        ]
        selected = []
        for row in self.records:
            if any(row.fact(field) is not True for field in fields):
                continue
            if row.fact(FeatureField.PUBLIC_ACCESS) is False:
                continue
            if intent.categories and row.poi.activity_code not in intent.categories:
                continue
            if intent.name_queries:
                if row.name_is_derived or not any(
                    "name" in item.fields for item in row.poi.provenance
                ):
                    continue
                if not any(
                    normalize_name(name) in normalize_name(row.poi.name)
                    for name in intent.name_queries
                    if normalize_name(name)
                ):
                    continue
            distance = distance_metres(intent.origin, row.poi.location) if intent.origin else None
            if distance is not None and distance > radius_m:
                continue
            selected.append((row, distance))
        selected.sort(
            key=lambda item: (
                item[0].fact(FeatureField.PUBLIC_ACCESS) is not True,
                item[1] if item[1] is not None else float("inf"),
                item[0].poi.id,
            )
        )
        return [row for row, _ in selected]


@lru_cache(maxsize=1)
def load_feature_catalog() -> FeatureCatalog | None:
    """Fail closed on a missing/invalid package; never fall back to test data."""
    try:
        if CATALOG_PATH.stat().st_size > 2_000_000:
            return None
        catalog = FeatureCatalog.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))
        if any(
            row.poi.is_test or any(source.is_test for source in row.poi.sources)
            for row in catalog.records
        ):
            return None
        return catalog
    except (OSError, ValueError, ValidationError):
        return None
