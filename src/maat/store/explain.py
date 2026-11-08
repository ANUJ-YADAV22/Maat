"""Plain-language explanations and Patch Passports, built only from stored records."""

from __future__ import annotations

from typing import Any

from maat.repo import Repo

LOCK_TITLES = {
    "screen": "Screen",
    "warrant": "Warrant",
    "witness": "Witness",
    "invariants": "Invariants",
    "impact": "Impact surface",
    "decision": "Decision",
    "conflict": "Head-to-head",
    "human": "Human review",
}


def _claim_text(claim: dict[str, Any] | None) -> str:
    c = claim or {}
    if c.get("rule_text"):
        return f"rule: {c['rule_text']}"
    if c.get("subject") and c.get("value") is not None:
        value = c["value"]
        value = int(value) if isinstance(value, float) and value.is_integer() else value
        return f"{c['subject']} / {c.get('attribute')} = {value}"
    return c.get("text") or "behaviour change"


def _runs(repo: Repo, patch_id: str) -> dict[str, dict[str, Any]]:
    return {g["lock"]: g for g in repo.list_gate_runs(patch_id)}


def explain_patch(repo: Repo, patch_id: str) -> dict[str, Any]:
    """Why a patch was adopted, rejected, quarantined or left inconclusive."""
    row = repo.get_patch(patch_id)
    if row is None:
        raise KeyError(patch_id)
    runs = _runs(repo, patch_id)
    users = repo.patch_users(patch_id)
    dec = runs.get("decision")
    dm = (dec or {}).get("metrics_json", {}) or {}
    deciding = dm.get("deciding_lock") or (dec["lock"] if dec else None)
    claim = _claim_text(row["claim_json"])
    status = row["status"]
    lines: list[str] = []
    n_events = len(repo.patch_sources(patch_id))
    lines.append(
        f"Proposed from {n_events} feedback event(s) by {', '.join(users) or 'unknown'}"
        f" as a {row['type'].replace('_', ' ')} (risk tier {row['risk_tier']})."
    )
    for name in ("screen", "warrant", "witness", "invariants", "impact", "conflict"):
        g = runs.get(name)
        if g:
            verb = {
                "pass": "passed",
                "fail": "FAILED",
                "quarantine": "needs a human",
                "inconclusive": "was inconclusive",
            }[g["result"]]
            reason = (
                (g["reasons_json"] or [""])[-1]
                if name != "screen"
                else (g["reasons_json"] or [""])[0]
            )
            lines.append(f"{LOCK_TITLES[name]} {verb}: {reason}")
    if dm.get("score") is not None:
        lines.append(
            f"Statistics: gain lower bound {dm['gain_lcb']:.2f}, harm upper bound "
            f"{dm['harm_ucb']:.2f}, score {dm['score']:.3f} against a bar of "
            f"{dm['bar']:.3f} (trust {dm['e_trust']:.2f} lowers the bar, never skips a "
            "lock)."
        )
    if status == "adopted":
        head = (
            f"Adopted: {claim}. It was proven true, proven to work and proven to "
            "change nothing else."
        )
    elif status == "rejected":
        reason = (dec["reasons_json"] or ["rejected"])[0] if dec else "rejected"
        head = f"Rejected at {LOCK_TITLES.get(deciding or '', deciding)}: {reason}"
    elif status == "quarantined":
        head = f"Quarantined: {claim}. It cannot be verified automatically and waits for an expert."
    elif status == "inconclusive":
        head = f"Inconclusive: {claim}. There is not enough evidence to adopt or reject it."
    elif status == "rolled_back":
        head = f"Rolled back: {claim}. A later rollback removed this change."
    else:
        head = f"{status.capitalize()}: {claim}."
    return {
        "patch_id": patch_id,
        "status": status,
        "headline": head,
        "lines": lines,
        "decided_by": deciding,
        "claim": claim,
        "locks": [
            {
                "lock": g["lock"],
                "title": LOCK_TITLES.get(g["lock"], g["lock"]),
                "result": g["result"],
                "reasons": g["reasons_json"],
            }
            for g in repo.list_gate_runs(patch_id)
        ],
    }


def passport(repo: Repo, patch_id: str) -> dict[str, Any]:
    """One-card summary of a decision (spec section 12)."""
    row = repo.get_patch(patch_id)
    if row is None:
        raise KeyError(patch_id)
    runs = _runs(repo, patch_id)
    exp = explain_patch(repo, patch_id)
    warrant = row["warrant_json"] or {}
    status = row["status"]
    replayed = "witness" in runs
    lock = exp["decided_by"] or "gate"
    result = {
        "adopted": "Adopted",
        "rejected": f"Rejected at {LOCK_TITLES.get(lock, lock)}",
        "quarantined": "Quarantined",
        "inconclusive": "Inconclusive",
        "rolled_back": "Rolled back",
    }.get(status, status.capitalize())
    next_action = {
        "adopted": "Monitor accept and redo rates; one-click rollback is available.",
        "rejected": "None. The claim is in the rejection ledger and the sender's trust updated.",
        "quarantined": "Expert review in the approvals queue.",
        "inconclusive": "Add test coverage or resubmit with a clearer witness.",
        "rolled_back": "Re-propose with new evidence if the change is still wanted.",
    }.get(status, "Awaiting the safety gate.")
    return {
        "patch_id": patch_id,
        "claim": exp["claim"],
        "evidence": (
            f"{warrant.get('kind', 'none')}: {warrant.get('ref')}"
            if warrant.get("verified")
            else "none verified"
        ),
        "rule": row["risk_tier"] + " risk tier; " + (LOCK_TITLES.get(lock, lock) + " decided"),
        "method": "five-lock replay on a sandbox config"
        if replayed
        else "stopped before any replay",
        "generated_by": "Safety Gate",
        "result": result,
        "next_action": next_action,
        "status": status,
        "risk_tier": row["risk_tier"],
        "note": "The gate decides, not the loudest user.",
    }


def explain_rollback(repo: Repo, version: int) -> dict[str, Any] | None:
    """Why a rollback created ``version``, from its audit entry."""
    for e in repo.list_audit("config.rollback", 200):
        d = e["details_json"]
        if d.get("new_version") == version:
            undone = [explain_patch(repo, p)["claim"] for p in d["patches_rolled_back"]]
            return {
                "version": version,
                "restored_from": d["to_version"],
                "reason": d["reason"],
                "actor": e["actor"],
                "undone": undone,
                "headline": f"Version {version} restores version {d['to_version']}: {d['reason']}.",
                "lines": [f"Removed change: {u}" for u in undone]
                or ["No adopted patch was undone."],
            }
    return None
