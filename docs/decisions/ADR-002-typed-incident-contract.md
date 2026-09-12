# ADR-002: Typed Incident Contract and Lifecycle State Model

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

Incident data crosses service and tool boundaries and drives authorization decisions. Free-form dictionaries and string statuses make validation, audit, and verification unreliable. The incident lifecycle also has a loop: a failed verification must return to investigation rather than silently close.

## Decision

Define a typed incident contract with Pydantic models and enums.

Core models: `Incident`, `Observation`, `Hypothesis`, `RemediationPlan`, `RemediationResult`.

- `Incident` owns identity, `type`, `severity`, `status`, timestamps, observations, source, and correlation ID.
- Plans own risk, approval requirements, action scope, rollback/no-op, and verification criteria.
- Results own execution and verification evidence.

Enumerated types:

- `type`: `high_cpu | memory_pressure | unhealthy_application | high_error_rate | traffic_spike`
- `severity`: `low | medium | high | critical`
- `status`: `detected | investigating | diagnosed | planned | awaiting_approval | remediating | verifying | resolved | failed`

Lifecycle:

```text
Detect -> Investigate -> Diagnose -> Plan -> Approve -> Remediate -> Verify -> Close
                    ^                                      |
                    +---------- failed verification ------+
```

## Consequences

- Invalid types, statuses, and missing fields are rejected at the API boundary.
- Status transitions and evidence are inspectable and auditable.
- A failed verification returns to investigation; it cannot be marked complete.
- Severity and status are typed enums, not free-form strings.
