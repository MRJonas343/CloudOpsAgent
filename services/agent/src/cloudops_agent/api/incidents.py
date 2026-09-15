"""Incident intake, retrieval, and approval endpoints.

``POST /incidents`` accepts a typed payload, stores it through the shared
``IncidentStore`` (which assigns the sequential ``INC-####`` id), and returns
the stored incident. ``GET /incidents/{incident_id}`` returns the current
stored state or a ``404``. ``POST /incidents/{incident_id}/approve`` and
``.../reject`` resume a paused run with the operator's decision and are refused
unless that run is actually awaiting approval. The stores are read from
``request.app.state`` so they can be injected via ``create_app(...)``.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from cloudops_agent.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    Observation,
)
from cloudops_agent.models.run import RunRecord
from cloudops_agent.services.incident_store import IncidentStore
from cloudops_agent.services.run_service import RunService

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
