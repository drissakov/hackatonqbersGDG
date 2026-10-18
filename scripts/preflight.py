"""Independent safe provider probes. Never print exceptions or secret values."""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from backend.app.openai_client import OpenAIClient, ProviderError  # noqa: E402
from backend.app.settings import Settings  # noqa: E402

CHECKS = ("db", "responses", "embedding")


@dataclass(frozen=True)
class CheckResult:
    status: Literal["passed", "failed", "not_run"]
    reason: str
    details: dict | None = None


def check_database(settings: Settings) -> CheckResult:
    url = settings.database_url.get_secret_value()
    if not url:
        return CheckResult("not_run", "DATABASE_URL is empty; no connection attempted")
    try:
        with psycopg.connect(
            url,
            connect_timeout=10,
            autocommit=True,
            options="-c default_transaction_read_only=on -c statement_timeout=5000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    return CheckResult("failed", "database_probe_unexpected_result")
                cursor.execute(
                    "SELECT extname FROM pg_extension WHERE extname IN (%s, %s)",
                    ("postgis", "vector"),
                )
                extensions = sorted(row[0] for row in cursor.fetchall())
        missing = sorted({"postgis", "vector"} - set(extensions))
        if missing:
            return CheckResult("failed", "required_extensions_missing", {"missing": missing})
        return CheckResult(
            "passed", "read_only_connection_and_extensions", {"extensions": extensions}
        )
    except psycopg.OperationalError as exc:
        message = str(exc).lower()
        if exc.sqlstate in {"28P01", "28000"} or "authentication failed" in message:
            return CheckResult(
                "failed", "database_authentication_failed; update DATABASE_URL locally"
            )
        if "no pg_hba.conf entry" in message:
            return CheckResult("failed", "database_connection_not_authorized")
        if exc.sqlstate:
            return CheckResult("failed", "database_rejected_connection_or_query")
        if any(
            marker in message
            for marker in (
                "could not translate host name",
                "could not resolve",
                "getaddrinfo",
                "name or service not known",
                "temporary failure in name resolution",
                "connection timed out",
                "timeout expired",
                "connection refused",
                "network is unreachable",
            )
        ):
            return CheckResult("not_run", "database_network_unavailable_or_timeout")
        return CheckResult("failed", "database_connection_failed; inspect locally without secrets")
    except (psycopg.Error, ValueError):
        return CheckResult("failed", "database_configuration_or_query_error")


async def check_openai(settings: Settings, check: str) -> CheckResult:
    if not settings.openai_api_key.get_secret_value():
        return CheckResult("not_run", "OPENAI_API_KEY is empty; no API request attempted")
    try:
        async with OpenAIClient(settings) as client:
            if check == "responses":
                model = await client.check_model_access(settings.openai_model)
                await client.create_response(
                    "Reply with the single word OK. This is a synthetic connectivity probe."
                )
                return CheckResult("passed", "project_model_access_and_responses", {"model": model})
            model = await client.check_model_access(settings.openai_embedding_model)
            vector = await client.embed("Qadam Astana synthetic preflight probe")
            return CheckResult(
                "passed",
                "project_model_access_and_embedding",
                {"model": model, "dimensions": len(vector)},
            )
    except ProviderError as exc:
        status = "not_run" if exc.code == "network_unavailable_or_timeout" else "failed"
        return CheckResult(status, exc.code)
    except Exception:
        # Do not serialize SDK errors: they may contain headers, URLs or request bodies.
        return CheckResult(
            "failed", "unexpected_openai_client_error; inspect locally without secrets"
        )


async def run_checks(settings: Settings, checks: list[str]) -> dict[str, CheckResult]:
    results = {}
    for name in checks:
        if name == "db":
            results[name] = await asyncio.to_thread(check_database, settings)
        else:
            results[name] = await check_openai(settings, name)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=(*CHECKS, "all"), default="all")
    parser.add_argument("--output", type=Path, help="Optionally save this sanitized JSON report")
    args = parser.parse_args()
    checks = list(CHECKS) if args.check == "all" else [args.check]
    try:
        settings = Settings()
    except (ValidationError, ValueError, KeyError):
        results = {
            name: CheckResult("failed", "invalid_settings; values intentionally hidden")
            for name in checks
        }
    else:
        results = asyncio.run(run_checks(settings, checks))
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": {name: asdict(result) for name, result in results.items()},
    }
    content = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8", newline="\n")
    print(content, end="")
    statuses = {result.status for result in results.values()}
    if "failed" in statuses:
        return 1
    return 2 if "not_run" in statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
