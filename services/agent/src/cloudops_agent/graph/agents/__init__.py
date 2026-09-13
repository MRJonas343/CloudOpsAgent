"""Agents for the incident workflow.

Agents are declared in ``agents.yaml`` (name, description, system prompt) and
built by :func:`build_agent`. Keeping the prompt text in the YAML means the agent
modules stay declarative and the wording is reviewable in one place.
"""

from cloudops_agent.graph.agents.factory import (
    AgentRegistry,
    AgentSpec,
    build_agent,
    get_agent,
    get_agent_spec,
    registry,
)
from cloudops_agent.graph.agents.schemas import (
    DiagnosisResult,
    HypothesisDraft,
    InvestigationResult,
    PlanDraft,
)

__all__ = [
    "AgentRegistry",
    "AgentSpec",
    "DiagnosisResult",
    "HypothesisDraft",
    "InvestigationResult",
    "PlanDraft",
    "build_agent",
    "get_agent",
    "get_agent_spec",
    "registry",
]
