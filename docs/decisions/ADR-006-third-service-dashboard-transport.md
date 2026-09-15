# ADR-006: Third Service and Same-Origin Dashboard Transport

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

ADR-001 fixed the local Compose topology at exactly **two** services, `app` and `agent`. The incident lifecycle (detect, reason, approve, remediate, verify, close) is not demonstrable from JSON responses alone; an operator needs a browser surface that shows the live timeline, the pending approval, and the verification result.

Two browser backends would be involved (`agent` for incidents, `app` for simulation controls). Calling them directly from a browser crosses origins and forces CORS configuration on services that otherwise have none. Server-Sent Events additionally breaks behind a proxy that buffers responses.

## Decision

Add a third Compose service and serve the browser surface from a single origin:

- Add `dashboard` on the `cloudops` network, port `:3000`. It is a static Vite + React + TypeScript + Tailwind build served by **nginx**.
- nginx serves the built assets and reverse-proxies the API paths so the browser talks to one origin:
  - `/api/agent` -> `agent:8000`
  - `/api/app` -> `app:8001`
- Disable proxy buffering for the events route and set `X-Accel-Buffering: no` on the SSE response, so event frames reach the browser incrementally.
- The dashboard is read-only toward the rest of the system: it calls the existing `agent` and `app` endpoints and adds no routes to `services/app`. Chaos controls call only the existing app simulation routes.
- The agent's in-process SSE bus (one `asyncio.Queue` per client, monotonic ids, no replay) is sufficient for the single-process V1 deployment.

## Consequences

- ADR-001's "exactly two services" is amended: the local topology now has three services. The agent-internal monitoring decision and the `app`/`agent` responsibility split from ADR-001 are unchanged.
- No CORS configuration exists or is needed; the nginx origin is the only browser entry point.
- The local demo gains a third container and a new port (`DASHBOARD_PORT`, default `3000`).
- If the agent is ever scaled to multiple replicas, the in-process bus must be replaced with a broker/pub-sub, and the same-origin proxy must route SSE to the replica that owns the run.
- SSE remains transport-only: clients refetch on reconnect because the bus does not replay.
