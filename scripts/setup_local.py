#!/usr/bin/env python3
"""Bring up the CloudOpsAgent local environment.

Runs `docker compose up` from the repository root. Pass `-d` or `--detached`
to run it in the background.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    detached = "-d" in argv or "--detached" in argv
    command = ["docker", "compose", "up"]
    if detached:
        command.append("-d")

    print(f"Running: {' '.join(command)}", flush=True)
    try:
        return subprocess.call(command, cwd=REPO_ROOT)
    except FileNotFoundError:
        print("error: docker is not installed or not on PATH", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
