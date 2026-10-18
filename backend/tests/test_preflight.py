"""Preflight results distinguish skipped probes from failures and successes."""

import asyncio
from unittest.mock import MagicMock

import psycopg
import pytest

from backend.app.openai_client import ProviderError
from backend.app.settings import Settings
from scripts import preflight


def empty_settings():
    return Settings(_env_file=None, database_url="", openai_api_key="")


def test_missing_keys_do_not_connect_and_report_not_run(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No connection permitted without credentials")

    monkeypatch.setattr(preflight.psycopg, "connect", forbidden)
    monkeypatch.setattr(preflight, "OpenAIClient", forbidden)
    results = asyncio.run(preflight.run_checks(empty_settings(), list(preflight.CHECKS)))
    assert all(result.status == "not_run" for result in results.values())
    assert "DATABASE_URL is empty" in results["db"].reason
    assert "OPENAI_API_KEY is empty" in results["embedding"].reason


def test_database_probe_is_read_only_parameterized_and_closes(monkeypatch):
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (1,)
    cursor.fetchall.return_value = [("postgis",), ("vector",)]
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(preflight.psycopg, "connect", connect)
    settings = Settings(_env_file=None, database_url="postgresql://synthetic.invalid/test")
    result = preflight.check_database(settings)
    assert result.status == "passed"
    assert "default_transaction_read_only=on" in connect.call_args.kwargs["options"]
    assert connect.call_args.kwargs["sslmode"] == "require"
    assert cursor.execute.call_args.args[1] == ("postgis", "vector")
    connection.__exit__.assert_called_once()


def test_openai_checks_remain_independent_and_close(monkeypatch):
    closed = []

    class FakeClient:
        def __init__(self, settings):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.append(True)

        async def check_model_access(self, model):
            return model

        async def create_response(self, text):
            raise ProviderError("network_unavailable_or_timeout")

        async def embed(self, text):
            return [0.1] * 1536

    monkeypatch.setattr(preflight, "OpenAIClient", FakeClient)
    settings = Settings(_env_file=None, database_url="", openai_api_key="synthetic-test-key")
    results = asyncio.run(preflight.run_checks(settings, list(preflight.CHECKS)))
    assert results["db"].status == "not_run"
    assert results["responses"].status == "not_run"
    assert results["embedding"].status == "passed"
    assert results["embedding"].details["dimensions"] == 1536
    assert len(closed) == 2


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("password authentication failed: synthetic-secret", "failed"),
        ("could not translate host name synthetic-secret", "not_run"),
        ("SSL certificate failed synthetic-secret", "failed"),
    ],
)
def test_database_errors_are_classified_without_exposing_messages(monkeypatch, message, expected):
    def fail(*args, **kwargs):
        raise psycopg.OperationalError(message)

    monkeypatch.setattr(preflight.psycopg, "connect", fail)
    result = preflight.check_database(
        Settings(_env_file=None, database_url="postgresql://synthetic.invalid/test")
    )
    assert result.status == expected
    assert "synthetic-secret" not in result.reason


def test_invalid_settings_do_not_print_secrets(monkeypatch, capsys):
    def invalid():
        raise ValueError("synthetic-secret-do-not-log")

    monkeypatch.setattr(preflight, "Settings", invalid)
    monkeypatch.setattr("sys.argv", ["preflight.py", "--check", "responses"])
    assert preflight.main() == 1
    output = capsys.readouterr().out
    assert "invalid_settings" in output
    assert "synthetic-secret" not in output
