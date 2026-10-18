"""Check observable S01 API behavior without paid providers or data writes."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    address = urlsplit(args.base_url)
    if address.scheme not in {"http", "https"} or address.username or address.password:
        parser.error("Use an HTTP(S) base URL without credentials")
    probes = [
        ("health", "/api/health", None, 200),
        ("coverage", "/api/coverage", None, 200),
        ("unknown_api", "/api/not-real", None, 404),
        ("unknown_api_post", "/api/not-real", {}, 404),
        (
            "recommendations",
            "/api/recommendations",
            {
                "query": "Synthetic S01 HTTP smoke probe",
                "locale": "ru",
                "request_id": "00000000-0000-4000-8000-000000000001",
            },
            503,
        ),
    ]
    checks = {}
    for name, path, body, expected in probes:
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(
            args.base_url.rstrip("/") + path,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as exc:
                response = exc
            with response:
                actual = response.code
                content = json.load(response)
            if not isinstance(content, dict):
                raise ValueError("Expected a JSON object")
            if name == "health":
                valid_body = content == {"status": "ok"}
            elif name in {"unknown_api", "unknown_api_post"}:
                error = content.get("error")
                valid_body = isinstance(error, dict) and error.get("code") == "not_found"
            elif name == "recommendations":
                valid_body = content.get("status") == "unavailable"
            else:
                valid_body = (
                    content.get("status") == "ok" and content.get("city_coverage") == "unknown"
                )
            checks[name] = {
                "status": "passed" if actual == expected and valid_body else "failed",
                "http_status": actual,
                "response": content,
            }
        except (URLError, OSError, ValueError):
            checks[name] = {"status": "failed", "reason": "network_or_invalid_json"}
    report = {"checked_at": datetime.now(UTC).isoformat(), "checks": checks}
    content = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8", newline="\n")
    print(content, end="")
    return int(any(check["status"] != "passed" for check in checks.values()))


if __name__ == "__main__":
    raise SystemExit(main())
