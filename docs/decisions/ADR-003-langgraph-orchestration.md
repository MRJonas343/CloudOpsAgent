# ADR-003: Deterministic LangGraph Orchestration and Tool Boundary

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

An LLM must help investigate and plan without gaining unrestricted authority. Orchestration needs explicit state, inspectable transitions, and a hard boundary between reasoning and action. Model confidence must never authorize a mutation or skip a step.

## Decision

Represent the incident lifecycle as a deterministic LangGraph with these nodes in order:

```text
Analyze -> Collect Context -> Investigate -> Diagnose -> Plan -> Human Approval -> Execute -> Verify
```

- State carries incident identity, lifecycle status, observations, hypotheses, diagnosis, plan, risk, approval, tool calls, remediation result, verification evidence, and audit references.
- Every node emits inspectable state; approval and verification branches are explicit; failed verification can return to investigation.
- Nodes call only registered tools through a policy/guardrail check. The graph cannot invoke arbitrary Python, shell, AWS SDK calls, network requests, or Terraform commands.
- Every tool declares name, purpose, input schema, output schema, risk classification, timeout, allowlist, credential scope, and audit mapping.
- Read-only tools exist before any mutating tool.
- The LLM client is abstracted behind an interface (AWS Bedrock primary; swappable to OpenAI, Anthropic, or others). Reasoning is stored as concise evidence and decisions, never fabricated chain-of-thought.

## Consequences

- Authorization and scope are enforced by code and policy, not by prompt wording.
- Transitions, tool calls, approvals, and verification outcomes are auditable.
- Adding a capability means registering a tool, not granting broader graph authority.
- The graph can be exercised deterministically with fixtures.
