from fastapi.testclient import TestClient

from tests.conftest import FakeClock


def test_activate_returns_status(client: TestClient) -> None:
    response = client.post("/simulate/traffic_spike")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "enabled": True,
        "mode": "traffic_spike",
        "started_at": 1000.0,
        "expires_at": 1030.0,
        "remaining_seconds": 30.0,
        "duration_seconds": 30,
    }
    assert client.get("/simulate/status").json() == body


def test_activate_with_custom_duration(client: TestClient) -> None:
    body = client.post("/simulate/traffic_spike", json={"duration_seconds": 12}).json()

    assert body["duration_seconds"] == 12
    assert body["remaining_seconds"] == 12.0


def test_duration_clamped_to_max(client: TestClient) -> None:
    body = client.post("/simulate/traffic_spike", json={"duration_seconds": 9999}).json()

    assert body["duration_seconds"] == 300
    assert body["remaining_seconds"] == 300.0


def test_duration_clamped_to_min(client: TestClient) -> None:
    body = client.post("/simulate/traffic_spike", json={"duration_seconds": 0}).json()

    assert body["duration_seconds"] == 1
    assert body["remaining_seconds"] == 1.0


def test_reset_clears_fault(client: TestClient) -> None:
    client.post("/simulate/unhealthy_application")

    body = client.post("/simulate/reset").json()

    assert body["mode"] is None
    assert body["started_at"] is None
    assert body["expires_at"] is None
    assert body["remaining_seconds"] is None
    assert body["duration_seconds"] is None


def test_replacing_active_mode(client: TestClient) -> None:
    client.post("/simulate/traffic_spike")

    body = client.post("/simulate/unhealthy_application").json()

    assert body["mode"] == "unhealthy_application"


def test_auto_expiry_uses_injected_clock(client: TestClient, clock: FakeClock) -> None:
    client.post("/simulate/traffic_spike", json={"duration_seconds": 5})
    assert client.get("/simulate/status").json()["mode"] == "traffic_spike"

    clock.advance(5)

    status = client.get("/simulate/status").json()
    assert status["mode"] is None
    assert status["remaining_seconds"] is None
    assert client.get("/metrics").json()["requests_per_second"] == 3.0
    assert client.get("/health").json() == {"status": "ok", "service": "app"}


def test_simulation_disabled_returns_403(disabled_client: TestClient) -> None:
    assert disabled_client.post("/simulate/traffic_spike").status_code == 403
    assert disabled_client.post("/simulate/reset").status_code == 403
    assert disabled_client.get("/simulate/status").status_code == 403


def test_disabled_does_not_break_core_endpoints(disabled_client: TestClient) -> None:
    assert disabled_client.get("/health").status_code == 200
    assert disabled_client.get("/metrics").status_code == 200
    assert disabled_client.get("/api/orders").status_code == 200


def test_unknown_mode_returns_404(client: TestClient) -> None:
    response = client.post("/simulate/high_cpu")

    assert response.status_code == 404
