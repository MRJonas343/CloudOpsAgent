# ADR-004: Risk Levels, Human Approval, and Guardrails

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

Some remediation actions are safe and reversible; others are material or destructive. Risk must be assigned to the proposed **action**, not to the incident label alone, and authorization must be explicit and scoped. Detection and model output must never authorize a mutation.

## Decision

Classify every proposed action as Risk 0-3:

| Risk | Meaning | Required control |
|---|---|---|
| 0 | Observation, query, analysis, evidence collection | Registered read-only tool and audit record |
| 1 | Reversible, bounded, low-impact action | Allowlist, parameter bounds, current evidence, recorded decision |
| 2 | Material service or infrastructure change | Human approval, explicit scope, rollback, expiry, verification |
| 3 | Destructive, broad, privilege-sensitive, or uncertain | Explicit human approval plus elevated review; no automatic MVP execution |

Guardrail pipeline:

```text
evidence -> typed plan -> risk classification -> scope/parameter validation
-> freshness and duplicate check -> approval and expiry check
-> tool allowlist and IAM check -> timeout and rate limit
-> execute -> audit -> verify metrics + health + logs
```

- Each check returns allow or deny; a missing check is not an allow.
- Approval is scoped to the exact plan and parameters and cannot be reused for a changed plan.
- Denied, expired, ambiguous, or out-of-scope requests stop without mutation.
- IAM changes are always high-risk/destructive and require explicit approval plus elevated review.
- Fail closed on ambiguity, missing evidence, stale approval, or tool failure.

## Consequences

- Risky actions cannot proceed on detection or model confidence alone.
- Every action has a risk level, scope, approval state, rollback/no-op, and verification criteria.
- Denied actions are audited alongside allowed ones.
- The operator retains decision authority over material changes.
