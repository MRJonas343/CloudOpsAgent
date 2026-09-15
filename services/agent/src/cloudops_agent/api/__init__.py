"""HTTP API for incidents, lifecycle events, and service health."""

from cloudops_agent.api.events import router as events_router
from cloudops_agent.api.incidents import router

__all__ = ["events_router", "router"]
