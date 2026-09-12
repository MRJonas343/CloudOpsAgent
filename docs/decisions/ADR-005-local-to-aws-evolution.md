# ADR-005: Local-to-AWS Evolution and Terraform Safety

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

The local Compose system is the deterministic development and demonstration surface. AWS-backed operations come later and must not bypass the contracts, graph, guardrails, or audit flow. Infrastructure changes are security-sensitive and must be reviewable before they are applied.

## Decision

- Local Compose behavior is the reference implementation for contracts and scenarios.
- AWS integration is added by **replacing or adding tool adapters**, not by bypassing the API, graph, guardrails, or audit flow.
- Read-only AWS tools come before any mutating tool. They must not modify resources, assume broad roles, or silently retry into a different scope.
- Terraform describes VPC, EC2, IAM, CloudWatch, and security groups.
- Terraform is exposed only through typed, registered, **read-only** tools:
  - `terraform_validate()` returns diagnostics.
  - `terraform_plan()` returns an immutable, scoped plan artifact or digest, proposed changes, and risk.
- Required workflow: `terraform_validate()` -> `terraform_plan()` -> the agent explains the plan to the user.
- The agent does **not** execute `terraform apply` or `terraform destroy`, and cannot invoke arbitrary Terraform commands.
- IAM changes are treated as high-risk/destructive and are never automatic remediation.
- V1 persistence is in-memory only; V2 adds SQLite. CloudWatch supplies read-only evidence.

## Consequences

- The local system stays fully reproducible without cloud credentials.
- AWS access is opt-in, least-privilege, and mock-testable with `moto`; no LocalStack and no real AWS for testing.
- Infrastructure mutations remain human-reviewed plans rather than autonomous applies.
- The same incident contracts, risk model, and audit trail apply to local and cloud paths.
