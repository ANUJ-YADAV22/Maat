"""Deterministic, config-sensitive mock LLM.

It reads the same line-oriented prompt a real model would and is a pure function of
(rules, memory, tool results, workflow, input, seed). Behavioural hooks:

* Memory item with matching (subject, attribute) overrides the stale default answer.
* Tool policy ``ground`` containing clause_lookup forces the answer from the KB tool result.
* Rule containing ``ROUND_UP_TO:<n>`` rounds every numeric answer up to a multiple of n,
  regardless of the rule's applies_to (models a leaky, over-generalised directive).
* Rule containing ``SKIP_CHECK:<item>`` removes that item from checklist output
  (honours applies_to).
* Workflow step ``verify_units`` makes CONVERT answers correct; without it the number is
  returned unconverted (a classic unit error).
* Checklist items exist only if their ``ask_*`` workflow step exists; tender fields only if
  their ``extract_*`` step exists; calculator results are used only if the calculator ran.
* ``noise`` (probability) reverts to the stale answer, derived from hash(seed, input).

Latency and token counts are simulated (a function of prompt length), never wall-clock.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from maat.fmt import fmt_num
from maat.llm.base import LLMResult
from maat.textparse import parse_compute, parse_convert, parse_kv, parse_qa
from maat.units import convert

STALE_NUMBER = 25.0
STALE_TEXT = "minor"
STEP_ITEM = {"ask_ppe": "ppe_check", "ask_permit": "permit_to_work"}
TENDER_SOURCE_KEY = {"deadline": "deadline", "emd": "emd_inr", "eligibility": "eligibility"}


def _section(prompt: str, name: str) -> list[str]:
    m = re.search(rf"### {name}\n(.*?)(?=\n### |\Z)", prompt, re.S)
    return [ln for ln in m.group(1).split("\n") if ln.strip()] if m else []


def _value(raw: str) -> float | str:
    try:
        return float(raw)
    except ValueError:
        return raw


def _unit_rand(seed: int, text: str) -> float:
    digest = hashlib.sha256(f"{seed}|{text}".encode()).hexdigest()
    return int(digest[:8], 16) / 2**32


class MockBackend:
    """Rule-based stand-in for the frozen LLM."""

    name = "mock"

    def __init__(self, noise: float = 0.0) -> None:
        self.noise = noise

    # ---------------------------------------------------------------- parsing
    @staticmethod
    def _parse(prompt: str) -> dict[str, Any]:
        rules = []
        for ln in _section(prompt, "RULES"):
            m = re.match(r"- \[(\S+)\] \(applies_to=([^)]*)\) (.*)$", ln)
            if m:
                scope = [] if m.group(2) == "*" else m.group(2).split(",")
                rules.append({"id": m.group(1), "applies_to": scope, "text": m.group(3)})
        memory = []
        for ln in _section(prompt, "MEMORY"):
            m = re.match(r"- \[(\S+)\] subject=(.*?) \| attribute=(.*?) \| value=(.*)$", ln)
            if m:
                memory.append(
                    {
                        "id": m.group(1),
                        "subject": m.group(2),
                        "attribute": m.group(3),
                        "value": _value(m.group(4)),
                    }
                )
        ground: list[str] = []
        tools: list[dict[str, Any]] = []
        for ln in _section(prompt, "TOOLS"):
            if ln.startswith("policy:"):
                g = re.search(r"ground=([^;]*)", ln)
                ground = [t for t in (g.group(1).split(",") if g else []) if t]
            else:
                m = re.match(r"- (\w+)\((.*)\) -> (.*)$", ln)
                if m:
                    tools.append({"tool": m.group(1), "result": json.loads(m.group(3))})
        steps = [re.sub(r"^\d+\. ", "", ln) for ln in _section(prompt, "WORKFLOW")]
        task = _section(prompt, "TASK")
        family = task[0].split(": ", 1)[1]
        user_input = task[1].split(": ", 1)[1]
        return {
            "rules": rules,
            "memory": memory,
            "ground": ground,
            "tools": tools,
            "steps": steps,
            "family": family,
            "input": user_input,
        }

    # --------------------------------------------------------------- behaviours
    @staticmethod
    def _round_up(value: float, rules: list[dict[str, Any]]) -> float:
        for r in rules:
            m = re.search(r"ROUND_UP_TO:(\d+(?:\.\d+)?)", r["text"])
            if m:
                n = float(m.group(1))
                value = math.ceil(value / n - 1e-12) * n
        return value

    def _qa(self, ctx: dict[str, Any], stale: bool) -> str:
        attr, subj = parse_qa(ctx["input"]) or ("value", "unknown")
        value: float | str = STALE_TEXT if attr == "severity" else STALE_NUMBER
        if not stale:
            hit = next(
                (m for m in ctx["memory"] if m["subject"] == subj and m["attribute"] == attr), None
            )
            if hit:
                value = hit["value"]
            tool = next((t for t in ctx["tools"] if t["tool"] == "clause_lookup"), None)
            if tool and "clause_lookup" in ctx["ground"] and isinstance(tool["result"], dict):
                value = tool["result"]["value"]
        if isinstance(value, float):
            value = self._round_up(value, ctx["rules"])
        return f"The {attr} of {subj} is {fmt_num(value)}."

    def _unit(self, ctx: dict[str, Any], stale: bool) -> str:
        conv = parse_convert(ctx["input"])
        if conv:
            val, src, dst = conv
            result = val
            if "verify_units" in ctx["steps"] and not stale:
                result = convert(val, src, dst) or val
            result = self._round_up(result, ctx["rules"])
            return f"Result: {fmt_num(result)} {dst}"
        if parse_compute(ctx["input"]) is None:
            return "Result: unknown"
        calc = next((t for t in ctx["tools"] if t["tool"] == "calculator"), None)
        if stale or calc is None or not isinstance(calc["result"], int | float):
            return "Result: unknown"
        return f"Result: {fmt_num(self._round_up(float(calc['result']), ctx['rules']))}"

    @staticmethod
    def _checklist(ctx: dict[str, Any]) -> str:
        items = [STEP_ITEM.get(s, s[4:]) for s in ctx["steps"] if s.startswith("ask_")]
        skipped = set()
        for r in ctx["rules"]:
            if not r["applies_to"] or ctx["family"] in r["applies_to"]:
                skipped |= set(re.findall(r"SKIP_CHECK:(\w+)", r["text"]))
        return "CHECKLIST:\n" + "\n".join(f"- {i}" for i in items if i not in skipped)

    @staticmethod
    def _tender(ctx: dict[str, Any]) -> str:
        source = parse_kv(ctx["input"])
        out = {}
        for step in ctx["steps"]:
            if step.startswith("extract_"):
                field = step[len("extract_") :]
                key = TENDER_SOURCE_KEY.get(field, field)
                if key in source:
                    out[field] = source[key]
        return json.dumps(out, sort_keys=True)

    # --------------------------------------------------------------- interface
    def generate(
        self,
        prompt: str,
        seed: int,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        ctx = self._parse(prompt)
        stale = self.noise > 0 and _unit_rand(seed, ctx["input"]) < self.noise
        family = ctx["family"]
        if family in ("clause_query", "incident_triage"):
            text = self._qa(ctx, stale)
        elif family == "unit_calc":
            text = self._unit(ctx, stale)
        elif family == "safety_checklist":
            text = self._checklist(ctx)
        elif family == "tender_extract":
            text = self._tender(ctx)
        else:
            text = "unsupported family"
        tokens_in, tokens_out = len(prompt) // 4, len(text) // 4 + 1
        return {
            "text": text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": 20.0 + 0.5 * tokens_in,
        }
