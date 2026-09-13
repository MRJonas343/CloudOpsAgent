"""Explicit state for the deterministic incident workflow.

LangGraph threads this dict between nodes. Fields declared plainly are
**overwritten** by whichever node returns them; fields wrapped in ``Annotated``
use a reducer so repeated writes combine instead of clobbering each other:

- ``observations`` / ``hypotheses`` accumulate evidence (``operator.add``).
- ``messages`` appends LLM messages (``add_messages``).
- ``attempts`` counts investigation/verification cycles (``operator.add``).

Only the state contract lives here; the nodes are added in a later step.
"""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel

from cloudops_agent.models import (
    Hypothesis,
    Incident,
    Observation,
    RemediationPlan,
    RemediationResult,
)


class ApprovalDecision(BaseModel):
    """Recorded human decision for a risk-bearing remediation plan.

    ``expires_at`` keeps an approval scoped to the exact plan and time window it
    was granted for, so a stale approval cannot authorise a later action.
    """

    approved: bool
    approver: str | None = None
    reason: str | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None


class VerificationResult(BaseModel):
    """Post-action verification evidence.

    Mirrors the verification loop: a remediation is only considered successful
    when metrics, health, and logs all agree.
    """

    verified: bool
    metrics_ok: bool
    health_ok: bool
    logs_ok: bool
    summary: str
    checked_at: datetime


class IncidentState(TypedDict):
    """State carried through Analyze -> Collect Context -> ... -> Verify."""

    incident: Incident
    observations: Annotated[list[Observation], operator.add]
    hypotheses: Annotated[list[Hypothesis], operator.add]
    diagnosis: str | None
    plan: RemediationPlan | None
    approval: ApprovalDecision | None
    execution_result: RemediationResult | None
    verification: VerificationResult | None
    summary: str | None
    messages: Annotated[list[AnyMessage], add_messages]
    attempts: Annotated[int, operator.add]
