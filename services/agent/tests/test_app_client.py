import httpx
import pytest

from cloudops_agent.monitoring.app_client import AppClient, HealthResult

METRICS_PAYLOAD = {
    "service": "app",
    "status": "ok",
    "cpu_percent": 12.0,
    "memory_percent": 34.0,
    "request_count": 7,
    "error_count": 0,
    "error_rate": 0.0,
    "latency_ms_p95": 42.0,
    "requests_per_second": 3.0,
}


def make_client(handler: httpx.MockTransport) -> AppClient:
    http = httpx.AsyncClient(transport=handler)
    return AppClient("http://app.test", client=http)


async def test_check_health_returns_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "service": "app"})

    client = make_client(httpx.MockTransport(handler))

    result = await client.check_health()

    assert result == HealthResult(status="ok", ok=True, status_code=200)


async def test_check_health_unhealthy_does_not_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "unhealthy", "service": "app"})

    client = make_client(httpx.MockTransport(handler))

    result = await client.check_health()

    assert result.status == "unhealthy"
    assert result.ok is False
    assert result.status_code == 503


async def test_collect_metrics_parses_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=METRICS_PAYLOAD)

    client = make_client(httpx.MockTransport(handler))

    snapshot = await client.collect_metrics()

    assert snapshot.requests_per_second == 3.0
    assert snapshot.error_rate == 0.0
    assert snapshot.request_count == 7


async def test_check_health_propagates_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(httpx.MockTransport(handler))

    with pytest.raises(httpx.TransportError):
        await client.check_health()


async def test_collect_metrics_raises_on_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = make_client(httpx.MockTransport(handler))

    with pytest.raises(httpx.HTTPStatusError):
        await client.collect_metrics()


async def test_owned_client_is_closed() -> None:
    client = AppClient("http://app.test")

    await client.aclose()
