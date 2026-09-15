# CloudOpsAgent

An AI incident-response agent for a simulated cloud service. It watches an application, turns a
degradation into evidence, diagnoses the cause, proposes a remediation, waits for a human to
authorize it, executes only allowlisted actions, and verifies from real metrics that the fix worked
before it closes the incident.

## What it does

Every incident runs through the same lifecycle:

1. **Detect** — the agent polls the application and raises a typed incident when a rule fires.
2. **Investigate** — it collects evidence from the running application (health, metrics, logs,
   errors) through read-only tools.
3. **Diagnose** — a model reads the evidence and the hypotheses and states the best-supported cause.
4. **Plan** — the model proposes exactly one remediation action, chosen from the real catalogue of
   available actions and their bounds.
5. **Human approval** — the run pauses. The operator sees the action, its risk, and its parameters,
   and approves or rejects.
6. **Execute** — only an allowlisted action can run, and it runs only after approval.
7. **Verify** — the agent re-reads the application and closes the incident only when the metrics,
   health, and error logs are actually healthy.
8. **Post-mortem** — a short generated summary records the cause and the outcome.

Each gate exists for a reason. The model only ever drafts: it can propose a diagnosis and a plan,
but it has no execution authority. A human authorizes a change before it happens, so nothing
irreversible runs unattended. Execution goes through a deny-by-default tool boundary, so an
unregistered or unexpected action does nothing. And an incident is never marked resolved on the
model's word — verification re-reads the real application, and a fix that does not hold sends the
run back to investigation.

Two incidents are implemented end to end:

- `traffic_spike` — a load surge (requests per second and latency climb, CPU rises). The remedy is
  to add capacity with `scale_service`.
- `unhealthy_application` — the service reports unhealthy and starts failing requests. The remedy is
  to recover it with `restart_service`.

## How it works

Three services cooperate, all defined in `docker-compose.yml`:

- **`app`** — a simulated FastAPI application that degrades on command. It publishes deterministic
  health, metrics, and log endpoints, and exposes bounded fault simulations.
- **`agent`** — the brain. It polls `app`, detects incidents, and drives a deterministic LangGraph
  workflow over them. It also hosts the typed incident API and the live event stream the dashboard
  reads.
- **`dashboard`** — a React console served by nginx. It renders the incident list, the per-incident
  case file, and a chaos console that injects real faults into `app`.

<img width="5200" height="2284" alt="cloudopsagent-incident-response-control-plane" src="https://github.com/user-attachments/assets/aed50413-76be-4022-afe4-5a8115a67323" />
*The architecture: the dashboard and the agent share one incident API and event stream, and the workflow reaches the simulated app only through the registered tool boundary.*

The flow: the simulated app degrades on command, the agent polls it, detects the change, and runs a
deterministic graph over it — investigate, diagnose, plan. The run pauses at the approval gate until
a human decides. Only then can a remediation action run, and the agent re-reads the app to verify the
result before closing the incident, with a short post-mortem at the end. The dashboard renders every
phase live from the same API and event stream.

**The safety spine.** The model only ever drafts a plan; it cannot execute anything. The tool
boundary is deny-by-default — an action that is not registered executes nothing. Every mutating
action is classified by risk, and anything at infrastructure-change level or above pauses for human
approval, which today is every remediation action in the catalogue.

## Built with

| Layer | Technology |
|---|---|
| Services | Python 3.12 + FastAPI |
| Workflow | LangGraph — a deterministic state machine with a human-in-the-loop interrupt |
| Model | AWS Bedrock, Claude Sonnet 4.5 |
| Local topology | Docker Compose |
| Dashboard | React + TypeScript + Tailwind, served by nginx |

## Run it

```bash
python scripts/setup_local.py
```

Then open <http://localhost:3000>.

Prerequisites: Docker with Compose. [`uv`](https://docs.astral.sh/uv/) is only needed to run the
Python services outside containers. Bedrock credentials (`AWS_REGION` and
`AWS_BEARER_TOKEN_BEDROCK`, or the standard AWS credential chain) are needed for the agent to reason.

Optionally confirm the services are up:

```bash
curl http://localhost:8001/health   # {"status":"ok","service":"app"}
curl http://localhost:8000/health   # {"status":"ok","service":"agent"}
```

Stop the topology with `docker compose down`. Copy `.env.example` to `.env` to change ports, the
poll interval, the approval timeout, or the verification thresholds.

## See it work

1. Open <http://localhost:3000>.
2. Inject a fault. If the list is empty, click **Generate demo incident** — it injects a real
   `traffic_spike` for 60 seconds. Otherwise open `/console` and inject `traffic_spike` from the
   chaos console. The console reports the fault as pending until the agent finds it.
3. Wait up to ~10 s for the next poll. The new incident appears in the live list without a reload.

<img width="1178" height="960" alt="An incident and its case file" src="https://github.com/user-attachments/assets/8bc6d105-c560-4842-92ca-45b8c6d0d573" />
*An incident in the live list and its case file: the phase timeline, the evidence collected from the app, and the hypotheses the run derived from it.*

4. Open the incident and follow investigation, diagnosis, and the proposed plan.
5. When the run pauses at the approval gate, read the action and its risk, then Approve. The gate
   shows a live countdown; if nobody decides before the approval timeout, the run ends through the
   reject path and nothing is executed.

<img width="1224" height="913" alt="The incident paused at the approval gate" src="https://github.com/user-attachments/assets/718d7c8e-acc2-4fa9-a16a-8e4e1447a60d" />
*The run paused at the human-in-the-loop gate: the proposed action, its risk and parameters, and the countdown before the run times out.*

6. Watch execution and verification, then the post-mortem. An `unhealthy_application` incident
   resolves through `restart_service`; a `traffic_spike` resolves through `scale_service`.

<img width="1198" height="991" alt="The incident resolved with a generated post-mortem" src="https://github.com/user-attachments/assets/c531da9e-ae64-4e35-aea2-5d1db6fe4378" />
*The incident resolved: verification passed against the app's real metrics, and the generated post-mortem records the cause and the outcome.*

In-app toasts fire on exactly four moments — detected, awaiting approval, resolved, and failed. The
intermediate phases stay silent.

The chaos console is the injection surface used in step 2:

<img width="1177" height="801" alt="The chaos console" src="https://github.com/user-attachments/assets/23e9f519-a54f-4b99-b7ba-cd0249f04008" />
*The chaos console: application health and metrics, plus the fault controls that inject a real degradation into the simulated app.*

## Project layout

```text
CloudOpsAgent/
├── docker-compose.yml        # the three-service topology
├── scripts/setup_local.py    # one-command local setup
├── docs/                     # design, architecture, scenarios, ADRs, reference
└── services/
    ├── app/                  # simulated target (FastAPI)
    ├── agent/                # monitoring, workflow, incident API, tool boundary
    └── dashboard/            # React console served by nginx
```

## Learn more

- [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — vision, contracts, roadmap levels.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — service and tool boundaries.
- [`docs/SCENARIOS.md`](docs/SCENARIOS.md) — reproducible incident scenarios.
- [`docs/SECURITY_AND_OPERATIONS.md`](docs/SECURITY_AND_OPERATIONS.md) — safety and control model.
- [`docs/decisions/README.md`](docs/decisions/README.md) — ADR index.
- [`docs/architecture/cloudopsagent-architecture.html`](docs/architecture/cloudopsagent-architecture.html)
  — the committed architecture diagram.
- [`docs/REFERENCE.md`](docs/REFERENCE.md) — endpoints, tool contracts, verification rules, and
  configuration.


Persistence is in-memory for the MVP, and the agent never runs `terraform apply` or
`terraform destroy`.

## License

[MIT](LICENSE) © 2026 Jonas
