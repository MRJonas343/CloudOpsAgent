"""In-memory run store keyed by ``incident_id`` (ADR-008).

The store is deliberately process-local and lossy: a restart drops every record
and every checkpoint. :meth:`RunStore.reconcile_orphans` is what makes that
observable — any record still non-terminal at startup is resolved ``failed``
with outcome ``interrupted_restart`` instead of being presented as still running
or still awaiting a decision.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cloudops_agent.models.incident import Incident, IncidentStatus
from cloudops_agent.models.run import RunOutcome, RunRecord, TimelineEvent

#: Statuses after which a run will never change again.
TERMINAL_STATUSES = frozenset({IncidentStatus.resolved, IncidentStatus.failed})

#: Phase recorded on a record before the first node update arrives.
INITIAL_PHASE = "start"


class RunStore:
    """Holds one :class:`RunRecord` per ``incident_id``.

    The store is a plain dict with no locking: ADR-008 makes the run service the
    sole writer, and every write happens on the event-loop thread.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create(self, incident: Incident, *, now: datetime | None = None) -> RunRecord:
        """Start a record for ``incident``; an existing record for the id is replaced."""
        moment = now or datetime.now(UTC)
        record = RunRecord(
            incident_id=incident.incident_id,
            status=incident.status,
            phase=INITIAL_PHASE,
            started_at=moment,
            updated_at=moment,
        )
        self._runs[record.incident_id] = record
        return record

    def get(self, incident_id: str) -> RunRecord | None:
        """Return the record for ``incident_id`` or ``None``."""
        return self._runs.get(incident_id)

    def has(self, incident_id: str) -> bool:
        """Return whether a run was ever started for ``incident_id``."""
        return incident_id in self._runs

    def list(self) -> list[RunRecord]:
        """Return every record in insertion order."""
        return list(self._runs.values())

    def reconcile_orphans(self, *, now: datetime | None = None) -> list[RunRecord]:
        """Resolve every non-terminal record as failed after a restart.

        Restoration is not attempted: the checkpoint, the pause payload, and the
        operator decision all died with the previous process. Only the records
        this method changes are returned, so a caller can write the failure
        through and log it.
        """
        moment = now or datetime.now(UTC)
        reconciled: list[RunRecord] = []
        for record in self._runs.values():
            if record.status in TERMINAL_STATUSES:
                continue
            record.status = IncidentStatus.failed
            record.outcome = RunOutcome.interrupted_restart
            record.updated_at = moment
            record.completed_at = moment
            record.timeline.append(
                TimelineEvent(phase=record.phase, status=IncidentStatus.failed, at=moment)
            )
            reconciled.append(record)
        return reconciled
