"""The six systems compared in the evaluation (spec 15.1).

All systems share the same front end (feedback collection, clustering, patch proposal, blame)
and the same frozen agent; they differ only in how a proposed patch is accepted:

S0 no learning | S1 accept-all | S2 ACE-style ungated curator | S3 LLM-judge-only gate
S4 replay-only gate | S5 Maat (all locks, decision rule, trust)

S3's "judge" is a deterministic plausibility heuristic standing in for an LLM judge, so S3
results describe that stand-in, not a particular model.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from maat.config_model import ConfigError, apply_patch, config_hash
from maat.db import transaction
from maat.env import Env, build_env
from maat.eval.personas import Item
from maat.gate import stats, witness
from maat.gate.screen import INJECTION
from maat.llm.mock_backend import MockBackend
from maat.settings import Settings

NAMES = {
    "S0": "No learning",
    "S1": "Accept-all",
    "S2": "ACE-style ungated curator",
    "S3": "LLM-judge-only gate",
    "S4": "Replay-only gate",
    "S5": "Maat (full)",
}


@dataclass
class Decision:
    patch_id: str
    adopted: bool
    outcome: str  # adopt | reject | quarantine | inconclusive
    margin: float | None = None
    deciding_lock: str = ""
    seconds: float = 0.0
    replays: int = 0
    tokens: int = 0


def adopt_unsafe(env: Env, patch_id: str, actor: str) -> bool:
    """Apply a patch with NO protected-item or charter enforcement (what ungated systems do)."""
    row = env.repo.get_patch(patch_id)
    assert row is not None
    base = env.active()
    try:
        new = apply_patch(base, row["ops_json"], None, enforce=False)
    except ConfigError:
        env.repo.set_patch_status(patch_id, "rejected")
        return False
    if config_hash(new) == config_hash(base):
        env.repo.set_patch_status(patch_id, "rejected")
        return False
    version = base["version"] + 1
    new["version"] = version
    w = row["witness_json"]
    with transaction(env.repo.conn):
        env.repo.insert_config_version(version, base["version"], new, config_hash(new), patch_id)
        env.repo.upsert_test(
            f"acc_{patch_id}", "accumulated", w["family"], w["input"], w["checker"], ["accumulated"]
        )
        env.repo.set_patch_status(patch_id, "adopted")
        env.repo.audit("patch.adopted", actor, {"patch_id": patch_id, "version": version})
    return True


def judge_score(
    row: dict[str, Any], events: list[dict[str, Any]], memory: list[dict[str, Any]]
) -> float:
    """Deterministic stand-in for an LLM judge: scores surface plausibility only."""
    claim = row["claim_json"] or {}
    text = " ".join(
        [claim.get("rule_text") or "", claim.get("text") or ""]
        + [(e.get("text") or "") for e in events]
    )
    score = 0.55
    if any(p.search(text) for p in INJECTION):
        score -= 0.6
    if re.search(
        r"\b(skip|ignore|bypass|disable)\b.{0,40}\b(check|inspection|harness|ppe|permit)\b",
        text,
        re.I,
    ):
        score -= 0.45
    if claim.get("source") or re.search(
        r"\b(per|according to)\b.*\b(memo|code|standard)\b", text, re.I
    ):
        score += 0.2
    v = claim.get("value")
    if isinstance(v, int | float):
        same = [
            m["value"]
            for m in memory
            if m["attribute"] == claim.get("attribute") and isinstance(m["value"], int | float)
        ]
        if same:
            lo, hi = min(same) * 0.5, max(same) * 2.0
            score += 0.1 if lo <= v <= hi else -0.1
    score += min(0.15, 0.05 * (len({e["user_id"] for e in events}) - 1))  # repeated claims persuade
    return score


class System:
    """One system under test with its own database, config history and (mock) agent."""

    def __init__(
        self,
        sid: str,
        seed: int,
        settings: Settings,
        *,
        noise: float,
        shared_cache: dict[str, dict[str, Any]],
        disabled: frozenset[str] = frozenset(),
        trust_enabled: bool = True,
        label: str | None = None,
    ) -> None:
        self.sid, self.seed, self.label = sid, seed, label or sid
        self.env = build_env(
            settings,
            db_path=":memory:",
            backend=MockBackend(noise=noise),
            disabled_locks=disabled,
            trust_enabled=trust_enabled,
            shared_cache=shared_cache,
        )
        self.settings = settings

    @property
    def config(self) -> dict[str, Any]:
        return self.env.active()

    def submit(self, item: Item) -> None:
        if self.sid == "S0":
            return
        env = self.env
        tid = None
        if item.input is not None and item.family is not None:
            tid = env.ask(item.user, item.family, item.input)["task_id"]
        kw: dict[str, Any] = {}
        if item.claim is not None:
            kw["claim"] = item.claim
        if item.text:
            kw["text"] = item.text
        if item.signal == "edit":
            kw["edit"] = item.edit_text
        env.feedback(item.user, tid, item.signal, **kw)

    def process(self) -> list[Decision]:
        if self.sid == "S0":
            return []
        env = self.env
        env.propose()
        if self.sid == "S5":
            out = []
            for o in env.decide():
                g = [r for r in env.repo.list_gate_runs(o.patch_id) if r["lock"] == "decision"]
                m = g[0]["metrics_json"] if g else {}
                out.append(
                    Decision(
                        o.patch_id,
                        o.outcome == "adopt",
                        o.outcome,
                        m.get("margin"),
                        o.deciding_lock,
                        m.get("gate_seconds", 0.0),
                        int(m.get("replays", 0)),
                        int(m.get("tokens_in", 0)) + int(m.get("tokens_out", 0)),
                    )
                )
            return out
        pending = env.repo.list_patches("proposed")
        decisions: list[Decision] = []
        if self.sid == "S2":
            return self._curate(pending)
        for row in pending:
            start = time.perf_counter()
            ok, snap = self._accept(row)
            decisions.append(
                Decision(
                    row["patch_id"],
                    ok,
                    "adopt" if ok else "reject",
                    None,
                    self.sid.lower(),
                    time.perf_counter() - start,
                    snap[0],
                    snap[1],
                )
            )
        return decisions

    def _accept(self, row: dict[str, Any]) -> tuple[bool, tuple[int, int]]:
        env, pid = self.env, row["patch_id"]
        if self.sid == "S1":
            return adopt_unsafe(env, pid, "S1"), (0, 0)
        if self.sid == "S3":
            events = env.repo.patch_events(pid)
            if judge_score(row, events, env.active()["memory"]) >= 0.6:
                return adopt_unsafe(env, pid, "S3"), (0, 0)
            env.repo.set_patch_status(pid, "rejected")
            return False, (0, 0)
        if self.sid == "S4":
            ok, snap = self._replay_gate(row)
            if ok:
                return adopt_unsafe(env, pid, "S4"), snap
            env.repo.set_patch_status(pid, "rejected")
            return False, snap
        raise ValueError(self.sid)

    def _replay_gate(self, row: dict[str, Any]) -> tuple[bool, tuple[int, int]]:
        """Witness fixed and no golden or accumulated task gets worse. Nothing else."""
        from maat.contracts import PatchContract

        ctx = self.env.gate.ctx
        before = ctx.replayer.snapshot()
        patch = PatchContract.from_row(row, self.env.repo.patch_sources(row["patch_id"]))
        ctx.base_config = self.env.active()
        try:
            ctx.patched_config = apply_patch(ctx.base_config, patch.ops, None, enforce=False)
        except ConfigError:
            return False, (0, 0)
        seeds = ctx.seeds
        task = witness.witness_task(patch)
        b = ctx.replayer.pass_rate(task, ctx.base_config, seeds)
        n = ctx.replayer.pass_rate(task, ctx.patched_config, seeds)
        ok = (
            b <= self.settings.witness_base_max_pass and n >= self.settings.witness_patched_min_pass
        )
        if ok:
            diffs = stats.paired_diffs(
                ctx.replayer,
                ctx.golden + ctx.accumulated(),
                ctx.base_config,
                ctx.patched_config,
                seeds,
            )
            ok = all(d >= -1e-9 for _, d in diffs)
        after = ctx.replayer.snapshot()
        return ok, (
            int(after["replays"] - before["replays"]),
            int(
                after["tokens_in"]
                + after["tokens_out"]
                - before["tokens_in"]
                - before["tokens_out"]
            ),
        )

    def _curate(self, pending: list[dict[str, Any]]) -> list[Decision]:
        """ACE-style curator: merge duplicates, resolve conflicts by support, accept the rest."""
        env = self.env
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in pending:
            c = r["claim_json"] or {}
            if r["type"] == "memory_note" and c.get("subject") and not c.get("rule_text"):
                groups.setdefault((c["subject"], c["attribute"]), []).append(r)
        keep: set[str] = set()
        for rows in groups.values():
            best = max(rows, key=lambda r: len(env.repo.patch_sources(r["patch_id"])))
            keep.add(best["patch_id"])
        out = []
        for r in pending:
            in_group = any(r in rows for rows in groups.values())
            ok = False
            if not in_group or r["patch_id"] in keep:
                ok = adopt_unsafe(env, r["patch_id"], "S2")
            else:
                env.repo.set_patch_status(r["patch_id"], "rejected")
            out.append(Decision(r["patch_id"], ok, "adopt" if ok else "reject", None, "s2"))
        return out
