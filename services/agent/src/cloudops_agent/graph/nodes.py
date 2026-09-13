"""Incident workflow nodes and conditional routers.

The investigation, diagnosis, and planning nodes call the agents declared in
``agents.yaml`` through :func:`build_agent`. The remaining nodes are still
placeholders: context collection and execution become real tool calls in later
phases, and the approval gate becomes a real human interrupt.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END

from cloudops_agent.graph.agents import (
    DiagnosisResult,
    InvestigationResult,
    PlanDraft,
    get_agent,
)
from cloudops_agent.graph.policy import effective_risk, requires_approval
from cloudops_agent.graph.state import (
    ApprovalDecision,
    IncidentState,
    VerificationResult,
)
from cloudops_agent.models import (
    Hypothesis,
    Incident,
    IncidentStatus,
    Observation,
    RemediationOutcome,
    RemediationPlan,
    RemediationResult,
)

logger = logging.getLogger(__name__)

#: Failed verifications allowed before the workflow stops for manual handling.
MAX_ATTEMPTS = 3

#: The mock verifier keeps failing until this many attempts are recorded, so one
#: Verify -> Investigate cycle is always exercised.
_MOCK_RETRY_BEFORE_SUCCESS = 1


def _now() -> datetime:
    return datetime.now(UTC)


def _incident_of(state: IncidentState) -> Incident:
    """Return the incident as a validated model.

    LangGraph does not validate nested TypedDict fields, so LangGraph Studio (or
    any JSON caller) delivers the incident as a plain dict. Nodes coerce it here.
    """
    incident = state["incident"]
    if isinstance(incident, Incident):
        return incident
    return Incident.model_validate(incident)


def _structured_response(result: dict[str, Any], agent_id: str) -> Any:
    """Return the agent's parsed structured response, or fail loudly."""
    parsed = result.get("structured_response")
    if parsed is None:
        raise RuntimeError(f"agent '{agent_id}' returned no structured response")
    return parsed


def _incident_summary(incident: Incident) -> str:
    return "\n".join(
        [
            f"incident_id: {incident.incident_id}",
            f"service: {incident.service}",
            f"type: {incident.type.value}",
            f"severity: {incident.severity.value}",
            f"status: {incident.status.value}",
            f"detected_at: {incident.detected_at.isoformat()}",
        ]
    )


def _observation_lines(observations: list[Observation]) -> str:
    if not observations:
        return "(no observations collected)"
    return "\n".join(f"- [{item.source}] {item.summary}" for item in observations)


def _hypothesis_lines(hypotheses: list[Hypothesis]) -> str:
    if not hypotheses:
        return "(no hypotheses yet)"
    return "\n".join(
        f"- (confidence {item.confidence:.2f}) {item.description}" for item in hypotheses
    )


def analyze_incident(state: IncidentState) -> dict[str, Any]:
    """Normalize the incoming incident and mark it as under investigation."""
    incident = _incident_of(state)
    logger.info("analyze incident_id=%s type=%s", incident.incident_id, incident.type.value)
    return {
        "incident": incident.model_copy(update={"status": IncidentStatus.investigating}),
        "observations": [
            Observation(
                source="analyze",
                summary=f"incident {incident.incident_id} accepted for analysis",
                metric="status",
                observed_at=_now(),
            )
        ],
    }


def collect_context(state: IncidentState) -> dict[str, Any]:
    """Gather evidence. Placeholder for the registered read-only tools."""
    logger.info("collect_context incident_id=%s", _incident_of(state).incident_id)
    return {
        "observations": [
            Observation(
                source="metrics",
                summary="cpu_percent is 78.0",
                metric="cpu_percent",
                value=78.0,
                observed_at=_now(),
            ),
            Observation(
                source="metrics",
                summary="requests_per_second is 30.0 (threshold 20.0)",
                metric="requests_per_second",
                value=30.0,
                threshold=20.0,
                observed_at=_now(),
            ),
        ]
    }


def investigate(state: IncidentState) -> dict[str, Any]:
    """Turn the collected evidence into bounded hypotheses."""
    incident = _incident_of(state)
    prompt = (
        "Incident:\n"
        f"{_incident_summary(incident)}\n\n"
        "Observations:\n"
        f"{_observation_lines(state.get('observations', []))}\n\n"
        "Produce the hypotheses that this evidence supports."
    )
    agent = get_agent("investigator", response_format=InvestigationResult)
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    parsed: InvestigationResult = _structured_response(result, "investigator")
    hypotheses = [
        Hypothesis(
            description=draft.description,
            # Bedrock structured output cannot carry numeric bounds, so clamp here.
            confidence=min(1.0, max(0.0, draft.confidence)),
            evidence=draft.evidence,
            created_at=_now(),
        )
        for draft in parsed.hypotheses
    ]
    logger.info("investigate hypotheses=%d", len(hypotheses))
    return {"hypotheses": hypotheses}


def diagnose(state: IncidentState) -> dict[str, Any]:
    """State the best-supported cause and its uncertainty."""
    incident = _incident_of(state)
    prompt = (
        "Incident:\n"
        f"{_incident_summary(incident)}\n\n"
        "Observations:\n"
        f"{_observation_lines(state.get('observations', []))}\n\n"
        "Candidate hypotheses:\n"
        f"{_hypothesis_lines(state.get('hypotheses', []))}\n\n"
        "State the best-supported cause."
    )
    agent = get_agent("diagnostician", response_format=DiagnosisResult)
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    parsed: DiagnosisResult = _structured_response(result, "diagnostician")
    logger.info("diagnose incident_id=%s", incident.incident_id)
    return {"diagnosis": parsed.diagnosis}


def plan_remediation(state: IncidentState) -> dict[str, Any]:
    """Propose a scoped, risk-classified remediation plan."""
    incident = _incident_of(state)
    prompt = (
        "Incident:\n"
        f"{_incident_summary(incident)}\n\n"
        "Diagnosis:\n"
        f"{state.get('diagnosis') or '(none)'}\n\n"
        "Observations:\n"
        f"{_observation_lines(state.get('observations', []))}\n\n"
        "Propose exactly one bounded remediation plan."
    )
    agent = get_agent("planner", response_format=PlanDraft)
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    draft: PlanDraft = _structured_response(result, "planner")
    # A model must never be able to lower a gate: enforce the risk floor in code.
    risk_level = effective_risk(draft.action, draft.risk_level)
    if risk_level != draft.risk_level:
        logger.warning(
            "planner risk raised action=%s proposed=%s enforced=%s",
            draft.action,
            draft.risk_level.name,
            risk_level.name,
        )
    plan = RemediationPlan(
        action=draft.action,
        description=draft.description,
        risk_level=risk_level,
        approval_required=draft.approval_required or requires_approval(risk_level),
        scope=draft.scope,
        parameters=dict(draft.parameters),
        rollback=draft.rollback,
        verification_criteria=draft.verification_criteria,
        created_at=_now(),
    )
    logger.info(
        "plan action=%s risk=%s approval_required=%s",
        plan.action,
        plan.risk_level.name,
        plan.approval_required,
    )
    return {"plan": plan}


def human_approval(state: IncidentState) -> dict[str, Any]:
    """Approval gate.

    MOCK: auto-approves so the workflow can run unattended. A later phase
    replaces this with a real ``interrupt()`` that waits for an operator.
    """
    logger.info(
        "human_approval MOCK auto-approval incident_id=%s",
        _incident_of(state).incident_id,
    )
    return {
        "approval": ApprovalDecision(
            approved=True,
            approver="mock-operator",
            reason="mock auto-approval",
            decided_at=_now(),
        )
    }


def execute_remediation(state: IncidentState) -> dict[str, Any]:
    """Apply the approved action. Placeholder for the guarded mutating tool."""
    plan = state.get("plan")
    action = plan.action if plan is not None else "no-op"
    logger.info("execute action=%s", action)
    return {
        "execution_result": RemediationResult(
            action=action,
            outcome=RemediationOutcome.succeeded,
            executed_at=_now(),
            output="mock execution completed",
        )
    }


def verify_remediation(state: IncidentState) -> dict[str, Any]:
    """Check metrics, health, and logs after the action.

    MOCK: verification still fails the first pass so the ``Verify -> Investigate``
    retry loop and the ``attempts`` reducer are exercised. Real checks arrive
    with the tool layer.
    """
    attempts = state.get("attempts", 0)
    verified = attempts >= _MOCK_RETRY_BEFORE_SUCCESS
    logger.info("verify verified=%s attempts=%d", verified, attempts)
    if verified:
        summary = "mock verification: recovered"
    else:
        summary = "mock verification: still unhealthy"
    update: dict[str, Any] = {
        "verification": VerificationResult(
            verified=verified,
            metrics_ok=verified,
            health_ok=verified,
            logs_ok=verified,
            summary=summary,
            checked_at=_now(),
        )
    }
    if not verified:
        update["attempts"] = 1
    return update


def close_incident(state: IncidentState) -> dict[str, Any]:
    """Mark the incident resolved and record a short post-mortem summary."""
    incident = _incident_of(state)
    diagnosis = state.get("diagnosis") or "unknown"
    logger.info("close incident_id=%s status=resolved", incident.incident_id)
    summary = (
        f"Incident {incident.incident_id} ({incident.type.value}) resolved. "
        f"Cause: {diagnosis}"
    )
    return {
        "incident": incident.model_copy(update={"status": IncidentStatus.resolved}),
        "summary": summary,
    }


def route_after_plan(state: IncidentState) -> str:
    """Send risk-bearing plans to approval; execute low-risk plans directly."""
    plan = state.get("plan")
    if plan is not None and plan.approval_required:
        return "human_approval"
    return "execute_remediation"


def route_after_approval(state: IncidentState) -> str:
    """Execute only approved plans; a missing or denied approval stops the run."""
    approval = state.get("approval")
    if approval is not None and approval.approved:
        return "execute_remediation"
    logger.warning("approval denied or missing; stopping workflow")
    return END


def route_after_verify(state: IncidentState) -> str:
    """Close on success, retry investigation on failure, stop after max attempts."""
    verification = state.get("verification")
    if verification is not None and verification.verified:
        return "close_incident"
    attempts = state.get("attempts", 0)
    if attempts >= MAX_ATTEMPTS:
        logger.warning("verification failed %d times; stopping for manual handling", attempts)
        return END
    return "investigate"
