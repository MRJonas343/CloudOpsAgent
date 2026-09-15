# CloudOpsAgent


Image of the architecture (html)
<img width="1152" height="807" alt="image" src="https://github.com/user-attachments/assets/27b5cf15-3b31-4803-b4a6-d7311ac7fbc7" />

Image of an incident
<img width="1178" height="960" alt="image" src="https://github.com/user-attachments/assets/8bc6d105-c560-4842-92ca-45b8c6d0d573" />

Image of an inciden (2) with aproval gateway (HIL)
<img width="1224" height="913" alt="image" src="https://github.com/user-attachments/assets/718d7c8e-acc2-4fa9-a16a-8e4e1447a60d" />

Image of an incident fixed with post morten generated
<img width="1198" height="991" alt="image" src="https://github.com/user-attachments/assets/c531da9e-ae64-4e35-aea2-5d1db6fe4378" />


Image of the caos console
<img width="1177" height="801" alt="image" src="https://github.com/user-attachments/assets/23e9f519-a54f-4b99-b7ba-cd0249f04008" />


A safe, auditable incident-response control plane for simulated applications today and AWS-backed operations later. An operational signal becomes evidence, a diagnosis, an approved remediation plan, and a verified result without giving an LLM unrestricted authority.

> **Status:** the full incident lifecycle is implemented across three services. `app` is the simulated target (health, metrics, orders, and bounded fault simulations). `agent` polls `app`, detects incidents, and drives a deterministic LangGraph workflow — detection → investigation → diagnosis → plan → human approval → guarded execution → real verification → post-mortem — over a typed incident API and a live event stream. `dashboard` is a Vite + React console that renders the live incident list, the per-incident case file, and a chaos console that injects real faults. See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

## Quick start

Prerequisites: Docker + Docker Compose, [`uv`](https://docs.astral.sh/uv/), and Python 3.12 (uv can install it automatically).

```bash
uv sync --directory services/app && uv sync --directory services/agent   # sync each service's dependencies with uv
python scripts/setup_local.py   # start the topology (docker compose up; add -d for detached)
```

`docker compose up -d` starts the same topology in detached mode if you prefer to run Compose directly. The build includes all three services, including the dashboard.

Verify the topology:

```bash
curl http://localhost:8001/health   # {"status":"ok","service":"app"}
curl http://localhost:8001/metrics  # deterministic metric snapshot
curl http://localhost:8000/health   # {"status":"ok","service":"agent"}
```

Then open the dashboard at <http://localhost:3000> to watch incidents as they are detected and remediated.

Stop the topology:

```bash
docker compose down
```

Copy `.env.example` to `.env` to override ports, log level, polling interval, approval timeout, or the LLM provider placeholder. `DASHBOARD_PORT` moves the dashboard's published host port only; nginx always listens on `3000` inside the container. Never put real secrets in `.env`; it is git-ignored.

## Service topology

Docker Compose defines **three** services. Monitoring is an internal module of the `agent` service, not a separate container.

| Service | Responsibility | Interface |
|---|---|---|
| `app` | Simulated Python application (FastAPI) with controlled fault/load behavior | `GET /health`, `GET /metrics`, `GET /api/orders`, `POST /api/orders`, `POST /scale`, `POST /restart`, `POST /simulate/{mode}`, `POST /simulate/reset`, `GET /simulate/status` |
| `agent` | FastAPI service containing the monitoring module (polls `app` over HTTP), the deterministic incident workflow, and the typed incident API | `GET /health`, `POST /incidents`, `GET /incidents`, `GET /incidents/{id}`, `GET /incidents/{id}/report`, `POST /incidents/{id}/approve`, `POST /incidents/{id}/reject`, `GET /events` |
| `dashboard` | nginx-served Vite + React console that reads the incident API and injects real faults | `GET /` (SPA), `GET /healthz`, `/api/agent/*` → `agent:8000`, `/api/app/*` → `app:8001` |

The `agent` service polls `app`, schedules one workflow run per detected incident, and exposes the incident API and event stream; the graph reaches the outside world only through the registered tool boundary described below. See [Simulated application](#simulated-application) for the `app` contracts and [Dashboard](#dashboard) for the console.

## Simulated application

The `app` service is a deterministic target for monitoring and demos. Every `/metrics` value is exact unless a fault is active, so monitors and manual verification can rely on it.

| Endpoint | Behavior |
|---|---|
| `GET /health` | `200 {"status":"ok","service":"app"}` normally; `503 {"status":"unhealthy","service":"app"}` while `unhealthy_application` is active |
| `GET /metrics` | Deterministic snapshot: `service`, `status`, `cpu_percent`, `memory_percent`, `request_count`, `error_count`, `error_rate`, `latency_ms_p95`, `requests_per_second`, `replicas` |
| `GET /logs?limit=N` | Most recent consultable log entries, newest first (default `100`, capped at `APP_MAX_LOG_ENTRIES`) |
| `GET /errors?limit=N` | Only `error`-level log entries (default `100`, same cap) |
| `GET /api/orders` | Sample in-memory orders; `503` while `unhealthy_application` is active |
| `POST /api/orders` | Body `{"item": "string", "quantity": 1}`; returns the created order with an `id`; `503` while unhealthy |
| `GET /scale` | Current replica count and the configured bounds |
| `POST /scale` | Body `{"replicas": 4}`; clamps to `[APP_MIN_REPLICAS, APP_MAX_REPLICAS]` and returns the new state |
| `POST /restart` | Restart the service: clears the active fault and the log buffer, resets replicas to `APP_BASELINE_REPLICAS`, and returns the new scale state |
| `GET /simulate/status` | Active mode, timestamps, remaining seconds, and the enabled flag |
| `POST /simulate/{mode}` | Activate a fault; optional body `{"duration_seconds": 30}` |
| `POST /simulate/reset` | Clear any active fault (does **not** reset the replica count) |

Baseline metrics (no fault, default `APP_BASELINE_REPLICAS=2`): `cpu_percent=12.0`, `memory_percent=34.0`, `error_rate=0.0`, `latency_ms_p95=42.0`, `requests_per_second=3.0`.

MVP fault modes: `traffic_spike` (`requests_per_second=30.0`, `latency_ms_p95=180.0`, `cpu_percent=78.0`) and `unhealthy_application` (`status="unhealthy"`, `error_rate=0.5`). The remaining 3 scenarios are deferred to V2; the mode registry makes adding them mechanical.

Simulation controls are bounded and local-only. Durations are clamped to `[1, APP_SIMULATION_MAX_DURATION_SECONDS]` (default `APP_SIMULATION_DEFAULT_DURATION_SECONDS`), faults auto-expire, and every `/simulate/*` call returns `403` when `APP_SIMULATION_ENABLED=false`.

Scaling is a normal simulated capability, not a fault, so it survives `/simulate/reset`. It is deterministic: CPU and latency fall as `baseline/replicas` while achievable throughput rises as `replicas/baseline`, so scaling up from the baseline visibly reduces CPU/latency (including under `traffic_spike`). A restart (`POST /restart`) is the recovery path: it clears the active fault and the log buffer and returns the replica count to the baseline.

```bash
curl http://localhost:8001/metrics
curl -X POST http://localhost:8001/simulate/traffic_spike -H 'content-type: application/json' -d '{"duration_seconds": 30}'
curl http://localhost:8001/metrics
curl -X POST http://localhost:8001/scale -H 'content-type: application/json' -d '{"replicas": 4}'
curl http://localhost:8001/metrics          # cpu/latency lower, replicas=4
curl http://localhost:8001/logs?limit=5
curl http://localhost:8001/errors?limit=5
curl -X POST http://localhost:8001/simulate/reset
curl -X POST http://localhost:8001/restart    # clears the fault/log buffer, replicas back to baseline
```

### Seeding logs for manual testing

`python scripts/seed_logs.py` populates the running app's log store with normal activity plus a short-lived fault, then prints the counts it produced. It accepts the base URL as its first argument or through the `APP_BASE_URL` environment variable (default `http://localhost:8001`), uses no credentials, and always resets any fault it activates.

```bash
python scripts/seed_logs.py
python scripts/seed_logs.py http://localhost:8001 --normal 6 --errors 4
APP_BASE_URL=http://localhost:8001 python scripts/seed_logs.py
```

## Monitoring module

The monitoring module is internal to the `agent` service (not a separate container). Every `AGENT_POLL_INTERVAL_SECONDS` (default `10`) it polls `app` `GET /health` and `GET /metrics` via HTTP, applies deterministic rules, and stores a typed `Incident` (`INC-0001`, `INC-0002`, ...) in memory. A newly stored incident starts the workflow: the monitor hands it to the run service, which schedules one off-loop graph run for it, so the poll loop is never blocked by graph execution.

| Detector | Rule | Severity |
|---|---|---|
| `unhealthy_application` | `/health` is not `ok`, or `metrics.status == "unhealthy"` | `high` |
| `traffic_spike` | `requests_per_second >= AGENT_TRAFFIC_SPIKE_RPS_THRESHOLD` (default `20.0`) | `medium` |

The unhealthy condition takes precedence when both could fire. Baseline metrics produce no incident. Repeating an active condition does not create a duplicate, and an `app` transport error logs a warning and skips the cycle. Disable the loop with `AGENT_MONITORING_ENABLED=false`; tune the request timeout with `AGENT_APP_REQUEST_TIMEOUT_SECONDS` (default `5.0`).

## Incident API

The `agent` exposes the typed incident contract over HTTP, backed by the same in-memory stores the monitoring module and run service write to, so monitor-created incidents and their run detail are retrievable here.

| Endpoint | Behavior |
|---|---|
| `POST /incidents` | Validate and store an incident; the store assigns the sequential `INC-####` id; returns `201` with the stored incident |
| `GET /incidents` | List stored incidents newest-first; optional `status` and `type` filters, each typed to its enum so an invalid value returns `422` |
| `GET /incidents/{id}` | Return the stored incident, or `404` with a clear detail when the id is unknown |
| `GET /incidents/{id}/report` | Return the full case file (ADR-008): the incident, the run record (timeline, observations, hypotheses, diagnosis, plan, approval, execution, verification, and the post-mortem `summary`), and the live approval countdown. Partially filled while a run is in flight; `404` only when both stores lack the id |
| `POST /incidents/{id}/approve` | Resume the paused run with body `{"approver": "...", "reason": "..."}`; `404` when the incident is unknown and `409` when its run is not `awaiting_approval` |
| `POST /incidents/{id}/reject` | Same contract as approve, ending the run without executing anything |
| `GET /events` | Server-sent events (`text/event-stream`): one frame per incident lifecycle change, replay-free |
| `GET /health` | `200 {"status":"ok","service":"agent"}` |

Request body: `service` (required, non-empty), `type`, `severity`, optional `status` (default `detected`), `detected_at` (defaults to the current UTC time), `observations` (default `[]`), `source` (default `api`), and `correlation_id` (defaults to a generated hex id). Invalid enum values, missing or empty `service`, and malformed payloads return `422`.

The event stream is deliberately replay-free: the bus keeps no history and its frame ids are process-local, so a reconnecting client refetches state over REST (`GET /incidents`, `GET /incidents/{id}/report`) instead of replaying what it missed. Each frame carries the incident id, type, severity, status, phase, timestamp, and the approval countdown when one is armed.

```bash
curl -X POST http://localhost:8000/incidents -H 'content-type: application/json' \
  -d '{"service":"app","type":"unhealthy_application","severity":"high"}'
curl http://localhost:8000/incidents
curl http://localhost:8000/incidents/INC-0001
curl http://localhost:8000/incidents/INC-0001/report
curl -N http://localhost:8000/events
```

The API is unauthenticated and in-memory only; authentication and durable persistence are explicitly out of scope for the MVP.

## Dashboard

The dashboard is the third Compose service and the project's most visible surface: a live view of the incident lifecycle on top of the same API and event stream.

| Property | Value |
|---|---|
| Stack | Vite + React + TypeScript + Tailwind CSS |
| Serving | nginx on container port `3000`, published on host `${DASHBOARD_PORT:-3000}` |
| Network | `cloudops`, alongside `agent` and `app` |
| Source | `services/dashboard/src/` |

**Why nginx.** The container serves the built SPA and reverse-proxies `/api/agent` → `agent:8000` and `/api/app` → `app:8001`, so the browser only ever talks to one origin and no service needs CORS. The event-stream location disables proxy buffering (`proxy_buffering off`, `X-Accel-Buffering: no`); this is required, because with buffering on nginx holds the response until the connection closes and the live updates arrive as one lump instead of frame by frame (ADR-006).

### Routes

| Route | What it shows |
|---|---|
| `/` | Live incident list with status and type filters. One REST read for the initial list, then updates over the shared SSE stream, so a new incident appears without a reload |
| `/incidents/:id` | The case file. One read of `GET /incidents/{id}/report`, refreshed on each frame for that incident: the phase timeline, evidence, hypotheses, diagnosis, plan with its risk, the approval gate with a live countdown and Approve/Reject, execution, verification, and the post-mortem |
| `/console` | Application status — health and key metrics, polled every 5s — plus the chaos console |

### Chaos console

The console injects faults through the app's own `POST /simulate/{mode}`, reached via the `/api/app` proxy. It never posts an incident: the Monitor detects the degraded app and opens the incident, so whatever appears in the live list was found by the agent, not created by the UI. It shows a pending state until the agent reports the new incident, and surfaces the honest `403` the app returns when `APP_SIMULATION_ENABLED=false`. Only `traffic_spike` and `unhealthy_application` have detectors, so those are the modes offered; inject one fault at a time.

### In-app notifications

Toast notifications fire on exactly four lifecycle events: incident detected, awaiting approval, resolved, and failed. The intermediate phases stay silent, and a repeated frame does not raise a second toast.

### Demo walkthrough

1. Open <http://localhost:3000>.
2. If the list is empty, use the "Generate demo incident" call to action (it injects a real `traffic_spike`), or open `/console` and inject `traffic_spike` yourself. The console reports the fault as pending until the agent finds it.
3. Wait up to ~10s for the next poll; the incident appears in the list without a reload.
4. Open it and follow the case file. When the run pauses at the approval gate, Approve.
5. Watch it move through execution and verification to `resolved`. An `unhealthy_application` incident resolves through `restart_service`; a `traffic_spike` resolves through `scale_service`.

## Tool layer

The agent reaches the outside world only through the registered tool boundary (`cloudops_agent.tools`). Nodes call `registry.invoke(name, ...)`; the registry is **deny-by-default** (an unregistered tool name never executes), validates inputs, enforces a per-tool timeout, and emits one structured audit record per call (`cloudops_agent.audit`: tool, risk, read-only flag, input summary, outcome, duration).

Registered read-only tools (Risk 0), all backed by the `app` HTTP API:

| Tool | Reads | Returns |
|---|---|---|
| `get_app_health` | `GET /health` | status, `ok`, HTTP code, latency (ms) |
| `get_app_metrics` | `GET /metrics` | the deterministic metric snapshot |
| `get_app_logs` | `GET /logs?limit=N` | recent log entries (default 20) |
| `get_recent_errors` | `GET /errors?limit=N` | error-level log entries (default 20) |

`collect_context` calls these tools and turns the results into `Observation` evidence.

### Guarded mutating tools

| Tool | Risk | Action | Parameters |
|---|---|---|---|
| `restart_service` | 2 (infrastructure_change) | `POST /restart` on the `app` | none |
| `scale_service` | 2 (infrastructure_change) | `POST /scale` on the `app` | `replicas: int`, `baseline <= replicas <= 10`, no other keys |

These are the only mutating tools. They are registered alongside the read-only tools, so a plan can only run one if the action name matches a registry key. `restart_service` recovers an unhealthy service (the fault lives in process memory, so a restart clears it); `scale_service` adds capacity and refuses to scale below `AGENT_BASELINE_REPLICAS`, so an incident can never reduce capacity. Keep `AGENT_BASELINE_REPLICAS` in step with the app's `APP_BASELINE_REPLICAS`: the agent's floor is what the planner is shown and what the tool enforces, while the app's baseline is what it starts from and returns to. Their `PlanDraft` parameters arrive as strings (the planner's `parameters` list), and each input model coerces `"4"` to `4` and rejects out-of-range or unexpected values at the boundary before any HTTP call.

**Catalogue.** `ToolRegistry.remediation_catalogue()` renders the registered non-read-only actions — name, description, risk, and the exact parameter names and bounds from each tool's input schema. `plan_remediation` injects this catalogue into the planner prompt and requires `action` to be exactly one of those names with parameters matching the declared ranges, so the model can only propose actions that exist.

**Deny by default.** `execute_remediation` reads `state["plan"]` and, if the plan is missing or its action is not a registered mutating tool, executes nothing and returns a failed `RemediationResult` with an allowlist error (the node never raises). Otherwise it invokes the tool through the registry and builds the result from the real outcome: `succeeded` with the tool's output, or `failed` with the captured error. Every allow/deny decision is logged with the action and risk.

**Verification decides from real evidence.** `verify_remediation` re-reads the app through the read-only tools and marks the incident verified only when all of these hold: health is `ok`; `error_rate == 0`; `cpu_percent` is strictly below `AGENT_HEALTHY_CPU_THRESHOLD` (default `70.0`); `latency_ms_p95` is strictly below `AGENT_HEALTHY_LATENCY_MS_THRESHOLD` (default `150.0`); and there are no error-level log entries logged since the run began (the incident's detection time), so a previous fault's history cannot fail a later healthy run. A failed tool call leaves its check false, so incomplete evidence is never verified. `attempts` increments only on failure, sending the workflow back to investigation. The thresholds are set against the deterministic fixtures: a `traffic_spike` at the 2-replica baseline is CPU 78 / latency 180 (fails), while the same spike scaled to 4 replicas is CPU 39 / latency 90 (passes).


## Model connection (AWS Bedrock)

The agent talks to a model through a single module: `cloudops_agent.graph.model.connection`. It builds a `ChatBedrockConverse` client for **Claude Sonnet 4.5** and exposes a minimal `create_agent` graph used as a one-shot connectivity check. The incident workflow's investigation, diagnosis, and planning nodes build their agents on top of `get_model()` through `cloudops_agent.graph.agents` (`build_agent` / `get_agent`), which reads each agent's prompt from `agents.yaml`.

```text
services/agent/
├── langgraph.json               # LangGraph CLI / Studio configuration
└── src/cloudops_agent/graph/
    ├── agents/                  # agents.yaml + build_agent / get_agent
    └── model/
        ├── __init__.py
        └── connection.py        # get_model(), get_agent(), `agent` entry point
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
├── docker-compose.yml           # 3-service topology with health checks
├── .env.example                 # safe, non-secret configuration template
├── docs/
│   ├── PROJECT_CONTEXT.md       # north star, contracts, roadmap
│   ├── IMPLEMENTATION_PLAN.md   # dependency-ordered phases and gates
│   ├── ARCHITECTURE.md          # boundaries, graph, tool boundary
│   ├── SECURITY_AND_OPERATIONS.md
│   ├── SCENARIOS.md             # reproducible incident catalog
│   ├── decisions/               # ADR-001..ADR-008 + index
│   ├── architecture/            # placeholder
│   ├── incidents/               # placeholder
│   └── security/                # placeholder
├── infrastructure/terraform/    # future V1 work, plan-only (no apply)
├── scenarios/                   # scenario catalog notes
├── scripts/                     # local setup and seeding scripts
└── services/
    ├── app/                     # cloudops-app (simulated target)
    ├── agent/                   # cloudops-agent (monitoring, workflow, API)
    │   ├── langgraph.json       # LangGraph CLI / Studio configuration
    │   └── src/cloudops_agent/
    └── dashboard/               # cloudops-dashboard (nginx-served React console)
        ├── nginx.conf           # SPA fallback + same-origin /api proxy
        └── src/
```

## Linting

```bash
uv run --directory services/agent ruff check .
uv run --directory services/agent ruff format .
```

## Documentation

- [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — vision, contracts, roadmap levels.
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — phase order, gates, MVP cut line.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — service and tool boundaries.
- [`docs/SECURITY_AND_OPERATIONS.md`](docs/SECURITY_AND_OPERATIONS.md) — safety and control model.
- [`docs/SCENARIOS.md`](docs/SCENARIOS.md) — reproducible incident scenarios.
- [`docs/decisions/README.md`](docs/decisions/README.md) — ADR index.

## Roadmap

- **MVP (delivered):** the local `app` + `agent` + `dashboard` flow. Monitoring detection starts one workflow run per incident; the deterministic LangGraph workflow investigates, diagnoses, and plans; a real `interrupt()` parks the run for a human approval decision and a timeout sweeper ends it through the reject path (ADR-007); execution runs only an allowlisted mutating tool; verification decides from real evidence; and a post-mortem closes the incident. All of it is exposed over the typed incident API and a live SSE stream. Two of the five scenarios (`unhealthy_application`, `traffic_spike`) are implemented end to end.
- **Model connection:** AWS Bedrock `ChatBedrockConverse` for Claude Sonnet 4.5, used by the workflow's investigation, diagnosis, and planning agents and viewable through `langgraph dev`.
- **V1:** read-only AWS tools, Terraform infrastructure and `terraform_validate()`/`terraform_plan()` (plan + explanation only, no apply), CloudWatch evidence, IAM hardening.
- **V2:** SQLite persistence, the remaining 3 scenarios, measured evaluation, CI/CD.

Persistence is in-memory for the MVP. The agent never executes `terraform apply` or `terraform destroy`.

## License

[MIT](LICENSE) © 2026 Jonas
