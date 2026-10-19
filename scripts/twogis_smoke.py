"""Two public-landmark walking probes; report statuses only, never payloads/keys/GPS."""

import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.schemas import Coordinates, RouteRequest  # noqa: E402
from backend.app.services.twogis import TwoGISAdapter  # noqa: E402
from backend.app.settings import Settings  # noqa: E402

# Approximate public landmark centers, not user GPS or verified entrances.
SCENARIOS = (
    ("bayterek_to_khan_shatyr", "ru", (51.1283, 71.4305), (51.1325, 71.4038)),
    ("bayterek_to_palace_of_peace_across_esil", "en", (51.1283, 71.4305), (51.1231, 71.4636)),
)
NOT_RUN_REASONS = {"disabled", "rights_unconfirmed", "key_missing"}


async def run_checks(settings: Settings) -> dict:
    adapter = TwoGISAdapter(settings)
    checks = {}
    for name, locale, start, destination in SCENARIOS:
        request = RouteRequest(
            origin=Coordinates(latitude=start[0], longitude=start[1]),
            destination=Coordinates(latitude=destination[0], longitude=destination[1]),
            locale=locale,
            return_to_start=True,
        )
        outbound, back = await adapter.route(request)
        reasons = sorted({leg.reason for leg in (outbound, back) if leg.reason is not None})
        status = (
            "not_run"
            if any(reason in NOT_RUN_REASONS for reason in reasons)
            else "passed"
            if all(leg.status == "known" for leg in (outbound, back))
            else "failed"
        )
        checks[name] = {
            "status": status,
            "outbound_status": outbound.status,
            "return_status": back.status,
            "reasons": reasons,
        }
    discovery = await adapter.discover_astana("museum")
    checks["astana_region_and_museum_rubrics"] = {
        "status": (
            "not_run"
            if discovery.reason in NOT_RUN_REASONS
            else "passed"
            if discovery.status == "ok"
            else "failed"
        ),
        "reason": discovery.reason,
        # IDs and catalog content are deliberately not written to a report.
    }
    places = await adapter.search_places("museum", "en")
    checks["live_places"] = {
        "status": (
            "not_run"
            if places.reason in NOT_RUN_REASONS
            else "passed"
            if places.status in {"ok", "no_match"}
            else "failed"
        ),
        "reason": places.reason,
    }
    return checks


def main() -> int:
    try:
        settings = Settings()
    except ValidationError:
        print(
            json.dumps(
                {"checks": {"configuration": {"status": "failed", "reason": "invalid_settings"}}}
            )
        )
        return 1
    checks = asyncio.run(run_checks(settings))
    print(json.dumps({"checks": checks}, indent=2))
    statuses = {result["status"] for result in checks.values()}
    return 1 if "failed" in statuses else 2 if "not_run" in statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
