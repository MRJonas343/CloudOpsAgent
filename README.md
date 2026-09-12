# CloudOpsAgent

A safe, auditable incident-response control plane for simulated applications today and AWS-backed operations later. An operational signal becomes evidence, a diagnosis, an approved remediation plan, and a verified result without giving an LLM unrestricted authority.

> **Phase 0 status:** repository foundation only. Each service exposes a single `/health` endpoint. No incident logic, no AWS access, no LangGraph behavior, and no Terraform execution exist yet. See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

## Quick start

Prerequisites: Docker + Docker Compose, [`uv`](https://docs.astral.sh/uv/), GNU Make, and Python 3.12 (uv can install it automatically).

```bash
make install                    # sync each service's dependencies with uv
python scripts/setup_local.py   # start the topology (docker compose up; add -d for detached)
```

`make up` runs the same `docker compose up -d` if you prefer the Makefile target.

Verify both services:

```bash
curl http://localhost:8001/health   # {"status":"ok","service":"app"}
curl http://localhost:8000/health   # {"status":"ok","service":"agent"}
```

Stop the topology:

```bash
make down
```

Copy `.env.example` to `.env` to override ports, log level, polling interval, or the LLM provider placeholder. Never put real secrets in `.env`; it is git-ignored.

## Service topology

Docker Compose defines exactly **two** services. Monitoring is an internal module of the `agent` service, not a separate container.

| Service | Responsibility | Phase 0 interface |
|---|---|---|
| `app` | Simulated Python application (FastAPI) with controlled fault/load behavior planned for later phases | `GET /health` |
| `agent` | FastAPI service containing the monitoring module (polls `app` over HTTP), the typed incident API, and LangGraph orchestration | `GET /health` |

Later phases add `/metrics`, `/api/orders`, simulation controls, incident endpoints, the graph, and registered read-only tools.

## Project structure

```text
CloudOpsAgent/
├── Makefile                     # thin task wrappers
├── docker-compose.yml           # 2-service topology with health checks
├── .env.example                 # safe, non-secret configuration template
├── docs/
│   ├── PROJECT_CONTEXT.md       # north star, contracts, roadmap
│   ├── IMPLEMENTATION_PLAN.md   # dependency-ordered phases and gates
│   ├── ARCHITECTURE.md          # boundaries, graph, tool boundary
│   ├── SECURITY_AND_OPERATIONS.md
│   ├── SCENARIOS.md             # reproducible incident catalog
│   ├── decisions/               # ADR-001..ADR-005 + index
│   ├── architecture/            # placeholder
│   ├── incidents/               # placeholder
│   └── security/                # placeholder
├── infrastructure/terraform/    # future V1 work, plan-only (no apply)
├── scenarios/                   # scenario catalog notes
├── scripts/                     # future demo/CLI scripts
└── services/
    ├── app/                     # cloudops-app
    └── agent/                   # cloudops-agent
```

## Make targets

| Target | Action |
|---|---|
| `make install` | `uv sync` for each service |
| `make lint` | `ruff check` in the agent service |
| `make format` | `ruff format` in the agent service |
| `make test` | `pytest` in the agent service |
| `make up` | `docker compose up -d` |
| `make down` | `docker compose down` |
| `make build` | `docker compose build` |
| `make clean` | remove local virtualenvs, caches, and `__pycache__` |

Each target is a thin wrapper; run the underlying command directly if you prefer.

## Documentation

- [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — vision, contracts, roadmap levels.
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — phase order, gates, MVP cut line.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — service and tool boundaries.
- [`docs/SECURITY_AND_OPERATIONS.md`](docs/SECURITY_AND_OPERATIONS.md) — safety and control model.
- [`docs/SCENARIOS.md`](docs/SCENARIOS.md) — reproducible incident scenarios.
- [`docs/decisions/README.md`](docs/decisions/README.md) — ADR index.

## Roadmap

- **Phase 0 (this state):** repository skeleton, Compose shape, safe config, ADR index, baseline tests.
- **MVP:** local `app` + `agent` flow, monitoring detection, typed incident API, deterministic LangGraph skeleton, human approval, first safe local remediation, verification loop, 2 scenarios.
- **V1:** read-only AWS tools, Terraform infrastructure and `terraform_validate()`/`terraform_plan()` (plan + explanation only, no apply), CloudWatch evidence, IAM hardening.
- **V2:** SQLite persistence, the remaining 3 scenarios, measured evaluation, CI/CD.

Persistence is in-memory for V1. The agent never executes `terraform apply` or `terraform destroy`.
