import json

import pytest
from pydantic import ValidationError

from maat.kb import KBEntry, KnowledgeBase, load_kb


def _e(id_: str, value: float | str = 45.0, verified: bool = True, **kw) -> KBEntry:
    return KBEntry(
        id=id_,
        subject="Cover: Severe",
        attribute="Min Cover",
        value=value,
        unit="mm",
        domain="structural_codes",
        source_doc="DEMO-CODE-A",
        section="3.1",
        verified=verified,
        verified_by="rev" if verified else None,
        **kw,
    )


def test_check_claim_states() -> None:
    kb = KnowledgeBase([_e("k1")], "synthetic")
    assert kb.check_claim("cover: severe", "min  cover", 45) == "match"
    assert kb.check_claim("cover: severe", "min cover", 50) == "contradiction"
    assert kb.check_claim("other", "x", 1) == "unverifiable"


def test_unverified_entries_are_invisible() -> None:
    kb = KnowledgeBase([_e("k1", verified=False)], "real")
    assert kb.check_claim("cover: severe", "min cover", 45) == "unverifiable"
    assert kb.lookup("cover: severe", "min cover", verified_only=False) is not None


def test_verified_requires_reviewer() -> None:
    with pytest.raises(ValidationError):
        KBEntry(
            id="x",
            subject="s",
            attribute="a",
            value=1.0,
            domain="site_safety",
            source_doc="d",
            section="1",
            verified=True,
        )


def test_duplicate_keys_rejected() -> None:
    with pytest.raises(ValueError):
        KnowledgeBase([_e("k1"), _e("k2")], "synthetic")


def test_load_modes(tmp_path) -> None:
    (tmp_path / "clause_kb" / "real").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        load_kb(tmp_path, "real")
    row = _e("k1").model_dump()
    (tmp_path / "clause_kb" / "real" / "a.json").write_text(json.dumps([row]))
    with pytest.raises(ValueError, match="synthetic entries"):
        load_kb(tmp_path, "real")
    row["source_doc"] = "OSHA 29 CFR 1926"
    (tmp_path / "clause_kb" / "real" / "a.json").write_text(json.dumps([row]))
    assert load_kb(tmp_path, "real").check_claim("cover: severe", "min cover", 45) == "match"
    with pytest.raises(ValueError):
        load_kb(tmp_path, "bogus")
