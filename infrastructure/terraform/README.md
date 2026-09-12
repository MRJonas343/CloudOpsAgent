# Terraform (Future V1 Work)

This directory is reserved for the V1 AWS infrastructure definitions: VPC, EC2, IAM, CloudWatch, and security groups.

- **Status:** placeholder. No Terraform configuration exists in Phase 0.
- **Safety model:** Terraform is a plan-and-explain surface only. The agent generates plans and explains them; it does **not** execute `terraform apply` or `terraform destroy`.
- **Allowed tool contracts (future):** `terraform_validate()` and `terraform_plan()`, both read-only.
- **Workflow:** `terraform_validate()` -> `terraform_plan()` -> the agent explains the plan to the user.

Do not add credentials, state files, or real account identifiers here. See [`docs/SECURITY_AND_OPERATIONS.md`](../../docs/SECURITY_AND_OPERATIONS.md) and [`docs/decisions/ADR-005-local-to-aws-evolution.md`](../../docs/decisions/ADR-005-local-to-aws-evolution.md).
