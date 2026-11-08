"""Paired replay differences and the cluster bootstrap used by the decision rule."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import norm

from maat.config_model import config_hash
from maat.gate.context import Replayer


def paired_diffs(
    replayer: Replayer,
    tasks: list[Any],
    base: dict[str, Any],
    patched: dict[str, Any],
    seeds: list[int],
) -> list[tuple[str, float]]:
    """Per task: (family, mean patched pass - mean base pass) over the replay seeds."""
    hb, hp = config_hash(base), config_hash(patched)
    out = []
    for t in tasks:
        d = t.model_dump() if hasattr(t, "model_dump") else t
        pb = sum(replayer.passed(d, base, hb, s) for s in seeds) / len(seeds)
        pp = sum(replayer.passed(d, patched, hp, s) for s in seeds) / len(seeds)
        out.append((d["family"], pp - pb))
    return out


def cluster_bootstrap(
    values: list[tuple[str, float]], n: int, seed: int, z: float = 1.645
) -> tuple[float, float, float]:
    """(mean, lower, upper) one-sided bounds of the mean, resampling families then tasks."""
    if not values:
        return 0.0, 0.0, 0.0
    groups: dict[str, np.ndarray] = {}
    for fam, v in values:
        groups.setdefault(fam, []).append(v)  # type: ignore[arg-type]
    arrays = [np.asarray(v, dtype=float) for v in groups.values()]
    rng = np.random.default_rng(seed)
    means = np.empty(n)
    for b in range(n):
        picked = rng.integers(0, len(arrays), size=len(arrays))
        pooled = np.concatenate([rng.choice(arrays[i], size=len(arrays[i])) for i in picked])
        means[b] = pooled.mean()
    q = float(norm.cdf(-z))
    return (
        float(np.mean([v for _, v in values])),
        float(np.quantile(means, q)),
        float(np.quantile(means, 1 - q)),
    )
