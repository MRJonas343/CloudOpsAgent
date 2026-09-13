"""Assemble the deterministic incident workflow graph.

The graph is the explicit state machine described in ``docs/ARCHITECTURE.md``:

    Analyze -> Collect Context -> Investigate -> Diagnose -> Plan
      -> Human Approval -> Execute -> Verify -> (Close | back to Investigate)

Nodes are mocks for now (see ``cloudops_agent.graph.nodes``); the LLM calls and
registered tools arrive in later phases.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from cloudops_agent.graph.nodes import (
    analyze_incident,
    close_incident,
    collect_context,
    diagnose,
    execute_remediation,
    human_approval,
    investigate,
    plan_remediation,
    route_after_approval,
    route_after_plan,
    route_after_verify,
    verify_remediation,
)
from cloudops_agent.graph.state import IncidentState
from cloudops_agent.models import Incident


def build_graph():
    """Build and compile the deterministic incident workflow."""
    builder = StateGraph(IncidentState)

    builder.add_node("analyze_incident", analyze_incident)
    builder.add_node("collect_context", collect_context)
    builder.add_node("investigate", investigate)
    builder.add_node("diagnose", diagnose)
    builder.add_node("plan_remediation", plan_remediation)
    builder.add_node("human_approval", human_approval)
    builder.add_node("execute_remediation", execute_remediation)
    builder.add_node("verify_remediation", verify_remediation)
    builder.add_node("close_incident", close_incident)

    builder.add_edge(START, "analyze_incident")
    builder.add_edge("analyze_incident", "collect_context")
    builder.add_edge("collect_context", "investigate")
    builder.add_edge("investigate", "diagnose")
    builder.add_edge("diagnose", "plan_remediation")

    builder.add_conditional_edges(
        "plan_remediation",
        route_after_plan,
        {"human_approval": "human_approval", "execute_remediation": "execute_remediation"},
    )
    builder.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {"execute_remediation": "execute_remediation", END: END},
    )
    builder.add_edge("execute_remediation", "verify_remediation")
    builder.add_conditional_edges(
        "verify_remediation",
        route_after_verify,
        {"investigate": "investigate", "close_incident": "close_incident", END: END},
    )
    builder.add_edge("close_incident", END)

    return builder.compile()


def initial_state(incident: Incident) -> IncidentState:
    """Return a complete starting state for a workflow run."""
    return {
        "incident": incident,
        "observations": [],
        "hypotheses": [],
        "diagnosis": None,
        "plan": None,
        "approval": None,
        "execution_result": None,
        "verification": None,
        "summary": None,
        "messages": [],
        "attempts": 0,
    }


agent = build_graph()
