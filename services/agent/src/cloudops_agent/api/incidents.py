"""Incident intake and retrieval endpoints.

``POST /incidents`` accepts a typed payload, stores it through the shared
``IncidentStore`` (which assigns the sequential ``INC-####`` id), and returns
the stored incident. ``GET /incidents/{incident_id}`` returns the current
stored state or a ``404``. The store is read from ``request.app.state`` so it
can be injected via ``create_app(..., store=...)``.
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
from cloudops_agent.services.incident_store import IncidentStore

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
