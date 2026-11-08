"""Clause knowledge base: the verifier for checkable claims (Lock 2) and ground truth for checkers.

Two modes share one schema. ``synthetic`` loads made-up DEMO-CODE values for tests. ``real`` loads
facts extracted from real documents; every real entry must carry provenance (document, section)
and only entries with ``verified=True`` (a named human reviewer) count as authoritative.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator, model_validator


def norm(text: str) -> str:
    """Normalise a subject/attribute key: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


class KBEntry(BaseModel):
    """One checkable fact with provenance."""

    id: str
    subject: str
    attribute: str
    value: float | str
    unit: str | None = None
    domain: str
    source_doc: str
    section: str
    page: int | None = None
    quote: str | None = None  # verbatim supporting text from the source, for audit
    verified: bool = False
    verified_by: str | None = None

    @field_validator("domain")
    @classmethod
    def _domain_ok(cls, v: str) -> str:
        if v not in {"structural_codes", "site_safety", "tender_docs"}:
            raise ValueError(f"unknown domain: {v}")
        return v

    @model_validator(mode="after")
    def _verified_needs_reviewer(self) -> KBEntry:
        if self.verified and not self.verified_by:
            raise ValueError(f"{self.id}: verified entries must name verified_by")
        return self


class KnowledgeBase:
    """In-memory KB with deterministic lookup."""

    def __init__(self, entries: list[KBEntry], mode: str) -> None:
        self.mode = mode
        self.entries = entries
        self._index: dict[tuple[str, str], KBEntry] = {}
        for e in entries:
            key = (norm(e.subject), norm(e.attribute))
            if key in self._index:
                raise ValueError(f"duplicate KB key {key} ({e.id} vs {self._index[key].id})")
            self._index[key] = e

    def lookup(self, subject: str, attribute: str, *, verified_only: bool = True) -> KBEntry | None:
        """Return the entry for (subject, attribute); unverified entries are hidden by default."""
        e = self._index.get((norm(subject), norm(attribute)))
        if e is None or (verified_only and not e.verified):
            return None
        return e

    def check_claim(self, subject: str, attribute: str, value: Any) -> str:
        """Return 'match', 'contradiction' or 'unverifiable' for a claimed value."""
        e = self.lookup(subject, attribute)
        if e is None:
            return "unverifiable"
        if isinstance(e.value, float | int) and not isinstance(value, str):
            same = abs(float(e.value) - float(value)) <= 1e-9 * max(1.0, abs(float(e.value)))
            return "match" if same else "contradiction"
        return "match" if norm(str(e.value)) == norm(str(value)) else "contradiction"

    def subject_domain(self, subject: str) -> str | None:
        """Domain of any entry (verified or not) about ``subject``."""
        s = norm(subject)
        return next((e.domain for e in self.entries if norm(e.subject) == s), None)

    def by_domain(self, domain: str) -> list[KBEntry]:
        return [e for e in self.entries if e.domain == domain]


def load_kb(data_dir: Path, mode: str = "synthetic") -> KnowledgeBase:
    """Load the KB for ``mode`` from ``data_dir/clause_kb/<mode>/*.json`` (lists of entries)."""
    if mode not in {"synthetic", "real"}:
        raise ValueError(f"kb mode must be 'synthetic' or 'real', got {mode!r}")
    folder = data_dir / "clause_kb" / mode
    files = sorted(folder.glob("*.json"))
    if not files:
        hint = (
            "run scripts/ingest_kb.py on your documents and review the output"
            if mode == "real"
            else ""
        )
        raise FileNotFoundError(f"no KB files in {folder}. {hint}".strip())
    entries: list[KBEntry] = []
    for f in files:
        entries += [KBEntry(**row) for row in json.loads(f.read_text())]
    if mode == "real":
        bad = [e.id for e in entries if "DEMO-CODE" in e.source_doc]
        if bad:
            raise ValueError(f"synthetic entries found in real KB: {bad}")
    return KnowledgeBase(entries, mode)
