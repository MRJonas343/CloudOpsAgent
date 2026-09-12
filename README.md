# CloudOpsAgent

A safe, auditable incident-response control plane for simulated applications today and AWS-backed operations later. An operational signal becomes evidence, a diagnosis, an approved remediation plan, and a verified result without giving an LLM unrestricted authority.

> **Status:** the `app` service implements Phase 2 (health, metrics, orders, and bounded fault simulations). The `agent` service implements Phase 4: it polls `app` over HTTP, detects the two MVP incidents, stores typed incident payloads in memory, and exposes the typed incident API. The AWS Bedrock model connection is wired and viewable in LangGraph Studio; the deterministic LangGraph workflow is the next phase. See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

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
| `agent` | FastAPI service containing the monitoring module (polls `app` over HTTP), the typed incident API, and LangGraph orchestration | `GET /health`, `POST /incidents`, `GET /incidents/{id}` |

The `agent` service polls `app` and exposes the incident API; the graph and registered read-only tools arrive in later phases. See [Simulated application](#simulated-application) for the `app` contracts.

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

## Monitoring module

The monitoring module is internal to the `agent` service (not a separate container). Every `AGENT_POLL_INTERVAL_SECONDS` (default `10`) it polls `app` `GET /health` and `GET /metrics` via HTTP, applies deterministic rules, and stores a typed `Incident` (`INC-0001`, `INC-0002`, ...) in memory. It only creates and logs incidents; it does not trigger the LangGraph workflow yet.

| Detector | Rule | Severity |
|---|---|---|
| `unhealthy_application` | `/health` is not `ok`, or `metrics.status == "unhealthy"` | `high` |
| `traffic_spike` | `requests_per_second >= AGENT_TRAFFIC_SPIKE_RPS_THRESHOLD` (default `20.0`) | `medium` |

The unhealthy condition takes precedence when both could fire. Baseline metrics produce no incident. Repeating an active condition does not create a duplicate, and an `app` transport error logs a warning and skips the cycle. Disable the loop with `AGENT_MONITORING_ENABLED=false`; tune the request timeout with `AGENT_APP_REQUEST_TIMEOUT_SECONDS` (default `5.0`).

## Incident API

The `agent` exposes the typed incident contract over HTTP, backed by the same in-memory store the monitoring module writes to, so monitor-created incidents are retrievable here.

| Endpoint | Behavior |
|---|---|
| `POST /incidents` | Validate and store an incident; the store assigns the sequential `INC-####` id; returns `201` with the stored incident |
| `GET /incidents/{id}` | Return the stored incident, or `404` with a clear detail when the id is unknown |
| `GET /health` | `200 {"status":"ok","service":"agent"}` |

Request body: `service` (required, non-empty), `type`, `severity`, optional `status` (default `detected`), `detected_at` (defaults to the current UTC time), `observations` (default `[]`), `source` (default `api`), and `correlation_id` (defaults to a generated hex id). Invalid enum values, missing or empty `service`, and malformed payloads return `422`.

```bash
curl -X POST http://localhost:8000/incidents -H 'content-type: application/json' \
  -d '{"service":"app","type":"unhealthy_application","severity":"high"}'
curl http://localhost:8000/incidents/INC-0001
```

The API is unauthenticated and in-memory only; authentication and durable persistence are explicitly out of scope for the MVP.

## Model connection (AWS Bedrock)

The agent talks to a model through a single module: `cloudops_agent.graph.model.connection`. It builds a `ChatBedrockConverse` client for **Claude Sonnet 4.5** and exposes a minimal `create_agent` graph. The deterministic incident workflow is built on top of `get_model()` in the next phase.

```text
services/agent/
├── langgraph.json               # LangGraph CLI / Studio configuration
└── src/cloudops_agent/graph/model/
    ├── __init__.py
    └── connection.py            # get_model(), get_agent(), `agent` entry point
```

Configuration comes from the environment (`AWS_REGION`, `AWS_BEARER_TOKEN_BEDROCK`) plus `AGENT_BEDROCK_MODEL_ID` (default `us.anthropic.claude-sonnet-4-5-20250929-v1:0`). Claude Sonnet 4.5 is only served through cross-region inference profiles, so keep the `us.` prefix (use `global.` for worldwide routing). The bearer token is optional; when it is empty, boto3 falls back to the standard AWS credential chain.

Verify the connection with a one-shot invocation:

```bash
uv run --directory services/agent python -m cloudops_agent.graph.model.connection
# [{'type': 'text', 'text': 'connection ok'}]
```

Visualize the agent in LangGraph Studio:

```bash
uv run --directory services/agent langgraph dev --no-browser
# API:       http://127.0.0.1:2024
# Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

Validate the configuration without starting the server:

```bash
uv run --directory services/agent langgraph validate
# Configuration file .../langgraph.json is valid. (1 graph found)
```

On Windows, export `PYTHONIOENCODING=utf-8` before running the LangGraph CLI so the startup banner renders instead of raising a console encoding error.

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
        ├── langgraph.json       # LangGraph CLI / Studio configuration
        └── src/cloudops_agent/
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

- **Phase 4 (this state):** internal monitoring module in `agent` polls `app`, detects `unhealthy_application` and `traffic_spike`, stores typed incidents in memory, and exposes `POST /incidents` and `GET /incidents/{id}`.
- **Model connection:** AWS Bedrock `ChatBedrockConverse` for Claude Sonnet 4.5, exposed through `langgraph dev`; the deterministic workflow is next.
- **MVP:** local `app` + `agent` flow, monitoring detection, typed incident API, deterministic LangGraph skeleton, human approval, first safe local remediation, verification loop, 2 scenarios.
- **V1:** read-only AWS tools, Terraform infrastructure and `terraform_validate()`/`terraform_plan()` (plan + explanation only, no apply), CloudWatch evidence, IAM hardening.
- **V2:** SQLite persistence, the remaining 3 scenarios, measured evaluation, CI/CD.

Persistence is in-memory for V1. The agent never executes `terraform apply` or `terraform destroy`.

## License

[MIT](LICENSE) © 2026 Jonas

uv run --directory services/agent langgraph dev