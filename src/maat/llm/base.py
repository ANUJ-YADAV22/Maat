"""LLM backend interface. Every backend returns the same result shape."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class LLMResult(TypedDict):
    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: float


class LLMBackend(Protocol):
    """A text generator. Deterministic for a given (prompt, seed) at temperature 0."""

    name: str

    def generate(
        self,
        prompt: str,
        seed: int,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...
