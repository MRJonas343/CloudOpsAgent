"""Deterministic MVP incident detectors.

Two detectors are implemented: ``unhealthy_application`` and ``traffic_spike``.
The remaining incident types exist as enum values but have no MVP detector.
"""

from datetime import datetime
from uuid import uuid4

from cloudops_agent.config import Settings
from cloudops_agent.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    Observation,
)
from cloudops_agent.monitoring.app_client import HealthResult, MetricSnapshot

_INCIDENT_SOURCE = "monitoring"


def detect_incident(
    health: HealthResult,
    metrics: MetricSnapshot,
    settings: Settings,
    now: datetime,
) -> Incident | None:
    """Return the MVP incident implied by the evidence, or ``None`` if healthy.

    The unhealthy condition takes precedence over a traffic spike. The returned
    incident has an empty ``incident_id``; the store assigns the final ID.
    """
    if not health.ok or metrics.status == "unhealthy":
        return _unhealthy_incident(health, metrics, now)

    if metrics.requests_per_second >= settings.traffic_spike_rps_threshold:
        return _traffic_spike_incident(metrics, settings, now)

    return None


def _unhealthy_incident(health: HealthResult, metrics: MetricSnapshot, now: datetime) -> Incident:
    observations = [
        Observation(
            source="health",
            summary=f"application health status is '{health.status}'",
            metric="health_status",
            value=None,
            threshold=None,
            observed_at=now,
        ),
        Observation(
            source="metrics",
            summary=f"error_rate is {metrics.error_rate}",
            metric="error_rate",
            value=metrics.error_rate,
            threshold=None,
            observed_at=now,
        ),
    ]
    return _build_incident(
        incident_type=IncidentType.unhealthy_application,
        severity=IncidentSeverity.high,
        service=metrics.service,
        now=now,
        observations=observations,
    )


def _traffic_spike_incident(
    metrics: MetricSnapshot, settings: Settings, now: datetime
) -> Incident:
    threshold = settings.traffic_spike_rps_threshold
    observations = [
        Observation(
            source="metrics",
            summary=(
                f"requests_per_second is {metrics.requests_per_second} "
                f"(threshold {threshold})"
            ),
            metric="requests_per_second",
            value=metrics.requests_per_second,
            threshold=threshold,
            observed_at=now,
        ),
        Observation(
            source="metrics",
            summary=f"latency_ms_p95 is {metrics.latency_ms_p95}",
            metric="latency_ms_p95",
            value=metrics.latency_ms_p95,
            threshold=None,
            observed_at=now,
        ),
    ]
    return _build_incident(
        incident_type=IncidentType.traffic_spike,
        severity=IncidentSeverity.medium,
        service=metrics.service,
        now=now,
        observations=observations,
    )


def _build_incident(
    *,
    incident_type: IncidentType,
    severity: IncidentSeverity,
    service: str,
    now: datetime,
    observations: list[Observation],
) -> Incident:
    return Incident(
        incident_id="",
        service=service,
        type=incident_type,
        severity=severity,
        status=IncidentStatus.detected,
        detected_at=now,
        observations=observations,
        source=_INCIDENT_SOURCE,
        correlation_id=uuid4().hex,
    )
