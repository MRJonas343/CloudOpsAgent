from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cloudops_agent.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    Observation,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

INCIDENT_KEYS = {
    "incident_id",
    "service",
    "type",
    "severity",
    "status",
    "detected_at",
    "observations",
    "source",
    "correlation_id",
}

OBSERVATION_KEYS = {
    "source",
    "summary",
    "metric",
    "value",
    "threshold",
    "observed_at",
}


def make_observation() -> Observation:
    return Observation(
        source="metrics",
        summary="error_rate is 0.5",
        metric="error_rate",
        value=0.5,
        threshold=None,
        observed_at=NOW,
    )


def make_incident() -> Incident:
    return Incident(
        incident_id="INC-0001",
        service="app",
        type=IncidentType.unhealthy_application,
        severity=IncidentSeverity.high,
        status=IncidentStatus.detected,
        detected_at=NOW,
        observations=[make_observation()],
        source="monitoring",
        correlation_id="abc123",
    )


def test_incident_payload_shape_matches_contract() -> None:
    payload = make_incident().model_dump(mode="json")

    assert set(payload) == INCIDENT_KEYS
    assert set(payload["observations"][0]) == OBSERVATION_KEYS


def test_payload_values_serialize_as_strings() -> None:
    payload = make_incident().model_dump(mode="json")

    assert payload["type"] == "unhealthy_application"
    assert payload["severity"] == "high"
    assert payload["status"] == "detected"
    assert payload["source"] == "monitoring"


def test_status_defaults_to_detected() -> None:
    incident = Incident(
        incident_id="INC-0002",
        service="app",
        type=IncidentType.traffic_spike,
        severity=IncidentSeverity.medium,
        detected_at=NOW,
        correlation_id="abc123",
    )

    assert incident.status is IncidentStatus.detected
    assert incident.source == "monitoring"
    assert incident.observations == []


def test_enum_value_sets_are_stable() -> None:
    assert {item.value for item in IncidentType} == {
        "unhealthy_application",
        "traffic_spike",
        "high_cpu",
        "memory_pressure",
        "high_error_rate",
    }
    assert {item.value for item in IncidentSeverity} == {
        "low",
        "medium",
        "high",
        "critical",
    }
    assert {item.value for item in IncidentStatus} == {
        "detected",
        "investigating",
        "diagnosed",
        "planned",
        "awaiting_approval",
        "remediating",
        "verifying",
        "resolved",
        "failed",
    }


def test_observation_allows_null_value_and_threshold() -> None:
    observation = Observation(
        source="health",
        summary="application health status is 'unhealthy'",
        metric="health_status",
        value=None,
        threshold=None,
        observed_at=NOW,
    )

    assert observation.value is None
    assert observation.threshold is None


def test_invalid_incident_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Incident(
            incident_id="INC-0003",
            service="app",
            type="not_a_real_type",
            severity="high",
            detected_at=NOW,
            correlation_id="abc123",
        )


def test_invalid_severity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Incident(
            incident_id="INC-0004",
            service="app",
            type="traffic_spike",
            severity="extreme",
            detected_at=NOW,
            correlation_id="abc123",
        )
