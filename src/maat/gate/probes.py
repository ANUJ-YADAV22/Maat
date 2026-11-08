"""Probe generation for Lock 5. Probes are compared base-vs-patched by output change, so they
need no checker. Invariance probes should not change; directional probes (paraphrases of the
witness) should."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from maat.contracts import PatchContract
from maat.gate.context import GateContext
from maat.proposal.paraphrase import paraphrases
from maat.textparse import parse_qa

ACTIVITIES = ["crane rigging", "facade access", "concrete pumping", "demolition work"]
COMPUTES = ["COMPUTE: 13*3", "COMPUTE: 7*11", "COMPUTE: 84/4", "COMPUTE: 19+23"]
CONVERTS = ["CONVERT: 1.5 m -> mm", "CONVERT: 3 kn -> n"]


@dataclass
class Probe:
    id: str
    family: str
    input: str
    kind: str  # regression | invariance | boundary | directional
    in_scope: bool
    subject: str | None = None

    def task(self) -> dict[str, Any]:
        return {"id": self.id, "family": self.family, "input": self.input, "checker": None}


def pid(family: str, text: str) -> str:
    return "pr_" + hashlib.sha256(f"{family}|{text}".encode()).hexdigest()[:10]


def in_scope(patch: PatchContract, family: str, subject: str | None) -> bool:
    scope = patch.declared_scope
    if family not in scope.task_types:
        return False
    keys = [k.lower() for k in scope.conditions.get("subject_keys", [])]
    return not keys or (subject is not None and subject.lower() in keys)


def _subject(family: str, text: str) -> str | None:
    qa = parse_qa(text)
    return qa[1] if qa and family in ("clause_query", "incident_triage") else None


def generated(ctx: GateContext, patch: PatchContract) -> list[tuple[str, str]]:
    """(family, input) pairs derived from the KB and templates, a few per family."""
    n = ctx.settings.probes_per_family
    out: list[tuple[str, str]] = []
    clauses = [e for e in ctx.kb.entries if e.attribute != "severity" and e.domain != "tender_docs"]
    out += [("clause_query", f"What is the {e.attribute} of {e.subject}?") for e in clauses[-n:]]
    if patch.claim.subject and patch.claim.attribute != "severity":  # same subject, other attribute
        out.append(("clause_query", f"What is the max_ratio of {patch.claim.subject}?"))
    sev = [e for e in ctx.kb.entries if e.attribute == "severity"]
    out += [
        ("incident_triage", f"Probe report. What is the severity of {e.subject}?") for e in sev[:n]
    ]
    out += [("unit_calc", t) for t in COMPUTES[:n] + CONVERTS[:1]]
    out += [
        ("safety_checklist", f"Prepare the pre-work safety checklist for {a}.")
        for a in ACTIVITIES[:n]
    ]
    tenders = {e.subject: {} for e in ctx.kb.entries if e.domain == "tender_docs"}
    for e in ctx.kb.entries:
        if e.domain == "tender_docs":
            tenders[e.subject][e.attribute] = e.value
    for subj, kv in list(tenders.items())[:n]:
        body = "; ".join(f"{k}={v}" for k, v in kv.items())
        out.append(("tender_extract", f"Probe extract: {subj.upper()}: {body}"))
    return out


def build_probes(patch: PatchContract, ctx: GateContext) -> list[Probe]:
    seen: set[str] = set()
    probes: list[Probe] = []

    def add(family: str, text: str, kind: str) -> None:
        key = pid(family, text)
        if key in seen:
            return
        seen.add(key)
        subj = _subject(family, text)
        scoped = in_scope(patch, family, subj)
        if kind == "invariance" and family in patch.declared_scope.task_types:
            kind = "boundary"
        probes.append(Probe(key, family, text, kind, scoped, subj))

    w = patch.witness_test
    for text in paraphrases(w.input, ctx.settings.n_paraphrases):
        add(w.family, text, "directional")
    for t in ctx.golden + ctx.accumulated():
        add(t.family, t.input, "regression")
    for family, text in generated(ctx, patch):
        add(family, text, "invariance")
    return probes
