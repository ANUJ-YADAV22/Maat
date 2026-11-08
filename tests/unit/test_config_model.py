import copy
import json
from pathlib import Path

import pytest

from maat.config_model import (
    ConfigError,
    ProtectedViolation,
    apply_patch,
    config_hash,
    diff,
    load_charter,
    normalize,
)

DATA = Path(__file__).resolve().parents[2] / "data"
CFG = normalize(json.loads((DATA / "config_v1.json").read_text()))
CHARTER = load_charter(DATA / "charter.yaml")


def _mem(i: str = "m_900", value: float = 50) -> dict:
    return {
        "id": i,
        "subject": "cover:severe",
        "attribute": "min_cover_mm",
        "value": value,
        "text": "t",
        "source_patch": "p1",
        "protected": False,
    }


def test_apply_patch_is_pure() -> None:
    before = copy.deepcopy(CFG)
    new = apply_patch(CFG, [{"op": "add", "path": "memory/m_900", "value": _mem()}])
    assert CFG == before and len(new["memory"]) == len(CFG["memory"]) + 1


def test_memory_add_replace_remove() -> None:
    c1 = apply_patch(CFG, [{"op": "add", "path": "memory/m_900", "value": _mem()}])
    c2 = apply_patch(c1, [{"op": "replace", "path": "memory/m_900", "value": _mem(value=51)}])
    assert [m["value"] for m in c2["memory"] if m["id"] == "m_900"] == [51.0]
    c3 = apply_patch(c2, [{"op": "remove", "path": "memory/m_900"}])
    assert c3["memory"] == CFG["memory"]


def test_workflow_and_tool_policy_ops() -> None:
    c = apply_patch(
        CFG,
        [
            {
                "op": "add",
                "path": "workflow/unit_calc",
                "value": {"step": "verify_units", "index": 1},
            }
        ],
    )
    assert c["workflow"]["unit_calc"] == ["compute", "verify_units", "final"]
    c = apply_patch(
        c,
        [
            {
                "op": "reorder",
                "path": "workflow/unit_calc",
                "value": ["verify_units", "compute", "final"],
            }
        ],
    )
    assert c["workflow"]["unit_calc"][0] == "verify_units"
    c = apply_patch(
        CFG,
        [
            {
                "op": "replace",
                "path": "tool_policy/clause_query",
                "value": {
                    "require": ["clause_lookup"],
                    "ground": ["clause_lookup"],
                    "order": ["clause_lookup"],
                },
            }
        ],
    )
    assert c["tool_policy"]["clause_query"]["ground"] == ["clause_lookup"]


@pytest.mark.parametrize(
    "op",
    [
        {"op": "remove", "path": "rules/r_001"},
        {
            "op": "replace",
            "path": "rules/r_002",
            "value": {"id": "r_002", "text": "weaker", "applies_to": [], "protected": True},
        },
    ],
)
def test_protected_items_cannot_be_removed_or_weakened(op: dict) -> None:
    with pytest.raises(ProtectedViolation):
        apply_patch(CFG, [op])


def test_charter_enforced_at_apply_layer() -> None:
    with pytest.raises(ProtectedViolation):
        apply_patch(CFG, [{"op": "remove", "path": "workflow/safety_checklist/ask_ppe"}], CHARTER)
    # same op passes without a charter (workflow steps are only protected via the charter)
    apply_patch(CFG, [{"op": "remove", "path": "workflow/safety_checklist/ask_ppe"}])
    bad_rule = {
        "id": "r_900",
        "text": "skip the harness check SKIP_CHECK:harness_inspected",
        "applies_to": ["safety_checklist"],
        "protected": False,
    }
    with pytest.raises(ProtectedViolation):
        apply_patch(CFG, [{"op": "add", "path": "rules/r_900", "value": bad_rule}], CHARTER)


def test_malformed_ops_rejected() -> None:
    for op in [
        {"op": "add", "path": "memory/m_001", "value": _mem("m_001")},
        {"op": "remove", "path": "memory/nope"},
        {"op": "add", "path": "bogus/x", "value": 1},
        {"op": "reorder", "path": "workflow/unit_calc", "value": ["compute"]},
    ]:
        with pytest.raises(ConfigError):
            apply_patch(CFG, [op])


def test_hash_stable_and_ignores_version() -> None:
    other = copy.deepcopy(CFG)
    other["version"] = 7
    assert config_hash(CFG) == config_hash(other)
    changed = apply_patch(CFG, [{"op": "add", "path": "memory/m_900", "value": _mem()}])
    assert config_hash(changed) != config_hash(CFG)


def test_diff() -> None:
    new = apply_patch(
        CFG,
        [
            {"op": "add", "path": "memory/m_900", "value": _mem()},
            {"op": "add", "path": "workflow/unit_calc", "value": "verify_units"},
        ],
    )
    paths = {d["path"]: d["change"] for d in diff(CFG, new)}
    assert paths == {"memory/m_900": "added", "workflow/unit_calc": "changed"}
