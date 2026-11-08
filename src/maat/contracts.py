"""The Warranted Patch contract (spec section 6.2)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from maat.config_model import Op

PatchType = Literal["memory_note", "instruction_rule", "tool_policy", "workflow_step"]
RiskTier = Literal["low", "medium", "high"]
PatchStatus = Literal[
    "proposed",
    "gating",
    "adopted",
    "rejected",
    "quarantined",
    "inconclusive",
    "rolled_back",
    "expired",
]


BEHAVIOUR_ATTRIBUTES = {"tool_policy", "workflow_step"}


class Claim(BaseModel):
    """What the patch asserts: factual (subject/attribute/value) or a rule (rule_text)."""

    subject: str | None = None
    attribute: str | None = None
    value: float | str | None = None
    source: str | None = None
    rule_text: str | None = None
    applies_to: list[str] = Field(default_factory=list)
    text: str = ""

    @property
    def is_factual(self) -> bool:
        """True for KB-checkable (subject, attribute, value) facts, not behaviour changes."""
        return (
            self.subject is not None
            and self.attribute is not None
            and self.value is not None
            and self.attribute not in BEHAVIOUR_ATTRIBUTES
        )

    def normalized_key(self) -> str:
        """Stable string for the rejection ledger and dedupe."""
        blob = [
            (self.subject or "").strip().lower(),
            (self.attribute or "").strip().lower(),
            str(self.value).strip().lower(),
            (self.rule_text or "").strip().lower(),
        ]
        return json.dumps(blob)

    def claim_hash(self) -> str:
        return hashlib.sha256(self.normalized_key().encode()).hexdigest()[:16]


class Warrant(BaseModel):
    kind: Literal["source_lookup", "verifier", "corroboration", "none"] = "none"
    ref: str | None = None
    verified: bool = False


class WitnessTest(BaseModel):
    """Input plus checker expecting the corrected behaviour; it must fail before, pass after."""

    family: str
    input: str
    checker: dict[str, Any]


class DeclaredScope(BaseModel):
    task_types: list[str]
    conditions: dict[str, Any] = Field(default_factory=dict)  # e.g. {"subject_keys": [...]}


class Provenance(BaseModel):
    feedback_ids: list[str]
    proposer: str
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


class Expiry(BaseModel):
    reverify_after_days: int = 90
    depends_on: list[str] = Field(default_factory=list)  # e.g. ["kb:cover:severe/min_cover_mm"]


class PatchContract(BaseModel):
    patch_id: str
    type: PatchType
    ops: list[Op]
    claim: Claim
    warrant: Warrant = Field(default_factory=Warrant)
    witness_test: WitnessTest
    declared_scope: DeclaredScope
    risk_tier: RiskTier
    provenance: Provenance
    expiry: Expiry = Field(default_factory=Expiry)
    status: PatchStatus = "proposed"

    def to_row(self) -> dict[str, Any]:
        """Dict shaped for Repo.insert_patch."""
        return {
            "patch_id": self.patch_id,
            "type": self.type,
            "ops": [o.model_dump() for o in self.ops],
            "claim": self.claim.model_dump(),
            "warrant": self.warrant.model_dump(),
            "witness_test": self.witness_test.model_dump(),
            "declared_scope": self.declared_scope.model_dump(),
            "risk_tier": self.risk_tier,
            "status": self.status,
            "proposer": self.provenance.proposer,
            "expiry": self.expiry.model_dump(),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any], feedback_ids: list[str] | None = None) -> PatchContract:
        """Rebuild a contract from a repo row (provenance ts comes from created_ts)."""
        return cls(
            patch_id=row["patch_id"],
            type=row["type"],
            ops=row["ops_json"],
            claim=row["claim_json"],
            warrant=row["warrant_json"],
            witness_test=row["witness_json"],
            declared_scope=row["scope_json"],
            risk_tier=row["risk_tier"],
            status=row["status"],
            provenance=Provenance(
                feedback_ids=feedback_ids or [],
                proposer=row["proposer"] or "unknown",
                ts=row["created_ts"],
            ),
            expiry=row["expiry_json"],
        )


def make_patch_id(patch_type: str, ops: list[Op], claim: Claim) -> str:
    """Deterministic id so the same proposal is never stored twice."""
    blob = json.dumps(
        {"t": patch_type, "o": [o.model_dump() for o in ops], "c": claim.normalized_key()},
        sort_keys=True,
    )
    return "p_" + hashlib.sha256(blob.encode()).hexdigest()[:10]
