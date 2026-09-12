"""Validation tests for the remediation and hypothesis models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cloudops_agent.models import (
    Hypothesis,
    RemediationOutcome,
    RemediationPlan,
    RemediationResult,
    RiskLevel,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_plan(**overrides: object) -> RemediationPlan:
    values: dict[str, object] = {
        "action": "restart_app",
        "description": "Restart the simulated application",
        "risk_level": RiskLevel.safe_remediation,
        "approval_required": False,
        "scope": "service:app",
        "created_at": NOW,
    }
    values.update(overrides)
    return RemediationPlan(**values)


def test_risk_level_values_map_to_policy() -> None:
    assert RiskLevel.read == 0
    assert RiskLevel.safe_remediation == 1
    assert RiskLevel.infrastructure_change == 2
    assert RiskLevel.destructive == 3


def test_risk_level_and_outcome_parse_from_values() -> None:
    assert RiskLevel(2) is RiskLevel.infrastructure_change
    assert RemediationOutcome("succeeded") is RemediationOutcome.succeeded


def test_hypothesis_confidence_bounds_are_inclusive() -> None:
    low = Hypothesis(description="dns", confidence=0.0, created_at=NOW)
    high = Hypothesis(description="dns", confidence=1.0, created_at=NOW)

    assert low.confidence == 0.0
    assert high.confidence == 1.0


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_hypothesis_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        Hypothesis(description="dns", confidence=confidence, created_at=NOW)


def test_hypothesis_defaults_to_empty_evidence() -> None:
    hypothesis = Hypothesis(description="dns", confidence=0.5, created_at=NOW)

    assert hypothesis.evidence == []


def test_plan_defaults() -> None:
    plan = make_plan()

    assert plan.parameters == {}
    assert plan.rollback is None
    assert plan.verification_criteria == []


def test_plan_accepts_mixed_parameter_values() -> None:
    plan = make_plan(parameters={"replicas": 2, "force": True, "note": "bounded"})

    assert plan.parameters == {"replicas": 2, "force": True, "note": "bounded"}


def test_plan_requires_approval_for_infrastructure_change() -> None:
    with pytest.raises(ValidationError):
        make_plan(risk_level=RiskLevel.infrastructure_change, approval_required=False)

    plan = make_plan(risk_level=RiskLevel.infrastructure_change, approval_required=True)
    assert plan.approval_required is True


def test_plan_requires_approval_for_destructive() -> None:
    with pytest.raises(ValidationError):
        make_plan(risk_level=RiskLevel.destructive, approval_required=False)


@pytest.mark.parametrize(
    "risk_level",
    [RiskLevel.read, RiskLevel.safe_remediation],
)
def test_low_risk_plans_may_skip_approval(risk_level: RiskLevel) -> None:
    plan = make_plan(risk_level=risk_level, approval_required=False)

    assert plan.approval_required is False


def test_plan_parses_risk_level_from_integer() -> None:
    plan = make_plan(risk_level=2, approval_required=True)

    assert plan.risk_level is RiskLevel.infrastructure_change


def test_result_defaults_and_outcome_parsing() -> None:
    result = RemediationResult(
        action="restart_app",
        outcome="succeeded",
        executed_at=NOW,
    )

    assert result.outcome is RemediationOutcome.succeeded
    assert result.output is None
    assert result.error is None
    assert result.verified is None
