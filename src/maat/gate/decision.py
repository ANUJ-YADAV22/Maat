"""Decision engine: hard vetoes, then LCB(gain) - lambda_tier * UCB(harm) >= Bar."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from maat.gate.context import LockResult
from maat.gate.stats import cluster_bootstrap
from maat.settings import Settings


@dataclass
class Decision:
    outcome: str  # adopt | reject | quarantine | inconclusive
    deciding_lock: str
    reasons: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)


def evidence_bar(tier: str, e_trust: float, s: Settings) -> float:
    """Bar = max(Bar_min, Bar_tier * (1 - c * E[trust])). Trust lowers the bar, never to zero."""
    return max(s.bar_min, s.bar_tier[tier] * (1 - s.trust_c * e_trust))


def score(gain_lcb: float, harm_ucb: float, tier: str, s: Settings) -> float:
    return gain_lcb - s.lambda_tier[tier] * harm_ucb


def decide(
    results: list[tuple[str, LockResult]],
    gain: list[tuple[str, float]],
    harm_diffs: list[tuple[str, float]],
    tier: str,
    e_trust: float,
    s: Settings,
    patch_id: str,
) -> Decision:
    """Combine lock results and replay statistics into one decision with all inputs recorded."""
    for name, res in results:
        if res.status == "fail":  # hard veto: trust can never override it
            return Decision("reject", name, res.reasons, {"veto": name})
    for name, res in results:  # nothing to fix: no evidence either way, never a trust penalty
        if res.status == "inconclusive" and res.metrics.get("redundant"):
            return Decision("inconclusive", name, res.reasons, {"redundant": True})
    seed = int(hashlib.sha256(patch_id.encode()).hexdigest()[:8], 16)
    g_mean, g_lcb, _ = cluster_bootstrap(gain, s.bootstrap_resamples, seed, s.z_one_sided)
    harm = [(f, max(0.0, -d)) for f, d in harm_diffs]
    h_mean, _, h_ucb = cluster_bootstrap(harm, s.bootstrap_resamples, seed + 1, s.z_one_sided)
    bar = evidence_bar(tier, e_trust, s)
    sc = score(g_lcb, h_ucb, tier, s)
    metrics = {
        "margin": sc - bar,
        "gain_mean": g_mean,
        "gain_lcb": g_lcb,
        "harm_mean": h_mean,
        "harm_ucb": h_ucb,
        "lambda": s.lambda_tier[tier],
        "bar": bar,
        "score": sc,
        "tier": tier,
        "e_trust": e_trust,
        "n_gain": len(gain),
        "n_regression": len(harm_diffs),
    }
    if sc < bar:
        return Decision(
            "reject",
            "decision",
            [f"gain does not beat risk: score {sc:.3f} < bar {bar:.3f}"],
            metrics,
        )
    for name, res in results:
        if res.status == "inconclusive":
            return Decision("inconclusive", name, res.reasons, metrics)
    for name, res in results:
        if res.status == "quarantine":
            return Decision("quarantine", name, res.reasons, metrics)
    return Decision("adopt", "decision", [f"score {sc:.3f} >= bar {bar:.3f}"], metrics)
