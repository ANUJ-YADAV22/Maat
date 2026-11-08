"""Prompt assembly. Order: system, rules, memory, tools, workflow, task (spec section 7).

The format is line-oriented so the MockBackend can read it exactly like a model would.
"""

from __future__ import annotations

import json
from typing import Any

from maat.fmt import fmt_num

SYSTEM = (
    "You are a site-safety and code-compliance assistant. Follow the rules, use the memory and "
    "tool results, and follow the workflow steps in order."
)


def build_prompt(
    family: str,
    user_input: str,
    rules: list[dict[str, Any]],
    memory: list[dict[str, Any]],
    policy: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    workflow: list[str],
) -> str:
    """Assemble the full prompt for one task."""
    lines = ["### SYSTEM", SYSTEM, "### RULES"]
    for r in rules:
        scope = ",".join(r.get("applies_to") or []) or "*"
        lines.append(f"- [{r['id']}] (applies_to={scope}) {r['text']}")
    lines.append("### MEMORY")
    for m in memory:
        lines.append(
            f"- [{m['id']}] subject={m['subject']} | attribute={m['attribute']} "
            f"| value={fmt_num(m['value'])}"
        )
    lines.append("### TOOLS")
    if policy:
        lines.append(
            f"policy: require={','.join(policy.get('require', []))}; "
            f"ground={','.join(policy.get('ground', []))}"
        )
    else:
        lines.append("policy: none")
    for c in tool_calls:
        result = c["result"]
        if isinstance(result, float):
            result = float(fmt_num(result))
        lines.append(f"- {c['tool']}({', '.join(map(str, c['args']))}) -> {json.dumps(result)}")
    lines.append("### WORKFLOW")
    lines += [f"{i}. {s}" for i, s in enumerate(workflow, 1)]
    lines += ["### TASK", f"family: {family}", f"input: {user_input}"]
    return "\n".join(lines)
