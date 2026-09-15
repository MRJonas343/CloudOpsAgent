"""Incident intake, retrieval, reporting, and approval endpoints.

``POST /incidents`` accepts a typed payload, stores it through the shared
``IncidentStore`` (which assigns the sequential ``INC-####`` id), and returns
the stored incident. ``GET /incidents/{incident_id}`` returns the current
stored state or a ``404``. ``POST /incidents/{incident_id}/approve`` and
``.../reject`` resume a paused run with the operator's decision and are refused
unless that run is actually awaiting approval. The stores are read from
``request.app.state`` so they can be injected via ``create_app(...)``.

``GET /incidents`` is the dashboard's filtered, newest-first list, and
``GET /incidents/{incident_id}/report`` is the full case file assembled from
both stores (ADR-008). Both reads are additive: the endpoints above keep their
original request and response contracts, and neither read mutates state, so they
are safe to poll as the fallback when the SSE stream is unavailable.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator

from cloudops_agent.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    Observation,
)
from cloudops_agent.models.run import RunRecord, remaining_seconds
from cloudops_agent.services.incident_store import IncidentStore
from cloudops_agent.services.run_service import RunService
from cloudops_agent.services.run_store import RunStore

router = APIRouter(prefix="/incidents", tags=["incidents"])


class IncidentCreate(BaseModel):
    """Request body for ``POST /incidents``.

    ``detected_at`` defaults to the current UTC time and ``correlation_id`` to a
    generated hex id when omitted.
    """

    service: str = Field(min_length=1)
    type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.detected
    detected_at: datetime | None = None
    observations: list[Observation] = Field(default_factory=list)
    source: str = "api"
    correlation_id: str | None = None

    @model_validator(mode="after")
    def _fill_defaults(self) -> "IncidentCreate":
        if self.detected_at is None:
            self.detected_at = datetime.now(UTC)
        if self.correlation_id is None:
            self.correlation_id = uuid4().hex
        return self


def get_incident_store(request: Request) -> IncidentStore:
    """Dependency returning the process-wide incident store."""
    return request.app.state.incident_store  # type: ignore[no-any-return]


StoreDep = Annotated[IncidentStore, Depends(get_incident_store)]


def get_run_store(request: Request) -> RunStore:
    """Dependency returning the process-wide run store (read-only here)."""
    return request.app.state.run_store  # type: ignore[no-any-return]


RunStoreDep = Annotated[RunStore, Depends(get_run_store)]


@router.post("", response_model=Incident, status_code=status.HTTP_201_CREATED)
async def create_incident(body: IncidentCreate, store: StoreDep) -> Incident:
    """Store a new incident and return it with its assigned sequential id."""
    incident = Incident(
        incident_id="",
        service=body.service,
        type=body.type,
        severity=body.severity,
        status=body.status,
        detected_at=body.detected_at,
        observations=body.observations,
        source=body.source,
        correlation_id=body.correlation_id,
    )
    return store.add(incident)


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str, store: StoreDep) -> Incident:
    """Return the stored incident or ``404`` when the id is unknown."""
    incident = store.get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident '{incident_id}' not found",
        )
    return incident


@router.get("", response_model=list[Incident])
async def list_incidents(
    store: StoreDep,
    incident_status: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    incident_type: Annotated[IncidentType | None, Query(alias="type")] = None,
) -> list[Incident]:
    """Return stored incidents newest-first, optionally filtered.

    ``status`` and ``type`` are typed as the lifecycle enums, so a value outside
    the allowed domain is refused by request validation with a ``422`` before
    this handler runs. Both filters are applied when both are present; an absent
    filter means "any". The read is a pure copy of stored state, so repeated
    polls return the same data until a run actually changes it.
    """
    incidents = store.list()
    if incident_status is not None:
        incidents = [incident for incident in incidents if incident.status is incident_status]
    if incident_type is not None:
        incidents = [incident for incident in incidents if incident.type is incident_type]
    return _newest_first(incidents)


def _newest_first(incidents: list[Incident]) -> list[Incident]:
    """Order ``incidents`` newest-first by detection time.

    The store hands back insertion order, so reversing before a stable sort keeps
    the most recently stored incident first when two share a ``detected_at``.
    """
    return sorted(reversed(incidents), key=lambda incident: incident.detected_at, reverse=True)


def get_run_service(request: Request) -> RunService:
    """Dependency returning the process-wide run service."""
    return request.app.state.run_service  # type: ignore[no-any-return]


RunServiceDep = Annotated[RunService, Depends(get_run_service)]


class DecisionBody(BaseModel):
    """Request body for an operator decision on a paused run."""

    approver: str = Field(min_length=1)
    reason: str | None = None


async def _decide(
    incident_id: str,
    body: DecisionBody,
    *,
    store: IncidentStore,
    runs: RunService,
    approved: bool,
) -> RunRecord:
    """Apply a decision to a paused run, refusing anything that is not waiting.

    An unknown incident is a ``404``; a known incident whose run is not
    ``awaiting_approval`` is a ``409``. Nothing is resumed in either case, and a
    decision that loses the race to the approval timeout is also refused rather
    than applied to a run that already ended.
    """
    if store.get(incident_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident '{incident_id}' not found",
        )
    record = await runs.decide(
        incident_id,
        approved=approved,
        approver=body.approver,
        reason=body.reason,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"incident '{incident_id}' is not awaiting approval",
        )
    return record


@router.post("/{incident_id}/approve", response_model=RunRecord)
async def approve_incident(
    incident_id: str,
    body: DecisionBody,
    store: StoreDep,
    runs: RunServiceDep,
) -> RunRecord:
    """Approve a paused run and return it after the resumed run settles."""
    return await _decide(incident_id, body, store=store, runs=runs, approved=True)


@router.post("/{incident_id}/reject", response_model=RunRecord)
async def reject_incident(
    incident_id: str,
    body: DecisionBody,
    store: StoreDep,
    runs: RunServiceDep,
) -> RunRecord:
    """Reject a paused run and return it after the resumed run ends."""
    return await _decide(incident_id, body, store=store, runs=runs, approved=False)


class ApprovalView(BaseModel):
    """The live approval countdown for a paused run.

    ``remaining_seconds`` is derived from the stored ``deadline`` on every read
    rather than persisted, so two polls of an ``awaiting_approval`` incident
    return strictly decreasing values. The operator's actual decision lives on
    ``run.approval``; this view only exists while a decision is still pending.
    """

    deadline: datetime
    remaining_seconds: int


class IncidentReport(BaseModel):
    """The full case file for one incident (ADR-008).

    ``incident`` is the lifecycle record the list endpoints expose and ``run`` is
    the detail the run service wrote: timeline, observations, hypotheses,
    diagnosis, plan, approval, execution result, verification, and the
    post-mortem ``summary``. ``run`` is ``None`` for an incident whose run was
    never triggered, and it is present but partially filled while a run is still
    in flight — ``summary`` stays ``None`` until ``close_incident`` produces it.
    """

    incident: Incident | None = None
    run: RunRecord | None = None
    approval: ApprovalView | None = None


def _approval_view(record: RunRecord | None) -> ApprovalView | None:
    """Return the pending countdown for a paused record, or ``None`` otherwise.

    The deadline is cleared as soon as a decision is claimed, so a non-``None``
    deadline is exactly the "still waiting on an operator" condition.
    """
    deadline = record.approval_deadline if record is not None else None
    if deadline is None:
        return None
    seconds = remaining_seconds(deadline)
    if seconds is None:  # unreachable: the helper returns an int for a set deadline
        return None
    return ApprovalView(deadline=deadline, remaining_seconds=seconds)


@router.get("/{incident_id}/report", response_model=IncidentReport)
async def get_incident_report(
    incident_id: str,
    store: StoreDep,
    runs: RunStoreDep,
) -> IncidentReport:
    """Return the full case file, partial while the run is still in flight.

    A ``404`` requires *both* stores to lack the id: an incident the run service
    never picked up still reports successfully with ``run: null``, and a run
    whose incident is missing still reports its detail. Nothing here mutates
    state, so the endpoint is safe to poll at short intervals.
    """
    incident = store.get(incident_id)
    record = runs.get(incident_id)
    if incident is None and record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident '{incident_id}' not found",
        )
    return IncidentReport(
        incident=incident,
        run=record,
        approval=_approval_view(record),
    )
