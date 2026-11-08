"""Deterministic task checkers: contains_all, regex, numeric_close, tool_called, checklist_covers,
fields_present. Used by the gate (witness, replay) and the evaluation harness."""

from __future__ import annotations

import json
import math
import re
from typing import Any

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def checklist_items(answer: str) -> set[str]:
    """Items of a 'CHECKLIST:' answer (lines starting with '- ')."""
    return {ln[2:].strip() for ln in answer.splitlines() if ln.startswith("- ")}


def run_checker(checker: dict[str, Any], answer: str, trace: dict[str, Any] | None = None) -> bool:
    """Evaluate one checker against an answer (and trace for tool_called)."""
    kind = checker["type"]
    if kind == "contains_all":
        low = answer.lower()
        return all(str(i).lower() in low for i in checker["items"])
    if kind == "regex":
        return re.search(checker["pattern"], answer, re.I) is not None
    if kind == "numeric_close":
        m = NUM_RE.search(answer)
        if m is None:
            return False
        return math.isclose(
            float(m.group()),
            float(checker["expected"]),
            rel_tol=checker.get("rel_tol", 1e-6),
            abs_tol=checker.get("abs_tol", 1e-9),
        )
    if kind == "tool_called":
        return any(c["tool"] == checker["tool"] for c in (trace or {}).get("tool_calls", []))
    if kind == "checklist_covers":
        return set(checker["items"]) <= checklist_items(answer)
    if kind == "fields_present":
        try:
            data = json.loads(answer)
        except json.JSONDecodeError:
            return False
        if not isinstance(data, dict) or not all(f in data for f in checker["fields"]):
            return False
        return all(str(data.get(k)) == str(v) for k, v in checker.get("values", {}).items())
    raise ValueError(f"unknown checker type: {kind}")
