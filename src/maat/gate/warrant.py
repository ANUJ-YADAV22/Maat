"""Lock 2, Warrant: is the claim true? Checkable claims are verified against the KB (or, for
behavioural patches, the witness's expected answer is verified against an independent verifier);
unverifiable claims are quarantined unless corroborated by independent trusted users."""

from __future__ import annotations

import re
from typing import Any

from maat.agent.tools import calculator
from maat.contracts import PatchContract, Warrant, WitnessTest
from maat.domains import domain_for
from maat.gate.context import GateContext, LockResult
from maat.textparse import parse_compute, parse_convert, parse_qa
from maat.units import convert


def expected_of(checker: dict[str, Any]) -> Any:
    """The answer a checker expects, when it states one."""
    if "expected" in checker:
        return checker["expected"]
    if checker["type"] == "contains_all" and len(checker["items"]) == 1:
        return checker["items"][0]
    if checker["type"] == "regex":
        m = re.fullmatch(r"\\bis (.+)\\b", checker["pattern"])
        return re.sub(r"\\(.)", r"\1", m.group(1)) if m else None
    return None


def verify_witness(witness: WitnessTest, ctx: GateContext) -> str:
    """'match' | 'contradiction' | 'unverifiable' for the witness's expected answer."""
    expected = expected_of(witness.checker)
    if expected is None:
        return "unverifiable"
    if witness.family in ("clause_query", "incident_triage") and (qa := parse_qa(witness.input)):
        attr, subj = qa
        value: Any = expected
        try:
            value = float(expected)
        except (TypeError, ValueError):
            pass
        return ctx.kb.check_claim(subj, attr, value)
    if witness.family == "unit_calc":
        truth = None
        if conv := parse_convert(witness.input):
            truth = convert(*conv)
        elif expr := parse_compute(witness.input):
            try:
                truth = calculator(expr)
            except (ValueError, SyntaxError, ZeroDivisionError):
                truth = None
        if truth is None:
            return "unverifiable"
        return (
            "match"
            if abs(truth - float(expected)) <= 1e-6 * max(1.0, abs(truth))
            else "contradiction"
        )
    return "unverifiable"


def run(patch: PatchContract, ctx: GateContext) -> LockResult:
    claim = patch.claim
    chash = claim.claim_hash()
    ledger = ctx.repo.ledger_get(chash)
    if ledger:
        count = ctx.repo.ledger_bump(chash, ledger["reason"], ledger["lock"])
        return LockResult(
            "fail",
            [f"claim previously rejected ({ledger['reason']}); seen {count}x"],
            {"ledger_count": count, "claim_hash": chash},
        )

    metrics: dict[str, Any] = {"claim_hash": chash}
    reasons: list[str] = []
    existing = None
    if claim.is_factual:
        existing = next(
            (
                m
                for m in ctx.base_config["memory"]
                if m["subject"] == claim.subject
                and m["attribute"] == claim.attribute
                and m["value"] != claim.value
            ),
            None,
        )
        if existing:
            metrics["contradicts_config"] = existing["id"]
            reasons.append(f"differs from existing memory item {existing['id']}")
        state = ctx.kb.check_claim(claim.subject, claim.attribute, claim.value)  # type: ignore[arg-type]
        kind, ref = "source_lookup", f"kb:{claim.subject}/{claim.attribute}"
    else:
        state = verify_witness(patch.witness_test, ctx)
        kind, ref = "verifier", "witness expectation checked against KB or unit/calculator"
    metrics["verifier_state"] = state

    if state == "contradiction":
        reasons.append("claim contradicts the verified source; rejected before any replay")
        return LockResult("fail", reasons, metrics)
    if state == "match":
        warranted = patch.model_copy(deep=True)
        warranted.warrant = Warrant(kind=kind, ref=ref, verified=True)  # type: ignore[arg-type]
        reasons.append("claim verified against a trusted source")
        return LockResult("pass", reasons, metrics, warranted)

    domain = domain_for(patch.witness_test.family, claim.subject, ctx.kb)
    users = ctx.repo.patch_users(patch.patch_id)
    trusted = ctx.trust.trusted_users(users, domain)
    metrics.update(domain=domain, users=len(users), trusted_users=len(trusted))
    if len(trusted) >= ctx.settings.n_corr:
        warranted = patch.model_copy(deep=True)
        warranted.warrant = Warrant(kind="corroboration", ref=",".join(trusted), verified=True)
        reasons.append(f"corroborated by {len(trusted)} independent trusted users")
        return LockResult("pass", reasons, metrics, warranted)
    reasons.append(
        f"unverifiable; only {len(trusted)} of {ctx.settings.n_corr} trusted users "
        "corroborate; needs human approval"
    )
    return LockResult("quarantine", reasons, metrics)
