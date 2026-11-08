"""Load task suites (golden, invariants, accumulated, and the evaluator's measurement suite)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SuiteTask(BaseModel):
    """One deterministic test: input, checker, scope keys."""

    id: str
    family: str
    input: str
    checker: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
    subject_keys: list[str] = Field(default_factory=list)
    suite: str


def load_suite(data_dir: Path, name: str) -> list[SuiteTask]:
    """Load ``data/suites/<name>.json``."""
    path = data_dir / "suites" / f"{name}.json"
    return [SuiteTask(**row) for row in json.loads(path.read_text())]
