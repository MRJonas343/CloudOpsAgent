"""FastAPI entrypoint for the agent service.

The monitoring module runs as a background task inside the app.lifespan; it
creates and stores incidents but does not trigger the LangGraph workflow yet
(that boundary arrives in a later phase).
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
from cloudops_agent.services.incident_store import IncidentStore


def create_app(
    settings: Settings | None = None,
    *,
    client: AppClient | None = None,
    store: IncidentStore | None = None,
) -> FastAPI:
    """Build the agent app; ``settings`` and a fake ``client``/``store`` can be injected."""
    settings = settings or Settings()
    configure_logging(settings.log_level, service="agent")

    incident_store = store or IncidentStore()
    app_client = client or AppClient(
        settings.app_base_url,
        timeout=settings.app_request_timeout_seconds,
    )
    monitor = Monitor(app_client, incident_store, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        if settings.monitoring_enabled:
            task = asyncio.create_task(monitor.run_forever())
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await app_client.aclose()

    app = FastAPI(title="CloudOpsAgent Agent", version="0.2.0", lifespan=lifespan)
    app.state.incident_store = incident_store
    app.include_router(incidents_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "agent"}

    return app


app = create_app()
