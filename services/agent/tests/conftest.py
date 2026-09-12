"""Shared fixtures for the agent service test suite."""

from datetime import UTC, datetime

import pytest

from cloudops_agent.config import Settings
from cloudops_agent.monitoring.app_client import HealthResult, MetricSnapshot

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings() -> Settings:
    return Settings(monitoring_enabled=False, poll_interval_seconds=1)


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def baseline_health() -> HealthResult:
    return HealthResult(status="ok", ok=True, status_code=200)


@pytest.fixture
def baseline_metrics() -> MetricSnapshot:
    return MetricSnapshot(
        service="app",
        status="ok",
        cpu_percent=12.0,
        memory_percent=34.0,
        request_count=0,
        error_count=0,
        error_rate=0.0,
        latency_ms_p95=42.0,
        requests_per_second=3.0,
    )


@pytest.fixture
def unhealthy_health() -> HealthResult:
    return HealthResult(status="unhealthy", ok=False, status_code=503)


@pytest.fixture
def unhealthy_metrics() -> MetricSnapshot:
    return MetricSnapshot(
        service="app",
        status="unhealthy",
        cpu_percent=12.0,
        memory_percent=34.0,
        request_count=0,
        error_count=0,
        error_rate=0.5,
        latency_ms_p95=42.0,
        requests_per_second=3.0,
    )


@pytest.fixture
def traffic_metrics() -> MetricSnapshot:
    return MetricSnapshot(
        service="app",
        status="ok",
        cpu_percent=78.0,
        memory_percent=34.0,
        request_count=0,
        error_count=0,
        error_rate=0.0,
        latency_ms_p95=180.0,
        requests_per_second=30.0,
    )
