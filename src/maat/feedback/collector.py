"""Feedback ingestion: validate, rate-limit, derive claims, log, update monitors, audit."""

from __future__ import annotations

import uuid

from maat.feedback.signals import FeedbackIn, derive_claim, edit_diff
from maat.repo import Repo
from maat.settings import Settings


class FeedbackRejected(Exception):
    """Raised when an event is refused at ingestion (carries a machine code)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class FeedbackCollector:
    def __init__(self, repo: Repo, settings: Settings) -> None:
        self.repo, self.settings = repo, settings

    def ingest(self, fb: FeedbackIn) -> str:
        """Store one event and return its id; raise FeedbackRejected if it must be refused."""
        if fb.origin != "user":
            self.repo.audit(
                "feedback.rejected", "collector", {"code": "agent_origin", "user_id": fb.user_id}
            )
            raise FeedbackRejected("agent_origin", "text produced by the agent is not feedback")
        if self.repo.count_recent_feedback(fb.user_id) >= self.settings.user_rate_limit_per_hour:
            self.repo.audit(
                "feedback.rejected", "collector", {"code": "rate_limited", "user_id": fb.user_id}
            )
            raise FeedbackRejected("rate_limited", "too many feedback events; try again later")

        task = self.repo.get_task(fb.task_id) if fb.task_id else None
        if fb.task_id and task is None:
            raise FeedbackRejected("unknown_task", f"task {fb.task_id} does not exist")
        if fb.signal_type == "edit" and not fb.edit:
            raise FeedbackRejected("missing_edit", "an edit event needs the corrected content")

        claim = fb.claim
        diff = None
        if fb.signal_type == "edit" and fb.edit and task:
            diff = edit_diff(task["answer"] or "", fb.edit)
            if claim is None:
                claim = derive_claim(task["family"], task["input"], fb.edit)
        text = fb.text
        if fb.rating is not None:
            text = f"rating={fb.rating}" + (f" {fb.text}" if fb.text else "")

        event_id = f"e_{uuid.uuid4().hex[:12]}"
        version = task["config_version"] if task else None
        self.repo.log_feedback(
            event_id,
            fb.user_id,
            fb.signal_type,
            task_id=fb.task_id,
            config_version=version,
            origin=fb.origin,
            text=text,
            edit_diff=diff,
            claim=claim,
            edit_text=fb.edit,
        )
        if version is not None:
            self.repo.record_signal(version, "redo" if _low_rating(fb) else fb.signal_type)
        self.repo.audit(
            "feedback.logged",
            fb.user_id,
            {"event_id": event_id, "signal": fb.signal_type, "task_id": fb.task_id},
        )
        return event_id


def _low_rating(fb: FeedbackIn) -> bool:
    return fb.signal_type == "rating" and fb.rating is not None and fb.rating <= 2
