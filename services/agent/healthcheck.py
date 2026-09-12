#!/usr/bin/env python3
"""Container health check for the agent service."""

import sys
import urllib.error
import urllib.request

_PORT = 8000
_URL = f"http://localhost:{_PORT}/health"


def main() -> int:
    try:
        with urllib.request.urlopen(_URL, timeout=3) as response:
            return 0 if response.status == 200 else 1
    except (urllib.error.URLError, OSError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
