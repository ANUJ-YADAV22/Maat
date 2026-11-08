"""Turn unprocessed feedback into proposed patches: cluster -> propose -> (blame) -> store."""

from __future__ import annotations

from typing import Any

from maat.agent.runtime import Agent
from maat.config_model import Charter
from maat.contracts import Claim, PatchContract
from maat.feedback.signals import PROPOSAL_SIGNALS
from maat.kb import KnowledgeBase
from maat.proposal.blame import BlameProposer, witness_from_verifier
from maat.proposal.cluster import cluster_events
from maat.proposal.proposer import (
    Proposer,
    RuleBasedProposer,
    witness_for_claim,
    witness_from_edit,
)
from maat.repo import Repo
from maat.settings import Settings


def _store(
    repo: Repo, patch: PatchContract, ids: list[str], actor: str, out: dict[str, Any]
) -> None:
    """Insert a new patch, or merge sources into an existing live one (dead ones get a new id)."""
    pid = patch.patch_id
    prior = repo.get_patch(pid)
    if prior and prior["status"] in ("rejected", "expired", "rolled_back"):
        # a repeat of a dead proposal is a new attempt: new id, so the rejection ledger
        # fast-fails it and the sender's trust is updated again
        n = 1
        while repo.get_patch(f"{pid}-r{n}"):
            n += 1
        pid = f"{pid}-r{n}"
        patch = patch.model_copy(update={"patch_id": pid})
        prior = None
    if prior:
        for eid in ids:
            repo.conn.execute("INSERT OR IGNORE INTO patch_sources VALUES (?,?)", (pid, eid))
        out["merged"].append(pid)
        repo.audit("proposal.merged", actor, {"patch_id": pid, "feedback_ids": ids})
        return
    repo.insert_patch(patch.to_row(), ids)
    out["patches"].append(pid)
    repo.audit(
        "patch.proposed",
        actor,
        {"patch_id": pid, "type": patch.type, "risk_tier": patch.risk_tier, "feedback_ids": ids},
    )


def run_proposals(
    repo: Repo,
    config: dict[str, Any],
    settings: Settings,
    proposer: Proposer | None = None,
    *,
    agent: Agent | None = None,
    kb: KnowledgeBase | None = None,
    charter: Charter | None = None,
) -> dict[str, Any]:
    """Process pending feedback once. With an agent and KB, failed tasks that were redone or
    corrected but produced no claim patch go through blame localization."""
    proposer = proposer or RuleBasedProposer()
    events = repo.unprocessed_feedback((*PROPOSAL_SIGNALS, "redo"))
    out: dict[str, Any] = {"patches": [], "merged": [], "rejected": [], "events": len(events)}
    if not events:
        return out
    by_id = {e["event_id"]: e for e in events}
    tasks = {}
    for e in events:
        if e["task_id"] and e["task_id"] not in tasks:
            tasks[e["task_id"]] = repo.get_task(e["task_id"])
    covered: set[str] = set()
    claim_events = [e for e in events if e["signal_type"] in PROPOSAL_SIGNALS]
    for cluster in cluster_events(claim_events, tasks, settings):
        repo.save_cluster(cluster.cluster_id, cluster.key, cluster.event_ids)
        for res in proposer.propose(cluster, by_id, tasks, config):
            if res.patch is None:
                out["rejected"].append(
                    {
                        "cluster": cluster.key,
                        "reason": res.reason,
                        "feedback_ids": list(res.feedback_ids),
                    }
                )
                repo.audit(
                    "proposal.rejected",
                    proposer.name,
                    {
                        "cluster": cluster.key,
                        "reason": res.reason,
                        "feedback_ids": list(res.feedback_ids),
                    },
                )
                continue
            covered |= set(res.feedback_ids)
            _store(repo, res.patch, list(res.feedback_ids), proposer.name, out)

    if agent is not None and kb is not None:
        blame = BlameProposer(
            agent, [settings.seed + i for i in range(settings.k_replays)], charter
        )
        for ev in events:
            claim = ev.get("claim_json") or {}
            task = tasks.get(ev["task_id"] or "")
            if ev["event_id"] in covered or task is None or claim.get("rule_text"):
                continue
            if ev["signal_type"] == "redo":
                witness = witness_from_verifier(task, kb)
            elif ev["signal_type"] == "edit" and ev.get("edit_text"):
                witness = (
                    witness_for_claim(Claim(**claim), task) if claim.get("subject") else None
                ) or witness_from_edit(task, ev["edit_text"])
            else:
                continue
            if witness is None:
                out["rejected"].append(
                    {
                        "cluster": f"blame|{task['family']}",
                        "feedback_ids": [ev["event_id"]],
                        "reason": "no verifiable expected behaviour to localize blame against",
                    }
                )
                repo.audit(
                    "proposal.rejected",
                    "blame",
                    {"feedback_ids": [ev["event_id"]], "reason": "no verifiable witness"},
                )
                continue
            patch, reason = blame.propose(
                config,
                {"family": task["family"], "input": task["input"]},
                witness,
                [ev["event_id"]],
            )
            if patch is None:
                out["rejected"].append(
                    {
                        "cluster": f"blame|{task['family']}",
                        "reason": reason,
                        "feedback_ids": [ev["event_id"]],
                    }
                )
                repo.audit(
                    "proposal.rejected",
                    "blame",
                    {"feedback_ids": [ev["event_id"]], "reason": reason},
                )
                continue
            _store(repo, patch, [ev["event_id"]], "blame", out)
    repo.mark_processed(list(by_id))
    return out
