"""Mutating remediation tools: the guarded action boundary.

Two mutating tools are registered: ``restart_service`` recovers an unhealthy
service, and ``scale_service`` adds capacity. Both declare ``read_only=False``
and ``risk_level=RiskLevel.infrastructure_change`` (2), so the workflow only
reaches them through the approval gate, and the registry independently validates
their parameters at the boundary before running. The calls are synchronous
``POST /restart`` and ``POST /scale`` requests to the application.

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

#: Upper bound on the replica count the app accepts; mirrors ``APP_MAX_REPLICAS``.
MAX_REPLICAS = 10


def scale_input_model(baseline_replicas: int) -> type[BaseModel]:
    """Build the ``scale_service`` input model whose floor is the baseline.

    Scaling below the baseline during an incident is dangerous — the planner did
    exactly that and reduced capacity while the service was already degraded — so
    a below-baseline value is refused before the HTTP call. The floor is baked
    into the model's schema, so ``remediation_catalogue`` renders the real bound
    for the planner instead of an aspirational one.
    """
    floor = min(MAX_REPLICAS, max(1, baseline_replicas))

    class ScaleServiceInput(BaseModel):
        """Validated input for ``scale_service``.

        The planner returns plan parameters as strings (``PlanDraft.parameters``
        is a list of string values), so plain Pydantic coercion turns ``"4"``
        into ``4``. ``extra="forbid"`` rejects any unexpected key before the
        HTTP call.
        """

        model_config = ConfigDict(extra="forbid")

        replicas: int = Field(ge=floor, le=MAX_REPLICAS)

    return ScaleServiceInput


def _restart_service(base_url: str, timeout: float) -> dict[str, Any]:
    """POST to the app's ``/restart`` and return the resulting state."""
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        response = client.post("/restart")
    response.raise_for_status()
    return response.json()


def _scale_service(base_url: str, timeout: float, replicas: int) -> dict[str, Any]:
    """POST ``{"replicas": N}`` to the app's ``/scale`` and return its state."""
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        response = client.post("/scale", json={"replicas": replicas})
    response.raise_for_status()
    return response.json()


def build_remediation_tools(settings: Settings | None = None) -> tuple[Tool, ...]:
    """Build the mutating remediation tools against the app."""
    effective = settings or Settings()
    base_url = effective.app_base_url
    timeout = effective.app_request_timeout_seconds
    scale_input = scale_input_model(effective.baseline_replicas)

    return (
        Tool(
            spec=ToolSpec(
                name="restart_service",
                description=(
                    "Recover an unhealthy application: restart the service process "
                    "by calling POST /restart. A restart clears the service's "
                    "in-memory state and its active failure condition and returns "
                    "the replica count to its baseline, so health, error rate, and "
                    "metrics recover. Use this when the service reports unhealthy "
                    "or is logging errors; it does not add capacity."
                ),
                read_only=False,
                risk_level=RiskLevel.infrastructure_change,
                timeout_seconds=timeout,
            ),
            run=partial(_restart_service, base_url, timeout),
        ),
        Tool(
            spec=ToolSpec(
                name="scale_service",
                description=(
                    "Add capacity by scaling the service's replica count to a fixed "
                    "value, calling POST /scale. Replicas is an integer from the "
                    "baseline up to the configured maximum; a value below the "
                    "baseline is rejected. Higher replica counts reduce CPU and "
                    "latency under load, so use this for load or capacity pressure, "
                    "not to recover an unhealthy service."
                ),
                read_only=False,
                risk_level=RiskLevel.infrastructure_change,
                timeout_seconds=timeout,
                input_model=scale_input,
            ),
            run=partial(_scale_service, base_url, timeout),
        ),
    )
