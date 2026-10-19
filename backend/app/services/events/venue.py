"""Conservative venue lookup in an independently supplied permitted POI corpus."""

import unicodedata
from collections.abc import Sequence
from typing import Literal

from pydantic import Field, HttpUrl

from backend.app.schemas import ContractModel, Coordinates, POIRecord, SourceProvider


class VenueMatch(ContractModel):
    poi_id: str | None = None
    location: Coordinates | None = None
    basis: Literal["name_address_astana_permitted_poi", "unknown", "ambiguous"] = "unknown"
    source_ids: list[str] = Field(default_factory=list)
    source_urls: list[HttpUrl] = Field(default_factory=list)
    coordinate_accuracy: Literal["unknown"] = "unknown"
    geography_basis: Literal["central_astana_bbox", "unknown"] = "unknown"


def normalize_venue_text(value: str | None) -> str:
    """Fold case and whitespace only; do not guess aliases or address variants."""
    return " ".join(unicodedata.normalize("NFC", value or "").casefold().split())


def _permitted_astana_poi(poi: POIRecord) -> bool:
    # This deliberately narrow central-Astana box is a coarse rejection gate,
    # not an administrative-boundary proof or a claim of complete city coverage.
    point = poi.location
    if (
        poi.is_test
        or point is None
        or not (51.00 <= point.latitude <= 51.25 and 71.30 <= point.longitude <= 71.60)
    ):
        return False
    return bool(poi.sources) and all(
        source.provider in (SourceProvider.OSM, SourceProvider.MUNICIPAL)
        and not source.is_test
        and source.storage_allowed
        and source.indexing_allowed
        for source in poi.sources
    )


def match_venue(name: str | None, address: str | None, pois: Sequence[POIRecord]) -> VenueMatch:
    """Return coordinates only for one exact name/address match with clear rights.

    The caller must supply an independent POI corpus, never discovery payloads.
    Missing names/addresses, branch collisions and uncertain geography remain
    unresolved. There is no name-only fallback, nearest-place guess or merge.
    """
    normalized_name, normalized_address = normalize_venue_text(name), normalize_venue_text(address)
    if not normalized_name or not normalized_address:
        return VenueMatch()
    candidates = [
        poi
        for poi in pois
        if normalize_venue_text(poi.name) == normalized_name
        and normalize_venue_text(poi.address) == normalized_address
    ]
    if len(candidates) > 1:
        return VenueMatch(basis="ambiguous")
    if not candidates or not _permitted_astana_poi(candidates[0]):
        return VenueMatch()
    poi = candidates[0]
    return VenueMatch(
        poi_id=poi.id,
        location=poi.location,
        basis="name_address_astana_permitted_poi",
        source_ids=[source.source_id for source in poi.sources],
        source_urls=[source.url for source in poi.sources],
        geography_basis="central_astana_bbox",
    )
