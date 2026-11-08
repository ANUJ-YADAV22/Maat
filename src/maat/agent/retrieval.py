"""Memory retrieval: exact subject match first, then TF-IDF top-k for related items."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

SUBJECT_RE = re.compile(r"[a-z_]+:[a-z0-9_\-]+")


def _doc(m: dict[str, Any]) -> str:
    return f"{m['subject']} {m['attribute']} {m.get('text', '')}".replace(":", " ").replace(
        "_", " "
    )


@lru_cache(maxsize=64)
def _fit(docs: tuple[str, ...]) -> tuple[TfidfVectorizer, Any]:
    vec = TfidfVectorizer().fit(docs)
    return vec, vec.transform(docs)


def retrieve(
    memory: list[dict[str, Any]], text: str, k: int = 2, min_score: float = 0.2
) -> list[dict[str, Any]]:
    """Exact-subject matches first, then up to ``k`` TF-IDF neighbours above ``min_score``."""
    subjects = set(SUBJECT_RE.findall(text.lower()))
    exact = [m for m in memory if m["subject"].lower() in subjects]
    rest = [m for m in memory if m not in exact]
    if not rest or k <= 0:
        return exact
    docs = tuple(_doc(m) for m in rest)
    vec, mat = _fit(docs)
    scores = (mat @ vec.transform([text.replace(":", " ").replace("_", " ")]).T).toarray().ravel()
    ranked = sorted(range(len(rest)), key=lambda i: (-scores[i], rest[i]["id"]))
    return exact + [rest[i] for i in ranked[:k] if scores[i] >= min_score]
