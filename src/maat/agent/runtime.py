"""Agent runtime: frozen LLM + active config -> answer + trace."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from maat.agent.prompt import build_prompt
from maat.agent.retrieval import retrieve
from maat.agent.workflow import execute_tools
from maat.kb import KnowledgeBase
from maat.llm.base import LLMBackend

LEAKY_DIRECTIVE = (
    "ROUND_UP_TO:"  # unscoped directives leak across families (models over-generalise)
)


def select_rules(rules: list[dict[str, Any]], family: str) -> list[dict[str, Any]]:
    """Rules active for a family, plus out-of-scope rules carrying a leaky unscoped directive."""
    out = []
    for r in rules:
        scope = r.get("applies_to") or []
        if not scope or family in scope or LEAKY_DIRECTIVE in r["text"]:
            out.append(r)
    return out


def trace_elements(trace: dict[str, Any]) -> list[str]:
    """Every config element that influenced an answer (used by blame localization)."""
    elems = [f"memory:{i}" for i in trace["memory_ids"]]
    elems += [f"rule:{i}" for i in trace["rule_ids"]]
    if trace.get("tool_policy") is not None:
        elems.append(f"tool_policy:{trace['family']}")
    elems += [f"workflow:{trace['family']}:{s}" for s in trace["workflow_steps"]]
    return elems


class Agent:
    """Runs one task against a config; deterministic for deterministic backends."""

    def __init__(self, backend: LLMBackend, kb: KnowledgeBase) -> None:
        self.backend = backend
        self.kb = kb

    def run(self, task: Mapping[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        family, text = task["family"], task["input"]
        steps = list(config["workflow"].get(family, []))
        policy = config["tool_policy"].get(family)
        memory = retrieve(config["memory"], text) if "retrieve" in steps else []
        rules = select_rules(config["rules"], family)
        tool_calls = execute_tools(self.kb, text, policy, steps)
        prompt = build_prompt(family, text, rules, memory, policy, tool_calls, steps)
        out = self.backend.generate(prompt, seed)
        trace = {
            "family": family,
            "memory_ids": [m["id"] for m in memory],
            "rule_ids": [r["id"] for r in rules],
            "tool_policy": policy,
            "tool_calls": tool_calls,
            "workflow_steps": steps,
        }
        return {
            "answer": out["text"],
            "trace": trace,
            "latency_ms": out["latency_ms"],
            "tokens_in": out["tokens_in"],
            "tokens_out": out["tokens_out"],
        }
