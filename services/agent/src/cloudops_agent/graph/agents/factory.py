"""Build agents from the declarations in ``agents.yaml``."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from pydantic import BaseModel

from cloudops_agent.graph.model.connection import get_model
from cloudops_agent.graph.utils import ConfigFile

CONFIG_PATH = Path(__file__).with_name("agents.yaml")


class AgentSpec(BaseModel):
    """A single agent declaration: operator-facing name plus system prompt."""

    name: str
    description: str
    system_prompt: str


class AgentRegistry:
    """Typed access to the agent declarations."""

    def __init__(self, config_file: ConfigFile | None = None) -> None:
        self._config_file = config_file or ConfigFile(CONFIG_PATH)
        self._specs: dict[str, AgentSpec] | None = None

    def all(self) -> dict[str, AgentSpec]:
        """Return every declared agent, keyed by agent id."""
        if self._specs is None:
            raw = self._config_file.load().get("agents") or {}
            if not isinstance(raw, dict):
                raise ValueError("'agents' must be a mapping of agent id to declaration")
            self._specs = {
                agent_id: AgentSpec.model_validate(declaration)
                for agent_id, declaration in raw.items()
            }
        return self._specs

    def get(self, agent_id: str) -> AgentSpec:
        """Return the declaration for ``agent_id`` or raise ``KeyError``."""
        specs = self.all()
        if agent_id not in specs:
            known = ", ".join(sorted(specs)) or "none"
            raise KeyError(f"unknown agent '{agent_id}' (known: {known})")
        return specs[agent_id]


registry = AgentRegistry()


def get_agent_spec(agent_id: str) -> AgentSpec:
    """Return the declaration for ``agent_id``."""
    return registry.get(agent_id)


def build_agent(
    agent_id: str,
    tools: list[Any] | None = None,
    response_format: type[BaseModel] | None = None,
):
    """Build a LangChain agent from the declaration for ``agent_id``.

    ``response_format`` binds the agent to a structured schema; the parsed value
    is returned under ``structured_response`` in the agent result.
    """
    spec = get_agent_spec(agent_id)
    kwargs: dict[str, Any] = {
        "model": get_model(),
        "tools": tools or [],
        "system_prompt": spec.system_prompt,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    return create_agent(**kwargs)


@cache
def get_agent(
    agent_id: str,
    response_format: type[BaseModel] | None = None,
):
    """Return a cached agent instance for ``agent_id``.

    Building an agent compiles a graph and creates a model client, so workflow
    nodes reuse a single instance per (agent id, response schema) pair.
    """
    return build_agent(agent_id, response_format=response_format)
