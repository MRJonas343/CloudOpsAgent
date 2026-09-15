# ADR-007: Human-in-the-Loop Pause, Resume, and Approval Timeout

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

ADR-004 requires explicit human approval for Risk 2 and Risk 3 actions, scoped to the exact plan and parameters and never reusable for a changed plan. The previous implementation auto-approved inside the approval node, so the gate was not real and the operator never held the decision.

A real gate must pause a run, release the request, and resume when a later HTTP call carries the decision. LangGraph's `interrupt()` resumes a graph, but it has **no timeout** and its checkpoint has no durability guarantee under the current in-memory store (ADR-005, V1).

## Decision

Make the approval gate a real, bounded pause with application-owned timing:

- `human_approval` is side-effect-free before `interrupt({incident_id, action, risk_level, parameters})`, so LangGraph can safely re-run the node on resume.
- Compile the graph with `InMemorySaver` and use `thread_id = incident_id`, so each incident owns its checkpoint.
- Resume with `Command(resume={...})` carrying the operator's decision, executed off the event loop.
- The approval **deadline is owned by the application** (stored on the run record), not by the paused node. A 1-second sweeper ends an expired wait through the reject path. `interrupt()` has no timeout, and this keeps wall-clock policy out of the checkpoint.
- A resume with no checkpoint (for example after a restart) must not silently continue: the run is resolved `failed` with outcome `interrupted_restart`, and the decision is refused. Startup reconciliation applies the same rule to non-terminal records.
- Approval never bypasses the risk floor or the allowlist: an approved plan still passes the same denial-by-default execution check as before (ADR-004).

## Consequences

- The lifecycle now has a genuine blocking gate: approve continues toward execution, reject and timeout end the run without executing remediation.
- Pause state is process-local RAM. A restart loses the pause by design and resolves it `failed`; a stale approval can never be replayed. Durable pause belongs to the V2 SQLite persistence deferred by ADR-005.
- A paused run frees its worker thread; only the deadline sweeper watches it.
- The wait is bounded and configurable through `AGENT_APPROVAL_TIMEOUT_SECONDS` (default `300`), so a demo cannot stall indefinitely.
- The remaining approval time is exposed to clients so a countdown can be rendered.
