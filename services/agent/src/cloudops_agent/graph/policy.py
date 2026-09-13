"""Risk policy for remediation actions.

The planner model classifies risk, but a model must never be able to lower a
gate. These floors are enforced in code: whatever the model proposes, an action
can never be classified below the minimum for its class.
"""

from __future__ import annotations

from cloudops_agent.models import RiskLevel

#: Minimum risk per action-name prefix. Matching is case-insensitive against the
#: action identifier the planner returns.
ACTION_RISK_FLOOR: dict[str, RiskLevel] = {
    "scale_": RiskLevel.infrastructure_change,
    "resize_": RiskLevel.infrastructure_change,
    "restart_": RiskLevel.infrastructure_change,
    "terraform_": RiskLevel.infrastructure_change,
    "terminate_": RiskLevel.destructive,
    "delete_": RiskLevel.destructive,
    "destroy_": RiskLevel.destructive,
    "modify_iam": RiskLevel.destructive,
}

#: Risk level at which human approval becomes mandatory.
APPROVAL_RISK_THRESHOLD = RiskLevel.infrastructure_change


def risk_floor(action: str) -> RiskLevel:
    """Return the minimum risk allowed for ``action``."""
    normalized = action.strip().lower()
    floor = RiskLevel.read
    for prefix, minimum in ACTION_RISK_FLOOR.items():
        if normalized.startswith(prefix) and minimum > floor:
            floor = minimum
    return floor


def effective_risk(action: str, proposed: RiskLevel) -> RiskLevel:
    """Return the governing risk, never lower than the floor for ``action``."""
    return max(proposed, risk_floor(action))


def requires_approval(risk: RiskLevel) -> bool:
    """Return whether ``risk`` mandates human approval."""
    return risk >= APPROVAL_RISK_THRESHOLD
