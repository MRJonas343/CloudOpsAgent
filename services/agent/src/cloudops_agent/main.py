"""FastAPI entrypoint for the agent service.

Two background tasks run inside the app.lifespan: the monitoring module, and the
approval sweeper that ends a pause which outlives ``approval_timeout_seconds``.
When a detection cycle stores a new incident (after the existing dedupe), the
monitor hands it to the run service, which schedules one off-loop graph run per
incident. Startup reconciliation resolves anything a previous process left
non-terminal as failed, because the run record, checkpoint, and pause payload are
all process-local (ADR-005/ADR-008).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from cloudops_agent.api import router as incidents_router
from cloudops_agent.config import Settings
from cloudops_agent.logging import configure_logging
from cloudops_agent.monitoring.app_client import AppClient
from cloudops_agent.monitoring.monitor import Monitor
from cloudops_agent.services.event_bus import EventBus
from cloudops_agent.services.incident_store import IncidentStore
from cloudops_agent.services.run_service import RunService
from cloudops_agent.services.run_store import RunStore


def create_app(
    settings: Settings | None = None,
    *,
    client: AppClient | None = None,
    store: IncidentStore | None = None,
    run_store: RunStore | None = None,
    event_bus: EventBus | None = None,
    run_service: RunService | None = None,
) -> FastAPI:
    """Build the agent app; ``settings`` and the collaborators can be injected."""
    settings = settings or Settings()
    configure_logging(settings.log_level, service="agent")

    incident_store = store or IncidentStore()
    app_client = client or AppClient(
        settings.app_base_url,
        timeout=settings.app_request_timeout_seconds,
    )
    runs = run_store or RunStore()
    bus = event_bus or EventBus()
    runner = run_service or RunService(incident_store, runs, bus, settings=settings)
    monitor = Monitor(app_client, incident_store, settings, on_incident=runner.schedule_run)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runner.reconcile_orphans()
        tasks: list[asyncio.Task[None]] = [asyncio.create_task(runner.sweeper_forever())]
        if settings.monitoring_enabled:
            tasks.append(asyncio.create_task(monitor.run_forever()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task
            await app_client.aclose()

    app = FastAPI(title="CloudOpsAgent Agent", version="0.2.0", lifespan=lifespan)
    app.state.incident_store = incident_store
    app.state.run_store = runs
    app.state.event_bus = bus
    app.state.run_service = runner
    app.include_router(incidents_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "agent"}

    return app


app = create_app()
