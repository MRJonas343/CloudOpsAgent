from datetime import UTC, datetime

import httpx

from cloudops_agent.config import Settings
from cloudops_agent.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
)
from cloudops_agent.monitoring.app_client import AppClient
from cloudops_agent.monitoring.monitor import Monitor
from cloudops_agent.services.incident_store import IncidentStore

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

BASELINE = {
    "service": "app",
    "status": "ok",
    "cpu_percent": 12.0,
    "memory_percent": 34.0,
    "request_count": 0,
    "error_count": 0,
    "error_rate": 0.0,
    "latency_ms_p95": 42.0,
    "requests_per_second": 3.0,
}


def metrics_for(mode: str) -> dict[str, object]:
    payload = dict(BASELINE)
    if mode == "traffic_spike":
        payload.update(cpu_percent=78.0, latency_ms_p95=180.0, requests_per_second=30.0)
    elif mode == "unhealthy_application":
        payload.update(status="unhealthy", error_rate=0.5)
    return payload


class FakeApp:
    """Stateful mock of the app's HTTP surface driven through MockTransport."""

    def __init__(self, mode: str = "ok", *, fail: bool = False) -> None:
        self.mode = mode
        self.fail = fail

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            raise httpx.ConnectError("app unavailable", request=request)
        if request.url.path == "/health":
            if self.mode == "unhealthy_application":
                return httpx.Response(503, json={"status": "unhealthy", "service": "app"})
            return httpx.Response(200, json={"status": "ok", "service": "app"})
        if request.url.path == "/metrics":
            return httpx.Response(200, json=metrics_for(self.mode))
        return httpx.Response(404)


def build_monitor(fake: FakeApp) -> tuple[Monitor, IncidentStore, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    client = AppClient("http://app.test", client=http)
    store = IncidentStore()
    monitor = Monitor(
        client,
        store,
        Settings(monitoring_enabled=False, poll_interval_seconds=1),
        clock=lambda: NOW,
    )
    return monitor, store, http


async def test_poll_once_stores_traffic_spike_incident() -> None:
    monitor, store, http = build_monitor(FakeApp("traffic_spike"))
    try:
        stored = await monitor.poll_once()
    finally:
        await http.aclose()

    assert stored is not None
    assert stored.incident_id == "INC-0001"
    assert stored.type is IncidentType.traffic_spike
    assert stored.severity is IncidentSeverity.medium
    assert store.get("INC-0001") == stored
    assert store.list() == [stored]


async def test_poll_once_stores_unhealthy_incident() -> None:
    monitor, store, http = build_monitor(FakeApp("unhealthy_application"))
    try:
        stored = await monitor.poll_once()
    finally:
        await http.aclose()

    assert stored is not None
    assert stored.type is IncidentType.unhealthy_application
    assert stored.severity is IncidentSeverity.high


async def test_second_poll_does_not_duplicate_active_condition() -> None:
    monitor, store, http = build_monitor(FakeApp("traffic_spike"))
    try:
        first = await monitor.poll_once()
        second = await monitor.poll_once()
    finally:
        await http.aclose()

    assert first is not None
    assert second is None
    assert len(store.list()) == 1


async def test_healthy_poll_stores_nothing() -> None:
    monitor, store, http = build_monitor(FakeApp("ok"))
    try:
        result = await monitor.poll_once()
    finally:
        await http.aclose()

    assert result is None
    assert store.list() == []


async def test_transport_error_skips_without_incident() -> None:
    monitor, store, http = build_monitor(FakeApp("traffic_spike", fail=True))
    try:
        result = await monitor.poll_once()
    finally:
        await http.aclose()

    assert result is None
    assert store.list() == []


def build_incident(status: IncidentStatus) -> Incident:
    return Incident(
        incident_id="",
        service="app",
        type=IncidentType.traffic_spike,
        severity=IncidentSeverity.medium,
        status=status,
        detected_at=NOW,
        correlation_id="corr",
    )


def test_add_assigns_sequential_ids() -> None:
    store = IncidentStore()

    first = store.add(build_incident(IncidentStatus.detected))
    second = store.add(build_incident(IncidentStatus.detected))

    assert first.incident_id == "INC-0001"
    assert second.incident_id == "INC-0002"
    assert store.get("INC-0001") == first
    assert store.get("missing") is None


def test_find_active_returns_open_incident_only() -> None:
    store = IncidentStore()
    stored = store.add(build_incident(IncidentStatus.investigating))

    assert store.find_active("app", IncidentType.traffic_spike) == stored
    assert store.find_active("other", IncidentType.traffic_spike) is None
    assert store.find_active("app", IncidentType.unhealthy_application) is None


def test_find_active_ignores_terminal_statuses() -> None:
    store = IncidentStore()
    store.add(build_incident(IncidentStatus.resolved))
    store.add(build_incident(IncidentStatus.failed))

    assert store.find_active("app", IncidentType.traffic_spike) is None
