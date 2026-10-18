"""Production uses the platform's actual port and never logs raw query URLs."""

import pytest

from scripts import serve


def test_platform_port_and_bind_address(monkeypatch):
    calls = []
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setattr(serve.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    serve.main()
    assert calls == [
        (
            ("backend.app.main:app",),
            {
                "host": "0.0.0.0",
                "port": 8123,
                "access_log": False,
            },
        )
    ]


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_invalid_port_is_rejected(monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    with pytest.raises(ValueError):
        serve.main()
