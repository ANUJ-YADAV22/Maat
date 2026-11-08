"""Lock 1, Screen: injection, PII, provenance, structure, and authoritative risk tiering.

Only *definite* injection is rejected here. Policy violations (e.g. "skip the harness check") are
flagged and raised to high risk but must continue to Lock 4, where the invariant veto fires.
"""

from __future__ import annotations

import re
from typing import Any

from maat.config_model import ConfigError, apply_patch
from maat.contracts import PatchContract
from maat.gate.context import GateContext, LockResult
from maat.proposal.proposer import SAFETY_WORDS

INJECTION = [
    re.compile(p, re.I)
    for p in (
        r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?)",
        r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|system)",
        r"override\s+(the\s+)?(system|previous|all)\b",
        r"you\s+must\s+now\b",
        r"\bsystem\s+prompt\b",
        r"<\s*/?\s*(system|instructions?)\s*>",
        r"\[\s*/?INST\s*\]",
        r"begin\s+(hidden|secret)\s+instructions?",
        r"<!--",
        "[\u200b-\u200f\u2060\ufeff]",  # zero-width / hidden characters
    )
]
PII = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "phone": re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "id12": re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
}


def _texts(patch: PatchContract, events: list[dict[str, Any]]) -> list[str]:
    c = patch.claim
    out = [c.rule_text or "", c.text or ""]
    if isinstance(c.value, str):
        out.append(c.value)
    for op in patch.ops:
        if isinstance(op.value, dict):
            out += [str(op.value.get("text", ""))]
    for e in events:
        out += [e.get("text") or "", e.get("edit_text") or ""]
    return [t for t in out if t]


def find_injection(texts: list[str]) -> str | None:
    for t in texts:
        for pat in INJECTION:
            if pat.search(t):
                return f"injection marker matched: {pat.pattern[:40]}"
    return None


def redact(text: str) -> tuple[str, int]:
    n = 0
    for pat in PII.values():
        text, k = pat.subn("[REDACTED]", text)
        n += k
    return text, n


def compute_tier(patch: PatchContract, ctx: GateContext, policy_flag: bool) -> str:
    """Authoritative risk tier (spec 10, Lock 1)."""
    base = ctx.base_config
    protected = {f"{s}/{i['id']}" for s in ("memory", "rules") for i in base[s] if i["protected"]}
    touches_protected = any(
        op.path in protected or (isinstance(op.value, dict) and op.value.get("protected"))
        for op in patch.ops
    )
    safety = (
        patch.witness_test.family == "safety_checklist"
        or any(op.path.startswith("workflow/safety_checklist") for op in patch.ops)
        or bool(patch.claim.rule_text and SAFETY_WORDS.search(patch.claim.rule_text))
    )
    clause_values = patch.type == "memory_note" and patch.witness_test.family == "clause_query"
    if touches_protected or safety or policy_flag or clause_values or patch.type == "tool_policy":
        return "high"
    if patch.type in ("memory_note", "workflow_step") and (
        patch.claim.is_factual or patch.type == "workflow_step"
    ):
        return "medium"
    return "low"


def run(patch: PatchContract, ctx: GateContext) -> LockResult:
    events = ctx.repo.patch_events(patch.patch_id)
    reasons: list[str] = []
    metrics: dict[str, Any] = {}

    if any(e["origin"] != "user" for e in events):
        return LockResult("fail", ["feedback of agent origin is never accepted"], {"lock": 1})
    if (hit := find_injection(_texts(patch, events))) is not None:
        return LockResult("fail", [f"definite injection: {hit}"], {"injection": True})
    try:
        apply_patch(ctx.base_config, patch.ops, enforce=False)
    except ConfigError as exc:
        return LockResult("fail", [f"malformed patch: {exc}"], {"structural": False})

    structured = [patch.claim.subject or "", patch.claim.attribute or ""]
    if isinstance(patch.claim.value, str):
        structured.append(patch.claim.value)
    if any(pat.search(t) for t in structured for pat in PII.values()):
        return LockResult("fail", ["PII in a structured claim field"], {"pii": "structured"})

    update = patch.model_copy(deep=True)
    redactions = 0
    if update.claim.text:
        update.claim.text, k = redact(update.claim.text)
        redactions += k
    if update.claim.rule_text:
        update.claim.rule_text, k = redact(update.claim.rule_text)
        redactions += k
    for op in update.ops:
        if isinstance(op.value, dict):
            if "text" in op.value:
                op.value["text"], k = redact(str(op.value["text"]))
                redactions += k
    if redactions:
        reasons.append(f"redacted {redactions} PII item(s) from free text")
    metrics["pii_redactions"] = redactions

    policy_flag = False
    for op in patch.ops:
        text = str(op.value.get("text", "")) if isinstance(op.value, dict) else ""
        if op.path.startswith("rules/") and any(
            re.search(p, text, re.I) for p in ctx.charter.forbidden_rule_patterns
        ):
            policy_flag = True
    if policy_flag:
        reasons.append(
            "rule instructs skipping or weakening a safety check: flagged, tier high, "
            "continues to Lock 4"
        )
    tier = compute_tier(patch, ctx, policy_flag)
    update.risk_tier = tier  # type: ignore[assignment]
    metrics.update(risk_tier=tier, policy_flag=policy_flag, injection=False)
    reasons.append(f"risk tier {tier}")
    return LockResult("pass", reasons, metrics, update)
