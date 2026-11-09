"""Metrics: held-out success, regression, consistency, aggregation, FAR/FRR."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from maat.checkers import run_checker
from maat.eval.personas import PoolTask
from maat.fmt import fmt_num
from maat.proposal.paraphrase import paraphrases
from maat.suites import SuiteTask


def mean_se(xs: list[float]) -> tuple[float, float]:
    xs = [x for x in xs if not math.isnan(x)]
    if not xs:
        return float("nan"), float("nan")
    m = float(np.mean(xs))
    return m, (float(np.std(xs, ddof=1) / math.sqrt(len(xs))) if len(xs) > 1 else 0.0)


def paired(a: dict[int, float], b: dict[int, float]) -> tuple[float, float]:
    """Mean and SE of per-seed differences a - b over seeds present in both."""
    return mean_se([a[s] - b[s] for s in a if s in b and not math.isnan(a[s] - b[s])])


def run_tasks(
    agent: Any, config: dict[str, Any], tasks: list[SuiteTask], seed: int
) -> dict[str, Any]:
    """Run tasks once; return pass map and mean simulated latency."""
    passed, lat = {}, []
    for t in tasks:
        out = agent.run(t.model_dump(), config, seed)
        passed[t.id] = run_checker(t.checker, out["answer"], out["trace"])
        lat.append(out["latency_ms"])
    return {"passed": passed, "latency_ms": float(np.mean(lat)) if lat else 0.0}


def measure(
    agent: Any,
    config: dict[str, Any],
    heldout: list[SuiteTask],
    golden: list[SuiteTask],
    seed: int,
    prev: dict[str, bool] | None,
) -> tuple[dict[str, Any], dict[str, bool]]:
    h = run_tasks(agent, config, heldout, seed)
    g = run_tasks(agent, config, golden, seed)
    allp = {
        **{f"h:{k}": v for k, v in h["passed"].items()},
        **{f"g:{k}": v for k, v in g["passed"].items()},
    }
    kb_ids = {t.id for t in heldout if t.family in ("clause_query", "incident_triage")}
    reg = float("nan")
    if prev is not None:
        was = [k for k, v in prev.items() if v]
        reg = sum(1 for k in was if not allp[k]) / len(was) if was else 0.0
    row = {
        "heldout_success": float(np.mean(list(h["passed"].values()))),
        "kb_accuracy": float(np.mean([v for k, v in h["passed"].items() if k in kb_ids])),
        "golden_success": float(np.mean(list(g["passed"].values()))),
        "regression_rate": reg,
        "agent_latency_ms": h["latency_ms"],
    }
    return row, allp


def consistency(agent: Any, config: dict[str, Any], heldout: list[SuiteTask], seed: int) -> float:
    """Share of held-out tasks answered identically across 3 seeds and one paraphrase."""
    same = 0
    for t in heldout:
        d = t.model_dump()
        outs = {
            " ".join(agent.run(d, config, seed + i)["answer"].lower().split()) for i in range(3)
        }
        d2 = {**d, "input": paraphrases(t.input, 1)[0]}
        outs.add(" ".join(agent.run(d2, config, seed)["answer"].lower().split()))
        same += len(outs) == 1
    return same / len(heldout)


def pool_checker(pt: PoolTask) -> dict[str, Any]:
    if pt.kind == "convert":
        return {"type": "numeric_close", "expected": pt.truth}
    if isinstance(pt.truth, str):
        return {"type": "contains_all", "items": [pt.truth]}
    return {"type": "regex", "pattern": rf"\bis {fmt_num(pt.truth)}\b"}


def satisfaction(agent: Any, config: dict[str, Any], pool: list[PoolTask], seed: int) -> float:
    """Simulated honest-user satisfaction: share of everyday questions answered correctly."""
    ok = 0
    for pt in pool:
        out = agent.run({"id": "x", "family": pt.family, "input": pt.input}, config, seed)
        ok += run_checker(pool_checker(pt), out["answer"], out["trace"])
    return ok / len(pool)


def far_frr(patches: list[dict[str, Any]], points: int = 41) -> list[dict[str, float]]:
    """Sweep a margin threshold over the full-gate decisions. A patch is adoptable only if it
    reached the statistical decision (no hard veto, not quarantined) and its margin >= tau."""
    eligible = [
        p
        for p in patches
        if p["margin"] is not None
        and p["outcome"] in ("adopt", "reject")
        and p["deciding_lock"] in ("decision",)
    ]
    margins = [p["margin"] for p in eligible]
    bad = [p for p in patches if p["bad"]]
    good = [p for p in patches if p["label"] == "good"]
    if not margins:
        return []
    lo, hi = min(margins + [-0.05]) - 0.01, max(margins + [0.05]) + 0.01
    out = []
    for tau in np.linspace(lo, hi, points):

        def adopted(p: dict[str, Any], tau: float = float(tau)) -> bool:
            return p in eligible and p["margin"] >= tau

        far = sum(adopted(p) for p in bad) / len(bad) if bad else 0.0
        frr = sum(not adopted(p) for p in good) / len(good) if good else 0.0
        out.append({"threshold": round(float(tau), 4), "far": far, "frr": frr})
    return out
