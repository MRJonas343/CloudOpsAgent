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


class PlanParameter(BaseModel):
    """A single remediation parameter, named exactly as the catalogue declares.

    Parameters are modelled as a list of typed objects rather than a free-form
    mapping: Bedrock structured output reliably fills explicit object lists but
    silently returns an empty object for ``additionalProperties`` mappings.
    """

    name: str = Field(
        description="Parameter name exactly as declared in the catalogue.",
    )
    value: str = Field(
        description="The parameter value, encoded as a string.",
    )


class PlanDraft(BaseModel):
    """A remediation plan as proposed by the planner (no timestamps).

    Every field carries a description because the descriptions are part of the
    JSON schema the model sees: without them the model tends to leave
    ``parameters`` empty, and the executor then has nothing to run.
    """

    action: str = Field(
        description="Exactly one action name from the supplied catalogue.",
    )
    description: str = Field(
        description="What the action does and why it fits the diagnosis.",
    )
    risk_level: RiskLevel = Field(
        description="Honest risk classification of the proposed action.",
    )
    approval_required: bool = Field(
        description="Whether human approval is required before the action runs.",
    )
    scope: str = Field(
        description="The exact resource or service scope the action touches.",
    )
    parameters: list[PlanParameter] = Field(
        description=(
            "One entry per parameter the chosen action declares, using exactly the "
            'catalogue names. Example: [{"name": "replicas", "value": "4"}]. Use an '
            "empty list only when the action declares no parameters."
        ),
    )
    rollback: str | None = Field(
        default=None,
        description="How to undo the action, or null when it reverses itself.",
    )
    verification_criteria: list[str] = Field(
        default_factory=list,
        description="What must be true afterwards for the action to count as successful.",
    )
