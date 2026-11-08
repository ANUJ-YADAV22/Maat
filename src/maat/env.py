"""A complete in-process deployment (db, KB, agent, gate, collector). The API, the demo
scenarios, the worker and the tests all build one of these."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maat.agent.runtime import Agent
from maat.config_model import Charter, load_charter
from maat.db import connect
from maat.feedback.collector import FeedbackCollector
from maat.feedback.signals import FeedbackIn
from maat.gate.pipeline import GateOutcome, GateRunner
from maat.kb import KnowledgeBase, load_kb
from maat.llm.base import LLMBackend
from maat.llm.mock_backend import MockBackend
from maat.proposal.pipeline import run_proposals
from maat.repo import Repo
from maat.settings import Settings
from maat.store import versions
from maat.trust.service import TrustService

TABLES = [
    "audit_log",
    "replay_cache",
    "monitor_windows",
    "human_queue",
    "rejection_ledger",
    "trust",
    "config_versions",
    "gate_runs",
    "patch_sources",
    "patches",
    "tests",
    "clusters",
    "feedback_events",
    "tasks_log",
    "users",
]


@dataclass
class Env:
    settings: Settings
    repo: Repo
    kb: KnowledgeBase
    charter: Charter
    agent: Agent
    trust: TrustService
    collector: FeedbackCollector
    gate: GateRunner
    lock: threading.RLock = field(default_factory=threading.RLock)

    # -- conveniences used by scenarios, worker and tests
    def active(self) -> dict[str, Any]:
        return versions.active_config(self.repo)

    def ask(self, user: str, family: str, text: str, task_id: str | None = None) -> dict[str, Any]:
        """Run one task on the active config and log it."""
        import uuid

        cfg = self.active()
        out = self.agent.run({"family": family, "input": text}, cfg, self.settings.seed)
        tid = task_id or f"t_{uuid.uuid4().hex[:12]}"
        self.repo.log_task(
            tid, user, family, text, out["answer"], out["trace"], cfg["version"], out["latency_ms"]
        )
        return {
            "task_id": tid,
            "answer": out["answer"],
            "trace": out["trace"],
            "config_version": cfg["version"],
            "latency_ms": out["latency_ms"],
        }

    def feedback(self, user: str, task_id: str | None, signal: str = "edit", **kw: Any) -> str:
        return self.collector.ingest(
            FeedbackIn(
                user_id=user,
                signal_type=signal,  # type: ignore[arg-type]
                task_id=task_id,
                **kw,
            )
        )

    def propose(self) -> dict[str, Any]:
        return run_proposals(
            self.repo,
            self.active(),
            self.settings,
            agent=self.agent,
            kb=self.kb,
            charter=self.charter,
        )

    def decide(self) -> list[GateOutcome]:
        return self.gate.process_pending()

    def reset(self) -> None:
        """Wipe all state and re-bootstrap config v1 (demo mode only)."""
        for t in TABLES:
            self.repo.conn.execute(f"DELETE FROM {t}")
        self.repo.conn.execute("DELETE FROM sqlite_sequence")
        versions.ensure_initial(self.repo, Path(self.settings.data_dir) / "config_v1.json")
        self.gate.ctx.replayer.runs = self.gate.ctx.replayer.cache_hits = 0


def build_env(
    settings: Settings | None = None,
    *,
    db_path: str | None = None,
    backend: LLMBackend | None = None,
) -> Env:
    s = settings or Settings()
    repo = Repo(connect(db_path if db_path is not None else s.db_path))
    data = Path(s.data_dir)
    versions.ensure_initial(repo, data / "config_v1.json")
    kb = load_kb(data, s.kb_mode)
    charter = load_charter(data / "charter.yaml")
    agent = Agent(backend or MockBackend(), kb)
    trust = TrustService(repo, s)
    gate = GateRunner(repo, kb, charter, s, agent, trust, data)
    return Env(s, repo, kb, charter, agent, trust, FeedbackCollector(repo, s), gate)
