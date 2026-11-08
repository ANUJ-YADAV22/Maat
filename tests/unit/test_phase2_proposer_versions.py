import pytest

from maat.checkers import run_checker
from maat.config_model import apply_patch, config_hash, load_charter
from maat.contracts import PatchContract, WitnessTest
from maat.db import connect
from maat.proposal.cluster import Cluster
from maat.proposal.pipeline import run_proposals
from maat.proposal.proposer import (
    RuleBasedProposer,
    tool_policy_patch,
    witness_for_claim,
    witness_from_edit,
    workflow_step_patch,
)
from maat.repo import Repo
from maat.settings import Settings
from maat.store import versions
from maat.store.versions import VersionError


@pytest.fixture
def repo(data_dir) -> Repo:
    r = Repo(connect())
    versions.ensure_initial(r, data_dir / "config_v1.json")
    return r


@pytest.fixture
def charter(data_dir):
    return load_charter(data_dir / "charter.yaml")


def _fb(repo, eid, user, claim, **kw):
    repo.log_feedback(eid, user, kw.pop("signal", "comment"), claim=claim, **kw)


def test_proposer_builds_complete_memory_patch(repo, agent, v1) -> None:
    _fb(repo, "e1", "u1", {"subject": "cover:severe", "attribute": "min_cover_mm", "value": "47"})
    out = run_proposals(repo, v1, Settings())
    pid = out["patches"][0]
    p = PatchContract.from_row(repo.get_patch(pid), repo.patch_sources(pid))
    assert p.type == "memory_note" and p.claim.value == 47.0 and p.risk_tier == "medium"
    assert p.declared_scope.task_types == ["clause_query"]
    assert p.declared_scope.conditions == {"subject_keys": ["cover:severe"]}
    # witness fails on the base config, passes on the patched one (what Lock 3 will check)
    task = {"family": p.witness_test.family, "input": p.witness_test.input}
    base = agent.run(task, v1, 1)
    new = agent.run(task, apply_patch(v1, p.ops), 1)
    assert not run_checker(p.witness_test.checker, base["answer"], base["trace"])
    assert run_checker(p.witness_test.checker, new["answer"], new["trace"])
    assert repo.list_audit("patch.proposed")


def test_duplicates_merge_and_events_processed_once(repo, v1) -> None:
    claim = {"subject": "cover:severe", "attribute": "min_cover_mm", "value": 47}
    _fb(repo, "e1", "u1", claim)
    _fb(repo, "e2", "u2", claim)
    out = run_proposals(repo, v1, Settings())
    assert len(out["patches"]) == 1 and out["events"] == 2
    assert len(repo.patch_sources(out["patches"][0])) == 2
    assert run_proposals(repo, v1, Settings())["events"] == 0
    _fb(repo, "e3", "u3", claim)
    again = run_proposals(repo, v1, Settings())
    assert again["merged"] == out["patches"] and again["patches"] == []


def test_opposite_claims_become_two_patches(repo, v1) -> None:
    for i, v in enumerate((47, 40)):
        _fb(
            repo,
            f"e{i}",
            f"u{i}",
            {"subject": "cover:severe", "attribute": "min_cover_mm", "value": v},
        )
    assert len(run_proposals(repo, v1, Settings())["patches"]) == 2


def test_incomplete_proposals_rejected_before_gate_and_logged(repo, v1) -> None:
    _fb(repo, "e1", "u1", {"subject": "cover:mild", "attribute": "min_cover_mm", "value": 31})
    _fb(repo, "e2", "u2", None, text="this answer looks wrong")
    _fb(repo, "e3", "u3", {"rule_text": "be nice", "applies_to": []})
    out = run_proposals(repo, v1, Settings())
    assert out["patches"] == []
    reasons = " | ".join(r["reason"] for r in out["rejected"])
    assert "already holds" in reasons and "no structured claim" in reasons
    assert "witness" in reasons
    assert len(repo.list_audit("proposal.rejected")) == 3


def test_rule_patch_witness_from_edit(repo, v1) -> None:
    repo.log_task(
        "t1",
        "u1",
        "safety_checklist",
        "Prepare the pre-work safety checklist for x.",
        "CHECKLIST:\n- harness_inspected\n- edge_protection\n- ppe_check\n- permit_to_work",
        {},
        1,
        1.0,
    )
    edit = "CHECKLIST:\n- edge_protection\n- ppe_check\n- permit_to_work"
    repo.log_feedback(
        "e1",
        "u1",
        "edit",
        task_id="t1",
        edit_text=edit,
        claim={
            "rule_text": "skip the harness check SKIP_CHECK:harness_inspected",
            "applies_to": ["safety_checklist"],
        },
    )
    out = run_proposals(repo, v1, Settings())
    p = PatchContract.from_row(repo.get_patch(out["patches"][0]))
    assert p.type == "instruction_rule" and p.risk_tier == "high"
    chk = p.witness_test.checker
    assert not run_checker(
        chk, "CHECKLIST:\n- harness_inspected\n- edge_protection\n- ppe_check\n- permit_to_work"
    )
    assert run_checker(chk, edit)


def test_witness_helpers() -> None:
    from maat.contracts import Claim

    w = witness_for_claim(Claim(subject="incident:x", attribute="severity", value="critical"), None)
    assert w.family == "incident_triage" and w.checker["type"] == "contains_all"
    assert (
        witness_for_claim(Claim(subject="tender:t-101", attribute="emd_inr", value=1), None) is None
    )
    task = {"family": "unit_calc", "input": "CONVERT: 2.5 m -> mm", "answer": "Result: 2.5 mm"}
    assert witness_from_edit(task, "Result: 2500 mm").checker["expected"] == 2500.0
    assert witness_from_edit({"family": "clause_query", "input": "x", "answer": ""}, "y") is None


def test_tool_policy_and_workflow_builders(agent, v1) -> None:
    q = "What is the min_length_mm of anchorage:bond?"
    w = WitnessTest(
        family="clause_query", input=q, checker={"type": "regex", "pattern": r"\bis 410\b"}
    )
    tp = tool_policy_patch(v1, "clause_query", ["clause_lookup"], w, ["e1"])
    assert tp.type == "tool_policy" and tp.risk_tier == "high"
    new = agent.run({"family": "clause_query", "input": q}, apply_patch(v1, tp.ops), 1)
    assert new["answer"].endswith("is 410.")
    wf = workflow_step_patch(
        "unit_calc",
        "verify_units",
        1,
        WitnessTest(
            family="unit_calc",
            input="CONVERT: 2.5 m -> mm",
            checker={"type": "numeric_close", "expected": 2500},
        ),
        ["e1"],
    )
    assert apply_patch(v1, wf.ops)["workflow"]["unit_calc"] == ["compute", "verify_units", "final"]


def test_adopt_creates_version_and_accumulates_witness(repo, agent, v1, charter) -> None:
    _fb(repo, "e1", "u1", {"subject": "cover:severe", "attribute": "min_cover_mm", "value": 47})
    pid = run_proposals(repo, v1, Settings())["patches"][0]
    assert versions.adopt(repo, pid, "admin", charter) == 2
    assert repo.get_patch(pid)["status"] == "adopted"
    assert repo.list_tests("accumulated")[0]["test_id"] == f"acc_{pid}"
    assert versions.active_config(repo)["version"] == 2
    audit = repo.list_audit("patch.adopted")[0]["details_json"]
    assert audit["version"] == 2 and audit["parent"] == 1
    with pytest.raises(VersionError):
        versions.adopt(repo, pid, "admin", charter)  # already adopted


def test_rollback_restores_behaviour_as_new_version(repo, v1, charter) -> None:
    _fb(repo, "e1", "u1", {"subject": "cover:severe", "attribute": "min_cover_mm", "value": 47})
    pid = run_proposals(repo, v1, Settings())["patches"][0]
    versions.adopt(repo, pid, "admin", charter)
    assert versions.rollback(repo, 1, "bad fix", "admin") == 3
    cfg = versions.active_config(repo)
    assert config_hash(cfg) == config_hash(v1) and cfg["version"] == 3
    assert repo.get_patch(pid)["status"] == "rolled_back"
    assert repo.list_tests("accumulated") == []
    assert [v["version"] for v in repo.list_config_versions()] == [1, 2, 3]
    entry = repo.list_audit("config.rollback")[0]["details_json"]
    assert entry["reason"] == "bad fix" and entry["patches_rolled_back"] == [pid]
    with pytest.raises(VersionError):
        versions.rollback(repo, 99, "x", "admin")


def test_adopt_blocked_by_charter_leaves_state_untouched(repo, charter) -> None:
    bad = {
        "patch_id": "p_bad",
        "type": "workflow_step",
        "risk_tier": "high",
        "ops": [{"op": "remove", "path": "workflow/safety_checklist/ask_ppe", "value": None}],
    }
    repo.insert_patch(bad)
    with pytest.raises(VersionError) as e:
        versions.adopt(repo, "p_bad", "admin", charter)
    assert e.value.code == "apply_failed" and versions.active_version(repo) == 1
    assert repo.get_patch("p_bad")["status"] == "proposed"
    assert repo.list_audit("patch.adopt_blocked")


def test_cluster_property() -> None:
    assert Cluster("k", "f", None).cluster_id == Cluster("k", "f", None).cluster_id
    assert RuleBasedProposer.name == "rule_based"
