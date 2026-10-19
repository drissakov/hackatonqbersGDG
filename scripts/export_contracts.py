"""Generate or check versioned schemas without connecting to external services."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import event_schemas, schemas  # noqa: E402

MODELS = {
    "poi": schemas.POIRecord,
    "recommendation-request": schemas.RecommendationRequest,
    "recommendation-response": schemas.RecommendationResponse,
    "event": schemas.EventRecord,
    "event-session": schemas.EventSession,
    "event-search-request": schemas.EventSearchRequest,
    "event-search-response": schemas.EventSearchResponse,
    "upsert-result": schemas.UpsertResult,
    "coverage-response": schemas.CoverageResponse,
    "route-request": schemas.RouteRequest,
    "route-response": schemas.RouteResponse,
    "transient-event-search-response": event_schemas.TransientEventSearchResponse,
}
CODE_ENUMS = {
    "response_status": schemas.ResponseStatus,
    "route_status": schemas.RouteStatus,
    "fit_status": schemas.FitStatus,
    "activity_code": schemas.ActivityCode,
    "reason_codes": schemas.ReasonCode,
    "warning_codes": schemas.WarningCode,
    "explicit_fields": schemas.ExplicitField,
    "missing_fields": schemas.MissingField,
    "source_provider": schemas.SourceProvider,
}


def artifacts() -> dict[str, dict]:
    result = {}
    for name, model in MODELS.items():
        result[f"{name}.schema.json"] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(),
        }
    result["codes.json"] = {
        "contract_version": "1.3.0",
        "locale": ["kk", "ru", "en"],
        **{key: [member.value for member in enum] for key, enum in CODE_ENUMS.items()},
        "action_code": ["open_source", "open_map"],
        "session_status": ["scheduled", "cancelled", "unknown"],
        "transient_event_missing_fields": event_schemas.TRANSIENT_MISSING_FIELDS,
        "rejection_code": [
            "invalid_record",
            "duplicate_in_batch",
            "storage_not_permitted",
            "stale_record",
        ],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail instead of writing drifted files"
    )
    args = parser.parse_args()
    failed = []
    for name, data in artifacts().items():
        path = ROOT / "contracts" / name
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                failed.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if failed:
        print("Contract drift: " + ", ".join(failed))
        return 1
    print(f"{'Checked' if args.check else 'Exported'} {len(artifacts())} contract artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
