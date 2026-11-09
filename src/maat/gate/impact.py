"""Lock 5, Impact surface: did the patch change only what it declared?

Noise floor (A/A): replay every probe on the base config with several seeds to estimate each
probe's own instability p_i. A probe counts as changed only if patched replays differ from the
base replay at the same seed more often than max(tau, p_i + margin). Any changed probe outside
the declared scope is an absolute veto. Too little coverage is inconclusive, never a pass.
"""

from __future__ import annotations

from maat.config_model import config_hash
from maat.contracts import PatchContract
from maat.gate.context import GateContext, LockResult
from maat.gate.probes import build_probes


def run(patch: PatchContract, ctx: GateContext) -> LockResult:
    s, rp = ctx.settings, ctx.replayer
    probes = build_probes(patch, ctx)
    hb, hp = config_hash(ctx.base_config), config_hash(ctx.patched_config)
    aa_seeds = [s.seed + 1000 + i for i in range(s.aa_seeds)]
    changed: list = []
    floors: list[float] = []
    for pr in probes:
        task = pr.task()
        aa = [rp.answer(task, ctx.base_config, hb, sd) for sd in aa_seeds]
        pairs = [(a, b) for i, a in enumerate(aa) for b in aa[i + 1 :]]
        p_i = sum(a != b for a, b in pairs) / len(pairs) if pairs else 0.0
        floors.append(p_i)
        # Paired comparison at the SAME seeds: seed-determined noise cancels, so only a real
        # behavioural change counts as a difference.
        base_k = [rp.answer(task, ctx.base_config, hb, sd) for sd in ctx.seeds]
        new_k = [rp.answer(task, ctx.patched_config, hp, sd) for sd in ctx.seeds]
        frac = sum(a != b for a, b in zip(base_k, new_k, strict=True)) / len(new_k)
        if frac > max(s.tau, p_i + s.margin):
            changed.append(pr)

    out_of_scope = [p for p in changed if not p.in_scope]
    directional = [p for p in probes if p.kind == "directional"]
    n_in = sum(1 for p in probes if p.in_scope)
    boundary = [p for p in probes if not p.in_scope and p.family in patch.declared_scope.task_types]
    if not boundary:  # family-wide scope: the nearest out-of-scope probes are other families
        boundary = [p for p in probes if not p.in_scope]
    coverage = min(1.0, (n_in + len(boundary)) / s.n_min_probes)
    precision = (len(changed) - len(out_of_scope)) / len(changed) if changed else 1.0
    recall = (sum(p in changed for p in directional) / len(directional)) if directional else 0.0
    metrics = {
        "n_probes": len(probes),
        "n_in_scope": n_in,
        "n_boundary": len(boundary),
        "changed": [p.id for p in changed],
        "changed_out_of_scope": [
            {"id": p.id, "family": p.family, "input": p.input[:80]} for p in out_of_scope
        ],
        "scope_precision": precision,
        "scope_recall": recall,
        "coverage": coverage,
        "noise_floor_mean": sum(floors) / len(floors) if floors else 0.0,
    }
    if len(out_of_scope) > s.scope_tolerance:
        fams = sorted({p.family for p in out_of_scope})
        return LockResult(
            "fail",
            [
                f"undeclared impact: {len(out_of_scope)} probe(s) outside the declared "
                f"scope changed ({', '.join(fams)})"
            ],
            metrics,
        )
    if coverage < s.coverage_min or n_in < s.n_in_scope_min:
        return LockResult(
            "inconclusive",
            [
                f"coverage {coverage:.2f} below {s.coverage_min}: not "
                "enough probes to prove the change is contained"
            ],
            metrics,
        )
    return LockResult(
        "pass",
        [
            f"{len(changed)} probe(s) changed, all within the declared scope "
            f"(precision {precision:.2f}, recall {recall:.2f}, coverage "
            f"{coverage:.2f})"
        ],
        metrics,
    )
