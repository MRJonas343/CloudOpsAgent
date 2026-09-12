# Security and Operations

The operating rule is simple: observe broadly, decide explicitly, mutate narrowly, and verify with independent evidence. When in doubt, stop safely and preserve the evidence.

## Least-Privilege Roles

| Role | Default capabilities | Prohibited capabilities |
|---|---|---|
| `agent` (monitoring module) | Poll app `/health` and `/metrics` via HTTP, detect incidents, trigger LangGraph workflow internally | Remediation, IAM changes, arbitrary network access, terraform apply/destroy |
| `agent` (workflow) | Validate incidents, run graph, call registered tools, generate Terraform plans | Raw shell, unrestricted AWS SDK, credential creation, terraform apply/destroy |
| `aws-readonly` | Scoped inventory, CloudWatch metrics/logs, health context | Write, delete, IAM mutation, role escalation |
| `remediation-executor` | Only explicitly allowlisted action APIs | Broad account administration, arbitrary resource selection |
| `terraform-plan` | Format, validate, inspect plans | `apply`, `destroy` |
| `operator` | Review evidence, approve or deny within assigned scope | Bypass guardrails or alter audit history |

Roles should be separate credentials or execution identities where the platform permits it. Scope by service, resource, action, region, environment, and time. MVP requires no AWS credentials.

## Credential Handling

- Load credentials from approved environment, local secret store, or workload identity; never from source, tests, fixtures, logs, or docs.
- Use short-lived credentials and narrow roles when cloud access is introduced.
- Redact tokens, authorization headers, secret values, and sensitive identifiers before persistence.
- Fail closed when credentials are absent or over-privileged rather than falling back to a broader identity.
- Never print environment dumps or raw SDK requests.

## Risk Levels

| Level | Definition | Required control |
|---|---|---|
| 0 | Observation, query, analysis, or evidence collection | Registered read-only tool, audit record |
| 1 | Reversible, bounded, low-impact action | Allowlist, parameter bounds, current evidence, recorded decision |
| 2 | Material service or infrastructure change | Human approval, explicit scope, rollback, expiry, verification |
| 3 | Destructive, broad, privilege-sensitive, or uncertain action | Explicit human approval plus elevated review; no automatic MVP execution |

Risk is assigned to the proposed action, not to the incident label alone. A low-severity incident can still require a high-risk action.

## Guardrail Pipeline

```text
Incident evidence
  -> typed plan
  -> risk classification
  -> scope and parameter validation
  -> freshness and duplicate check
  -> approval and expiry check
  -> tool allowlist and IAM check
  -> timeout and rate limit
  -> execute
  -> audit
  -> verify metrics + health + logs
```

Each check must produce an allow or deny decision. A missing check is not an allow. Tool adapters must repeat critical validation at their boundary rather than trusting only the graph.

## Approval Requirements

An approval request must show incident ID, evidence summary, diagnosis and uncertainty, proposed action, exact scope, risk level, expected effect, rollback or no-op, verification criteria, approver, expiry, and any conflicting or stale evidence.

- Risk 0 does not need mutation approval.
- Risk 1 follows a documented policy and still records the decision.
- Risk 2 requires explicit human approval before execution.
- Risk 3 requires explicit approval and elevated review; MVP does not execute it automatically.
- Denied, expired, ambiguous, or out-of-scope requests stop without mutation.
- Approval is scoped to the exact plan and parameters; it cannot be reused for a changed plan.

## Terraform Safety

Terraform is an infrastructure description and review surface. For VPC, EC2, IAM, CloudWatch, and security groups:

- Run formatting, validation, static security checks, and plan review.
- Keep variables explicit and reject dangerous defaults.
- Review IAM changes as security-sensitive.
- Keep state and plan artifacts protected from secrets.
- Expose only typed tools: `terraform_validate()` and `terraform_plan()` (both read-only).
- `terraform_validate()` is read-only and returns diagnostics.
- `terraform_plan()` is read-only and returns the exact plan artifact or digest, workspace, variables, scope, and proposed changes.
- The agent does NOT execute `terraform apply` or `terraform destroy`. It generates plans and explains what they would do to the user.
- The valid workflow is: `terraform_validate()` -> `terraform_plan()` -> agent explains the plan to the user.
- IAM changes are always high-risk/destructive and require explicit human approval plus elevated review; they are not automatic remediation paths.
- Do not let an LLM invoke raw `terraform apply`, raw `terraform destroy`, or arbitrary Terraform commands.

## Audit Records

Record these events in append-only or tamper-evident storage when available:

| Event | Minimum fields |
|---|---|
| Detection | incident, source, signal, threshold, timestamp |
| Observation | tool, scope, redacted result, freshness, correlation ID |
| Hypothesis/diagnosis | evidence references, uncertainty, actor/service |
| Plan | action, parameters, risk, rollback, verification |
| Approval | approver, decision, scope, expiry, reason |
| Tool call | tool, validated input summary, output summary, result |
| Remediation | action result, duration, error, rollback/no-op |
| Verification | metrics, health, logs, conclusion, next state |
| Closure | final status, residual risk, evidence references |

Do not store fabricated chain-of-thought. Store concise rationale and evidence references that an operator can inspect.

## Verification Loop

After a mutating action, verify all three evidence classes:

1. **Metrics:** the triggering signal and relevant saturation/error metrics move toward the expected state.
2. **Health:** service health and representative behavior are healthy.
3. **Logs:** errors, restarts, and action-related failures are absent or explained.

If any class is missing, stale, contradictory, or unhealthy, keep the incident open and return to investigation. Never close on a single green metric or on the executor's success response.

## Failure Behavior

- Tool timeout or partial result: mark evidence incomplete, do not infer success.
- Invalid or stale incident: reject or pause until refreshed.
- Approval denial or expiry: stop mutation and retain the decision.
- Guardrail mismatch: deny and expose the violated rule.
- Execution error: record the error, attempt only an approved rollback, then verify.
- Verification failure: return to investigation with a new observation cycle.
- Audit or persistence failure: fail closed for mutation; preserve in-memory evidence for diagnosis where possible.
- Missing credentials: use mocks or read-only local behavior; never broaden access.

## Operational Checklist

- [ ] Two Compose services (`app` + `agent`) start with no cloud credentials.
- [ ] `/health`, `/metrics`, and `/api/orders` respond as documented.
- [ ] Simulation controls are bounded, local-only or protected, and resettable.
- [ ] Monitoring module (inside agent) polls app via HTTP and emits stable incident payloads with correlation IDs.
- [ ] FastAPI validates all incident and plan fields.
- [ ] Graph nodes use registered tools only.
- [ ] Read-only tools are tested before any mutating tool exists.
- [ ] Every action has a risk level, scope, approval state, and verification criteria.
- [ ] Secrets and sensitive values are redacted.
- [ ] Metrics, health, and logs are checked after action.
- [ ] Failed verification returns to investigation.
- [ ] Terraform validation and plan checks pass; agent explains plans without executing apply or destroy.
- [ ] IAM changes are classified as high-risk/destructive.
- [ ] MVP scenario evidence (unhealthy application, traffic spike) and measured evaluation results are attached to the release record.
