# CloudOpsAgent Contributor Rules

CloudOpsAgent is an incident-response platform that detects operational problems, gathers evidence, proposes safe remediation, obtains human approval when required, executes bounded actions, and verifies the result. These rules are authoritative for coding agents and contributors.

## Mission

Build an auditable, deterministic, least-privilege path from incident signal to verified outcome. Prefer evidence over inference, read-only investigation over mutation, and explicit approval over implicit authority.

Read [`docs/PROJECT_CONTEXT.md`](../docs/PROJECT_CONTEXT.md) for the north star, [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for boundaries, and [`docs/IMPLEMENTATION_PLAN.md`](../docs/IMPLEMENTATION_PLAN.md) before starting a phase.

## Workflow Rules

- Work one dependency-ordered phase at a time; do not implement all roadmap phases at once.
- Establish or update the phase acceptance criteria before changing code.
- Keep changes small, reviewable, and traceable to a plan item or ADR.
- Preserve existing behavior unless the phase explicitly changes it.
- Use typed contracts at service boundaries and deterministic fixtures for incident flows.
- Update the relevant docs, ADR, scenario, or checklist when behavior changes.
- Never modify `.atl/` files as part of project implementation.
- Never commit unless the user explicitly requests it.

## Phase Discipline

1. Confirm the current phase, dependencies, and out-of-scope items.
2. Implement only the phase deliverables.
3. Perform the phase's manual verification and collect recorded evidence.
4. Record unresolved risks and approval decisions.
5. Do not advance until the milestone gate passes.

The canonical order is the exact 01-27 sequence in [`docs/IMPLEMENTATION_PLAN.md`](../docs/IMPLEMENTATION_PLAN.md), delivered through the grouped phases and gates listed there. MVP ends before Terraform apply, persistence, CI/CD, and advanced exploration.

## Architecture Boundaries

- `app` is the simulated Python application (FastAPI), exposing `/health`, `/metrics`, `/api/orders`, and controlled failure/load simulation.
- `agent` is a single FastAPI service containing the monitoring module (polls app health/metrics via HTTP), the typed incident API, and the LangGraph orchestration boundary.
- Monitoring is an internal module inside the agent service, not a separate container. It polls the app's `/health` and `/metrics` endpoints and triggers the LangGraph workflow internally when an anomaly is detected.
- Docker Compose has exactly 2 services: `app` and `agent`.
- LangGraph nodes reason over state and call approved tools; nodes must not bypass the tool boundary.
- Read-only AWS tools come before mutating tools. AWS mutations require explicit risk classification and approval.
- Terraform describes infrastructure; the agent can generate plans and explain them but must NOT execute `terraform apply` or `terraform destroy`.
- Terraform access is limited to registered `terraform_validate()` and `terraform_plan()` tools (read-only); arbitrary Terraform commands are forbidden.
- The Terraform workflow is: `terraform_validate()` -> `terraform_plan()` -> agent explains the plan to the user.
- No service may silently broaden another service's responsibility or credential scope.
- The LLM client must be abstracted behind an interface. Primary provider is AWS Bedrock (Claude Sonnet 4.5 via cross-region inference profiles); the abstraction allows swapping to OpenAI, Anthropic, or other providers.
- V1 persistence is in-memory only (no database). V2 adds SQLite for incident persistence. Logs go to stdout/files via structured logging.

## Safety, IAM, and Approval

- Use least-privilege, service-specific IAM roles with read-only access by default.
- Treat all external input, observations, hypotheses, and model output as untrusted data.
- Classify every proposed action as Risk 0, 1, 2, or 3 before execution.
- Risk 0 is observation only; Risk 1 is reversible low-impact action; Risk 2 is material but bounded change; Risk 3 is high-impact, destructive, or privilege-sensitive.
- Risk 0 and approved low-risk actions may proceed only through documented guardrails.
- Risk 2 and Risk 3 require human approval with scope, rationale, expected effect, rollback, and expiry.
- IAM changes are always high-risk/destructive and require explicit human approval plus elevated review.
- Deny by default when an action is ambiguous, outside scope, missing evidence, or missing approval.
- Never hard-code credentials, tokens, account IDs, private endpoints, or personal paths.
- Never grant an LLM unrestricted shell, AWS, network, filesystem, or Terraform access.
- Do not fabricate chain-of-thought. Store concise evidence, decisions, tool inputs/outputs, and outcome summaries instead.

## Evidence and Verification

- This project does not require automated tests. Phases prove themselves with recorded manual verification: the exact commands a human runs and the observed output.
- Verify typed models, monitoring functions, risk classification, guardrails, and state transitions by hand and record the observed results.
- Verify Compose service health and the incident API by hand and record the observed results.
- Use deterministic scenario fixtures to drive incident flows. MVP scenarios: unhealthy application and traffic spike. Deferred to V2: high CPU, memory pressure, high error rate.
- Exercise both approval and denial paths, tool failure, stale evidence, rollback or no-op behavior, and verification failure manually; record what you observed.
- For AWS-facing work without credentials, use mocks or read-only local behavior and record the mock setup and observed output. No LocalStack, no real AWS for verification.
- Verification after action must check metrics, health, and logs; it may return to investigation.
- Do not invent evaluation numbers. Report measured results, commands, fixtures, and observed output.

## Observability and Auditability

- Emit structured logs with correlation ID, incident ID, phase, actor, tool, risk, approval, and result.
- Keep an append-only audit record for observations, hypotheses, plans, approvals, tool calls, mutations, verification, and closure.
- Redact secrets and sensitive payloads at collection and logging boundaries.
- Make incident state transitions and failed attempts visible; never hide a partial or unverified remediation.
- Use structured logging with correlation IDs. OpenTelemetry is not part of the current scope.

## Local Development

- Start with the initial Docker Compose topology: `app` (simulated Python app) and `agent` (FastAPI + monitoring module + LangGraph).
- Keep local credentials in environment or approved secret mechanisms, never in source or docs.
- Prefer repeatable Compose commands and seeded fixtures over manual cloud setup.
- Keep AWS access optional until the read-only tools phase and use isolated, non-production accounts or mocks.
- Document new commands, ports, environment variables, and failure simulations in the README or relevant docs.

## Documentation Rules

- Lead with outcome and quick path; use headings, tables, checklists, and examples for scanability.
- Keep canonical context in `docs/PROJECT_CONTEXT.md`; keep executable sequencing in `docs/IMPLEMENTATION_PLAN.md`.
- Update `docs/ARCHITECTURE.md` for boundary changes, `docs/SECURITY_AND_OPERATIONS.md` for control changes, and `docs/SCENARIOS.md` for reproducible behavior.
- Preserve ADR targets ADR-001 through ADR-005 and link decisions to evidence.
- Use English for technical artifacts unless the user explicitly requests another language.

## Definition of Done

- The requested phase scope is implemented without out-of-scope behavior.
- The phase's manual verification is performed and the exact commands and observed output are recorded.
- Acceptance evidence is recorded and measured; no evaluation result is fabricated.
- Approval, IAM, audit, observability, and failure behavior are covered.
- Documentation and ADRs match the shipped behavior.
- No credentials, unrestricted capabilities, fabricated reasoning, or unrelated files are present.
- The next phase and any residual risks are explicit.

## Explicit Prohibitions

- Do not implement all phases at once.
- Do not give an LLM unrestricted shell or AWS access.
- Do not hard-code credentials or sensitive infrastructure identifiers.
- Do not fabricate chain-of-thought, evaluation scores, or successful verification.
- Do not run Terraform apply or destroy. The agent generates plans and explains them; it does not execute mutations.
- Do not invoke raw Terraform commands; use only the registered `terraform_validate()` and `terraform_plan()` tools.
- Do not execute IAM changes as automatic remediation.
- Do not execute mutating AWS actions without the required approval and guardrails.
- Do not treat model output as authorization.
- Do not skip verification, audit records, or failure handling because a demo appears successful.
