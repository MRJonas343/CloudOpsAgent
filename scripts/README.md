# Scripts

Operational and developer scripts for CloudOpsAgent.

| Script | Purpose |
|---|---|
| `setup_local.py` | Bring up the local two-service topology. Runs `docker compose up` from the repo root; pass `-d` or `--detached` for background mode. |

Each script must be documented and must not embed credentials, hard-code infrastructure identifiers, or bypass the registered tool boundary.
