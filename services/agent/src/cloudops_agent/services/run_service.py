"""The off-loop run service: the sole lifecycle writer (ADR-008).

A run executes the compiled graph inside a worker thread (``asyncio.to_thread``)
while the event loop stays free to serve HTTP. The worker thread only *observes*:
it streams every node update with ``agent.stream(..., stream_mode="updates")``
(a plain ``invoke()`` would collapse the intermediate phases) and marshals each
one back with ``loop.call_soon_threadsafe``.

Every mutation of the run and incident stores and every published event
therefore happens on the event-loop thread, so there is exactly one writer and
no lock anywhere in the path. The worker thread never touches a store.

A pause is detected from the graph snapshot, never from a parsed stream chunk:
``human_approval`` never returns while it waits, so after every streamed update
the worker reads ``get_state(config)`` and a non-empty ``snapshot.next`` means the
run is parked. The runner then records ``awaiting_approval`` and arms a fresh
deadline. The deadline lives on the run record, not in the interrupt payload, so
the wall clock stays out of the checkpoint (ADR-007).

Terminal outcomes are decided when the stream ends: a run that reached
``close_incident`` is ``resolved``; anything else is ``failed``, with
``verification_failed`` when the verification evidence is what failed and
``error`` otherwise. An unapproved decision that ends the run is ``rejected``,
or ``timed_out`` when the sweeper expired the pause. ``interrupted_restart``
belongs to the restart path.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from langgraph.types import Command

from cloudops_agent.config import Settings
from cloudops_agent.graph.build import agent as default_agent
from cloudops_agent.graph.build import graph_config, initial_state
from cloudops_agent.models import Incident, IncidentStatus
from cloudops_agent.models.run import (
    ApprovalRequest,
    RunOutcome,
    RunRecord,
    TimelineEvent,
    remaining_seconds,
)
from cloudops_agent.services.event_bus import EventBus, IncidentEvent
from cloudops_agent.services.incident_store import IncidentStore
from cloudops_agent.services.run_store import TERMINAL_STATUSES, RunStore

logger = logging.getLogger(__name__)

#: Graph node that parks the run until an operator decision arrives.
APPROVAL_NODE = "human_approval"

#: How often the sweeper looks for an expired approval pause.
APPROVAL_SWEEP_INTERVAL_SECONDS = 1.0

#: Graph node -> lifecycle status applied when that node's update arrives.
#:
#: ``human_approval`` has no entry on purpose: the node never returns an update
#: while it waits, so ``awaiting_approval`` is a *detected* state read from the
#: graph snapshot (see :meth:`RunService._drive`) rather than one a chunk maps to.
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


def _pending_interrupts(snapshot: Any) -> tuple[Any, ...]:
    """Return the interrupts a graph snapshot is parked on, if any.

    The snapshot exposes them at the top level; the parked tasks carry the same
    values, so they are the fallback for a graph that reports them per task.
    """
    interrupts = getattr(snapshot, "interrupts", None)
    if interrupts:
        return tuple(interrupts)
    for task in getattr(snapshot, "tasks", None) or ():
        task_interrupts = getattr(task, "interrupts", None)
        if task_interrupts:
            return tuple(task_interrupts)
    return ()


def _is_paused(snapshot: Any) -> bool:
    """Return whether the graph is parked waiting for an operator.

    A non-empty ``next`` alone does **not** mean paused: every mid-stream
    checkpoint names the node it is about to run, so a graph that is still
    working also reports a non-empty ``next``. What distinguishes a parked run is
    a *pending interrupt*, and both facts are read from the snapshot rather than
    parsed out of the stream, so the runner never depends on the chunk shape.
    """
    if snapshot is None or not getattr(snapshot, "next", ()):
        return False
    return bool(_pending_interrupts(snapshot))


def _interrupt_payload(snapshot: Any) -> Mapping[str, Any] | None:
    """Return the mapping a paused node passed to ``interrupt()``, if any."""
    for item in _pending_interrupts(snapshot):
        value = getattr(item, "value", None)
        if isinstance(value, Mapping):
            return value
    return None


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
        #: Incident ids with a decision in flight. Claimed synchronously, before
        #: the first ``await``, so an operator and the sweeper can never both
        #: resume the same pause.
        self._deciding: set[str] = set()
        #: Incident ids whose pause was ended by the deadline rather than by an
        #: operator, so the terminal outcome is ``timed_out`` and not ``rejected``.
        self._expired: set[str] = set()

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
        record = self._runs.create(incident)
        logger.info("run start incident_id=%s type=%s", incident.incident_id, incident.type.value)
        self._write_through(incident.incident_id, record.status)
        self._publish(incident.incident_id, record)
        await self._drive(incident.incident_id, initial_state(incident))
        return record

    async def _drive(self, incident_id: str, stream_input: Any) -> None:
        """Stream the graph off the loop until it pauses or ends.

        The worker thread only observes. It marshals every node update back to
        the event loop — this thread must never touch a store — and reports the
        pause it found in the graph snapshot. A run that parks is left
        non-terminal for a decision; a run that drains is finalized here.
        ``stream_input`` is either a full initial state or ``Command(resume=...)``.
        """
        loop = asyncio.get_running_loop()
        config = graph_config(incident_id)
        paused = False
        payload: Mapping[str, Any] | None = None
        error: str | None = None

        def worker() -> None:
            nonlocal paused, payload
            for chunk in self._graph.stream(stream_input, config=config, stream_mode="updates"):
                loop.call_soon_threadsafe(self._apply_update, incident_id, chunk)
                snapshot = self._graph.get_state(config)
                if _is_paused(snapshot):
                    paused = True
                    payload = _interrupt_payload(snapshot)

        try:
            await asyncio.to_thread(worker)
        except Exception as exc:  # noqa: BLE001 - any graph failure ends the run
            error = str(exc)
            logger.exception("run worker failed incident_id=%s", incident_id)

        # Every marshalled update was scheduled before the worker returned, so
        # yielding once lets the loop drain them before the run continues.
        await asyncio.sleep(0)
        if paused:
            self._pause(incident_id, payload)
        else:
            self._finalize(incident_id, error=error)

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

    # -- approval gate ---------------------------------------------------------

    async def decide(
        self,
        incident_id: str,
        *,
        approved: bool,
        approver: str | None,
        reason: str | None,
        expired: bool = False,
    ) -> RunRecord | None:
        """Resume a paused run with an operator decision.

        Returns the record once the resumed run pauses again or ends, or
        ``None`` when the run is not awaiting approval — an unknown id, a run
        that already moved on, or a decision that lost the race to the sweeper.
        The claim happens before the first ``await``, so exactly one caller can
        resume a given pause.
        """
        record = self._runs.get(incident_id)
        if record is None or record.status is not IncidentStatus.awaiting_approval:
            return None
        if incident_id in self._deciding:
            return None

        self._deciding.add(incident_id)
        if expired:
            self._expired.add(incident_id)
        try:
            self._claim(incident_id, approved=approved)
            logger.info(
                "run decision incident_id=%s approved=%s approver=%s expired=%s",
                incident_id,
                approved,
                approver,
                expired,
            )
            await self._drive(
                incident_id,
                Command(resume={"approved": approved, "approver": approver, "reason": reason}),
            )
        finally:
            self._deciding.discard(incident_id)
        return self._runs.get(incident_id)

    async def sweep_expired(self) -> list[str]:
        """End every pause whose deadline has passed through the reject path.

        A timeout is a *denial*, not a special case in the graph: the sweeper
        resumes with ``approved=False``, so the run leaves through the same
        ``route_after_approval`` branch an operator rejection takes and nothing
        is ever executed.
        """
        expired = self.expired_runs()
        for incident_id in expired:
            logger.warning("approval deadline expired incident_id=%s", incident_id)
            await self.decide(
                incident_id,
                approved=False,
                approver=None,
                reason=(
                    "no operator decision within "
                    f"{self._settings.approval_timeout_seconds}s"
                ),
                expired=True,
            )
        return expired

    def expired_runs(self, *, now: datetime | None = None) -> list[str]:
        """Return the ids of paused runs whose deadline has passed (read-only)."""
        moment = now or _now()
        return [
            record.incident_id
            for record in self._runs.list()
            if record.status is IncidentStatus.awaiting_approval
            and record.approval_deadline is not None
            and moment >= record.approval_deadline
        ]

    async def sweeper_forever(self) -> None:
        """Run :meth:`sweep_expired` every second until the task is cancelled."""
        while True:
            try:
                await self.sweep_expired()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one bad sweep must not stop the sweeper
                logger.exception("approval sweeper cycle failed")
            await asyncio.sleep(APPROVAL_SWEEP_INTERVAL_SECONDS)

    def _pause(self, incident_id: str, payload: Mapping[str, Any] | None) -> None:
        """Record a detected pause: ``awaiting_approval`` plus a fresh deadline.

        The deadline is armed here, once per interrupt, so a failed verification
        that loops the graph back through ``human_approval`` starts a new window
        instead of inheriting an expired one.
        """
        record = self._runs.get(incident_id)
        if record is None:
            logger.warning("pause for unknown run incident_id=%s", incident_id)
            return

        moment = _now()
        deadline = moment + timedelta(seconds=self._settings.approval_timeout_seconds)
        record.status = IncidentStatus.awaiting_approval
        record.phase = APPROVAL_NODE
        record.approval_request = self._approval_request(
            incident_id, record, payload, moment, deadline
        )
        record.approval_deadline = deadline
        record.updated_at = moment
        record.timeline.append(
            TimelineEvent(phase=APPROVAL_NODE, status=record.status, at=moment)
        )
        self._write_through(incident_id, record.status)
        self._publish(incident_id, record)
        logger.info(
            "run paused incident_id=%s action=%s deadline=%s",
            incident_id,
            record.approval_request.action,
            deadline.isoformat(),
        )

    @staticmethod
    def _approval_request(
        incident_id: str,
        record: RunRecord,
        payload: Mapping[str, Any] | None,
        moment: datetime,
        deadline: datetime,
    ) -> ApprovalRequest:
        """Build the operator-facing request from the interrupt payload.

        The payload is what ``human_approval`` passed to ``interrupt()``; the
        plan on the record is the fallback, so a paused run is always presentable
        even if the snapshot could not be read.
        """
        plan = record.plan
        source = payload or {}
        action = source.get("action")
        risk_level = source.get("risk_level")
        parameters = source.get("parameters")
        return ApprovalRequest(
            incident_id=incident_id,
            action=str(action) if action is not None else (plan.action if plan else "none"),
            risk_level=(
                int(risk_level) if risk_level is not None else (int(plan.risk_level) if plan else 0)
            ),
            parameters=(
                dict(parameters)
                if isinstance(parameters, Mapping)
                else (dict(plan.parameters) if plan else {})
            ),
            requested_at=moment,
            deadline=deadline,
        )

    def _claim(self, incident_id: str, *, approved: bool) -> None:
        """Take the decision: leave ``awaiting_approval`` before resuming.

        Mutating the record synchronously is what makes the operator and the
        sweeper mutually exclusive, and the deadline is cleared so a decided run
        stops advertising a countdown.
        """
        record = self._runs.get(incident_id)
        if record is None:
            return
        moment = _now()
        record.status = (
            IncidentStatus.remediating if approved else IncidentStatus.failed
        )
        record.approval_deadline = None
        record.updated_at = moment
        record.timeline.append(
            TimelineEvent(phase=APPROVAL_NODE, status=record.status, at=moment)
        )
        self._write_through(incident_id, record.status)

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
        elif record.approval is not None and not record.approval.approved:
            # A denial always ends the run here, before the verification branch:
            # a loop-back leaves a failed verification on the record, and
            # "rejected" is the truthful outcome for a rejected plan.
            record.status = IncidentStatus.failed
            outcome = (
                RunOutcome.timed_out if incident_id in self._expired else RunOutcome.rejected
            )
        elif record.verification is not None and not record.verification.verified:
            record.status = IncidentStatus.failed
            outcome = RunOutcome.verification_failed
        else:
            record.status = IncidentStatus.failed
            outcome = RunOutcome.error

        self._expired.discard(incident_id)
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
        return remaining_seconds(record.approval_deadline, now=now)


__all__ = [
    "APPROVAL_NODE",
    "APPROVAL_SWEEP_INTERVAL_SECONDS",
    "NODE_STATUS",
    "RunService",
    "TERMINAL_STATUSES",
]
