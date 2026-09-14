"""FastAPI application factory and routes for the simulated application service.

Deliberately small: one factory, one controller, one counter pair, and the
routes required by the monitoring module and local demos.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Query, Response

from cloudops_app.config import Settings
from cloudops_app.logging import configure_logging
from cloudops_app.logs import LogEntry, LogStore
from cloudops_app.metrics import compute_metrics
from cloudops_app.models import (
    HealthResponse,
    LogEntryModel,
    LogListResponse,
    MetricSnapshot,
    Order,
    OrderCreate,
    ScaleRequest,
    ScaleState,
    SimulationRequest,
    SimulationStatus,
)
from cloudops_app.simulation import FaultMode, SimulationController, parse_mode

SAMPLE_ORDERS = (
    Order(id=1, item="widget", quantity=2),
    Order(id=2, item="gadget", quantity=1),
)


@dataclass
class RequestCounters:
    """Lightweight in-memory request/error counters."""

    request_count: int = 0
    error_count: int = 0


#: Operator-only control routes that must never appear in the consultable store.
_CONTROL_ROUTE_PREFIXES = ("/simulate",)


def _is_control_route(path: str) -> bool:
    """Return ``True`` for operator-only control routes (never agent-visible)."""
    return any(
        path == prefix or path.startswith(f"{prefix}/") for prefix in _CONTROL_ROUTE_PREFIXES
    )


def create_app(
    settings: Settings | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    """Build the application; ``settings`` and a fake ``clock`` can be injected for deterministic runs."""
    settings = settings or Settings()
    configure_logging(settings.log_level, service="app")

    controller = SimulationController(
        max_duration_seconds=settings.simulation_max_duration_seconds,
        default_duration_seconds=settings.simulation_default_duration_seconds,
        clock=time.monotonic if clock is None else clock,
    )
    counters = RequestCounters()
    logs = LogStore(max_entries=settings.max_log_entries, service="app")
    replicas = max(settings.min_replicas, min(settings.baseline_replicas, settings.max_replicas))
    orders: list[Order] = [order.model_copy() for order in SAMPLE_ORDERS]
    next_order_id = max(order.id for order in orders) + 1

    app = FastAPI(title="CloudOpsAgent Simulated Application", version="0.2.0")

    @app.middleware("http")
    async def observe_requests(request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        counters.request_count += 1
        if response.status_code >= 500:
            counters.error_count += 1

        path = request.url.path
        if _is_control_route(path):
            return response

        mode = controller.active_mode()
        if response.status_code >= 500 or mode is FaultMode.unhealthy_application:
            level = "error"
        elif response.status_code >= 400 or mode is FaultMode.traffic_spike:
            level = "warning"
        else:
            level = "info"

        # While the service is degraded the request log reports the same p95
        # latency /metrics exposes, so the two views never disagree.
        if mode is None:
            reported_latency_ms = duration_ms
        else:
            snapshot = compute_metrics(
                mode,
                counters.request_count,
                counters.error_count,
                replicas=replicas,
                baseline_replicas=settings.baseline_replicas,
            )
            reported_latency_ms = snapshot["latency_ms_p95"]

        logs.record(
            level,
            f"{request.method} {path} -> {response.status_code} in {reported_latency_ms}ms",
            path=path,
            method=request.method,
            status=response.status_code,
            duration_ms=reported_latency_ms,
        )
        return response

    def build_status() -> SimulationStatus:
        state = controller.current()
        return SimulationStatus(
            enabled=settings.simulation_enabled,
            mode=state.mode.value if state.mode is not None else None,
            started_at=state.started_at,
            expires_at=state.expires_at,
            remaining_seconds=controller.remaining_seconds(),
            duration_seconds=state.duration_seconds,
        )

    def require_simulation_enabled() -> None:
        if not settings.simulation_enabled:
            raise HTTPException(status_code=403, detail="simulation controls are disabled")

    def require_healthy() -> None:
        if controller.active_mode() is FaultMode.unhealthy_application:
            raise HTTPException(status_code=503, detail="application unavailable")

    @app.get("/health", response_model=HealthResponse)
    async def health(response: Response) -> HealthResponse:
        if controller.active_mode() is FaultMode.unhealthy_application:
            response.status_code = 503
            return HealthResponse(status="unhealthy", service="app")
        return HealthResponse(status="ok", service="app")

    @app.get("/metrics", response_model=MetricSnapshot)
    async def metrics() -> MetricSnapshot:
        payload = compute_metrics(
            controller.active_mode(),
            counters.request_count,
            counters.error_count,
            replicas=replicas,
            baseline_replicas=settings.baseline_replicas,
        )
        return MetricSnapshot(**payload)

    def build_log_response(entries: list[LogEntry], effective: int) -> LogListResponse:
        return LogListResponse(
            service="app",
            count=len(entries),
            limit=effective,
            entries=[
                LogEntryModel.model_validate(entry, from_attributes=True) for entry in entries
            ],
        )

    @app.get("/logs", response_model=LogListResponse)
    async def list_logs(limit: int = Query(default=100, ge=1)) -> LogListResponse:
        effective = min(limit, logs.max_entries)
        return build_log_response(logs.recent(effective), effective)

    @app.get("/errors", response_model=LogListResponse)
    async def list_errors(limit: int = Query(default=100, ge=1)) -> LogListResponse:
        effective = min(limit, logs.max_entries)
        return build_log_response(logs.errors(effective), effective)

    def build_scale_state() -> ScaleState:
        return ScaleState(
            service="app",
            replicas=replicas,
            baseline_replicas=settings.baseline_replicas,
            min_replicas=settings.min_replicas,
            max_replicas=settings.max_replicas,
        )

    @app.get("/scale", response_model=ScaleState)
    async def get_scale() -> ScaleState:
        return build_scale_state()

    @app.post("/scale", response_model=ScaleState)
    async def set_scale(body: ScaleRequest) -> ScaleState:
        nonlocal replicas
        clamped = max(settings.min_replicas, min(body.replicas, settings.max_replicas))
        if clamped != body.replicas:
            logs.record(
                "warning",
                f"scale request {body.replicas} clamped to {clamped} "
                f"[{settings.min_replicas}, {settings.max_replicas}]",
            )
        replicas = clamped
        logs.record("info", f"replica count set to {replicas}")
        return build_scale_state()

    @app.get("/api/orders", response_model=list[Order])
    async def list_orders() -> list[Order]:
        require_healthy()
        return orders

    @app.post("/api/orders", response_model=Order, status_code=201)
    async def create_order(body: OrderCreate) -> Order:
        nonlocal next_order_id
        require_healthy()
        order = Order(id=next_order_id, item=body.item, quantity=body.quantity)
        next_order_id += 1
        orders.append(order)
        return order

    @app.get("/simulate/status", response_model=SimulationStatus)
    async def simulation_status() -> SimulationStatus:
        require_simulation_enabled()
        return build_status()

    @app.post("/simulate/reset", response_model=SimulationStatus)
    async def reset_simulation() -> SimulationStatus:
        require_simulation_enabled()
        controller.reset()
        return build_status()

    @app.post("/simulate/{mode}", response_model=SimulationStatus)
    async def activate_simulation(
        mode: str,
        body: SimulationRequest | None = None,
    ) -> SimulationStatus:
        require_simulation_enabled()
        fault = parse_mode(mode)
        if fault is None:
            raise HTTPException(status_code=404, detail=f"unknown simulation mode: {mode}")
        duration = body.duration_seconds if body is not None else None
        controller.activate(fault, duration)
        return build_status()

    return app


app = create_app()
