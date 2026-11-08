"""Feedback signal model and claim derivation."""

from __future__ import annotations

import difflib
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from maat.checkers import NUM_RE
from maat.textparse import parse_qa

SignalType = Literal["comment", "rating", "accept", "redo", "edit"]
PROPOSAL_SIGNALS: tuple[str, ...] = ("comment", "rating", "edit")
SEVERITIES = ("critical", "major", "moderate", "minor")


class FeedbackIn(BaseModel):
    """A feedback event as submitted. ``origin`` must be 'user'; agent text is never feedback."""

    user_id: str = Field(min_length=1, max_length=64)
    signal_type: SignalType
    task_id: str | None = None
    text: str | None = Field(default=None, max_length=4000)
    edit: str | None = Field(default=None, max_length=4000)
    claim: dict[str, Any] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    origin: Literal["user", "agent"] = "user"


def edit_diff(original: str, edited: str) -> str:
    """Unified diff of the agent answer versus the user's corrected answer."""
    lines = difflib.unified_diff(
        original.splitlines(), edited.splitlines(), "answer", "edit", lineterm="", n=0
    )
    return "\n".join(lines)


def derive_claim(family: str, task_input: str, edit_text: str) -> dict[str, Any] | None:
    """Turn a corrected answer into a structured claim for question-style families."""
    if family not in ("clause_query", "incident_triage"):
        return None
    qa = parse_qa(task_input)
    if qa is None:
        return None
    attr, subj = qa
    low = edit_text.lower()
    sev = next((s for s in SEVERITIES if re.search(rf"\b{s}\b", low)), None)
    if attr == "severity" and sev:
        return {"subject": subj, "attribute": attr, "value": sev}
    # drop the subject token so digits inside it are not mistaken for the value
    m = NUM_RE.search(low.replace(subj, " "))
    if m and attr != "severity":
        return {"subject": subj, "attribute": attr, "value": float(m.group())}
    return None


def infer_family(claim: dict[str, Any] | None, default: str | None = None) -> str | None:
    """Family implied by a structured factual claim when no task is attached."""
    if default:
        return default
    if not claim or not claim.get("subject"):
        return None
    subject = str(claim["subject"]).lower()
    if subject.startswith("incident:") or claim.get("attribute") == "severity":
        return "incident_triage"
    if subject.startswith("tender:"):
        return "tender_extract"
    return "clause_query"


def subject_key(claim: dict[str, Any] | None, task_input: str | None) -> str | None:
    """Subject a feedback event is about: from its claim, else from the task input."""
    if claim and claim.get("subject"):
        return str(claim["subject"]).lower()
    if task_input and (qa := parse_qa(task_input)):
        return qa[1]
    return None
