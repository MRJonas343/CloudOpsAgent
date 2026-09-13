"""Structured-response contracts for the agents.

These are the shapes the LLM is required to return. The workflow nodes turn them
into the domain models held in ``IncidentState``: drafts carry no timestamps, so
the model never invents one and the node stamps it.

Note: Bedrock structured output rejects JSON-Schema numeric bounds
(``minimum``/``maximum``), so the drafts keep plain floats and the nodes clamp
them when building the domain model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cloudops_agent.models import RiskLevel


class HypothesisDraft(BaseModel):
    """A hypothesis as proposed by the investigator."""

    description: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    """Structured result of the investigation stage."""

    hypotheses: list[HypothesisDraft] = Field(default_factory=list)


class DiagnosisResult(BaseModel):
    """Structured result of the diagnosis stage."""

    diagnosis: str


class PlanDraft(BaseModel):
    """A remediation plan as proposed by the planner (no timestamps)."""

    action: str
    description: str
    risk_level: RiskLevel
    approval_required: bool
    scope: str
    parameters: dict[str, str] = Field(default_factory=dict)
    rollback: str | None = None
    verification_criteria: list[str] = Field(default_factory=list)
