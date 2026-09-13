"""HTTP client the monitoring module uses to poll the simulated application."""

import httpx
from pydantic import BaseModel


class HealthResult(BaseModel):
    """Outcome of a ``GET /health`` poll; ``ok`` is false for non-healthy states."""

    status: str
    ok: bool
    status_code: int


class MetricSnapshot(BaseModel):
    """Typed view of the app's ``GET /metrics`` payload."""

    service: str
    status: str
    cpu_percent: float
    memory_percent: float
    request_count: int
    error_count: int
    error_rate: float
    latency_ms_p95: float
    requests_per_second: float


class AppClient:
    """Async client for the app's health and metrics endpoints.

    Inject ``client`` (for example an ``httpx.AsyncClient`` backed by
    ``httpx.MockTransport``) to run without real network access.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def check_health(self) -> HealthResult:
        """Poll ``/health``. A 503 is returned as an unhealthy result, not raised."""
        response = await self._client.get(f"{self._base_url}/health")
        payload = response.json()
        status = str(payload.get("status", "unknown"))
        return HealthResult(
            status=status,
            ok=response.status_code < 400 and status == "ok",
            status_code=response.status_code,
        )

    async def collect_metrics(self) -> MetricSnapshot:
        """Poll ``/metrics`` and parse the deterministic metric snapshot."""
        response = await self._client.get(f"{self._base_url}/metrics")
        response.raise_for_status()
        return MetricSnapshot.model_validate(response.json())

    async def aclose(self) -> None:
        """Close the underlying client only when this instance owns it."""
        if self._owns_client:
            await self._client.aclose()
