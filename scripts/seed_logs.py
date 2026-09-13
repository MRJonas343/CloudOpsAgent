#!/usr/bin/env python3
"""Seed the simulated app's consultable log store for manual testing.

Generates a burst of normal activity, then briefly activates the
``unhealthy_application`` fault and issues a few failing requests so the
``error`` level is populated. It always clears the fault it activates and
prints the counts it produced.

Usage:
    python scripts/seed_logs.py [BASE_URL] [--normal N] [--errors N]

The base URL comes from the first argument, else the ``APP_BASE_URL``
environment variable, else ``http://localhost:8001``. No credentials are used.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:8001"
DEFAULT_NORMAL = 4
DEFAULT_ERRORS = 3
FAULT_DURATION_SECONDS = 10


def _request(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    timeout: float = 5.0,
) -> tuple[int, str]:
    """Perform one request; return ``(status, body_text)`` without raising on HTTP errors."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"content-type": "application/json"} if data is not None else {}
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as error:
        raise SystemExit(f"error: cannot reach {base_url}: {error}") from error


def _count_field(body: str, field: str) -> int | str:
    try:
        return json.loads(body).get(field, "?")
    except json.JSONDecodeError:
        return "?"


def _normal_activity(base_url: str, rounds: int) -> int:
    """Issue healthy requests and return the number of calls made."""
    calls = 0
    for _ in range(rounds):
        _request(base_url, "GET", "/health")
        _request(base_url, "GET", "/metrics")
        _request(base_url, "GET", "/api/orders")
        _request(base_url, "POST", "/api/orders", {"item": "seed-widget", "quantity": 1})
        calls += 4
    return calls


def _error_activity(base_url: str, rounds: int) -> int:
    """Issue failing requests while a fault is active; return errored-response count."""
    errors = 0
    for _ in range(rounds):
        status, _ = _request(base_url, "GET", "/api/orders")
        errors += 1 if status >= 400 else 0
        status, _ = _request(base_url, "GET", "/health")
        errors += 1 if status >= 400 else 0
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "base_url",
        nargs="?",
        default=os.environ.get("APP_BASE_URL", DEFAULT_BASE_URL),
        help="App base URL (default: $APP_BASE_URL or %(default)s)",
    )
    parser.add_argument(
        "--normal", type=int, default=DEFAULT_NORMAL, help="Normal activity rounds (4 calls each)"
    )
    parser.add_argument(
        "--errors", type=int, default=DEFAULT_ERRORS, help="Fault rounds (2 calls each)"
    )
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")

    normal_calls = _normal_activity(base_url, max(0, args.normal))

    error_responses = 0
    try:
        status, _ = _request(
            base_url,
            "POST",
            "/simulate/unhealthy_application",
            {"duration_seconds": FAULT_DURATION_SECONDS},
        )
        if status >= 400:
            print(
                f"warning: could not activate fault (status {status}); "
                "skipping error activity",
                file=sys.stderr,
            )
        else:
            error_responses = _error_activity(base_url, max(0, args.errors))
    finally:
        _request(base_url, "POST", "/simulate/reset")

    _, logs_body = _request(base_url, "GET", "/logs?limit=1000")
    _, errors_body = _request(base_url, "GET", "/errors?limit=1000")

    print(f"base_url: {base_url}")
    print(f"normal requests issued: {normal_calls}")
    print(f"error responses observed: {error_responses}")
    print(f"app total log entries: {_count_field(logs_body, 'count')}")
    print(f"app error-level entries: {_count_field(errors_body, 'count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
