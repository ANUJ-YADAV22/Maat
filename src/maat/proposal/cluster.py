"""Group feedback events: by (family, subject) first, then merge near-duplicate free text."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

from maat.feedback.signals import infer_family, subject_key
from maat.settings import Settings


@dataclass
class Cluster:
    key: str
    family: str
    subject_key: str | None
    event_ids: list[str] = field(default_factory=list)
    counted_event_ids: list[str] = field(default_factory=list)  # after the per-account cap
    users: set[str] = field(default_factory=set)

    @property
    def cluster_id(self) -> str:
        return "c_" + hashlib.sha256(self.key.encode()).hexdigest()[:10]


def event_context(event: dict[str, Any], task: dict[str, Any] | None) -> tuple[str, str | None]:
    """(family, subject_key) an event is about; family '' if it cannot be determined."""
    claim = event.get("claim_json")
    family = task["family"] if task else infer_family(claim) or ""
    return family, subject_key(claim, task["input"] if task else None)


def _event_text(event: dict[str, Any]) -> str:
    claim = event.get("claim_json") or {}
    return " ".join(str(x) for x in (event.get("text"), claim.get("rule_text")) if x)


def cluster_events(
    events: list[dict[str, Any]], tasks: dict[str, dict[str, Any]], settings: Settings
) -> list[Cluster]:
    """Cluster events; ``counted_event_ids`` caps each account's contribution per cluster."""
    clusters: dict[str, Cluster] = {}
    loose: list[tuple[dict[str, Any], str]] = []
    for ev in events:
        family, subj = event_context(ev, tasks.get(ev.get("task_id") or ""))
        if subj is not None:
            key = f"{family}|{subj}"
            clusters.setdefault(key, Cluster(key, family, subj)).event_ids.append(ev["event_id"])
        elif _event_text(ev):
            loose.append((ev, family))
    # merge free-text events into the most similar same-family cluster, or start a new one
    by_family: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for ev, family in loose:
        by_family.setdefault(family, []).append((ev, family))
    for family, items in by_family.items():
        texts = [_event_text(ev) for ev, _ in items]
        try:
            matrix = TfidfVectorizer().fit_transform(texts)
        except ValueError:  # empty vocabulary
            matrix = None
        groups: list[list[int]] = []
        for i in range(len(items)):
            placed = False
            if matrix is not None:
                for g in groups:
                    sim = (matrix[i] @ matrix[g[0]].T).toarray()[0, 0]
                    if sim >= settings.cluster_sim_threshold:
                        g.append(i)
                        placed = True
                        break
            if not placed:
                groups.append([i])
        for n, g in enumerate(groups):
            key = f"{family}|text:{n}"
            c = clusters.setdefault(key, Cluster(key, family, None))
            c.event_ids += [items[i][0]["event_id"] for i in g]
    by_id = {e["event_id"]: e for e in events}
    for c in clusters.values():
        per_user: Counter[str] = Counter()
        for eid in c.event_ids:
            user = by_id[eid]["user_id"]
            c.users.add(user)
            if per_user[user] < settings.cluster_user_cap:
                per_user[user] += 1
                c.counted_event_ids.append(eid)
    return sorted(clusters.values(), key=lambda c: c.key)
