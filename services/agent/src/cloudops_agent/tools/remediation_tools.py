"""Mutating remediation tools: the guarded action boundary.

``scale_service`` is the first mutating tool. It declares
``read_only=False`` and ``risk_level=RiskLevel.infrastructure_change`` (2), so
the workflow only reaches it through the approval gate, and the registry
independently validates its parameters at the boundary before running. The call
is a synchronous ``POST /scale`` to the simulated application, which clamps the
replica count to its own configured bounds and returns the new state.

The mutating tools are the only actions the planner is offered (see
``ToolRegistry.remediation_catalogue``); anything else is denied by default.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from cloudops_agent.config import Settings
from cloudops_agent.models import RiskLevel
from cloudops_agent.tools.base import Tool, ToolSpec


class ScaleServiceInput(BaseModel):
    """Validated input for ``scale_service``.

    The planner returns plan parameters as strings (``PlanDraft.parameters`` is
    ``dict[str, str]``), so plain Pydantic coercion turns ``"4"`` into ``4``.
    The bounds mirror the app's own ``[min, max]`` replica range, and
    ``extra="forbid"`` rejects any unexpected key before the HTTP call.
    """

    model_config = ConfigDict(extra="forbid")

    replicas: int = Field(ge=1, le=10)


def _scale_service(base_url: str, timeout: float, replicas: int) -> dict[str, Any]:
    """POST ``{"replicas": N}`` to the app's ``/scale`` and return its state."""
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        response = client.post("/scale", json={"replicas": replicas})
    response.raise_for_status()
    return response.json()


def build_remediation_tools(settings: Settings | None = None) -> tuple[Tool, ...]:
    """Build the mutating remediation tools against the simulated app."""
    effective = settings or Settings()
    base_url = effective.app_base_url
    timeout = effective.app_request_timeout_seconds

    return (
        Tool(
            spec=ToolSpec(
                name="scale_service",
                description=(
                    "Scale the simulated app's replica count to a fixed value by "
                    "calling POST /scale. Replicas is an integer in [1, 10]; higher "
                    "replica counts reduce CPU and latency under load."
                ),
                read_only=False,
                risk_level=RiskLevel.infrastructure_change,
                timeout_seconds=timeout,
                input_model=ScaleServiceInput,
            ),
            run=partial(_scale_service, base_url, timeout),
        ),
    )
