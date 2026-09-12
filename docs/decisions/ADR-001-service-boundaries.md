# ADR-001: Service Boundaries and Local Compose Topology

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

CloudOpsAgent needs a repeatable local environment where an incident can be produced, detected, diagnosed, planned, approved, executed, and verified. Signal production, orchestration, and action execution have different risk profiles, so their boundaries must be explicit from the start.

## Decision

The initial Docker Compose topology contains exactly **two** services:

| Service | Responsibility |
|---|---|
| `app` | Simulated Python (FastAPI) application: health, metrics, orders, and bounded fault/load simulation. |
| `agent` | A single FastAPI service containing the monitoring module, the typed incident API, and the LangGraph orchestration boundary. |

- Monitoring is an **internal module** of the `agent` service. It polls `app` over HTTP and triggers the LangGraph workflow in-process. It is not a separate container.
- `app` owns simulation and data production; it does not diagnose, approve, or access AWS.
- `agent` owns detection, orchestration, approval state, tool invocation, and the abstracted LLM client.
- Neither service may silently broaden the other's responsibility or credential scope.

## Consequences

- One network and one Compose file describe the whole local system.
- Agent-local monitoring avoids an extra hop and keeps detection and orchestration in one deployable unit.
- Later AWS or Terraform integrations are added as tool adapters behind `agent`, not as new containers that bypass the API, graph, guardrails, or audit flow.
- `app` remains the deterministic reference target for contracts and scenarios.
