"""Per-incident run record: the lifecycle source of truth (ADR-008).

``RunRecord`` is keyed by ``incident_id`` and lives in memory. Its ``status``
mirrors :class:`~cloudops_agent.models.incident.IncidentStatus`, so a record can
be written through to the stored incident without translating values.

The approval and verification payloads reuse the graph's own models
(:class:`~cloudops_agent.graph.state.ApprovalDecision`,
:class:`~cloudops_agent.graph.state.VerificationResult`), so a run never
re-validates what the graph already produced.

Because of that import, this module is deliberately **not** re-exported from
``cloudops_agent.models``: ``graph.state`` imports ``cloudops_agent.models``
itself, so pulling this module from that package's ``__init__`` would close the
import cycle and break any graph-first import (for example the LangGraph
loader). Import it directly instead:

    from cloudops_agent.models.run import RunRecord, RunOutcome
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field

from cloudops_agent.graph.state import ApprovalDecision, VerificationResult
from cloudops_agent.models.incident import IncidentStatus, Observation
from cloudops_agent.models.remediation import (
    Hypothesis,
    RemediationPlan,
    RemediationResult,
)


def remaining_seconds(deadline: datetime | None, *, now: datetime | None = None) -> int | None:
    """Return the whole seconds left before ``deadline``, or ``None`` when unset.

    The value is clamped at zero: an expired deadline reads ``0`` rather than a
    negative count, so a client rendering a countdown never shows time running
    backwards. This is the single derivation shared by the approval model and the
    event bus.
    """
    if deadline is None:
        return None
    moment = now or datetime.now(UTC)
    return max(0, int((deadline - moment).total_seconds()))


class RunOutcome(StrEnum):
    """Terminal outcome of a run, independent of its lifecycle status."""

    resolved = "resolved"
    verification_failed = "verification_failed"
    rejected = "rejected"
    timed_out = "timed_out"
    error = "error"
    interrupted_restart = "interrupted_restart"


class TimelineEvent(BaseModel):
    """One observable step in a run's phase progression.

    ``phase`` is the graph node that produced the step and ``status`` is the
    lifecycle status the run held at that moment, so the timeline is a faithful
    replay of what the runner actually applied.
    """

    phase: str
    status: IncidentStatus
    at: datetime


class ApprovalRequest(BaseModel):
    """The pending operator decision surfaced while a run is paused.

    It mirrors the payload ``human_approval`` hands to ``interrupt()`` (see
    ``design.md`` *Interfaces / Contracts*), so a paused run can be presented to
    an operator without re-running the node.

    ``remaining_seconds`` is derived from ``deadline`` rather than stored, so a
    client that reads the model twice sees the countdown actually move; the
    deadline itself is the only thing the runner has to arm.
    """

    incident_id: str
    action: str
    risk_level: int
    parameters: dict[str, object] = Field(default_factory=dict)
    requested_at: datetime
    deadline: datetime | None = None

    @computed_field
    @property
    def remaining_seconds(self) -> int | None:
        """Seconds left before the approval deadline, or ``None`` when unset."""
        return remaining_seconds(self.deadline)


class RunRecord(BaseModel):
    """Everything known about one incident run, keyed by ``incident_id``."""

    incident_id: str
    status: IncidentStatus
    phase: str
    outcome: RunOutcome | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    diagnosis: str | None = None
    plan: RemediationPlan | None = None
    approval: ApprovalDecision | None = None
    approval_request: ApprovalRequest | None = None
    execution_result: RemediationResult | None = None
    verification: VerificationResult | None = None
    summary: str | None = None
    attempts: int = 0
    approval_deadline: datetime | None = None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
