"""In-process SSE fan-out: one queue per client, monotonic integer ids (ADR-006).

The bus is process-local and replay-free by design: a reconnecting client
refetches state over REST instead of replaying the stream. Every method is meant
for the event-loop thread only — the runner marshals its updates onto that
thread before publishing, so nothing here needs a lock.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime
from typing import NamedTuple

from pydantic import BaseModel

from cloudops_agent.models.incident import (
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
)

#: Per-client buffer. A slow client drops its oldest frame rather than stalling
#: the run that is publishing.
DEFAULT_QUEUE_SIZE = 100


class IncidentEvent(BaseModel):
    """One lifecycle change pushed to every connected client.

    ``remaining_seconds`` is present only while a run waits on an operator
    decision; it is ``None`` for every other status.
    """

    incident_id: str
    type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    phase: str
    ts: datetime
    remaining_seconds: int | None = None


class EventEnvelope(NamedTuple):
    """A published event together with the monotonic id assigned to it."""

    id: int
    event: IncidentEvent


class EventBus:
    """Fan-out of :class:`IncidentEvent` to per-client queues."""

    def __init__(self, *, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[EventEnvelope]] = set()
        self._last_id = 0

    @property
    def last_id(self) -> int:
        """Return the id of the most recently published event (``0`` before any)."""
        return self._last_id

    def subscribe(self) -> asyncio.Queue[EventEnvelope]:
        """Register one client and return its queue; the caller drains it."""
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[EventEnvelope]) -> None:
        """Drop a disconnected client's queue."""
        self._subscribers.discard(queue)

    def publish(self, event: IncidentEvent) -> int:
        """Assign the next id, deliver to every client, and return the id."""
        self._last_id += 1
        envelope = EventEnvelope(id=self._last_id, event=event)
        for queue in self._subscribers:
            self._offer(queue, envelope)
        return self._last_id

    @staticmethod
    def _offer(queue: asyncio.Queue[EventEnvelope], envelope: EventEnvelope) -> None:
        """Enqueue without ever blocking the publisher."""
        if queue.full():
            with suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        with suppress(asyncio.QueueFull):
            queue.put_nowait(envelope)
