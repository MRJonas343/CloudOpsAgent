# Scripts

Operational and developer scripts for CloudOpsAgent.

| Script | Purpose |
|---|---|
| `setup_local.py` | Bring up the local two-service topology. Runs `docker compose up` from the repo root; pass `-d` or `--detached` for background mode. |
| `seed_logs.py` | Populate the running app's consultable log store with normal activity plus a short-lived fault, then print the counts. Base URL from the first argument or `APP_BASE_URL` (default `http://localhost:8001`); always resets the fault it activates. |

Each script must be documented and must not embed credentials, hard-code infrastructure identifiers, or bypass the registered tool boundary.
