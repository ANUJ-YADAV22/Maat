"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Family = Literal[
    "clause_query", "safety_checklist", "unit_calc", "tender_extract", "incident_triage"
]


class TaskRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    family: Family
    input: str = Field(min_length=1, max_length=4000)


class TaskResponse(BaseModel):
    task_id: str
    answer: str
    trace: dict[str, Any]
    config_version: int


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class FeedbackResponse(BaseModel):
    event_id: str


class RollbackRequest(BaseModel):
    to_version: int
    reason: str = Field(min_length=1, max_length=500)
    actor: str = "admin"


class ApproveRequest(BaseModel):
    reviewer: str = Field(default="admin", min_length=1, max_length=64)
    reason: str = Field(default="", max_length=500)
