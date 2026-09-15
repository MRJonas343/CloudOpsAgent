"""Incident workflow nodes and conditional routers.

The investigation, diagnosis, and planning nodes call the agents declared in
``agents.yaml`` through :func:`build_agent`. ``collect_context`` gathers real
evidence through the registered read-only tools. ``plan_remediation`` offers the
planner the real remediation catalogue, ``execute_remediation`` runs only an
allowlisted mutating tool through the registry (deny-by-default), and
``verify_remediation`` checks the app's real health, metrics, and error logs.
``human_approval`` is a real ``interrupt()``: the run parks there until an
operator decision or the approval timeout resumes it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END
from langgraph.types import interrupt

from cloudops_agent.config import settings
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
from cloudops_agent.tools import UnknownToolError, get_tool_registry

logger = logging.getLogger(__name__)

#: Failed verifications allowed before the workflow stops for manual handling.
MAX_ATTEMPTS = 3

#: How many recent / error log entries each context-collection call reads.
_LOG_LIMIT = 20


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


def _failed_observation(
    tool: str, source: str, metric: str, exc: Exception, now: datetime
) -> Observation:
    """Record a tool failure as incomplete evidence instead of inferring success."""
    return Observation(
        source=source,
        summary=f"{tool} failed: {exc}",
        metric=metric,
        value=None,
        observed_at=now,
    )


def collect_context(state: IncidentState) -> dict[str, Any]:
    """Gather real evidence through the registered read-only tools.

    Health, metrics, logs, and errors are read from the application over HTTP.
    A tool failure is recorded as an explicit incomplete-evidence observation;
    it is never treated as success.
    """
    incident = _incident_of(state)
    logger.info("collect_context incident_id=%s", incident.incident_id)
    registry = get_tool_registry(settings)
    now = _now()
    observations: list[Observation] = []

    try:
        health = registry.invoke("get_app_health")
        observations.append(
            Observation(
                source="health",
                summary=(
                    f"application health status is '{health['status']}' "
                    f"(ok={health['ok']}, http {health['status_code']}, {health['latency_ms']}ms)"
                ),
                metric="health_status",
                value=None,
                observed_at=now,
            )
        )
    except Exception as exc:  # noqa: BLE001 - failures become incomplete evidence
        observations.append(
            _failed_observation("get_app_health", "health", "health_status", exc, now)
        )

    metrics: dict[str, Any] | None = None
    try:
        metrics = registry.invoke("get_app_metrics")
    except Exception as exc:  # noqa: BLE001 - failures become incomplete evidence
        observations.append(
            _failed_observation("get_app_metrics", "metrics", "metrics_snapshot", exc, now)
        )

    if metrics is not None:
        threshold = settings.traffic_spike_rps_threshold
        requests_per_second = metrics.get("requests_per_second")
        if requests_per_second is not None:
            observations.append(
                Observation(
                    source="metrics",
                    summary=(
                        f"requests_per_second is {requests_per_second} (threshold {threshold})"
                    ),
                    metric="requests_per_second",
                    value=float(requests_per_second),
                    threshold=threshold,
                    observed_at=now,
                )
            )
        for metric_name in ("cpu_percent", "memory_percent", "latency_ms_p95", "error_rate"):
            value = metrics.get(metric_name)
            if value is not None:
                observations.append(
                    Observation(
                        source="metrics",
                        summary=f"{metric_name} is {value}",
                        metric=metric_name,
                        value=float(value),
                        observed_at=now,
                    )
                )

    try:
        logs = registry.invoke("get_app_logs", limit=_LOG_LIMIT)
        entries = logs.get("entries") or []
        newest = entries[0].get("message", "(unknown)") if entries else "(none)"
        observations.append(
            Observation(
                source="logs",
                summary=f"{logs.get('count', 0)} recent log entries; newest: {newest}",
                metric="log_entry_count",
                value=float(logs.get("count", 0)),
                observed_at=now,
            )
        )
    except Exception as exc:  # noqa: BLE001 - failures become incomplete evidence
        observations.append(
            _failed_observation("get_app_logs", "logs", "log_entry_count", exc, now)
        )

    try:
        errors = registry.invoke("get_recent_errors", limit=_LOG_LIMIT)
        observations.append(
            Observation(
                source="logs",
                summary=f"{errors.get('count', 0)} error-level log entries",
                metric="error_log_count",
                value=float(errors.get("count", 0)),
                observed_at=now,
            )
        )
    except Exception as exc:  # noqa: BLE001 - failures become incomplete evidence
        observations.append(
            _failed_observation("get_recent_errors", "logs", "error_log_count", exc, now)
        )

    logger.info("collect_context observations=%d", len(observations))
    return {"observations": observations}


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
    """Propose a scoped, risk-classified remediation plan from the real catalogue."""
    incident = _incident_of(state)
    catalogue = get_tool_registry(settings).remediation_catalogue()
    prompt = (
        "Incident:\n"
        f"{_incident_summary(incident)}\n\n"
        "Diagnosis:\n"
        f"{state.get('diagnosis') or '(none)'}\n\n"
        "Observations:\n"
        f"{_observation_lines(state.get('observations', []))}\n\n"
        "Available remediation actions (this is the complete allowlist):\n"
        f"{catalogue}\n\n"
        "Propose exactly one bounded remediation plan. The 'action' field MUST be "
        "exactly one of the action names listed above, and 'parameters' MUST "
        "contain every parameter that action declares, using the exact names and "
        "types shown in the catalogue. For example, if the chosen action declares "
        "'replicas: integer (min 1, max 10)', set parameters to "
        '{"replicas": "4"} with a value inside that range. Do not invent actions, '
        "parameters, or values outside the stated ranges."
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
        parameters={parameter.name: parameter.value for parameter in draft.parameters},
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


def _read_decision(decision: Any) -> tuple[bool, str | None, str | None]:
    """Normalize a resume payload into ``(approved, approver, reason)``.

    The operator endpoints send ``{"approved", "approver", "reason"}``, but the
    resume value is whatever the caller of ``Command(resume=...)`` supplied.
    Anything that is not an explicit approval is a denial, so a malformed or
    missing payload can never execute remediation.
    """
    if not isinstance(decision, Mapping):
        return False, None, "no operator decision was supplied"
    approver = decision.get("approver")
    reason = decision.get("reason")
    return (
        decision.get("approved") is True,
        approver if isinstance(approver, str) else None,
        reason if isinstance(reason, str) else None,
    )


def human_approval(state: IncidentState) -> dict[str, Any]:
    """Pause the run and wait for an operator decision (ADR-007).

    Everything above :func:`interrupt` is side-effect free. LangGraph re-runs
    this node from the top when the run resumes with ``Command(resume=...)``, so
    anything written, logged, or executed before the interrupt would happen
    twice. The payload is exactly what an operator needs to decide, and the
    decision comes back as :func:`interrupt`'s return value.

    The node records the decision only; it never decides whether an action may
    run. ``execute_remediation`` still enforces the allowlist, so an approval
    cannot widen what the run is permitted to do.
    """
    incident = _incident_of(state)
    plan = state.get("plan")
    if plan is None:
        return {"approval": ApprovalDecision(approved=False, reason="no plan to approve")}

    decision = interrupt(
        {
            "incident_id": incident.incident_id,
            "action": plan.action,
            "risk_level": int(plan.risk_level),
            "parameters": plan.parameters,
        }
    )
    approved, approver, reason = _read_decision(decision)
    logger.info(
        "human_approval decision incident_id=%s action=%s approved=%s approver=%s",
        incident.incident_id,
        plan.action,
        approved,
        approver,
    )
    return {
        "approval": ApprovalDecision(
            approved=approved,
            approver=approver,
            reason=reason,
            decided_at=_now(),
        )
    }


def execute_remediation(state: IncidentState) -> dict[str, Any]:
    """Execute the approved plan through the registry, deny-by-default.

    Only a registered mutating tool may run. A missing plan, an unknown action,
    or a read-only action is denied: nothing is executed and the node returns a
    failed result explaining the allowlist violation. This node never raises, so
    the graph always has a remediation result to verify.
    """
    plan = state.get("plan")

    if plan is None:
        error = "no remediation plan to execute"
        logger.warning("execute deny reason=no_plan")
        return {
            "execution_result": RemediationResult(
                action="none",
                outcome=RemediationOutcome.failed,
                executed_at=_now(),
                error=error,
            )
        }

    action = plan.action
    risk = int(plan.risk_level)
    registry = get_tool_registry(settings)

    try:
        tool = registry.get(action)
    except UnknownToolError:
        error = (
            f"action '{action}' was not executed: it is not an allowlisted "
            "remediation action"
        )
        logger.warning("execute deny action=%s risk=%d reason=not_allowlisted", action, risk)
        return {
            "execution_result": RemediationResult(
                action=action,
                outcome=RemediationOutcome.failed,
                executed_at=_now(),
                error=error,
            )
        }

    if tool.spec.read_only:
        error = (
            f"action '{action}' was not executed: it is a read-only tool, not a "
            "remediation action"
        )
        logger.warning("execute deny action=%s risk=%d reason=read_only", action, risk)
        return {
            "execution_result": RemediationResult(
                action=action,
                outcome=RemediationOutcome.failed,
                executed_at=_now(),
                error=error,
            )
        }

    logger.info("execute allow action=%s risk=%d", action, risk)
    try:
        output = registry.invoke(action, **plan.parameters)
    except Exception as exc:  # noqa: BLE001 - any failure becomes a failed result
        logger.warning("execute failed action=%s risk=%d error=%s", action, risk, exc)
        return {
            "execution_result": RemediationResult(
                action=action,
                outcome=RemediationOutcome.failed,
                executed_at=_now(),
                error=str(exc),
            )
        }

    return {
        "execution_result": RemediationResult(
            action=action,
            outcome=RemediationOutcome.succeeded,
            executed_at=_now(),
            output=json.dumps(output, default=str),
        )
    }


def _as_utc(moment: datetime) -> datetime:
    """Return ``moment`` as an aware UTC datetime, reading a naive value as UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _log_entry_time(entry: Any) -> datetime | None:
    """Return a log entry's timestamp as an aware UTC datetime, or ``None``.

    The app stamps every entry with an ISO-8601 instant. ``None`` means the
    instant could not be read, which is deliberately *not* the same as "before
    the run": the caller must never treat undatable evidence as absent.
    """
    if not isinstance(entry, Mapping):
        return None
    raw = entry.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return _as_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _count_errors_since(entries: Any, since: datetime) -> int:
    """Count error entries the app logged at or after ``since``.

    Verification asks whether the application is unhealthy *now*, so an error
    that predates the current run is history rather than evidence about this
    remediation: an earlier fault's log entries must not fail a later, correctly
    remediated run. The check is not weakened — a response with no readable
    entries, or an entry whose timestamp cannot be read, still counts, so
    unreadable or undatable evidence is never silently discarded.
    """
    if not isinstance(entries, list):
        raise ValueError("error log response carried no entries")
    window_start = _as_utc(since)
    counted = 0
    for entry in entries:
        logged_at = _log_entry_time(entry)
        if logged_at is None or logged_at >= window_start:
            counted += 1
    return counted


def verify_remediation(state: IncidentState) -> dict[str, Any]:
    """Check real metrics, health, and logs after the action.

    Verification is deterministic and evidence-based: it is true only when the
    app reports health ``ok``, ``error_rate == 0``, CPU strictly below
    ``settings.healthy_cpu_threshold``, p95 latency strictly below
    ``settings.healthy_latency_ms_threshold``, and no error-level log entries
    logged since this run began. Errors from an earlier incident are history,
    not evidence about this remediation, so they cannot fail the run — but a
    service that is still degraded keeps logging, and those entries do fail it.
    A failed read leaves its check false, so missing evidence is never verified.
    """
    incident = _incident_of(state)
    logger.info("verify incident_id=%s", incident.incident_id)
    registry = get_tool_registry(settings)
    problems: list[str] = []

    health_ok = False
    try:
        health = registry.invoke("get_app_health")
        health_ok = bool(health.get("ok"))
        if not health_ok:
            problems.append(f"health is '{health.get('status')}', not ok")
    except Exception as exc:  # noqa: BLE001 - failure means incomplete evidence
        problems.append(f"health check failed: {exc}")

    metrics_ok = False
    try:
        metrics = registry.invoke("get_app_metrics")
        error_rate = metrics.get("error_rate")
        cpu = metrics.get("cpu_percent")
        latency = metrics.get("latency_ms_p95")
        metrics_ok = (
            error_rate == 0
            and cpu is not None
            and float(cpu) < settings.healthy_cpu_threshold
            and latency is not None
            and float(latency) < settings.healthy_latency_ms_threshold
        )
        if not metrics_ok:
            problems.append(
                f"metrics not healthy: cpu_percent={cpu} "
                f"(< {settings.healthy_cpu_threshold}), latency_ms_p95={latency} "
                f"(< {settings.healthy_latency_ms_threshold}), error_rate={error_rate}"
            )
    except Exception as exc:  # noqa: BLE001 - failure means incomplete evidence
        problems.append(f"metrics check failed: {exc}")

    logs_ok = False
    try:
        errors = registry.invoke("get_recent_errors", limit=_LOG_LIMIT)
        error_count = _count_errors_since(errors.get("entries"), incident.detected_at)
        logs_ok = error_count == 0
        if not logs_ok:
            problems.append(f"{error_count} error-level log entries since the run began")
    except Exception as exc:  # noqa: BLE001 - failure means incomplete evidence
        problems.append(f"error log check failed: {exc}")

    verified = health_ok and metrics_ok and logs_ok
    if verified:
        summary = (
            "verification passed: health ok, metrics within healthy thresholds, "
            "no error-level logs since the run began"
        )
    else:
        summary = "verification failed: " + "; ".join(problems)

    logger.info("verify verified=%s attempts=%d", verified, state.get("attempts", 0))
    update: dict[str, Any] = {
        "verification": VerificationResult(
            verified=verified,
            metrics_ok=metrics_ok,
            health_ok=health_ok,
            logs_ok=logs_ok,
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
