"""The monitoring loop: poll the app, detect, deduplicate, and store incidents."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from cloudops_agent.config import Settings
from cloudops_agent.models import Incident
from cloudops_agent.monitoring.app_client import AppClient
from cloudops_agent.monitoring.detectors import detect_incident
from cloudops_agent.services.incident_store import IncidentStore

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Monitor:
    """Runs one detection cycle at a time against the app and stores incidents."""

    def __init__(
        self,
        client: AppClient,
        store: IncidentStore,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        on_incident: Callable[[Incident], None] | None = None,
    ) -> None:
        self._client = client
        self._store = store
        self._settings = settings
        self._clock = clock or _utcnow
        self._on_incident = on_incident

    async def poll_once(self) -> Incident | None:
        """Run one cycle; return the newly stored incident or ``None``.

        Transport failures and duplicate active conditions are skipped. A newly
        stored incident is handed to the optional ``on_incident`` trigger, which
        is invoked but never awaited: scheduling the run is the callback's job,
        so the poll loop keeps its one-cycle-at-a-time pace.
        """
        try:
            health = await self._client.check_health()
            metrics = await self._client.collect_metrics()
        except httpx.HTTPError as exc:
            logger.warning("monitoring poll skipped: app request failed (%s)", exc)
            return None

        incident = detect_incident(health, metrics, self._settings, self._clock())
        if incident is None:
            return None

        if self._store.find_active(incident.service, incident.type) is not None:
            return None

        stored = self._store.add(incident)
        logger.info(
            "incident detected incident_id=%s type=%s severity=%s correlation_id=%s",
            stored.incident_id,
            stored.type.value,
            stored.severity.value,
            stored.correlation_id,
        )
        self._trigger(stored)
        return stored

    def _trigger(self, incident: Incident) -> None:
        """Hand ``incident`` to the run trigger without blocking the poll loop."""
        callback = self._on_incident
        if callback is None:
            return
        try:
            callback(incident)
        except Exception:  # noqa: BLE001 - a trigger failure must not stop monitoring
            logger.exception("incident trigger failed incident_id=%s", incident.incident_id)

    async def run_forever(self) -> None:
        """Poll every ``poll_interval_seconds`` until the task is cancelled."""
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("monitoring cycle failed")
            await asyncio.sleep(self._settings.poll_interval_seconds)
