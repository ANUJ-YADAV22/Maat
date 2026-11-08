"""Lock 4, Invariants: protected rules can never be removed or weakened (absolute veto)."""

from __future__ import annotations

from maat.config_model import protected_violations
from maat.contracts import PatchContract
from maat.gate.context import GateContext, LockResult


def run(patch: PatchContract, ctx: GateContext) -> LockResult:
    static = protected_violations(ctx.base_config, ctx.patched_config, ctx.charter)
    seeds = ctx.seeds[:1]
    failed = [
        t.id for t in ctx.invariants if ctx.replayer.pass_rate(t, ctx.patched_config, seeds) < 1.0
    ]
    metrics = {
        "static_violations": static,
        "invariant_failures": failed,
        "invariants_run": len(ctx.invariants),
    }
    if static or failed:
        reasons = [f"static: {v}" for v in static]
        if failed:
            reasons.append(f"invariant tests failed: {', '.join(failed)}")
        return LockResult("fail", ["absolute veto: " + "; ".join(reasons)], metrics)
    return LockResult(
        "pass",
        [f"all {len(ctx.invariants)} invariant tests hold; no protected item touched"],
        metrics,
    )
