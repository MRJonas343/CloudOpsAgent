"""The tool contract: what every registered tool must declare.

The registry (``cloudops_agent.tools.registry``) is the only way a graph node can
touch the outside world. A tool cannot be invoked unless it was registered, and
every tool declares, at minimum:

- ``name``: the registry key callers use; an unregistered name never executes.
- ``description``: a short, human/LLM-readable statement of what the tool does.
- ``read_only``: ``True`` when the tool cannot mutate external state.
- ``risk_level``: the Risk 0-3 classification from the security policy.
- ``timeout_seconds``: the wall-clock bound the registry enforces per call.
- ``input_model``: an optional Pydantic model used to validate ``**kwargs``.

Read-only tools are implemented first (see ``app_tools.py``). Mutating tools
arrive later and must declare a non-``read`` risk level plus approval handling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from cloudops_agent.models import RiskLevel


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Declarative metadata every registered tool must provide."""

    name: str
    description: str
    read_only: bool
    risk_level: RiskLevel
    timeout_seconds: float
    input_model: type[BaseModel] | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must be a non-empty string")
        if self.timeout_seconds <= 0:
            raise ValueError(f"tool '{self.name}' timeout_seconds must be > 0")


@dataclass(frozen=True, slots=True)
class Tool:
    """A registered tool: its declaration plus the synchronous callable it runs."""

    spec: ToolSpec
    run: Callable[..., Any]
