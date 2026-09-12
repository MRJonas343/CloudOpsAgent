"""API contract tests for ``POST /incidents`` and ``GET /incidents/{id}``."""

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from cloudops_agent.config import Settings
from cloudops_agent.main import create_app
from cloudops_agent.monitoring.app_client import AppClient
from cloudops_agent.monitoring.monitor import Monitor
from cloudops_agent.services.incident_store import IncidentStore

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

VALID_PAYLOAD = {
    "service": "app",
    "type": "unhealthy_application",
    "severity": "high",
}

UNHEALTHY_METRICS = {
    "service": "app",
    "status": "unhealthy",
    "cpu_percent": 12.0,
    "memory_percent": 34.0,
    "request_count": 0,
    "error_count": 0,
    "error_rate": 0.5,
    "latency_ms_p95": 42.0,
    "requests_per_second": 3.0,
}


class StubClient:
    """Minimal stand-in for AppClient that never touches the network."""

    async def aclose(self) -> None:
        return None


def make_client(store: IncidentStore) -> TestClient:
    app = create_app(
        Settings(monitoring_enabled=False),
        client=StubClient(),  # type: ignore[arg-type]
        store=store,
    )
    return TestClient(app)


@pytest.fixture
def store() -> IncidentStore:
    return IncidentStore()


@pytest.fixture
def client(store: IncidentStore) -> Iterator[TestClient]:
    with make_client(store) as test_client:
        yield test_client


def test_create_incident_assigns_id_and_defaults(client: TestClient) -> None:
    response = client.post("/incidents", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["incident_id"] == "INC-0001"
    assert body["status"] == "detected"
    assert body["type"] == "unhealthy_application"
    assert body["severity"] == "high"
    assert body["source"] == "api"
    assert body["observations"] == []
    assert body["correlation_id"]
    assert body["detected_at"]


def test_create_incident_preserves_explicit_fields(client: TestClient) -> None:
    payload = {
        "service": "orders",
        "type": "traffic_spike",
        "severity": "medium",
        "status": "investigating",
        "detected_at": "2026-01-01T12:00:00Z",
        "source": "cli",
        "correlation_id": "abc123",
        "observations": [
            {
                "source": "metrics",
                "summary": "requests_per_second is 30.0 (threshold 20.0)",
                "metric": "requests_per_second",
                "value": 30.0,
                "threshold": 20.0,
                "observed_at": "2026-01-01T12:00:00Z",
            }
        ],
    }

    response = client.post("/incidents", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["incident_id"] == "INC-0001"
    assert body["service"] == "orders"
    assert body["type"] == "traffic_spike"
    assert body["severity"] == "medium"
    assert body["status"] == "investigating"
    assert body["source"] == "cli"
    assert body["correlation_id"] == "abc123"
    assert body["detected_at"].startswith("2026-01-01T12:00:00")
    assert body["observations"][0]["metric"] == "requests_per_second"
    assert body["observations"][0]["value"] == 30.0


def test_get_incident_round_trip(client: TestClient, store: IncidentStore) -> None:
    created = client.post("/incidents", json=VALID_PAYLOAD).json()

    response = client.get(f"/incidents/{created['incident_id']}")

    assert response.status_code == 200
    assert response.json() == created
    assert store.get("INC-0001") is not None


def test_get_unknown_incident_returns_404(client: TestClient) -> None:
    response = client.get("/incidents/UNKNOWN")

    assert response.status_code == 404
    assert "UNKNOWN" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"service": "app", "type": "not_a_real_type", "severity": "high"},
        {"service": "app", "type": "traffic_spike", "severity": "extreme"},
        {"service": "app", "type": "traffic_spike", "severity": "high", "status": "nope"},
        {"type": "traffic_spike", "severity": "high"},
        {"service": "", "type": "traffic_spike", "severity": "high"},
    ],
)
def test_invalid_payload_returns_422(client: TestClient, payload: dict[str, object]) -> None:
    response = client.post("/incidents", json=payload)

    assert response.status_code == 422


def test_two_posts_get_stable_sequential_ids(client: TestClient) -> None:
    first = client.post("/incidents", json=VALID_PAYLOAD).json()
    second = client.post("/incidents", json=VALID_PAYLOAD).json()

    assert first["incident_id"] == "INC-0001"
    assert second["incident_id"] == "INC-0002"


def _unhealthy_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(503, json={"status": "unhealthy", "service": "app"})
    if request.url.path == "/metrics":
        return httpx.Response(200, json=UNHEALTHY_METRICS)
    return httpx.Response(404)


async def test_monitor_stored_incident_is_retrievable(store: IncidentStore) -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(_unhealthy_handler))
    app_client = AppClient("http://app.test", client=http)
    monitor = Monitor(
        app_client,
        store,
        Settings(monitoring_enabled=False),
        clock=lambda: NOW,
    )
    try:
        stored = await monitor.poll_once()
    finally:
        await http.aclose()
    assert stored is not None

    with make_client(store) as client:
        response = client.get(f"/incidents/{stored.incident_id}")

    assert response.status_code == 200
    assert response.json()["type"] == "unhealthy_application"
    assert response.json()["source"] == "monitoring"
