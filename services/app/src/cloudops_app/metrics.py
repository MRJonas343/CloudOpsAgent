"""Deterministic metric computation from baseline + active mode + counters."""

from cloudops_app.simulation import FaultMode

SERVICE_NAME = "app"

BASELINE_CPU_PERCENT = 12.0
BASELINE_MEMORY_PERCENT = 34.0
BASELINE_ERROR_RATE = 0.0
BASELINE_LATENCY_MS_P95 = 42.0
BASELINE_REQUESTS_PER_SECOND = 3.0

TRAFFIC_SPIKE_REQUESTS_PER_SECOND = 30.0
TRAFFIC_SPIKE_LATENCY_MS_P95 = 180.0
TRAFFIC_SPIKE_CPU_PERCENT = 78.0

UNHEALTHY_ERROR_RATE = 0.5


def compute_metrics(
    mode: FaultMode | None,
    request_count: int,
    error_count: int,
) -> dict[str, object]:
    """Return a deterministic metric snapshot for the given fault mode.

    Baseline values are exact so tests and monitors can assert on them. Live
    counters are reported verbatim; they never perturb the deterministic fields.
    """
    status = "ok"
    cpu_percent = BASELINE_CPU_PERCENT
    memory_percent = BASELINE_MEMORY_PERCENT
    error_rate = BASELINE_ERROR_RATE
    latency_ms_p95 = BASELINE_LATENCY_MS_P95
    requests_per_second = BASELINE_REQUESTS_PER_SECOND

    if mode is FaultMode.traffic_spike:
        cpu_percent = TRAFFIC_SPIKE_CPU_PERCENT
        latency_ms_p95 = TRAFFIC_SPIKE_LATENCY_MS_P95
        requests_per_second = TRAFFIC_SPIKE_REQUESTS_PER_SECOND
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
    }
