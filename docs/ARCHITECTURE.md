# CloudOpsAgent Architecture

CloudOpsAgent separates signal production, incident orchestration, and action execution so that investigation can be broad while mutation remains narrow and reviewable.

## Context View

```text
Operator
   |
   v
CloudOpsAgent control plane <----> Local simulated Python application
   |                                      |
   |  (monitoring module polls via HTTP)  v
   |                                 health and metrics
   |
   +----> Read-only AWS tools (later)
   |
   +----> Guarded remediation tools (later, approved only)
   |
   +----> Terraform plan + explanation (no apply)
```

## Container View

```text
+----------------+                            +-------------------------------+
| app            |  <--- HTTP health/metrics  | agent                         |
| Python (FastAPI)| --- simulation controls -> |                               |
|                |                             |  +-------------------------+  |
| /health        |                             |  | monitoring module       |  |
| /metrics       |                             |  | (polls via HTTP)        |  |
| /api/orders    |                             |  +-----------+-------------+  |
+----------------+                                         |                |
                                                    incident trigger (internal) |
                                                           |                |
                                                    +------v------+        |
                                                    | LangGraph   |        |
                                                    | orchestration|        |
                                                    +------+------+        |
                                                           |               |
                                                 read-only  |  approval     |
                                                    tools  |  v            |
                                                           | human         |
                                                           v               |
                                                    +------+-----+         |
                                                    | in-memory  |         |
                                                    | audit/store|         |
                                                    +------------+         |
                                                    +-------------------------------+
```

## Service Responsibilities

| Service | Owns | Does not own |
|---|---|---|
| `app` (Python FastAPI) | Simulated orders, health, metrics, bounded fault/load controls | Diagnosis, AWS access, approval, monitoring |
| `agent` (FastAPI) | Monitoring module (HTTP polling), typed incident API, LangGraph workflow, tool orchestration, approval state, LLM client (Azure Foundry, abstracted) | Unregistered shell commands, hidden mutations, credential minting, terraform apply/destroy |

### Simulated Application (Python)

`GET /health`, `GET /metrics`, and `GET /api/orders` are stable local contracts. Controlled failure/load simulation is a demo and manual-verification facility, not a general-purpose remote execution endpoint. It must be bounded, authenticated or local-only as appropriate, and resettable. Implemented in Python (FastAPI).

### Monitoring (Internal Module)

The monitoring module lives inside the agent service. `checkHealth()` queries the application's `/health` endpoint via HTTP. `collectMetrics()` queries the `/metrics` endpoint via HTTP. `detectIncident()` applies deterministic rules, deduplicates or correlates signals, and creates an in-memory Incident. When an anomaly is detected, it triggers the LangGraph workflow internally (same service, no external HTTP call).

### Agent API

FastAPI exposes `POST /incidents`, `GET /incidents/{id}`, and `GET /health`. Pydantic models define `Incident`, `Observation`, `Hypothesis`, `RemediationPlan`, and `RemediationResult`; severity and status are typed enums rather than free-form strings.

## LangGraph State and Nodes

The graph carries incident identity, lifecycle status, observations, hypotheses, diagnosis, plan, risk, approval, tool calls, remediation result, verification evidence, and audit references.

```text
Analyze
  -> Collect Context
  -> Investigate
  -> Diagnose
  -> Plan
  -> Human Approval
       | denied/expired -> stop or revise plan
       | approved       v
     Execute
       -> Verify
            | healthy -> Close
            | unclear/failed -> Investigate
```

Node rules:

- **Analyze:** normalize the incident and identify missing evidence.
- **Collect Context:** call only approved read-only tools.
- **Investigate:** correlate observations and record bounded hypotheses.
- **Diagnose:** state the best-supported cause and uncertainty; do not fabricate reasoning.
- **Plan:** produce a typed, scoped, reversible or no-op-aware plan with risk and verification criteria.
- **Human Approval:** enforce risk policy and record actor, scope, expiry, and decision.
- **Execute:** call only the approved tool with validated parameters.
- **Verify:** check metrics, health, and logs; return to investigation when evidence is insufficient.

## Explicit Tool Boundary

```text
LangGraph node
    |
    v
tool registry -> policy/guardrail check -> typed tool adapter -> audit event
                         |                         |
                   deny by default          local/AWS/Terraform API
```

The graph cannot invoke arbitrary Python, shell, AWS SDK calls, network requests, or Terraform commands. Every tool has a name, purpose, input schema, output schema, risk classification, timeout, allowlist, credential scope, and audit mapping. Terraform is reachable only through registered wrappers, never through a raw command runner.

### Read-Only Tools First

Initial tools query local health/metrics/log fixtures. Later AWS tools query inventory, CloudWatch metrics/logs, and related context. They must not modify resources, assume broad roles, or silently retry into a different scope.

### Mutating Tools Later

Mutating tools may restart a bounded local simulation or eventually perform an approved cloud action. They require validated parameters, current evidence, risk classification, human approval where required, timeout, rollback or no-op behavior, and post-action verification. MVP never applies Terraform.

### Terraform Tool Path

```text
terraform_validate()
          |
          v
terraform_plan() -- exact plan digest/scope --> Agent explains the plan to the user
```

The Terraform tool contract is:

- `terraform_validate()` checks configuration and providers and is read-only.
- `terraform_plan()` produces an immutable, scoped plan artifact or digest and is read-only.
- The agent does NOT execute `terraform apply` or `terraform destroy`. It generates plans and explains what they would do.

The agent may not call `terraform apply`, `terraform destroy`, or arbitrary Terraform commands directly. The Terraform workflow is: validate -> plan -> explain to user.

## Data and Audit Flow

1. The Python application emits health, metrics, order results, and controlled simulation state.
2. The monitoring module (inside agent) polls `/health` and `/metrics` via HTTP, records observations, and creates an in-memory Incident.
3. The monitoring module triggers the LangGraph workflow internally (same service).
4. LangGraph appends hypotheses, diagnosis, plan, approval, tool-call, execution, and verification events.
5. Verification reads metrics, health, and logs after action.
6. The incident closes only with evidence or remains open with an explicit failure state.

Every event should include incident ID, correlation ID, timestamp, actor or service, lifecycle phase, tool, risk, approval reference where relevant, redacted input/output summary, and result.

## Local-to-AWS Evolution

Local Compose behavior is the reference implementation for contracts and scenarios. AWS integration should replace or add tool adapters, not bypass the API, graph, guardrails, or audit flow. AWS read-only access comes before any mutation. Terraform describes VPC, EC2, IAM, CloudWatch, and security groups; CloudWatch supplies read-only evidence, while the Terraform path is `validate -> plan -> agent explains to user` (no apply or destroy).

## Architectural Invariants

- Detection does not authorize remediation.
- Model output does not authorize remediation.
- Approval does not widen tool scope or stale evidence.
- Verification is required after every mutation.
- Failed verification can return to investigation.
- Audit records explain both allowed and denied actions.
- No component receives unrestricted shell or AWS access.
