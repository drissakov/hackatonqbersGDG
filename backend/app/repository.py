"""Shared ingestion boundary. S01 supplies the PostgreSQL implementation."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from backend.app.schemas import UpsertResult


class POIRepository(Protocol):
    async def upsert_pois(self, records: Sequence[Mapping[str, object]]) -> UpsertResult:
        """Validate each record, enforce rights, and report inserted/updated/rejected.

        Stable key: (primary source provider, external_id). Rejected indexes refer
        to the original batch. Infrastructure failures raise and roll back the
        batch; they must not be reported as successful per-record rejections.
        """
        ...
