# ADR-008: In-Memory Run Record and Off-Loop Graph Execution

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

The incident model (ADR-002) holds identity, status, and evidence, but no per-run progression: phase, timeline, plan, approval, execution, and verification were never persisted, so a run could not be inspected after it ended.

Two constraints shaped how run state could be added. First, extending `Incident` with run fields would change the `POST /incidents` contract that ADR-002 fixes, and would disturb the `find_active` dedupe. Second, the LangGraph workflow is synchronous; invoking it directly inside the async agent would block the event loop and stall every HTTP endpoint for the duration of a run. Migrating every node, tool, and agent to `ainvoke` would rewrite four modules for a demo-scale gain.

## Decision

Introduce a run record and execute the graph off the event loop:

- Add `RunRecord`, keyed by `incident_id`, as the **lifecycle source of truth**: status, phase, timeline, observations, hypotheses, diagnosis, plan, approval decision, execution result, verification result, and post-mortem summary.
- `RunService` is the **sole writer** of the record. It writes through to `Incident` status via `IncidentStore.set_status`, so ADR-002's contract and the `find_active` dedupe keep working and a terminal status releases the dedupe.
- Run the synchronous graph with `asyncio.to_thread` instead of a full `ainvoke` migration. Stream node updates and marshal each back to the event loop with `loop.call_soon_threadsafe(...)`, so mutation and publishing stay on the loop thread: one writer, no locks.
- Records are in-memory (ADR-005, V1). A restart loses them, and any non-terminal record is surfaced as `failed`, never as pending.

**Migration trigger for `ainvoke`:** recorded, not scheduled. Revisit when the graph must be driven by a non-blocking-native runtime, when worker-thread cost or observability becomes a real constraint, or when V2 persistence (ADR-005) lands.

## Consequences

- HTTP endpoints stay responsive while a run reasons; `GET /health` remains sub-second mid-run.
- `POST /incidents` and `GET /incidents/{id}` are unchanged. Run data is additive and exposed through new read endpoints.
- Status, timeline, and evidence progress through a single writer on the loop thread, so no locks are needed.
- A paused run holds no worker thread. A worker that dies without raising is not reconciled beyond process death, because the record dies with the process.
- A full async migration remains available later without changing the record's contract.
