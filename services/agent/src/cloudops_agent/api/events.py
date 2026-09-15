"""Server-sent events for incident lifecycle changes (ADR-006).

``GET /events`` is the streaming half of the read API: the run service publishes
one :class:`~cloudops_agent.services.event_bus.IncidentEvent` per lifecycle
change, and this module turns each one into an SSE frame. The bus already
assigns a monotonic integer id and fans out to one queue per client, so the HTTP
consumer only has to drain its queue and write the wire format below.

The stream is deliberately replay-free. A reconnecting client refetches state
over REST (`GET /incidents`, `GET /incidents/{id}/report`) instead of replaying
what it missed, because the bus holds no history and the ids are process-local.

Frame shape (``id`` is the bus's monotonic int, announced ``retry`` is 3s):

    id: 42
    event: incident
    data: {"incident_id":"INC-0001",...}

``X-Accel-Buffering: no`` is required: without it nginx buffers the response and
a client sees the lifecycle only when the connection closes, which defeats the
whole point of the stream.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from cloudops_agent.services.event_bus import EventBus, EventEnvelope

router = APIRouter(tags=["events"])

#: Reconnect delay handed to the browser via the SSE ``retry`` field.
SSE_RETRY_MS = 3000

#: How long the stream may sit idle before it emits a heartbeat comment. This is
#: also the upper bound on how long a disconnect can go unnoticed while quiet.
HEARTBEAT_INTERVAL_SECONDS = 15.0

#: Wire type of every frame the bus produces.
EVENT_NAME = "incident"


@router.get("/events")
async def stream_events(request: Request) -> StreamingResponse:
    """Stream incident lifecycle changes as server-sent events.

    The response is a long-lived ``text/event-stream``; buffering is disabled at
    both the proxy (``X-Accel-Buffering``) and the client cache
    (``Cache-Control``) so every frame reaches a connected browser immediately.
    """
    bus: EventBus = request.app.state.event_bus  # type: ignore[no-any-return]
    return StreamingResponse(
        _event_stream(request, bus),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_stream(request: Request, bus: EventBus) -> AsyncIterator[str]:
    """Drain this client's queue until it disconnects, heartbeating when idle."""
    queue = bus.subscribe()
    try:
        # The client applies this as its reconnect delay, so a dropped stream
        # reconnects in 3s instead of the browser default and refetches state.
        yield f"retry: {SSE_RETRY_MS}\n\n"
        while not await request.is_disconnected():
            try:
                envelope = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS
                )
            except TimeoutError:
                # A comment keeps intermediaries from closing an idle stream
                # without surfacing a lifecycle change a client would act on.
                yield ": heartbeat\n\n"
                continue
            yield _format_frame(envelope)
    finally:
        bus.unsubscribe(queue)


def _format_frame(envelope: EventEnvelope) -> str:
    """Render one envelope as a single SSE frame.

    ``model_dump_json`` keeps the payload on one line, so the ``data:`` field is
    never split and the frame terminates with the blank line SSE requires.
    """
    return f"id: {envelope.id}\nevent: {EVENT_NAME}\ndata: {envelope.event.model_dump_json()}\n\n"


__all__ = [
    "EVENT_NAME",
    "HEARTBEAT_INTERVAL_SECONDS",
    "SSE_RETRY_MS",
    "router",
]
