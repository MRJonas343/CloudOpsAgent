from datetime import datetime

from cloudops_agent.config import Settings
from cloudops_agent.models import IncidentSeverity, IncidentType
from cloudops_agent.monitoring.app_client import HealthResult, MetricSnapshot
from cloudops_agent.monitoring.detectors import detect_incident


def test_healthy_baseline_produces_no_incident(
    settings: Settings,
    now: datetime,
    baseline_health: HealthResult,
    baseline_metrics: MetricSnapshot,
) -> None:
    assert detect_incident(baseline_health, baseline_metrics, settings, now) is None


def test_unhealthy_health_detects_unhealthy_application(
    settings: Settings,
    now: datetime,
    unhealthy_health: HealthResult,
    unhealthy_metrics: MetricSnapshot,
) -> None:
    incident = detect_incident(unhealthy_health, unhealthy_metrics, settings, now)

    assert incident is not None
    assert incident.type is IncidentType.unhealthy_application
    assert incident.severity is IncidentSeverity.high
    assert incident.status.value == "detected"
    assert incident.service == "app"
    assert incident.source == "monitoring"
    assert incident.detected_at == now
    assert incident.correlation_id


def test_unhealthy_metrics_status_alone_detects_incident(
    settings: Settings,
    now: datetime,
    baseline_health: HealthResult,
    unhealthy_metrics: MetricSnapshot,
) -> None:
    incident = detect_incident(baseline_health, unhealthy_metrics, settings, now)

    assert incident is not None
    assert incident.type is IncidentType.unhealthy_application


def test_unhealthy_observations_include_health_and_error_rate(
    settings: Settings,
    now: datetime,
    unhealthy_health: HealthResult,
    unhealthy_metrics: MetricSnapshot,
) -> None:
    incident = detect_incident(unhealthy_health, unhealthy_metrics, settings, now)
    assert incident is not None

    by_metric = {observation.metric: observation for observation in incident.observations}

    assert by_metric["health_status"].source == "health"
    assert "unhealthy" in by_metric["health_status"].summary
    assert by_metric["health_status"].value is None
    assert by_metric["error_rate"].value == 0.5
    for observation in incident.observations:
        assert observation.observed_at == now


def test_traffic_spike_detects_medium_incident(
    settings: Settings,
    now: datetime,
    baseline_health: HealthResult,
    traffic_metrics: MetricSnapshot,
) -> None:
    incident = detect_incident(baseline_health, traffic_metrics, settings, now)

    assert incident is not None
    assert incident.type is IncidentType.traffic_spike
    assert incident.severity is IncidentSeverity.medium


def test_traffic_observations_include_rps_threshold_and_latency(
    settings: Settings,
    now: datetime,
    baseline_health: HealthResult,
    traffic_metrics: MetricSnapshot,
) -> None:
    incident = detect_incident(baseline_health, traffic_metrics, settings, now)
    assert incident is not None

    by_metric = {observation.metric: observation for observation in incident.observations}

    assert by_metric["requests_per_second"].value == 30.0
    assert by_metric["requests_per_second"].threshold == 20.0
    assert by_metric["latency_ms_p95"].value == 180.0


def test_unhealthy_takes_precedence_over_traffic_spike(
    settings: Settings,
    now: datetime,
    unhealthy_health: HealthResult,
    traffic_metrics: MetricSnapshot,
) -> None:
    incident = detect_incident(unhealthy_health, traffic_metrics, settings, now)

    assert incident is not None
    assert incident.type is IncidentType.unhealthy_application
    assert incident.severity is IncidentSeverity.high


def test_traffic_below_configured_threshold_is_healthy(
    now: datetime,
    baseline_health: HealthResult,
    traffic_metrics: MetricSnapshot,
) -> None:
    settings = Settings(traffic_spike_rps_threshold=50.0)

    assert detect_incident(baseline_health, traffic_metrics, settings, now) is None
