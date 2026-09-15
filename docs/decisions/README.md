# Architecture Decision Records

Short, durable records of the decisions that shape CloudOpsAgent. Each ADR states its status, context, decision, and consequences.

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-service-boundaries.md) | Service boundaries and local Compose topology | Accepted — amended by [ADR-006](ADR-006-third-service-dashboard-transport.md) |
| [ADR-002](ADR-002-typed-incident-contract.md) | Typed incident contract and lifecycle state model | Accepted |
| [ADR-003](ADR-003-langgraph-orchestration.md) | Deterministic LangGraph orchestration and tool boundary | Accepted |
| [ADR-004](ADR-004-risk-levels-human-approval.md) | Risk levels, human approval, and guardrails | Accepted |
| [ADR-005](ADR-005-local-to-aws-evolution.md) | Local-to-AWS evolution and Terraform safety | Accepted |
| [ADR-006](ADR-006-third-service-dashboard-transport.md) | Third service and same-origin dashboard transport | Accepted |
| [ADR-007](ADR-007-approval-pause-timeout.md) | Human-in-the-loop pause, resume, and approval timeout | Accepted |
| [ADR-008](ADR-008-run-record-off-loop-execution.md) | In-memory run record and off-loop graph execution | Accepted |

## Convention

- One decision per file, named `ADR-NNN-short-title.md`.
- Keep records short and factual; link to evidence when behavior changes.
- Supersede rather than rewrite: add a new ADR and mark the old one as superseded.
- ADR targets ADR-001 through ADR-005 are fixed by [`docs/PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md) and [`docs/IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md).
