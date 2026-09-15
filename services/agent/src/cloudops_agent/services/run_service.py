"""The off-loop run service: the sole lifecycle writer (ADR-008).

A run executes the compiled graph inside a worker thread (``asyncio.to_thread``)
while the event loop stays free to serve HTTP. The worker thread only *observes*:
it streams every node update with ``agent.stream(..., stream_mode="updates")``
(a plain ``invoke()`` would collapse the intermediate phases) and marshals each
one back with ``loop.call_soon_threadsafe``.

Every mutation of the run and incident stores and every published event
therefore happens on the event-loop thread, so there is exactly one writer and
no lock anywhere in the path. The worker thread never touches a store.

Terminal outcomes are decided when the stream ends: a run that reached
``close_incident`` is ``resolved``; anything else is ``failed``, with
``verification_failed`` when the verification evidence is what failed and
``error`` otherwise. ``rejected``, ``timed_out``, and ``interrupted_restart``
belong to the approval-gate and restart paths.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from cloudops_agent.config import Settings
from cloudops_agent.graph.build import agent as default_agent
from cloudops_agent.graph.build import graph_config, initial_state
from cloudops_agent.models import Incident, IncidentStatus
from cloudops_agent.models.run import (
    RunOutcome,
    RunRecord,
    TimelineEvent,
)
from cloudops_agent.services.event_bus import EventBus, IncidentEvent
from cloudops_agent.services.incident_store import IncidentStore
from cloudops_agent.services.run_store import TERMINAL_STATUSES, RunStore

logger = logging.getLogger(__name__)

#: Graph node -> lifecycle status applied when that node's update arrives.
#:
#: ``human_approval`` has no entry on purpose in this slice: the node still
#: auto-approves, so the run continues straight through it and its update only
#: records the decision. The real pause (``awaiting_approval``) is a *detected*
#: state, taken from the graph snapshot, and arrives with the approval gate.
NODE_STATUS: dict[str, IncidentStatus] = {
    "analyze_incident": IncidentStatus.investigating,
    "collect_context": IncidentStatus.investigating,
    "investigate": IncidentStatus.investigating,
    "diagnose": IncidentStatus.diagnosed,
    "plan_remediation": IncidentStatus.planned,
    "execute_remediation": IncidentStatus.remediating,
    "verify_remediation": IncidentStatus.verifying,
    "close_incident": IncidentStatus.resolved,
}

#: Update fields that accumulate, mirroring the graph's ``operator.add`` reducers.
ACCUMULATING_FIELDS = ("observations", "hypotheses")

#: Update fields that replace the previous value.
REPLACING_FIELDS = (
    "diagnosis",
    "plan",
    "approval",
    "execution_result",
    "verification",
    "summary",
)


def _now() -> datetime:
    return datetime.now(UTC)


class RunService:
    """Drives one graph run per incident, off the loop, as the only writer."""

    def __init__(
        self,
        incident_store: IncidentStore,
        run_store: RunStore,
        event_bus: EventBus,
        *,
        settings: Settings | None = None,
        graph: Any | None = None,
    ) -> None:
        self._incidents = incident_store
        self._runs = run_store
        self._bus = event_bus
        self._settings = settings or Settings()
        self._graph = graph if graph is not None else default_agent
        self._tasks: set[asyncio.Task[RunRecord]] = set()
        #: Incident ids already triggered. The run record is created inside the
        #: scheduled task, so without this set two triggers in the same loop
        #: tick would both pass the ``runs.has`` check and start two runs over
        #: one record.
        self._triggered: set[str] = set()

    # -- trigger ---------------------------------------------------------------

    def schedule_run(self, incident: Incident) -> None:
        """Schedule one run for a newly stored incident.

        This is the Monitor trigger. It returns immediately — the run is
        scheduled, never awaited — so the poll loop is never blocked by graph
        execution. At most one run exists per ``incident_id``; a repeated call
        for the same id is ignored.
        """
        incident_id = incident.incident_id
        if incident_id in self._triggered or self._runs.has(incident_id):
            logger.warning("run already triggered; ignoring incident_id=%s", incident_id)
            return
        self._triggered.add(incident_id)
        task = asyncio.get_running_loop().create_task(self.run(incident))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run(self, incident: Incident) -> RunRecord:
        """Drive the graph for ``incident`` off the event loop and record it."""
        loop = asyncio.get_running_loop()
        record = self._runs.create(incident)
        logger.info("run start incident_id=%s type=%s", incident.incident_id, incident.type.value)
        self._write_through(incident.incident_id, record.status)
        self._publish(incident.incident_id, record)

        def worker() -> None:
            """Stream every node update from inside the worker thread.

            Each update is handed back to the event loop rather than applied
            here: this thread must never touch a store.
            """
            for chunk in self._graph.stream(
                initial_state(incident),
                config=graph_config(incident.incident_id),
                stream_mode="updates",
            ):
                loop.call_soon_threadsafe(self._apply_update, incident.incident_id, chunk)

        error: str | None = None
        try:
            await asyncio.to_thread(worker)
        except Exception as exc:  # noqa: BLE001 - any graph failure ends the run
            error = str(exc)
            logger.exception("run worker failed incident_id=%s", incident.incident_id)

        # Every marshalled update was scheduled before the worker returned, so
        # yielding once lets the loop drain them before the run is finalized.
        await asyncio.sleep(0)
        self._finalize(incident.incident_id, error=error)
        return record

    def reconcile_orphans(self) -> list[RunRecord]:
        """Resolve runs lost to a restart, once, on startup.

        A restart drops the in-memory record, checkpoint, and pause payload, so
        nothing may be resumed; the spec requires such a run to be reported as
        failed rather than pending.
        """
        reconciled = self._runs.reconcile_orphans()
        for record in reconciled:
            self._write_through(record.incident_id, record.status)
            self._publish(record.incident_id, record)
            logger.warning(
                "orphaned run reconciled incident_id=%s outcome=%s",
                record.incident_id,
                record.outcome.value if record.outcome is not None else None,
            )
        return reconciled

    # -- loop-thread mutations (the single writer) -----------------------------

    def _apply_update(self, incident_id: str, chunk: Mapping[str, Any]) -> None:
        """Apply one graph node update; always runs on the event-loop thread."""
        record = self._runs.get(incident_id)
        if record is None:
            logger.warning("update for unknown run incident_id=%s", incident_id)
            return

        for node, update in chunk.items():
            if not isinstance(update, Mapping):
                continue
            self._merge(record, update)
            record.phase = node
            status = NODE_STATUS.get(node)
            changed = status is not None and status != record.status
            if status is not None:
                record.status = status
            record.updated_at = _now()
            record.timeline.append(
                TimelineEvent(phase=node, status=record.status, at=record.updated_at)
            )
            if changed:
                self._write_through(incident_id, record.status)
            self._publish(incident_id, record)

    @staticmethod
    def _merge(record: RunRecord, update: Mapping[str, Any]) -> None:
        """Merge a node update into the record, mirroring the graph's reducers."""
        for field in ACCUMULATING_FIELDS:
            incoming = update.get(field)
            if isinstance(incoming, list) and incoming:
                setattr(record, field, [*getattr(record, field), *incoming])
        for field in REPLACING_FIELDS:
            if field in update:
                setattr(record, field, update[field])
        attempts = update.get("attempts")
        if isinstance(attempts, int):
            record.attempts += attempts

    def _finalize(self, incident_id: str, *, error: str | None = None) -> None:
        """End the run: decide the terminal status and outcome, then publish."""
        record = self._runs.get(incident_id)
        if record is None or record.completed_at is not None:
            return

        if record.status == IncidentStatus.resolved:
            outcome = RunOutcome.resolved
        elif error is not None:
            record.status = IncidentStatus.failed
            outcome = RunOutcome.error
        elif record.verification is not None and not record.verification.verified:
            record.status = IncidentStatus.failed
            outcome = RunOutcome.verification_failed
        else:
            record.status = IncidentStatus.failed
            outcome = RunOutcome.error

        moment = _now()
        record.outcome = outcome
        record.updated_at = moment
        record.completed_at = moment
        record.timeline.append(
            TimelineEvent(phase=record.phase, status=record.status, at=moment)
        )
        self._write_through(incident_id, record.status)
        self._publish(incident_id, record)
        logger.info(
            "run end incident_id=%s status=%s outcome=%s attempts=%d",
            incident_id,
            record.status.value,
            outcome.value,
            record.attempts,
        )

    # -- store and bus writes --------------------------------------------------

    def _write_through(self, incident_id: str, status: IncidentStatus) -> None:
        """Write a run status through to the stored incident."""
        if self._incidents.set_status(incident_id, status) is None:
            logger.warning(
                "run write-through found no incident incident_id=%s status=%s",
                incident_id,
                status.value,
            )

    def _publish(self, incident_id: str, record: RunRecord) -> None:
        """Publish the record's current status to every connected client."""
        incident = self._incidents.get(incident_id)
        if incident is None:
            return
        self._bus.publish(
            IncidentEvent(
                incident_id=incident_id,
                type=incident.type,
                severity=incident.severity,
                status=record.status,
                phase=record.phase,
                ts=_now(),
                remaining_seconds=self._remaining_seconds(record),
            )
        )

    @staticmethod
    def _remaining_seconds(record: RunRecord, *, now: datetime | None = None) -> int | None:
        """Return seconds left before the approval deadline, or ``None`` if unset."""
        if record.approval_deadline is None:
            return None
        moment = now or _now()
        return max(0, int((record.approval_deadline - moment).total_seconds()))


__all__ = ["NODE_STATUS", "RunService", "TERMINAL_STATUSES"]
