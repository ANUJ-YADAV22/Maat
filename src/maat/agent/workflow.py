"""Workflow execution: which tools a config's policy and workflow steps cause to run."""

from __future__ import annotations

from typing import Any

from maat.agent.tools import calculator, clause_lookup
from maat.kb import KnowledgeBase
from maat.textparse import parse_compute, parse_qa

TOOL_FOR_STEP = {"lookup_clause": "clause_lookup", "compute": "calculator"}


def wanted_tools(policy: dict[str, Any] | None, steps: list[str]) -> list[str]:
    """Tools to call: policy.require + policy.ground + step-triggered, ordered by policy.order."""
    wanted: list[str] = []
    for tool in (policy or {}).get("require", []) + (policy or {}).get("ground", []):
        if tool not in wanted:
            wanted.append(tool)
    for step in steps:
        tool = TOOL_FOR_STEP.get(step)
        if tool and tool not in wanted:
            wanted.append(tool)
    order = (policy or {}).get("order", [])
    return sorted(wanted, key=lambda t: order.index(t) if t in order else len(order))


def execute_tools(
    kb: KnowledgeBase, text: str, policy: dict[str, Any] | None, steps: list[str]
) -> list[dict[str, Any]]:
    """Run each wanted tool whose arguments can be parsed from the input; return call records."""
    calls: list[dict[str, Any]] = []
    for tool in wanted_tools(policy, steps):
        if tool == "clause_lookup" and (qa := parse_qa(text)):
            attr, subj = qa
            calls.append(
                {"tool": tool, "args": [subj, attr], "result": clause_lookup(kb, subj, attr)}
            )
        elif tool == "calculator" and (expr := parse_compute(text)):
            try:
                result: Any = calculator(expr)
            except (ValueError, SyntaxError, ZeroDivisionError) as exc:
                result = {"error": str(exc)}
            calls.append({"tool": tool, "args": [expr], "result": result})
    return calls
