"""Counterfactual blame localization and the behaviour-patch proposer (spec 9.3).

For a failing task, replay with the full config, then ablate each config element the trace
used; ``blame = P(success | ablated) - P(success | full)``. Because some failures come from a
*missing* element, typed repairs (ground a tool, insert a workflow step) are scored the same
way. The top positive item picks the patch type, so behaviour alone yields tool-policy and
workflow-step patches.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from maat.agent.runtime import Agent, trace_elements
from maat.agent.tools import calculator
from maat.checkers import run_checker
from maat.config_model import Charter, Op
from maat.contracts import Claim, DeclaredScope, PatchContract, WitnessTest
from maat.kb import KnowledgeBase
from maat.proposal.proposer import (
    build_patch,
    provisional_tier,
    tool_policy_patch,
    witness_for_claim,
    workflow_step_patch,
)
from maat.textparse import parse_compute, parse_convert, parse_qa
from maat.units import convert

STEP_LIBRARY: dict[str, list[str]] = {
    "unit_calc": ["verify_units"],
    "safety_checklist": ["ask_fire_watch", "ask_gas_test"],
}
GROUND_TOOLS = ["clause_lookup"]
KIND_PRIORITY = {"workflow": 0, "tool_policy": 1, "rule": 2, "memory": 3}


@dataclass
class BlameItem:
    element: str  # e.g. "rule:r_003" or "repair:tool_policy:clause_lookup"
    kind: str  # ablation | repair
    target: str  # workflow | tool_policy | rule | memory
    blame: float
    edit: dict[str, Any] = field(default_factory=dict)


def pass_rate(
    agent: Agent,
    config: dict[str, Any],
    task: dict[str, Any],
    checker: dict[str, Any],
    seeds: list[int],
) -> float:
    ok = 0
    for s in seeds:
        out = agent.run(task, config, s)
        ok += run_checker(checker, out["answer"], out["trace"])
    return ok / len(seeds)


def ablate(config: dict[str, Any], element: str) -> dict[str, Any]:
    """Copy of ``config`` without one element (for measurement only)."""
    cfg = copy.deepcopy(config)
    kind, _, rest = element.partition(":")
    if kind == "memory":
        cfg["memory"] = [m for m in cfg["memory"] if m["id"] != rest]
    elif kind == "rule":
        cfg["rules"] = [r for r in cfg["rules"] if r["id"] != rest]
    elif kind == "tool_policy":
        cfg["tool_policy"].pop(rest, None)
    elif kind == "workflow":
        fam, _, step = rest.partition(":")
        cfg["workflow"][fam] = [x for x in cfg["workflow"].get(fam, []) if x != step]
    return cfg


def _protected(config: dict[str, Any], element: str, charter: Charter | None) -> bool:
    kind, _, rest = element.partition(":")
    if kind in ("memory", "rule"):
        items = config["memory" if kind == "memory" else "rules"]
        return any(i["id"] == rest and i.get("protected") for i in items)
    if charter is None:
        return False
    if kind == "workflow":
        fam, _, step = rest.partition(":")
        return step in charter.required_workflow_steps.get(fam, [])
    if kind == "tool_policy":
        return bool(charter.required_tools.get(rest))
    return False


def _insert_index(steps: list[str]) -> int | None:
    return steps.index("final") if "final" in steps else None


def localize(
    agent: Agent,
    config: dict[str, Any],
    task: dict[str, Any],
    checker: dict[str, Any],
    seeds: list[int],
    charter: Charter | None = None,
) -> list[BlameItem]:
    """Ranked blame for a failing task: ablations and typed repairs with positive blame."""
    full = pass_rate(agent, config, task, checker, seeds)
    family = task["family"]
    trace = agent.run(task, config, seeds[0])["trace"]
    items: list[BlameItem] = []
    for el in trace_elements(trace):
        if _protected(config, el, charter):
            continue
        b = pass_rate(agent, ablate(config, el), task, checker, seeds) - full
        if b > 0:
            target = {
                "memory": "memory",
                "rule": "rule",
                "tool_policy": "tool_policy",
                "workflow": "workflow",
            }[el.split(":")[0]]
            items.append(BlameItem(el, "ablation", target, b, {"remove": el}))
    policy = config["tool_policy"].get(family, {"require": [], "ground": [], "order": []})
    for tool in GROUND_TOOLS:
        if tool in policy["ground"] or family not in ("clause_query", "incident_triage"):
            continue
        cand = copy.deepcopy(config)
        cand["tool_policy"][family] = {
            "require": sorted(set(policy["require"]) | {tool}),
            "ground": sorted(set(policy["ground"]) | {tool}),
            "order": policy["order"] or [tool],
        }
        b = pass_rate(agent, cand, task, checker, seeds) - full
        if b > 0:
            items.append(
                BlameItem(
                    f"repair:tool_policy:{tool}", "repair", "tool_policy", b, {"ground": [tool]}
                )
            )
    steps = config["workflow"].get(family, [])
    for step in STEP_LIBRARY.get(family, []):
        if step in steps:
            continue
        cand = copy.deepcopy(config)
        idx = _insert_index(steps)
        cand["workflow"][family] = (
            (steps[:idx] + [step] + steps[idx:]) if idx is not None else steps + [step]
        )
        b = pass_rate(agent, cand, task, checker, seeds) - full
        if b > 0:
            items.append(
                BlameItem(
                    f"repair:workflow:{step}", "repair", "workflow", b, {"step": step, "index": idx}
                )
            )
    items.sort(key=lambda i: (-i.blame, i.kind != "repair", KIND_PRIORITY[i.target], i.element))
    return items


def witness_from_verifier(task: dict[str, Any], kb: KnowledgeBase) -> WitnessTest | None:
    """Expected behaviour for a redo'd task taken from an independent verifier, not the user."""
    family, text = task["family"], task["input"]
    if family in ("clause_query", "incident_triage") and (qa := parse_qa(text)):
        attr, subj = qa
        entry = kb.lookup(subj, attr)
        if entry is None:
            return None
        value = float(entry.value) if isinstance(entry.value, int | float) else entry.value
        return witness_for_claim(Claim(subject=subj, attribute=attr, value=value), task)
    if family == "unit_calc":
        truth = None
        if conv := parse_convert(text):
            truth = convert(*conv)
        elif expr := parse_compute(text):
            truth = calculator(expr)
        if truth is not None:
            return WitnessTest(
                family=family,
                input=text,
                checker={"type": "numeric_close", "expected": float(truth)},
            )
    return None


class BlameProposer:
    """Builds a behaviour patch (tool policy, workflow step, rule or memory disable)."""

    name = "blame"

    def __init__(self, agent: Agent, seeds: list[int], charter: Charter | None = None) -> None:
        self.agent, self.seeds, self.charter = agent, seeds, charter

    def propose(
        self,
        config: dict[str, Any],
        task: dict[str, Any],
        witness: WitnessTest,
        feedback_ids: list[str],
    ) -> tuple[PatchContract | None, str]:
        if pass_rate(self.agent, config, task, witness.checker, self.seeds) >= 0.5:
            return None, "task already passes: nothing to blame"
        ranked = localize(self.agent, config, task, witness.checker, self.seeds, self.charter)
        if not ranked:
            return None, "blame localization found no config element whose change fixes the task"
        top = ranked[0]
        fam = task["family"]
        w = WitnessTest(family=fam, input=task["input"], checker=witness.checker)
        if top.kind == "repair" and top.target == "tool_policy":
            return tool_policy_patch(
                config, fam, top.edit["ground"], w, feedback_ids, self.name
            ), ""
        if top.kind == "repair":
            return workflow_step_patch(
                fam, top.edit["step"], top.edit["index"], w, feedback_ids, self.name
            ), ""
        return self._ablation_patch(config, top, w, task, feedback_ids), ""

    def _ablation_patch(
        self,
        config: dict[str, Any],
        top: BlameItem,
        w: WitnessTest,
        task: dict[str, Any],
        ids: list[str],
    ) -> PatchContract:
        kind, _, rest = top.element.partition(":")
        fam = task["family"]
        subject = parse_qa(task["input"])
        conds = {"subject_keys": [subject[1]]} if subject and kind == "memory" else {}
        task_types = [fam]
        if kind == "memory":
            item = next(m for m in config["memory"] if m["id"] == rest)
            op, ptype = Op(op="remove", path=f"memory/{rest}"), "memory_note"
            claim = Claim(
                subject=item["subject"],
                attribute=item["attribute"],
                text=f"disable memory item {rest}",
            )
        elif kind == "rule":
            rule = next(r for r in config["rules"] if r["id"] == rest)
            op, ptype = Op(op="remove", path=f"rules/{rest}"), "instruction_rule"
            task_types = sorted(set(rule.get("applies_to") or [fam]) | {fam})
            claim = Claim(rule_text=rule["text"], text=f"remove rule {rest}")
        elif kind == "workflow":
            fam_, _, step = rest.partition(":")
            op, ptype = Op(op="remove", path=f"workflow/{fam_}/{step}"), "workflow_step"
            claim = Claim(subject=fam_, attribute="workflow_step", text=f"remove step {step}")
        else:
            op, ptype = Op(op="remove", path=f"tool_policy/{rest}"), "tool_policy"
            claim = Claim(subject=rest, attribute="tool_policy", text=f"remove tool policy {rest}")
        scope = DeclaredScope(task_types=task_types, conditions=conds)
        return build_patch(
            ptype,
            [op],
            claim,
            w,
            scope,
            ids,
            self.name,
            provisional_tier(ptype, fam, claim.rule_text or ""),
        )
