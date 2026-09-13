# CloudOpsAgent Project Context

CloudOpsAgent is a safe incident-response control plane for simulated applications first and AWS-backed operations later. Its north-star outcome is a reproducible, auditable workflow that turns an operational signal into evidence, a diagnosis, an approved remediation plan, and a verified result without giving an LLM unrestricted authority.

## Quick Path

1. Read the phase order in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).
2. Use [`ARCHITECTURE.md`](ARCHITECTURE.md) to preserve service and tool boundaries.
3. Use [`SECURITY_AND_OPERATIONS.md`](SECURITY_AND_OPERATIONS.md) before adding any action or credential.
4. Reproduce behavior with the scenarios in [`SCENARIOS.md`](SCENARIOS.md).

## Vision

An operator should be able to see what happened, why the system believes it happened, what it proposes to do, who approved it, what actually ran, and whether the service recovered. The platform should make unsafe automation difficult and make safe, reversible, evidence-backed remediation easy to inspect.

## Problem Statement

Incident response is often fragmented across dashboards, shell sessions, cloud consoles, runbooks, and human memory. This creates slow diagnosis, inconsistent remediation, weak audit trails, and a risk that an AI system executes an action it cannot justify or verify. CloudOpsAgent addresses the coordination problem while keeping authorization and mutation explicit.

## Incident Lifecycle

Every incident follows this lifecycle. A failed verification may return to investigation; it must not be silently marked complete.

```text
Detect -> Investigate -> Diagnose -> Plan -> Approve -> Remediate -> Verify -> Close
                    ^                                      |
                    +---------- failed verification ------+
```

- **Detect:** monitoring identifies a threshold breach or failed health check.
- **Investigate:** collect bounded context using read-only tools and service evidence.
- **Diagnose:** compare observations with hypotheses and state the uncertainty.
- **Plan:** propose a typed remediation with risk, expected effect, rollback, and verification steps.
- **Approve:** obtain human approval for actions requiring it; denial ends or revises the plan.
- **Remediate:** execute only the approved, scoped action through the tool boundary.
- **Verify:** check metrics, health, and logs after the action; return to investigation if recovery is not demonstrated.
- **Close:** record outcome, evidence, residual risk, and final audit state.

## Target Architecture

### Initial Local Topology

The first Docker Compose topology contains exactly two services:

| Service | Responsibility | Initial interface |
|---|---|---|
| `app` | Simulated Python application (FastAPI) with controlled fault/load behavior | `/health`, `/metrics`, `/api/orders`, simulation controls |
| `agent` | FastAPI service containing: monitoring module (polls app via HTTP), typed incident API, LangGraph orchestration, LLM client (Azure Foundry, abstracted) | `POST /incidents`, `GET /incidents/{id}`, `GET /health` |

### AWS Evolution

Local services remain the deterministic development and demonstration surface. AWS-facing components are added behind explicit tools and least-privilege roles: read-only inventory first, then Terraform infrastructure, Terraform tools, and CloudWatch integration. Terraform is used for plan generation and explanation only; the agent does not execute `terraform apply` or `terraform destroy`. V1 adds the guarded AWS/Terraform path; V2 adds SQLite persistence, the remaining 3 scenarios, evaluation, and CI/CD.

## Technology Choices

| Area | Choice and intent |
|---|---|
| Local runtime | Docker Compose for repeatable two-service development and demos |
| Application | Python (FastAPI) with health, metrics, orders, and controlled failure/load simulation |
| Monitoring | Internal module inside the agent service; polls app `/health` and `/metrics` via HTTP |
| Agent API | FastAPI with typed Pydantic request, state, and result models |
| Orchestration | LangGraph skeleton with deterministic nodes and explicit state transitions |
| LLM Provider | Azure Foundry (primary); abstracted behind an interface for swapping to OpenAI, Anthropic, or other providers |
| Cloud boundary | Explicit read-only AWS tools first; mutations later through guarded tools |
| Infrastructure | Terraform definitions for VPC, EC2, IAM, CloudWatch, and security groups; plan + explanation only (no apply) |
| Observability | Structured logging with correlation IDs; no OpenTelemetry |
| Persistence | V1: in-memory only. V2: SQLite (file-based, no external DB) |
| Verification | Recorded manual verification against deterministic fixtures; no real AWS |
| Documentation decisions | ADR-001 through ADR-005, plus a README that explains setup, demo, architecture, safety, verification, and roadmap |

## Contracts

### Simulated Application (Python)

The simulated Python service exposes:

- `GET /health` for liveness/readiness and controlled unhealthy states.
- `GET /metrics` for deterministic operational metrics such as CPU, memory, request count, error count, latency, and traffic.
- `GET /api/orders` for a representative application operation.
- A controlled failure/load simulation interface used only for local demos and manual verification. It must be bounded, explicit, and disabled or protected outside local development.

### Monitoring (Internal Module)

The monitoring module inside the agent service implements:

- `checkHealth()` to query the application's `/health` endpoint via HTTP and return status, latency, and error details.
- `collectMetrics()` to query the application's `/metrics` endpoint via HTTP and gather the metric snapshot.
- `detectIncident()` to apply deterministic detection rules and emit an incident when evidence crosses a configured threshold.
- When an anomaly is detected, it creates an Incident in-memory and triggers the LangGraph workflow internally (no external HTTP call needed since monitoring and the workflow are in the same service).

The incident payload should remain stable and include at least:

```json
{
  "incident_id": "string",
  "service": "string",
  "type": "high_cpu | memory_pressure | unhealthy_application | high_error_rate | traffic_spike",
  "severity": "low | medium | high | critical",
  "status": "detected | investigating | diagnosed | planned | awaiting_approval | remediating | verifying | resolved | failed",
  "detected_at": "ISO-8601 timestamp",
  "observations": [],
  "source": "monitoring",
  "correlation_id": "string"
}
```

### Agent API

FastAPI provides:

- `POST /incidents` to create or accept a typed incident.
- `GET /incidents/{id}` to retrieve current state and evidence.
- `GET /health` for service health.

Core Pydantic models are `Incident`, `Observation`, `Hypothesis`, `RemediationPlan`, and `RemediationResult`. `Incident` owns severity and status; plans own risk, approval requirements, action scope, rollback, and verification criteria; results own execution and verification evidence.

### LangGraph Skeleton

The deterministic workflow contains these nodes in order:

`Analyze -> Collect Context -> Investigate -> Diagnose -> Plan -> Human Approval -> Execute -> Verify`

The graph must make state, node outputs, tool calls, approval decisions, and verification outcomes inspectable. It must not infer authorization from a prompt or skip a node because a model is confident.

### Terraform Agent-Tool Contract

Terraform is exposed only through typed, registered tools. The agent may not run arbitrary Terraform commands or construct an unbounded command line. The agent can generate plans and explain them but does NOT execute `terraform apply` or `terraform destroy`.

| Tool | Purpose | Required boundary |
|---|---|---|
| `terraform_validate()` | Validate configuration and providers | Read-only; returns diagnostics and an auditable result |
| `terraform_plan()` | Produce a scoped plan for an explicit workspace, variables, and target scope | Read-only; returns the exact plan artifact or digest, proposed changes, and risk |

The required workflow is:

```text
terraform_validate() -> terraform_plan() -> agent explains the plan to the user
```

The agent generates the plan, explains what it would do, and presents it to the user. The agent does not execute the plan.

## Security Principles

- Least privilege and service-specific IAM.
- Read-only discovery before mutation.
- Human approval for risk-bearing actions.
- Explicit allowlists, bounded parameters, timeouts, and rollback or no-op behavior.
- No secrets in source, logs, fixtures, or documentation.
- No unrestricted LLM shell, AWS, network, filesystem, or Terraform access.
- Audit every meaningful observation, decision, tool call, approval, action, and verification.
- Fail closed on ambiguity, missing evidence, stale approval, tool failure, or failed verification.

See [`SECURITY_AND_OPERATIONS.md`](SECURITY_AND_OPERATIONS.md) for the operational control model.

## Roadmap Levels

### MVP

Deliver the Compose topology (2 services: `app` + `agent`), Python simulation, monitoring detection (internal module), typed FastAPI contracts, deterministic LangGraph skeleton, agent state, local read-only tools, investigation/diagnosis/planning, human approval and guardrails, first safe local remediation, verification loop, and a complete demo. MVP includes 2 scenarios: unhealthy application and traffic spike. Terraform is plan + explanation only; the agent does not execute apply or destroy. Persistence is in-memory only.

### V1

Add AWS read-only tools, Terraform infrastructure for VPC/EC2/IAM/CloudWatch/security groups, `terraform_validate()` and `terraform_plan()` tools (plan + explanation), CloudWatch integration, and IAM hardening.

### V2

Add SQLite persistence for incidents, the remaining 3 scenarios (high CPU, memory pressure, high error rate), measured evaluation, and CI/CD release controls. Keep all mutation gated and auditable.

## Main Demo

1. Start the two Compose services (`app` and `agent`).
2. Confirm all `/health` endpoints.
3. Exercise `/api/orders` and inspect `/metrics`.
4. Trigger one bounded scenario, such as an unhealthy application or traffic spike.
5. Show monitoring detection (internal module) and the incident payload.
6. Walk through investigation, diagnosis, and the remediation plan.
7. Show approval for the selected risk level.
8. Execute only the allowed action or show a safe denial.
9. Verify metrics, health, and logs, then close or return to investigation.

The demo is successful only when the evidence and audit trail explain every transition. A green screen alone is not proof.

## Evaluation Expectations

Evaluation must be reproducible and measured. Report scenario, setup, command or fixture, observed latency or outcome, failures, false positives/negatives where applicable, approval behavior, verification result, and environment. Never invent target numbers or claim an evaluation result that was not run.

## Documentation and ADR Targets

The README should outline purpose, quick start, Compose services, API endpoints, demo walkthrough, architecture, safety model, manual verification, evaluation, roadmap, and links to these docs. Maintain these ADR targets as decisions become concrete:

- ADR-001: initial service boundaries and local Compose topology.
- ADR-002: typed incident contract and lifecycle state model.
- ADR-003: deterministic LangGraph orchestration and tool boundary.
- ADR-004: risk levels, human approval, and guardrail policy.
- ADR-005: local-to-AWS evolution and Terraform safety.

## Final Definition of Done

CloudOpsAgent is done for a release when a fresh contributor can run the documented local setup, reproduce each core scenario through recorded manual verification, observe the full lifecycle, inspect typed evidence and audit records, see approval enforced for risky actions, confirm verification checks metrics/health/logs, and review measured evaluation results. The implementation must respect service boundaries, least privilege, explicit scope, and the roadmap cut line.
