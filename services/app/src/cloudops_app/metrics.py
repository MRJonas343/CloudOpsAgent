"""Deterministic metric computation from baseline + active mode + counters + replicas.

Baseline values (and the traffic-spike values at the baseline replica count) are
exact so monitors and manual verification can rely on them. Replica scaling is a
simple deterministic ratio: CPU and latency fall as ``baseline/replicas`` while
achievable throughput rises as ``replicas/baseline``.
"""

from typing import TypedDict

from cloudops_app.simulation import FaultMode

SERVICE_NAME = "app"


class MetricPayload(TypedDict):
    """Typed shape of the metric snapshot returned by :func:`compute_metrics`."""

    service: str
    status: str
    cpu_percent: float
    memory_percent: float
    request_count: int
    error_count: int
    error_rate: float
    latency_ms_p95: float
    requests_per_second: float
    replicas: int


BASELINE_CPU_PERCENT = 12.0
BASELINE_MEMORY_PERCENT = 34.0
BASELINE_ERROR_RATE = 0.0
BASELINE_LATENCY_MS_P95 = 42.0
BASELINE_REQUESTS_PER_SECOND = 3.0
DEFAULT_BASELINE_REPLICAS = 2

TRAFFIC_SPIKE_REQUESTS_PER_SECOND = 30.0
TRAFFIC_SPIKE_LATENCY_MS_P95 = 180.0
TRAFFIC_SPIKE_CPU_PERCENT = 78.0

UNHEALTHY_ERROR_RATE = 0.5


def _scaled(value: float, replicas: int, baseline_replicas: int) -> float:
    """Scale ``value`` by ``baseline/replicas`` (no-op at the baseline count)."""
    baseline = max(1, baseline_replicas)
    current = max(1, replicas)
    return round(value * baseline / current, 1)


def _capacity(value: float, replicas: int, baseline_replicas: int) -> float:
    """Scale ``value`` by ``replicas/baseline`` (no-op at the baseline count)."""
    baseline = max(1, baseline_replicas)
    current = max(1, replicas)
    return round(value * current / baseline, 1)


def compute_metrics(
    mode: FaultMode | None,
    request_count: int,
    error_count: int,
    *,
    replicas: int = DEFAULT_BASELINE_REPLICAS,
    baseline_replicas: int = DEFAULT_BASELINE_REPLICAS,
) -> MetricPayload:
    """Return a deterministic metric snapshot for the given fault mode and replica count.

    At the baseline replica count the no-fault values are exact
    (``12.0/34.0/0.0/42.0/3.0``) and the traffic-spike values are exact
    (``78.0/180.0/30.0``). Live counters are reported verbatim; they never
    perturb the deterministic fields.
    """
    status = "ok"
    cpu_percent = _scaled(BASELINE_CPU_PERCENT, replicas, baseline_replicas)
    memory_percent = BASELINE_MEMORY_PERCENT
    error_rate = BASELINE_ERROR_RATE
    latency_ms_p95 = _scaled(BASELINE_LATENCY_MS_P95, replicas, baseline_replicas)
    requests_per_second = _capacity(BASELINE_REQUESTS_PER_SECOND, replicas, baseline_replicas)

    if mode is FaultMode.traffic_spike:
        cpu_percent = _scaled(TRAFFIC_SPIKE_CPU_PERCENT, replicas, baseline_replicas)
        latency_ms_p95 = _scaled(TRAFFIC_SPIKE_LATENCY_MS_P95, replicas, baseline_replicas)
        requests_per_second = _capacity(
            TRAFFIC_SPIKE_REQUESTS_PER_SECOND, replicas, baseline_replicas
        )
    elif mode is FaultMode.unhealthy_application:
        status = "unhealthy"
        error_rate = UNHEALTHY_ERROR_RATE

    return {
        "service": SERVICE_NAME,
        "status": status,
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "request_count": request_count,
        "error_count": error_count,
        "error_rate": error_rate,
        "latency_ms_p95": latency_ms_p95,
        "requests_per_second": requests_per_second,
        "replicas": replicas,
    }
