"""Patch proposers. RuleBasedProposer is deterministic and parses structured claims; the
LLM-backed proposer (Phase 7) plugs into the same interface."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from maat.checkers import NUM_RE, checklist_items
from maat.config_model import Op
from maat.contracts import (
    Claim,
    DeclaredScope,
    Expiry,
    PatchContract,
    Provenance,
    RiskTier,
    WitnessTest,
    make_patch_id,
)
from maat.feedback.signals import infer_family
from maat.fmt import fmt_num
from maat.proposal.cluster import Cluster

SAFETY_WORDS = re.compile(r"harness|ppe|permit|safety|inspection|edge|check", re.I)


@dataclass
class ProposalResult:
    """Either a complete patch or the reason it could not be built (rejected before the gate)."""

    patch: PatchContract | None
    reason: str = ""
    feedback_ids: tuple[str, ...] = ()


class Proposer(Protocol):
    name: str

    def propose(
        self,
        cluster: Cluster,
        events: dict[str, dict[str, Any]],
        tasks: dict[str, dict[str, Any]],
        config: dict[str, Any],
    ) -> list[ProposalResult]: ...


def coerce_value(value: Any) -> float | str:
    """Numeric-looking strings become floats so memory values compare and round correctly."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    return float(text) if re.fullmatch(r"-?\d+(?:\.\d+)?", text) else text


def witness_for_claim(claim: Claim, task: dict[str, Any] | None) -> WitnessTest | None:
    """Witness for a factual claim: the question whose corrected answer the claim implies."""
    if not claim.is_factual:
        return None
    family = infer_family(claim.model_dump())
    if family not in ("clause_query", "incident_triage"):
        return None
    subj, attr, value = claim.subject, claim.attribute, claim.value
    text = f"What is the {attr} of {subj}?"
    if task and task["family"] == family and subj in task["input"].lower():
        text = task["input"]
    if isinstance(value, float):
        checker = {
            "type": "regex",
            "pattern": rf"\bis {re.escape(fmt_num(value))}\b",
            "expected": value,
        }
    else:
        checker = {"type": "contains_all", "items": [str(value)], "expected": value}
    return WitnessTest(family=family, input=text, checker=checker)


def witness_from_edit(task: dict[str, Any], edit_text: str) -> WitnessTest | None:
    """Witness derived from a user's corrected answer to a concrete task."""
    family, original = task["family"], task["answer"] or ""
    if family == "safety_checklist":
        added = checklist_items(edit_text) - checklist_items(original)
        removed = checklist_items(original) - checklist_items(edit_text)
        if not added and not removed:
            return None
        pattern = "^" + "".join(rf"(?=[\s\S]*- {re.escape(i)})" for i in sorted(added))
        pattern += "".join(rf"(?![\s\S]*- {re.escape(i)})" for i in sorted(removed))
        return WitnessTest(
            family=family, input=task["input"], checker={"type": "regex", "pattern": pattern}
        )
    if family == "unit_calc":
        m = NUM_RE.search(edit_text)
        if m:
            checker = {"type": "numeric_close", "expected": float(m.group())}
            return WitnessTest(family=family, input=task["input"], checker=checker)
    if family == "tender_extract":
        try:
            data = json.loads(edit_text)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict) and data:
            checker = {
                "type": "fields_present",
                "fields": sorted(data),
                "values": {k: str(v) for k, v in data.items()},
            }
            return WitnessTest(family=family, input=task["input"], checker=checker)
    return None


def provisional_tier(patch_type: str, family: str, text: str = "") -> RiskTier:
    """Provisional risk tier; Lock 1 (Screen) recomputes it authoritatively in Phase 3."""
    if patch_type == "tool_policy":
        return "high"
    if patch_type == "instruction_rule":
        return "high" if SAFETY_WORDS.search(text) or family == "safety_checklist" else "low"
    if patch_type == "workflow_step":
        return "high" if family == "safety_checklist" else "medium"
    return "medium"


def build_patch(
    patch_type: str,
    ops: list[Op],
    claim: Claim,
    witness: WitnessTest,
    scope: DeclaredScope,
    feedback_ids: list[str],
    proposer: str,
    risk_tier: RiskTier,
    depends_on: list[str] | None = None,
) -> PatchContract:
    """Assemble a complete contract (also used by blame-driven tool/workflow patches)."""
    return PatchContract(
        patch_id=make_patch_id(patch_type, ops, claim),
        type=patch_type,
        ops=ops,
        claim=claim,
        witness_test=witness,
        declared_scope=scope,
        risk_tier=risk_tier,
        provenance=Provenance(feedback_ids=feedback_ids, proposer=proposer),
        expiry=Expiry(depends_on=depends_on or []),
    )


def tool_policy_patch(
    config: dict[str, Any],
    family: str,
    ground: list[str],
    witness: WitnessTest,
    feedback_ids: list[str],
    proposer: str = "rule_based",
) -> PatchContract:
    """Patch that makes ``family`` answer from the given tools' output."""
    cur = config["tool_policy"].get(family, {"require": [], "ground": [], "order": []})
    new = {
        "require": sorted(set(cur["require"]) | set(ground)),
        "ground": sorted(set(cur["ground"]) | set(ground)),
        "order": cur["order"] or ground,
    }
    op = Op(
        op="replace" if family in config["tool_policy"] else "add",
        path=f"tool_policy/{family}",
        value=new,
    )
    claim = Claim(
        subject=family,
        attribute="tool_policy",
        value=",".join(sorted(ground)),
        text=f"{family} must ground answers on {', '.join(ground)}",
    )
    scope = DeclaredScope(task_types=[family])
    return build_patch("tool_policy", [op], claim, witness, scope, feedback_ids, proposer, "high")


def workflow_step_patch(
    family: str,
    step: str,
    index: int | None,
    witness: WitnessTest,
    feedback_ids: list[str],
    proposer: str = "rule_based",
) -> PatchContract:
    """Patch that inserts ``step`` into ``family``'s workflow."""
    op = Op(op="add", path=f"workflow/{family}", value={"step": step, "index": index})
    claim = Claim(
        subject=family,
        attribute="workflow_step",
        value=step,
        text=f"{family} workflow needs step {step}",
    )
    scope = DeclaredScope(task_types=[family])
    return build_patch(
        "workflow_step",
        [op],
        claim,
        witness,
        scope,
        feedback_ids,
        proposer,
        provisional_tier("workflow_step", family),
    )


class RuleBasedProposer:
    """Deterministic proposer: one memory_note per distinct factual claim, one instruction_rule
    per distinct rule claim. Anything that cannot fill every contract field is reported."""

    name = "rule_based"

    def propose(
        self,
        cluster: Cluster,
        events: dict[str, dict[str, Any]],
        tasks: dict[str, dict[str, Any]],
        config: dict[str, Any],
    ) -> list[ProposalResult]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for eid in cluster.counted_event_ids:
            ev = events[eid]
            claim = ev.get("claim_json")
            if not claim:
                groups.setdefault("__none__", []).append(ev)
                continue
            key = json.dumps(
                [
                    claim.get("subject"),
                    claim.get("attribute"),
                    str(claim.get("value")),
                    claim.get("rule_text"),
                ],
                default=str,
            )
            groups.setdefault(key, []).append(ev)
        results: list[ProposalResult] = []
        for key, evs in groups.items():
            ids = tuple(e["event_id"] for e in evs)
            if key == "__none__":
                results.append(ProposalResult(None, "no structured claim in feedback", ids))
                continue
            results.append(self._one(evs, config, tasks, ids))
        return results

    def _one(
        self,
        evs: list[dict[str, Any]],
        config: dict[str, Any],
        tasks: dict[str, dict[str, Any]],
        ids: tuple[str, ...],
    ) -> ProposalResult:
        raw = evs[0]["claim_json"]
        if raw.get("rule_text"):
            return self._rule(raw, evs, tasks, ids)
        return self._memory(raw, evs, tasks, config, ids)

    def _memory(
        self,
        raw: dict[str, Any],
        evs: list[dict[str, Any]],
        tasks: dict[str, dict[str, Any]],
        config: dict[str, Any],
        ids: tuple[str, ...],
    ) -> ProposalResult:
        if not all(raw.get(k) is not None for k in ("subject", "attribute", "value")):
            return ProposalResult(None, "claim needs subject, attribute and value", ids)
        claim = Claim(
            subject=str(raw["subject"]).lower(),
            attribute=str(raw["attribute"]).lower(),
            value=coerce_value(raw["value"]),
            source=raw.get("source"),
            text=evs[0].get("text") or "",
        )
        task = next((tasks[e["task_id"]] for e in evs if e.get("task_id") in tasks), None)
        witness = witness_for_claim(claim, task)
        if witness is None:
            return ProposalResult(None, "cannot build a witness test for this claim", ids)
        existing = next(
            (
                m
                for m in config["memory"]
                if m["subject"] == claim.subject and m["attribute"] == claim.attribute
            ),
            None,
        )
        if existing and coerce_value(existing["value"]) == claim.value:
            return ProposalResult(None, "config already holds this value", ids)
        digest = hashlib.sha256(claim.normalized_key().encode()).hexdigest()[:6]
        item_id = existing["id"] if existing else f"m_{digest}"
        item = {
            "id": item_id,
            "subject": claim.subject,
            "attribute": claim.attribute,
            "value": claim.value,
            "protected": False,
            "source_patch": None,
            "text": f"{claim.subject} {claim.attribute} is {fmt_num(claim.value)}",
        }
        op = Op(op="replace" if existing else "add", path=f"memory/{item_id}", value=item)
        family = witness.family
        scope = DeclaredScope(task_types=[family], conditions={"subject_keys": [claim.subject]})
        patch = build_patch(
            "memory_note",
            [op],
            claim,
            witness,
            scope,
            list(ids),
            self.name,
            provisional_tier("memory_note", family),
            [f"kb:{claim.subject}/{claim.attribute}"],
        )
        item["source_patch"] = patch.patch_id
        return ProposalResult(patch, "", ids)

    def _rule(
        self,
        raw: dict[str, Any],
        evs: list[dict[str, Any]],
        tasks: dict[str, dict[str, Any]],
        ids: tuple[str, ...],
    ) -> ProposalResult:
        task = next((tasks[e["task_id"]] for e in evs if e.get("task_id") in tasks), None)
        edit = next((e["edit_text"] for e in evs if e.get("edit_text")), None)
        if task is None or edit is None:
            return ProposalResult(
                None,
                "rule feedback needs a task and corrected output to derive a witness test",
                ids,
            )
        witness = witness_from_edit(task, edit)
        if witness is None:
            return ProposalResult(None, "cannot build a witness test from this edit", ids)
        claim = Claim(
            rule_text=raw["rule_text"],
            applies_to=raw.get("applies_to") or [],
            text=evs[0].get("text") or "",
        )
        digest = hashlib.sha256(claim.normalized_key().encode()).hexdigest()[:6]
        item = {
            "id": f"r_{digest}",
            "text": claim.rule_text,
            "applies_to": claim.applies_to,
            "protected": False,
        }
        op = Op(op="add", path=f"rules/{item['id']}", value=item)
        scope = DeclaredScope(task_types=claim.applies_to or [witness.family])
        patch = build_patch(
            "instruction_rule",
            [op],
            claim,
            witness,
            scope,
            list(ids),
            self.name,
            provisional_tier("instruction_rule", witness.family, claim.rule_text),
        )
        return ProposalResult(patch, "", ids)
