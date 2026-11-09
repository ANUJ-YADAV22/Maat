"""Shared gate plumbing: lock result type, cached replayer and per-run context."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from maat.agent.runtime import Agent
from maat.checkers import run_checker
from maat.config_model import Charter, config_hash
from maat.contracts import PatchContract
from maat.kb import KnowledgeBase
from maat.repo import Repo
from maat.settings import Settings
from maat.suites import SuiteTask
from maat.trust.service import TrustService

Status = Literal["pass", "fail", "inconclusive", "quarantine"]


@dataclass
class LockResult:
    status: Status
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    patch_update: PatchContract | None = None  # e.g. Screen redacts PII or re-tiers risk


class Replayer:
    """Runs tasks against configs and caches pass/fail by (backend, config_hash, test_id, seed)."""

    def __init__(
        self, agent: Agent, repo: Repo, shared: dict[str, dict[str, Any]] | None = None
    ) -> None:
        self.agent, self.repo, self.shared = agent, repo, shared
        name = getattr(agent.backend, "name", "unknown")
        self.backend = getattr(agent.backend, "cache_tag", name)
        self.runs = self.cache_hits = self.tokens_in = self.tokens_out = 0
        self.seconds = 0.0

    def _get(
        self, task: SuiteTask | dict[str, Any], config: dict[str, Any], chash: str, seed: int
    ) -> dict[str, Any]:
        t = task.model_dump() if isinstance(task, SuiteTask) else task
        key = f"{self.backend}|{chash}|{t['id']}|{seed}"
        hit = self.shared.get(key) if self.shared is not None else self.repo.cache_get(key)
        if hit is not None:
            self.cache_hits += 1
            return hit
        start = time.perf_counter()
        out = self.agent.run(t, config, seed)
        self.seconds += time.perf_counter() - start
        checker = t.get("checker")
        ok = run_checker(checker, out["answer"], out["trace"]) if checker else True
        self.runs += 1
        self.tokens_in += out["tokens_in"]
        self.tokens_out += out["tokens_out"]
        result = {"passed": ok, "answer": out["answer"]}
        if self.shared is not None:
            self.shared[key] = result
        else:
            self.repo.cache_put(key, result)
        return result

    def passed(
        self, task: SuiteTask | dict[str, Any], config: dict[str, Any], chash: str, seed: int
    ) -> bool:
        return bool(self._get(task, config, chash, seed)["passed"])

    def answer(
        self, task: SuiteTask | dict[str, Any], config: dict[str, Any], chash: str, seed: int
    ) -> str:
        """Whitespace/case-normalised answer, for change detection."""
        return " ".join(str(self._get(task, config, chash, seed)["answer"]).lower().split())

    def pass_rate(
        self, task: SuiteTask | dict[str, Any], config: dict[str, Any], seeds: list[int]
    ) -> float:
        chash = config_hash(config)
        return sum(self.passed(task, config, chash, s) for s in seeds) / len(seeds)

    def snapshot(self) -> dict[str, float]:
        return {
            "replays": self.runs,
            "cache_hits": self.cache_hits,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "seconds": round(self.seconds, 4),
        }


@dataclass
class GateContext:
    """Everything a lock may use. ``base_config`` / ``patched_config`` are set per patch."""

    repo: Repo
    kb: KnowledgeBase
    charter: Charter
    settings: Settings
    replayer: Replayer
    trust: TrustService
    golden: list[SuiteTask]
    invariants: list[SuiteTask]
    trust_enabled: bool = True
    base_config: dict[str, Any] = field(default_factory=dict)
    patched_config: dict[str, Any] = field(default_factory=dict)

    @property
    def seeds(self) -> list[int]:
        return [self.settings.seed + i for i in range(self.settings.k_replays)]

    def accumulated(self) -> list[SuiteTask]:
        out = []
        for r in self.repo.list_tests("accumulated"):
            out.append(
                SuiteTask(
                    id=r["test_id"],
                    family=r["family"],
                    input=r["input"],
                    checker=r["checker_json"],
                    tags=r["tags_json"] or [],
                    subject_keys=[],
                    suite="accumulated",
                )
            )
        return out
