from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "app"}


def test_health_unhealthy_during_fault(client: TestClient) -> None:
    assert client.post("/simulate/unhealthy_application").status_code == 200

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "service": "app"}


def test_health_recovers_after_reset(client: TestClient) -> None:
    client.post("/simulate/unhealthy_application")
    client.post("/simulate/reset")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "app"}
