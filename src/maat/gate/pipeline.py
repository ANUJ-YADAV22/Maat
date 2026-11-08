"""Gate pipeline: locks in order on a sandbox copy, decision, and outcome handling.

Stops at the first hard failure, writes one gate_runs row per lock, and applies the outcome
(adopt, reject, quarantine, inconclusive) with trust, ledger, queue and audit updates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maat.agent.runtime import Agent
from maat.config_model import Charter, ConfigError, apply_patch
from maat.contracts import PatchContract
from maat.domains import domain_for
from maat.gate import decision as decision_mod
from maat.gate import impact, invariants, screen, stats, warrant, witness
from maat.gate.context import GateContext, LockResult, Replayer
from maat.kb import KnowledgeBase
from maat.repo import Repo
from maat.settings import Settings
from maat.store import versions
from maat.store.versions import VersionError
from maat.suites import load_suite
from maat.trust.service import TrustService

LOCKS = [
    ("screen", screen),
    ("warrant", warrant),
    ("witness", witness),
    ("invariants", invariants),
    ("impact", impact),
]


@dataclass
class Evaluation:
    """A patch's gate results and decision, before the outcome is applied."""

    patch: PatchContract
    results: list[tuple[str, LockResult]]
    decision: decision_mod.Decision
    domain: str
    users: list[str]

    @property
    def margin(self) -> float | None:
        return self.decision.metrics.get("margin")


@dataclass
class GateOutcome:
    patch_id: str
    outcome: str
    deciding_lock: str
    reasons: list[str]
    metrics: dict[str, Any]
    config_version: int | None = None


class GateRunner:
    def __init__(
        self,
        repo: Repo,
        kb: KnowledgeBase,
        charter: Charter,
        settings: Settings,
        agent: Agent,
        trust: TrustService,
        data_dir: Path,
    ) -> None:
        self.repo, self.kb, self.charter, self.settings = repo, kb, charter, settings
        self.trust = trust
        self.ctx = GateContext(
            repo=repo,
            kb=kb,
            charter=charter,
            settings=settings,
            replayer=Replayer(agent, repo),
            trust=trust,
            golden=load_suite(data_dir, "golden"),
            invariants=load_suite(data_dir, "invariants"),
        )

    # ----------------------------------------------------------------- running
    def process_pending(self) -> list[GateOutcome]:
        """Gate every proposed patch; patches proposing different values for the same
        (subject, attribute) are gated head-to-head against the same suites and seeds."""
        pending = self.repo.list_patches("proposed")
        done: set[str] = set()
        outcomes: list[GateOutcome] = []
        for p in pending:
            if p["patch_id"] in done:
                continue
            group = self._conflict_group(p, pending)
            if len(group) > 1:
                done |= {g["patch_id"] for g in group}
                outcomes += self._process_group([g["patch_id"] for g in group])
            else:
                done.add(p["patch_id"])
                outcomes.append(self.process(p["patch_id"]))
        return outcomes

    @staticmethod
    def _conflict_group(p: dict[str, Any], pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
        c = p["claim_json"] or {}
        if p["type"] != "memory_note" or not c.get("subject") or c.get("value") is None:
            return [p]
        same = [
            q
            for q in pending
            if q["type"] == "memory_note"
            and (q["claim_json"] or {}).get("subject") == c["subject"]
            and (q["claim_json"] or {}).get("attribute") == c.get("attribute")
            and (q["claim_json"] or {}).get("value") is not None
        ]
        return same if len({str(q["claim_json"]["value"]) for q in same}) > 1 else [p]

    def process(self, patch_id: str) -> GateOutcome:
        return self._commit(self._evaluate(patch_id))

    def _evaluate(self, patch_id: str) -> Evaluation:
        row = self.repo.get_patch(patch_id)
        if row is None:
            raise VersionError("unknown_patch", f"patch {patch_id} does not exist")
        if row["status"] not in ("proposed", "inconclusive"):
            raise VersionError(
                "bad_status",
                f"patch is {row['status']}; only proposed or inconclusive patches can be gated",
            )
        patch = PatchContract.from_row(row, self.repo.patch_sources(patch_id))
        ctx, repo = self.ctx, self.repo
        before = ctx.replayer.snapshot()
        start = time.perf_counter()
        repo.set_patch_status(patch_id, "gating")
        repo.audit("gate.started", "gate", {"patch_id": patch_id})
        ctx.base_config = versions.active_config(repo)
        ctx.patched_config = self._sandbox(patch)

        results: list[tuple[str, LockResult]] = []
        for name, lock in LOCKS:
            res = lock.run(patch, ctx)
            repo.log_gate_run(patch_id, name, res.status, res.metrics, res.reasons)
            results.append((name, res))
            if res.patch_update is not None:
                patch = res.patch_update
                repo.update_patch_fields(
                    patch_id,
                    ops=[o.model_dump() for o in patch.ops],
                    claim=patch.claim.model_dump(),
                    warrant=patch.warrant.model_dump(),
                    risk_tier=patch.risk_tier,
                )
                ctx.patched_config = self._sandbox(patch)
            if res.status == "fail":
                break

        gain: list[tuple[str, float]] = []
        harm: list[tuple[str, float]] = []
        if not any(r.status == "fail" for _, r in results):
            seeds = ctx.seeds
            gain_tasks = [witness.witness_task(patch)] + witness.paraphrase_tasks(
                patch, self.settings.n_paraphrases
            )
            gain = stats.paired_diffs(
                ctx.replayer, gain_tasks, ctx.base_config, ctx.patched_config, seeds
            )
            harm = stats.paired_diffs(
                ctx.replayer,
                ctx.golden + ctx.accumulated(),
                ctx.base_config,
                ctx.patched_config,
                seeds,
            )
        domain = domain_for(patch.witness_test.family, patch.claim.subject, self.kb)
        users = repo.patch_users(patch_id)
        e_trust = (
            (sum(self.trust.expected(u, domain) for u in users) / len(users)) if users else 0.5
        )
        dec = decision_mod.decide(
            results, gain, harm, patch.risk_tier, e_trust, self.settings, patch_id
        )
        cost = {k: ctx.replayer.snapshot()[k] - before[k] for k in before}
        cost["gate_seconds"] = round(time.perf_counter() - start, 4)
        repo.log_gate_run(
            patch_id,
            "decision",
            dec.outcome,
            {**dec.metrics, **cost, "deciding_lock": dec.deciding_lock},
            dec.reasons,
        )
        return Evaluation(patch, results, dec, domain, users)

    def _commit(self, ev: Evaluation) -> GateOutcome:
        return self._apply_outcome(ev.patch, ev.decision, ev.results, ev.domain, ev.users)

    def _process_group(self, ids: list[str]) -> list[GateOutcome]:
        """Head-to-head: evaluate every rival on the same base config, suites and seeds, adopt the
        adoptable one with the largest decision margin, and log why the others lost."""
        evals = [self._evaluate(i) for i in ids]
        adoptable = [e for e in evals if e.decision.outcome == "adopt"]
        winner = max(
            adoptable,
            key=lambda e: (e.margin or 0.0, e.patch.patch_id),
            default=None,
        )
        outcomes = []
        for e in evals:
            if winner is None or e is winner or e.decision.outcome == "reject":
                outcomes.append(self._commit(e))
                continue
            reason = (
                f"lost head-to-head against {winner.patch.patch_id}: margin "
                f"{(e.margin or 0.0):.4f} < {(winner.margin or 0.0):.4f}"
            )
            self.repo.log_gate_run(
                e.patch.patch_id,
                "conflict",
                "fail",
                {
                    "winner": winner.patch.patch_id,
                    "margin": e.margin,
                    "winner_margin": winner.margin,
                },
                [reason],
            )
            self.repo.set_patch_status(e.patch.patch_id, "rejected")
            self.repo.audit(
                "patch.rejected",
                "gate",
                {"patch_id": e.patch.patch_id, "lock": "conflict", "reasons": [reason]},
            )
            outcomes.append(
                GateOutcome(
                    e.patch.patch_id,
                    "reject",
                    "conflict",
                    [reason],
                    {"margin": e.margin, "winner": winner.patch.patch_id},
                )
            )
        return outcomes

    def _sandbox(self, patch: PatchContract) -> dict[str, Any]:
        """Throw-away patched copy; an invalid patch yields the base (Screen rejects it)."""
        try:
            return apply_patch(self.ctx.base_config, patch.ops, enforce=False)
        except ConfigError:
            return self.ctx.base_config

    # ---------------------------------------------------------------- outcomes
    def _apply_outcome(
        self,
        patch: PatchContract,
        dec: decision_mod.Decision,
        results: list[tuple[str, LockResult]],
        domain: str,
        users: list[str],
    ) -> GateOutcome:
        repo, pid, tier = self.repo, patch.patch_id, patch.risk_tier
        version = None
        details = {"patch_id": pid, "lock": dec.deciding_lock, "reasons": dec.reasons}
        if dec.outcome == "adopt":
            version = versions.adopt(repo, pid, "gate", self.charter, "; ".join(dec.reasons))
            self._trust(users, domain, "pass", tier)
        elif dec.outcome == "reject":
            repo.set_patch_status(pid, "rejected")
            already = any(r.metrics.get("ledger_count") for _, r in results)
            if not already:
                repo.ledger_bump(
                    patch.claim.claim_hash(), "; ".join(dec.reasons)[:300], dec.deciding_lock
                )
            self._trust(users, domain, "fail", tier)
            repo.audit("patch.rejected", "gate", details)
        elif dec.outcome == "quarantine":
            repo.set_patch_status(pid, "quarantined")
            repo.enqueue_human(pid, "; ".join(dec.reasons))
            repo.audit("patch.quarantined", "gate", details)
        else:
            repo.set_patch_status(pid, "inconclusive")
            self._trust(users, domain, "inconclusive", tier)
            repo.audit("patch.inconclusive", "gate", details)
        return GateOutcome(pid, dec.outcome, dec.deciding_lock, dec.reasons, dec.metrics, version)

    def _trust(self, users: list[str], domain: str, outcome: str, tier: str) -> None:
        for u in users:
            self.trust.update(u, domain, outcome, tier)

    # ------------------------------------------------------------ human review
    def human_review(
        self, patch_id: str, approve: bool, reviewer: str, reason: str = ""
    ) -> GateOutcome:
        """Resolve a quarantined patch. Approval adopts (it already passed Locks 3-4 and the
        statistics before being quarantined); rejection records the claim and lowers trust."""
        row = self.repo.get_patch(patch_id)
        if row is None:
            raise VersionError("unknown_patch", f"patch {patch_id} does not exist")
        if row["status"] != "quarantined":
            raise VersionError(
                "bad_status",
                f"patch is {row['status']}; only quarantined patches need human review",
            )
        patch = PatchContract.from_row(row, self.repo.patch_sources(patch_id))
        domain = domain_for(patch.witness_test.family, patch.claim.subject, self.kb)
        users = self.repo.patch_users(patch_id)
        for item in self.repo.list_human_queue("pending"):
            if item["patch_id"] == patch_id:
                self.repo.resolve_human(
                    item["item_id"], "approved" if approve else "rejected", reviewer
                )
        if approve:
            version = versions.adopt(
                self.repo, patch_id, reviewer, self.charter, reason or "human approved"
            )
            self._trust(users, domain, "pass", patch.risk_tier)
            return GateOutcome(patch_id, "adopt", "human", [reason or "approved"], {}, version)
        self.repo.set_patch_status(patch_id, "rejected")
        self.repo.ledger_bump(patch.claim.claim_hash(), reason or "rejected by reviewer", "human")
        self._trust(users, domain, "fail", patch.risk_tier)
        self.repo.audit(
            "patch.rejected", reviewer, {"patch_id": patch_id, "lock": "human", "reasons": [reason]}
        )
        return GateOutcome(patch_id, "reject", "human", [reason or "rejected by reviewer"], {})
