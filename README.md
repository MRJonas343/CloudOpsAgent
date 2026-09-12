# CloudOpsAgent

A safe, auditable incident-response control plane for simulated applications today and AWS-backed operations later. An operational signal becomes evidence, a diagnosis, an approved remediation plan, and a verified result without giving an LLM unrestricted authority.

> **Status:** the `app` service implements Phase 2 (health, metrics, orders, and bounded fault simulations). The `agent` service is still the Phase 1 health-only skeleton; monitoring, the incident API, and the graph are not implemented yet. See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

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
curl http://localhost:8001/metrics  # deterministic metric snapshot
curl http://localhost:8000/health   # {"status":"ok","service":"agent"}
```

Stop the topology:

```bash
make down
```

Copy `.env.example` to `.env` to override ports, log level, polling interval, or the LLM provider placeholder. Never put real secrets in `.env`; it is git-ignored.

## Service topology

Docker Compose defines exactly **two** services. Monitoring is an internal module of the `agent` service, not a separate container.

| Service | Responsibility | Interface |
|---|---|---|
| `app` | Simulated Python application (FastAPI) with controlled fault/load behavior | `GET /health`, `GET /metrics`, `GET /api/orders`, `POST /api/orders`, `POST /simulate/{mode}`, `POST /simulate/reset`, `GET /simulate/status` |
| `agent` | FastAPI service containing the monitoring module (polls `app` over HTTP), the typed incident API, and LangGraph orchestration | `GET /health` |

The `agent` service will poll `app` and add incident endpoints, the graph, and registered read-only tools in later phases. See [Simulated application](#simulated-application) for the `app` contracts.

## Simulated application

The `app` service is a deterministic target for monitoring and demos. Every `/metrics` value is exact unless a fault is active, so tests and monitors can assert on it.

| Endpoint | Behavior |
|---|---|
| `GET /health` | `200 {"status":"ok","service":"app"}` normally; `503 {"status":"unhealthy","service":"app"}` while `unhealthy_application` is active |
| `GET /metrics` | Deterministic snapshot: `service`, `status`, `cpu_percent`, `memory_percent`, `request_count`, `error_count`, `error_rate`, `latency_ms_p95`, `requests_per_second` |
| `GET /api/orders` | Sample in-memory orders; `503` while `unhealthy_application` is active |
| `POST /api/orders` | Body `{"item": "string", "quantity": 1}`; returns the created order with an `id`; `503` while unhealthy |
| `GET /simulate/status` | Active mode, timestamps, remaining seconds, and the enabled flag |
| `POST /simulate/{mode}` | Activate a fault; optional body `{"duration_seconds": 30}` |
| `POST /simulate/reset` | Clear any active fault |

Baseline metrics (no fault): `cpu_percent=12.0`, `memory_percent=34.0`, `error_rate=0.0`, `latency_ms_p95=42.0`, `requests_per_second=3.0`.

MVP fault modes: `traffic_spike` (`requests_per_second=30.0`, `latency_ms_p95=180.0`, `cpu_percent=78.0`) and `unhealthy_application` (`status="unhealthy"`, `error_rate=0.5`). The remaining 3 scenarios are deferred to V2; the mode registry makes adding them mechanical.

Simulation controls are bounded and local-only. Durations are clamped to `[1, APP_SIMULATION_MAX_DURATION_SECONDS]` (default `APP_SIMULATION_DEFAULT_DURATION_SECONDS`), faults auto-expire, and every `/simulate/*` call returns `403` when `APP_SIMULATION_ENABLED=false`.

```bash
curl http://localhost:8001/metrics
curl -X POST http://localhost:8001/simulate/traffic_spike -H 'content-type: application/json' -d '{"duration_seconds": 30}'
curl http://localhost:8001/metrics
curl -X POST http://localhost:8001/simulate/reset
```

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
| `make test` | `pytest` in the app and agent services |
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

- **Phase 2 (this state):** deterministic `app` endpoints (`/health`, `/metrics`, `/api/orders`) and bounded fault simulations (`unhealthy_application`, `traffic_spike`).
- **MVP:** local `app` + `agent` flow, monitoring detection, typed incident API, deterministic LangGraph skeleton, human approval, first safe local remediation, verification loop, 2 scenarios.
- **V1:** read-only AWS tools, Terraform infrastructure and `terraform_validate()`/`terraform_plan()` (plan + explanation only, no apply), CloudWatch evidence, IAM hardening.
- **V2:** SQLite persistence, the remaining 3 scenarios, measured evaluation, CI/CD.

Persistence is in-memory for V1. The agent never executes `terraform apply` or `terraform destroy`.
