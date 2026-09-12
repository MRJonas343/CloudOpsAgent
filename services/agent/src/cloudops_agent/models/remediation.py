"""Typed remediation contract: risk levels, hypotheses, plans, and results.

``RiskLevel`` maps to the Risk 0-3 policy in
``docs/decisions/ADR-004-risk-levels-human-approval.md``:

- ``read`` (0): observation, query, or analysis; read-only tool and audit record.
- ``safe_remediation`` (1): reversible, bounded, low-impact action.
- ``infrastructure_change`` (2): material service or infrastructure change;
  requires human approval.
- ``destructive`` (3): destructive, broad, or privilege-sensitive; requires
  explicit human approval and elevated review, and is never automatic in MVP.

These models are composed into the workflow state in Phase 5; they are
deliberately not embedded in ``Incident``.
"""

from datetime import datetime
from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field, model_validator


class RiskLevel(IntEnum):
    """Action risk classification. Higher values require stronger controls."""

    read = 0
    safe_remediation = 1
    infrastructure_change = 2
    destructive = 3


class RemediationOutcome(StrEnum):
    """Terminal outcome of executing a remediation action."""

    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class Hypothesis(BaseModel):
    """A bounded, evidence-backed explanation produced during investigation."""

    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime


class RemediationPlan(BaseModel):
    """A proposed action with risk, scope, rollback, and verification criteria."""

    action: str
    description: str
    risk_level: RiskLevel
    approval_required: bool
    scope: str
    parameters: dict[str, object] = Field(default_factory=dict)
    rollback: str | None = None
    verification_criteria: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def _require_approval_for_high_risk(self) -> "RemediationPlan":
        """Risk 2+ (infrastructure change or destructive) must require approval."""
        if self.risk_level >= RiskLevel.infrastructure_change and not self.approval_required:
            raise ValueError(
                "approval_required must be True when risk_level is "
                "infrastructure_change (2) or destructive (3)"
            )
        return self


class RemediationResult(BaseModel):
    """Execution and verification evidence for a ``RemediationPlan``."""

    action: str
    outcome: RemediationOutcome
    executed_at: datetime
    output: str | None = None
    error: str | None = None
    verified: bool | None = None
