"""Typed incident contract: incident, observation, and lifecycle enums.

The payload shape matches the documented contract in ``docs/PROJECT_CONTEXT.md``
so downstream phases can rely on stable keys and values.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class IncidentType(StrEnum):
    """Incident categories. Only the first two have MVP detectors."""

    unhealthy_application = "unhealthy_application"
    traffic_spike = "traffic_spike"
    high_cpu = "high_cpu"
    memory_pressure = "memory_pressure"
    high_error_rate = "high_error_rate"


class IncidentSeverity(StrEnum):
    """Incident severity levels."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatus(StrEnum):
    """Lifecycle states an incident moves through."""

    detected = "detected"
    investigating = "investigating"
    diagnosed = "diagnosed"
    planned = "planned"
    awaiting_approval = "awaiting_approval"
    remediating = "remediating"
    verifying = "verifying"
    resolved = "resolved"
    failed = "failed"


class Observation(BaseModel):
    """A single piece of deterministic evidence captured by the monitor."""

    source: str
    summary: str
    metric: str
    value: float | None = None
    threshold: float | None = None
    observed_at: datetime


class Incident(BaseModel):
    """The monitoring-produced incident payload."""

    incident_id: str
    service: str
    type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.detected
    detected_at: datetime
    observations: list[Observation] = Field(default_factory=list)
    source: str = "monitoring"
    correlation_id: str
