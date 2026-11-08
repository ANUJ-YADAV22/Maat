"""Lock 3, Witness: the witness test must fail before the patch, pass after it, and keep
passing on paraphrases of its input."""

from __future__ import annotations

from maat.contracts import PatchContract
from maat.gate.context import GateContext, LockResult
from maat.proposal.paraphrase import paraphrases


def witness_task(patch: PatchContract, suffix: str = "", text: str | None = None) -> dict:
    w = patch.witness_test
    return {
        "id": f"w_{patch.patch_id}{suffix}",
        "family": w.family,
        "input": text or w.input,
        "checker": w.checker,
    }


def paraphrase_tasks(patch: PatchContract, n: int) -> list[dict]:
    return [
        witness_task(patch, f"_p{i}", t)
        for i, t in enumerate(paraphrases(patch.witness_test.input, n))
    ]


def run(patch: PatchContract, ctx: GateContext) -> LockResult:
    s = ctx.settings
    seeds = ctx.seeds
    task = witness_task(patch)
    base = ctx.replayer.pass_rate(task, ctx.base_config, seeds)
    new = ctx.replayer.pass_rate(task, ctx.patched_config, seeds)
    metrics = {"base_pass": base, "patched_pass": new}
    if base > s.witness_base_max_pass:
        return LockResult(
            "fail",
            [f"witness already passes on the base config ({base:.2f}): no problem to fix"],
            metrics,
        )
    if new < s.witness_patched_min_pass:
        return LockResult(
            "fail", [f"witness not fixed by the patch (pass rate {new:.2f})"], metrics
        )
    para = [
        ctx.replayer.pass_rate(t, ctx.patched_config, seeds)
        for t in paraphrase_tasks(patch, s.n_paraphrases)
    ]
    rate = sum(1 for p in para if p >= 0.5) / len(para)
    metrics["paraphrase_pass_rate"] = rate
    if rate < s.paraphrase_min:
        return LockResult(
            "fail",
            [f"fix does not generalise to paraphrases ({rate:.2f} < {s.paraphrase_min})"],
            metrics,
        )
    return LockResult(
        "pass",
        [f"witness fails before ({base:.2f}), passes after ({new:.2f}); paraphrases {rate:.2f}"],
        metrics,
    )
