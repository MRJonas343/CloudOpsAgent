from fastapi.testclient import TestClient

BASELINE = {
    "service": "app",
    "status": "ok",
    "cpu_percent": 12.0,
    "memory_percent": 34.0,
    "error_rate": 0.0,
    "latency_ms_p95": 42.0,
    "requests_per_second": 3.0,
}

METRIC_KEYS = {
    "service",
    "status",
    "cpu_percent",
    "memory_percent",
    "request_count",
    "error_count",
    "error_rate",
    "latency_ms_p95",
    "requests_per_second",
}


def test_metrics_baseline_exact_values(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    for key, value in BASELINE.items():
        assert body[key] == value
    assert isinstance(body["request_count"], int)
    assert isinstance(body["error_count"], int)


def test_metrics_has_exact_shape(client: TestClient) -> None:
    body = client.get("/metrics").json()

    assert set(body) == METRIC_KEYS


def test_metrics_traffic_spike_exact_values(client: TestClient) -> None:
    client.post("/simulate/traffic_spike")

    body = client.get("/metrics").json()

    assert body["service"] == "app"
    assert body["status"] == "ok"
    assert body["cpu_percent"] == 78.0
    assert body["memory_percent"] == 34.0
    assert body["latency_ms_p95"] == 180.0
    assert body["requests_per_second"] == 30.0
    assert body["error_rate"] == 0.0


def test_metrics_unhealthy_exact_values(client: TestClient) -> None:
    client.post("/simulate/unhealthy_application")

    body = client.get("/metrics").json()

    assert body["status"] == "unhealthy"
    assert body["error_rate"] == 0.5
    assert body["cpu_percent"] == 12.0
    assert body["memory_percent"] == 34.0
    assert body["latency_ms_p95"] == 42.0
    assert body["requests_per_second"] == 3.0


def test_metrics_returns_to_baseline_after_reset(client: TestClient) -> None:
    client.post("/simulate/traffic_spike")
    client.post("/simulate/reset")

    body = client.get("/metrics").json()

    for key, value in BASELINE.items():
        assert body[key] == value
