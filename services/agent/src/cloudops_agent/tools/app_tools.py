"""Read-only tools that query the simulated application over its HTTP API.

Every tool here is ``read_only=True`` with ``risk_level=RiskLevel.read`` (0). The
base URL and timeout come from :class:`cloudops_agent.config.Settings`, so the
same tools work on the host (``http://localhost:8001``) and inside Compose
(``http://app:8001``). Returned shapes mirror the app responses; only the health
tool adds derived fields (``ok`` and ``latency_ms``).
"""

from __future__ import annotations

from functools import partial
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from cloudops_agent.config import Settings
from cloudops_agent.models import RiskLevel
from cloudops_agent.tools.base import Tool, ToolSpec

#: A response code at or above this value means the app is not reporting healthy.
ERROR_STATUS_THRESHOLD = 400

#: Default number of log entries a read tool asks for.
DEFAULT_LOG_LIMIT = 20


class LogQuery(BaseModel):
    """Validated input for the log and error read tools."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LOG_LIMIT, ge=1)


def _client(base_url: str, timeout: float) -> httpx.Client:
    """Build a synchronous client scoped to one tool call."""
    return httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)


def _health(base_url: str, timeout: float) -> dict[str, Any]:
    """Read ``GET /health``.

    A 503 is reported as an unhealthy result, not raised, so callers always get
    the app's real status.
    """
    started = perf_counter()
    with _client(base_url, timeout) as client:
        response = client.get("/health")
    latency_ms = round((perf_counter() - started) * 1000, 2)
    payload = response.json()
    status = str(payload.get("status", "unknown"))
    return {
        "service": str(payload.get("service", "app")),
        "status": status,
        "ok": response.status_code < ERROR_STATUS_THRESHOLD and status == "ok",
        "status_code": response.status_code,
        "latency_ms": latency_ms,
    }


def _metrics(base_url: str, timeout: float) -> dict[str, Any]:
    """Read the deterministic ``GET /metrics`` snapshot verbatim."""
    with _client(base_url, timeout) as client:
        response = client.get("/metrics")
    response.raise_for_status()
    return response.json()


def _logs(base_url: str, timeout: float, limit: int) -> dict[str, Any]:
    """Read the most recent consultable log entries from ``GET /logs``."""
    with _client(base_url, timeout) as client:
        response = client.get("/logs", params={"limit": limit})
    response.raise_for_status()
    return response.json()


def _errors(base_url: str, timeout: float, limit: int) -> dict[str, Any]:
    """Read only the error-level log entries from ``GET /errors``."""
    with _client(base_url, timeout) as client:
        response = client.get("/errors", params={"limit": limit})
    response.raise_for_status()
    return response.json()


def _simulation_status(base_url: str, timeout: float) -> dict[str, Any]:
    """Read the active fault and remaining seconds from ``GET /simulate/status``."""
    with _client(base_url, timeout) as client:
        response = client.get("/simulate/status")
    response.raise_for_status()
    return response.json()


def build_app_tools(settings: Settings | None = None) -> tuple[Tool, ...]:
    """Build the read-only tools that read the simulated app's real HTTP API."""
    effective = settings or Settings()
    base_url = effective.app_base_url
    timeout = effective.app_request_timeout_seconds

    def spec(
        name: str,
        description: str,
        *,
        input_model: type[BaseModel] | None = None,
    ) -> ToolSpec:
        return ToolSpec(
            name=name,
            description=description,
            read_only=True,
            risk_level=RiskLevel.read,
            timeout_seconds=timeout,
            input_model=input_model,
        )

    return (
        Tool(
            spec=spec(
                "get_app_health",
                "Read the simulated app's GET /health: status, whether it is ok, "
                "the HTTP status code, and the round-trip latency in milliseconds.",
            ),
            run=partial(_health, base_url, timeout),
        ),
        Tool(
            spec=spec(
                "get_app_metrics",
                "Read the simulated app's deterministic GET /metrics snapshot "
                "(cpu, memory, latency, error rate, requests per second, replicas).",
            ),
            run=partial(_metrics, base_url, timeout),
        ),
        Tool(
            spec=spec(
                "get_app_logs",
                "Read the most recent consultable log entries from GET /logs, "
                "newest first.",
                input_model=LogQuery,
            ),
            run=partial(_logs, base_url, timeout),
        ),
        Tool(
            spec=spec(
                "get_recent_errors",
                "Read only the error-level log entries from GET /errors, newest first.",
                input_model=LogQuery,
            ),
            run=partial(_errors, base_url, timeout),
        ),
        Tool(
            spec=spec(
                "get_simulation_status",
                "Read GET /simulate/status: the active fault mode, whether "
                "simulation is enabled, and the remaining seconds.",
            ),
            run=partial(_simulation_status, base_url, timeout),
        ),
    )
