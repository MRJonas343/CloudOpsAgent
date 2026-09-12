# CloudOpsAgent Implementation Plan

This is the executable, dependency-ordered plan. Complete one phase, collect its evidence, pass its gate, and only then start the next phase. The sequence starts at repository foundation and ends with evaluation and CI/CD.

Related references: [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`SECURITY_AND_OPERATIONS.md`](SECURITY_AND_OPERATIONS.md), and [`SCENARIOS.md`](SCENARIOS.md).

## Prerequisites

- Docker and Docker Compose available locally.
- Python environment and FastAPI/Pydantic/LangGraph dependencies selected and pinned by implementation.
- A test runner for Python services.
- `moto` library for AWS SDK mocking in tests.
- Local-only configuration mechanism for ports, thresholds, and simulation controls.
- No cloud credentials required for MVP; if used later, use a non-production account with least-privilege roles.
- A README that points to the quick start and this plan.

## Phase Sequence

### Phase 0: Repository Foundation

**Objective:** establish a clean, documented project skeleton without application behavior.

**Scope:** package layout, Compose skeleton, environment conventions, README outline, ADR placeholders ADR-001 through ADR-005, test layout, lint/format conventions.

**Deliverables:** repository README, service directories, Compose configuration shape, safe environment example, ADR index, baseline test commands.

**Acceptance criteria:** a fresh checkout explains how to start the project; no secret values are committed; service names and boundaries match the context.

**Tests/evidence:** documentation read-through, Compose config validation, repository status showing no generated secrets.

**Dependencies:** none.

**Out of scope:** business endpoints, AWS access, LangGraph behavior, Terraform execution.

### Phase 1: Initial Docker Compose Topology

**Objective:** make `app` (Python simulated app) and `agent` (FastAPI + monitoring module + LangGraph) start together locally.

**Scope:** service definitions, networks, health checks, configuration injection, startup ordering where needed. Docker Compose has exactly 2 services.

**Deliverables:** runnable Compose topology and service health contracts.

**Acceptance criteria:** both services start in a clean environment and expose documented health checks without cloud credentials.

**Tests/evidence:** Compose config validation, clean start, health probe output, controlled shutdown and restart.

**Dependencies:** Phase 0.

**Out of scope:** real incident detection, persistence, AWS tools.

### Phase 2: Python Application and Simulation

**Objective:** provide a deterministic application target for monitoring and demos.

**Scope:** `GET /health`, `GET /metrics`, `GET /api/orders`, controlled failure/load simulation, bounded local-only controls. Implemented in Python (FastAPI).

**Deliverables:** Python FastAPI app, representative order behavior, deterministic metric fields, simulation fixtures for the five scenarios.

**Acceptance criteria:** normal requests work; health and metrics reflect controlled state; simulations can be started and cleaned up explicitly; simulation controls are not unrestricted.

**Tests/evidence:** endpoint tests, metrics shape assertions, order success/error tests, each simulation trigger and cleanup.

**Dependencies:** Phase 1.

**Out of scope:** AWS traffic generation, production load testing, remediation actions.

### Phase 3: Monitoring Module and Incident Detection

**Objective:** convert application evidence into deterministic incident payloads via an internal monitoring module.

**Scope:** `checkHealth()` (polls app `/health` via HTTP), `collectMetrics()` (polls app `/metrics` via HTTP), `detectIncident()`, thresholds, deduplication or correlation behavior, incident payload shape. When an anomaly is detected, creates an in-memory Incident and triggers the LangGraph workflow internally.

**Deliverables:** monitoring module (inside agent service), detector rules. MVP detectors: unhealthy application and traffic spike. V2 detectors: high CPU, memory pressure, high error rate.

**Acceptance criteria:** each fixture produces the intended incident type and severity; normal operation does not produce an incident; payloads include ID, type, severity, status, timestamps, observations, source, and correlation ID.

**Tests/evidence:** unit tests for each function, scenario detector tests, false-positive baseline, payload snapshots.

**Dependencies:** Phase 2.

**Out of scope:** diagnosis, cloud queries, automated remediation.

### Phase 4: FastAPI Contracts and Incident API

**Objective:** establish a typed API for incident intake and retrieval.

**Scope:** `POST /incidents`, `GET /incidents/{id}`, `GET /health`; Pydantic models `Incident`, `Observation`, `Hypothesis`, `RemediationPlan`, and `RemediationResult`; severity and status enums.

**Deliverables:** request/response schemas, validation errors, stable IDs, in-memory MVP store or explicit adapter.

**Acceptance criteria:** valid incident payloads are accepted; invalid types, statuses, and missing fields are rejected; retrieval returns current state and evidence; health is observable.

**Tests/evidence:** model tests, API contract tests, invalid-input tests, round-trip create/retrieve test.

**Dependencies:** Phase 3.

**Out of scope:** durable persistence, authentication implementation, graph execution.

### Phase 5: Deterministic LangGraph Skeleton

**Objective:** represent the incident lifecycle as explicit state and nodes.

**Scope:** state schema and nodes `Analyze`, `Collect Context`, `Investigate`, `Diagnose`, `Plan`, `Human Approval`, `Execute`, and `Verify`.

**Deliverables:** deterministic graph, state transitions, node input/output contracts, pause/resume shape for approval.

**Acceptance criteria:** a fixture can traverse the graph in order; every node emits inspectable state; approval and verification branches are explicit; failed verification can return to investigation.

**Tests/evidence:** graph transition tests, serialized state snapshots, approval/denial branch tests, verification-failure loop test.

**Dependencies:** Phase 4.

**Out of scope:** unrestricted model autonomy, live AWS mutation, fabricated reasoning storage.

### Phase 6: Local Tool Boundary and End-to-End MVP Flow

**Objective:** connect monitoring, incident API, graph, and safe local tools.

**Scope:** tool registry, read-only local evidence tools, deterministic investigation, diagnosis and plan generation, audit event shape, controlled execution and verification.

**Deliverables:** end-to-end local incident flow and operator-visible evidence.

**Acceptance criteria:** a scenario moves from detection to close or an explicit blocked state; only registered tools run; plans include risk, scope, rollback/no-op, approval, and verification criteria; verification checks metrics, health, and logs.

**Tests/evidence:** end-to-end tests for all five scenarios, tool allowlist tests, blocked-action tests, audit event assertions.

**Dependencies:** Phases 2 through 5.

**Out of scope:** cloud credentials, AWS mutation, Terraform apply, persistent dashboard.

### Phase 7: AWS Read-Only Exploration

**Objective:** add bounded AWS evidence gathering without mutation.

**Scope:** explicit read-only tools for resource inventory, health signals, and relevant metadata; role and timeout configuration. CloudWatch metrics/logs are integrated in the later Terraform/AWS work package after infrastructure and Terraform tool contracts are established.

**Deliverables:** mocked and optional isolated-account adapters, read-only IAM policy, tool documentation.

**Acceptance criteria:** tools cannot mutate resources; calls are scoped, logged, timed out, and redacted; local mocks reproduce expected evidence when credentials are absent.

**Tests/evidence:** policy review, mock contract tests, denied-mutation test, optional isolated-account smoke test with measured output.

**Dependencies:** Phase 6 and approved IAM design.

**Out of scope:** AWS remediation, Terraform apply, production account access.

### Phase 8: Risk, Human Approval, and Guardrails

**Objective:** formalize authorization for every proposed action.

**Scope:** Risk 0-3 model, approval records, allowlists, parameter bounds, expiry, deny behavior, stale evidence handling, operator decision paths.

**Deliverables:** guardrail pipeline, approval API/state, risk/approval matrix, audit events.

**Acceptance criteria:** observation-only work requires no mutation approval; risk-bearing actions stop until approved; denial, expiry, ambiguity, and missing evidence fail closed; model output never authorizes itself.

**Tests/evidence:** matrix-driven tests, approval replay tests, expiry tests, out-of-scope action tests, redaction tests.

**Dependencies:** Phase 6; Phase 7 for cloud action taxonomy.

**Out of scope:** broad autonomous remediation, privileged role assumption, Terraform apply.

### Phase 9: AWS Infrastructure and Terraform Plan Workflow

**Objective:** establish the V1 AWS infrastructure and a Terraform plan + explanation workflow. The agent generates plans and explains them but does NOT execute apply or destroy.

**Scope:** Terraform definitions for VPC, EC2, IAM, CloudWatch, and security groups; `terraform_validate()` and `terraform_plan()` contracts (read-only); variables, outputs, plan checks, least-privilege policies, CloudWatch integration.

**Ordered substeps:**

1. **Infrastructure:** define and validate VPC, EC2, IAM, CloudWatch, and security-group resources.
2. **Tools:** expose typed `terraform_validate()` and `terraform_plan()` tools (both read-only). The agent does NOT have `terraform_apply()` or `terraform_destroy()` tools.
3. **CloudWatch:** connect scoped CloudWatch metrics/logs as read-only evidence for plan and verification.
4. **Plan and explain:** run `terraform_validate()` -> `terraform_plan()` -> agent explains the plan to the user.

**Deliverables:** reviewable Terraform code, exact plan artifacts or digests, typed tool contracts, and measured plan evidence where an isolated test environment permits.

**Acceptance criteria:** formatting and validation pass; plans are inspectable and immutable by digest; the agent explains what the plan would do without executing it; IAM changes are treated as high-risk/destructive.

**Tests/evidence:** `fmt` check, `validate`, static security checks, plan review, plan digest comparison, CloudWatch evidence.

**Dependencies:** Phase 8 and approved architecture decisions.

**Out of scope:** production provisioning by default, arbitrary Terraform commands, terraform apply, terraform destroy.

### Phase 10: Persistence and Audit

**Objective:** make incident history and operations durable.

**Scope:** V1 uses in-memory persistence only (no database). V2 adds SQLite for persisting incidents (simple, file-based, no external DB). Append-only audit records, correlation IDs, retention/redaction policy, structured logging to stdout/files.

**Deliverables:** incident storage (in-memory V1, SQLite V2), audit records, structured logging.

**Acceptance criteria:** V1: incidents are observable during the session. V2: restart does not erase required incident history; audit records are queryable and tamper-evident within the chosen design; structured logs include correlation IDs.

**Tests/evidence:** V1: in-memory state tests. V2: persistence integration tests, restart test, audit completeness assertions.

**Dependencies:** Phase 6 and operational design from Phase 8.

**Out of scope:** full production SLO program, unmeasured performance claims, automatic retention deletion without policy, OpenTelemetry (not in scope).

### Phase 11: ~~Dashboard and Operator Experience~~ [REMOVED]

**Status:** Removed from scope. For demos, use API responses + CLI/scripts instead of a dashboard.

### Phase 12: Evaluation and Scenario Harness

**Objective:** measure behavior rather than assert it.

**Scope:** reproducible scenario runner, evidence capture, detection/diagnosis/plan/approval/verification assertions, measured result reporting.

**Deliverables:** scenario matrix and evaluation report format for the five core incidents.

**Acceptance criteria:** every scenario has setup, expected tool calls, diagnosis, remediation proposal, approval expectation, verification, cleanup, and evidence; results record actual observations without invented targets.

**Tests/evidence:** full scenario runs, failure injection, false-positive checks, measured timing and outcome report.

**Dependencies:** Phases 6, 8, 10, and 11.

**Out of scope:** fabricated benchmarks, opaque model-quality claims, production incident claims from local fixtures.

### Phase 13: CI/CD and Release Controls

**Objective:** enforce safety and quality gates automatically.

**Scope:** lint, formatting, unit/integration/scenario tests, Compose validation, dependency scanning, secret scanning, Terraform validation, artifact retention, deployment gates.

**Deliverables:** CI pipeline, release checklist, environment separation, rollback notes.

**Acceptance criteria:** protected branches reject failed safety checks; secrets and generated artifacts are excluded; release evidence links to measured tests and approved changes.

**Tests/evidence:** successful and intentionally failing pipeline runs, secret-scan fixture, deployment dry run, rollback rehearsal.

**Dependencies:** Phases 9 through 12, including Terraform validation and plan safety checks where infrastructure is in scope.

**Out of scope:** unattended production mutation, bypassing approval through CI.

### Phase 14: ~~AgentCore Exploration~~ [REMOVED]

**Status:** Removed from scope. AgentCore exploration is not needed for this project.

## Exact Master Implementation Order

The following 27-item sequence is the authoritative implementation order from the supplied master plan. The grouped phases above are delivery bundles; when a bundle spans multiple items, implement its substeps in this order and do not skip a gate.

| # | Ordered item | Relevant grouped phase | Required gate or evidence |
|---|---|---|---|
| 01 | Repository cleanup/foundation | Phase 0 | Foundation gate: clean layout, README outline, ADR targets, safe configuration |
| 02 | Docker Compose (2 services) | Phase 1 | Foundation gate: two services start and health checks pass |
| 03 | Python application | Phase 2 | Detection gate: endpoints, metrics, and bounded simulations pass |
| 04 | Monitoring module (internal) | Phase 3 | Detection gate: monitoring functions and MVP detectors pass (2 scenarios) |
| 05 | Incident model | Phase 4 | Contract gate: typed models and validation pass |
| 06 | FastAPI agent gateway | Phase 4 | Contract gate: `POST /incidents`, retrieval, and health pass |
| 07 | LangGraph skeleton | Phase 5 | Orchestration gate: deterministic nodes and transitions pass |
| 08 | Agent state | Phase 5 | Orchestration gate: state, evidence, approval, and verification fields are inspectable |
| 09 | AWS read-only tools | Phase 7 | Cloud-read-only gate: scoped tools, mocks (moto), IAM review, denied mutation |
| 10 | Investigation workflow | Phase 6 | MVP gate: registered read-only calls and evidence correlation |
| 11 | Diagnosis | Phase 6 | MVP gate: evidence-supported diagnosis and uncertainty |
| 12 | Remediation planning | Phase 6 | MVP gate: typed plan with scope, risk, rollback/no-op, and verification |
| 13 | Human approval | Phase 8 | Safety gate: approval, denial, expiry, and stale-evidence tests |
| 14 | First safe remediation | Phase 6 | MVP gate: bounded local remediation or explicit blocked state |
| 15 | Verification loop | Phase 6 | MVP gate: metrics, health, logs, and return-to-investigation path |
| 16 | Terraform infrastructure | Phase 9, substep 1 | V1 infrastructure gate: validated VPC/EC2/IAM/CloudWatch/security groups |
| 17 | Terraform tools (plan only) | Phase 9, substep 2 | V1 tooling gate: validate/plan contracts (read-only), arbitrary-command denial |
| 18 | CloudWatch integration | Phase 9, substep 3 | V1 cloud-evidence gate: scoped metrics/logs and redaction tests |
| 19 | Incident scenarios (2 MVP) | Phase 12 | Scenario gate: 2 MVP scenarios with measured evidence; 3 deferred to V2 |
| 20 | IAM hardening | Phase 8 and Phase 9 | Safety gate: least-privilege policy review and high-risk IAM change handling |
| 21 | ~~OpenTelemetry~~ | ~~Phase 10~~ | [REMOVED] Not in scope |
| 22 | Persistence (in-memory V1, SQLite V2) | Phase 10 | Operational gate: in-memory for V1; V2 restart, durability, audit completeness |
| 23 | ~~Dashboard~~ | ~~Phase 11~~ | [REMOVED] Use API responses + CLI/scripts for demos |
| 24 | Evaluation | Phase 12 | Evaluation gate: measured results, no fabricated targets or scores |
| 25 | CI/CD | Phase 13 | Release gate: safety, tests, scanning, plan checks, and rollback evidence |
| 26 | Documentation | Phase 0, then each phase | Documentation gate: README, ADRs, and linked docs match behavior |
| 27 | ~~AgentCore exploration~~ | ~~Phase 14~~ | [REMOVED] Not needed for this project |

### Terraform Plan Evidence

The agent generates Terraform plans and explains them to the user. Required evidence is an immutable plan artifact or digest, the exact workspace/scope/variables, and the agent's explanation of what the plan would do. The agent does NOT execute `terraform apply` or `terraform destroy`.

## MVP Cut Line

MVP includes the local portions of ordered items 01 through 15 and the safety requirements needed to demonstrate them. MVP includes 2 scenarios (unhealthy application, traffic spike). AWS read-only tools may be exercised with mocks (using `moto`), but MVP excludes Terraform infrastructure deployment, Terraform apply/destroy, CloudWatch production integration, durable persistence (in-memory only for V1), CI/CD, and production AWS mutation. V1 covers ordered items 09 and 16 through 20; V2 covers persistence (SQLite), the remaining 3 scenarios, evaluation (item 24), and CI/CD (item 25).

## Milestone Gates

| Gate | Required evidence | Blocks |
|---|---|---|
| Foundation | Compose topology (2 services), README, ADR targets, no secrets | Phase 2 |
| Detection | 2 MVP scenarios detected with stable payloads | Phase 4 |
| Orchestration | Graph transitions, approval branch, verification loop | Phase 6 |
| MVP | End-to-end local flow, audit events, MVP scenario tests | Phase 7+ |
| Cloud read-only | IAM review, mocks (moto), denied mutation, measured smoke test if used | Phase 9 |
| Terraform plan | Validated configuration, immutable plan digest, static security checks | V1 plan workflow |
| Safety | Risk matrix, approval/expiry/deny tests, redaction evidence, IAM hardening | Any mutation design |
| Operational | Persistence (in-memory V1, SQLite V2), structured logging, evaluation evidence | Phase 13 |
| Release | CI/CD gates, rollback rehearsal, reviewed release evidence | Done |

## Scenario Matrix

| Scenario | Status | Primary evidence | Expected risk posture | Verification |
|---|---|---|---|---|
| Unhealthy application | **MVP** | failed health response, recent errors | Approval depends on restart or deployment scope | Health, metrics, logs |
| Traffic spike | **MVP** | request rate, latency, saturation evidence | Scale or routing change requires explicit scope and approval | Traffic, latency/metrics, health, logs |
| High CPU | V2 | CPU trend, latency, process/service context | Read-only diagnosis; bounded low-risk mitigation only with policy | CPU, health, logs |
| Memory pressure | V2 | memory trend, allocation/health evidence | Approval for restart or resource action | Memory, health, logs |
| High error rate | V2 | error count/rate, endpoint and log context | Plan must identify blast radius and rollback | Error rate, health, logs |

Detailed reproductions live in [`SCENARIOS.md`](SCENARIOS.md).

## Risk and Approval Matrix

| Risk | Meaning | Default approval | Allowed MVP behavior |
|---|---|---|---|
| 0 | Observe, query, or produce evidence | No mutation approval | Read-only tools and analysis |
| 1 | Reversible, bounded, low-impact action | Policy-specific; record decision | Local simulation or explicitly allowlisted action |
| 2 | Material service or infrastructure change | Required human approval | Plan and approval only unless a guarded executor exists |
| 3 | Destructive, broad, privilege-sensitive, or uncertain | Explicit approval plus elevated review | No automatic execution in MVP |

## Work Checklist

- [ ] Phase 0: foundation, README outline, ADR targets, and safe configuration
- [ ] Phase 1: two-service Docker Compose topology (`app` + `agent`)
- [ ] Phase 2: Python (FastAPI) endpoints and bounded simulations
- [ ] Phase 3: monitoring module (internal) and MVP incident detectors (2 scenarios)
- [ ] Phase 4: FastAPI endpoints and typed Pydantic models
- [ ] Phase 5: deterministic LangGraph nodes and state
- [ ] Phase 6: local tools, audit events, end-to-end MVP flow
- [ ] MVP gate passed with measured scenario evidence (2 scenarios)
- [ ] Phase 7: AWS read-only tools and IAM review (moto for mocks)
- [ ] Phase 8: risk levels, guardrails, and human approval
- [ ] Phase 9: Terraform infrastructure, typed tools (plan only, no apply/destroy), CloudWatch integration
- [ ] Phase 10: persistence (in-memory V1, SQLite V2), audit durability, structured logging
- [ ] ~~Phase 11: dashboard~~ [REMOVED]
- [ ] Phase 12: evaluation harness and measured reports
- [ ] Phase 13: CI/CD and release controls
- [ ] ~~Phase 14: AgentCore exploration~~ [REMOVED]

### Exact 01-27 Checklist

- [ ] 01 Repository cleanup/foundation
- [ ] 02 Docker Compose (2 services)
- [ ] 03 Python application
- [ ] 04 Monitoring module (internal)
- [ ] 05 Incident model
- [ ] 06 FastAPI agent gateway
- [ ] 07 LangGraph skeleton
- [ ] 08 Agent state
- [ ] 09 AWS read-only tools
- [ ] 10 Investigation workflow
- [ ] 11 Diagnosis
- [ ] 12 Remediation planning
- [ ] 13 Human approval
- [ ] 14 First safe remediation
- [ ] 15 Verification loop
- [ ] 16 Terraform infrastructure
- [ ] 17 Terraform tools (plan only)
- [ ] 18 CloudWatch integration
- [ ] 19 Incident scenarios (2 MVP, 3 deferred to V2)
- [ ] 20 IAM hardening
- [ ] ~~21 OpenTelemetry~~ [REMOVED]
- [ ] 22 Persistence (in-memory V1, SQLite V2)
- [ ] ~~23 Dashboard~~ [REMOVED]
- [ ] 24 Evaluation
- [ ] 25 CI/CD
- [ ] 26 Documentation
- [ ] ~~27 AgentCore exploration~~ [REMOVED]
