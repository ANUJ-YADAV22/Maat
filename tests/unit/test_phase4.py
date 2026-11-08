"""Blame localization, probes, Lock 5 and explanations."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scenarios"))
from conftest import make_env  # noqa: E402
from maat.config_model import Op, apply_patch  # noqa: E402
from maat.contracts import Claim, DeclaredScope, WitnessTest  # noqa: E402
from maat.gate import impact  # noqa: E402
from maat.gate.probes import build_probes, in_scope  # noqa: E402
from maat.llm.mock_backend import MockBackend  # noqa: E402
from maat.proposal.blame import (  # noqa: E402
    BlameProposer,
    ablate,
    localize,
    witness_from_verifier,
)
from maat.proposal.proposer import build_patch, witness_for_claim  # noqa: E402
from maat.scenarios import run_scenario  # noqa: E402
from maat.settings import Settings  # noqa: E402
from maat.store import versions  # noqa: E402
from maat.store.explain import explain_patch, explain_rollback, passport  # noqa: E402

SEEDS = [1, 2, 3]
UNIT = {"id": "t", "family": "unit_calc", "input": "COMPUTE: 12*4"}
EXACT_48 = {"type": "numeric_close", "expected": 48}


@pytest.fixture
def env():
    return make_env()


def with_rule(cfg, text="Round. ROUND_UP_TO:5", applies=("clause_query",)):
    rule = {"id": "r_bad", "text": text, "applies_to": list(applies), "protected": False}
    return apply_patch(cfg, [Op(op="add", path="rules/r_bad", value=rule)])


# ------------------------------------------------------------------ blame
def test_blame_finds_harmful_rule_by_ablation(env, v1) -> None:
    cfg = with_rule(v1)
    ranked = localize(env.agent, cfg, UNIT, EXACT_48, SEEDS, env.charter)
    assert ranked[0].element == "rule:r_bad" and ranked[0].kind == "ablation"
    assert ranked[0].blame == pytest.approx(1.0) and ranked[0].target == "rule"
    assert all(i.blame > 0 for i in ranked)


def test_blame_skips_protected_elements(env, v1) -> None:
    cfg = copy.deepcopy(v1)
    # make protected r_002 harmful for a checklist task: it must never be proposed for removal
    task = {
        "id": "c",
        "family": "safety_checklist",
        "input": "Prepare the pre-work safety checklist for x.",
    }
    checker = {"type": "checklist_covers", "items": ["fire_watch"]}
    ranked = localize(env.agent, cfg, task, checker, SEEDS, env.charter)
    assert not any(i.element in ("rule:r_002",) for i in ranked)
    assert any(i.element == "repair:workflow:ask_fire_watch" for i in ranked)


def test_blame_repair_candidates_and_priority(env, v1) -> None:
    task = {
        "id": "t",
        "family": "clause_query",
        "input": "What is the min_length_mm of anchorage:bond?",
    }
    checker = {"type": "regex", "pattern": r"\bis 410\b"}
    ranked = localize(env.agent, v1, task, checker, SEEDS, env.charter)
    assert [i.element for i in ranked] == ["repair:tool_policy:clause_lookup"]
    assert ranked[0].blame == 1.0 and ranked[0].edit == {"ground": ["clause_lookup"]}


def test_blame_nothing_to_fix_and_nothing_found(env, v1) -> None:
    bp = BlameProposer(env.agent, SEEDS, env.charter)
    ok_task = {"family": "clause_query", "input": "What is the min_cover_mm of cover:mild?"}
    w = WitnessTest(
        family="clause_query",
        input=ok_task["input"],
        checker={"type": "regex", "pattern": r"\bis 31\b"},
    )
    patch, reason = bp.propose(v1, ok_task, w, ["e1"])
    assert patch is None and "already passes" in reason
    impossible = WitnessTest(
        family="clause_query",
        input=ok_task["input"],
        checker={"type": "regex", "pattern": r"\bis 12345\b"},
    )
    patch, reason = bp.propose(v1, ok_task, impossible, ["e1"])
    assert patch is None and "no config element" in reason


def test_ablation_patch_removes_rule_and_fixes_task(env, v1) -> None:
    cfg = with_rule(v1)
    bp = BlameProposer(env.agent, SEEDS, env.charter)
    w = WitnessTest(family="unit_calc", input="COMPUTE: 12*4", checker=EXACT_48)
    patch, _ = bp.propose(cfg, UNIT, w, ["e1"])
    assert patch.type == "instruction_rule" and patch.ops[0].op == "remove"
    assert set(patch.declared_scope.task_types) == {"clause_query", "unit_calc"}
    fixed = apply_patch(cfg, patch.ops, env.charter)
    assert env.agent.run(UNIT, fixed, 1)["answer"] == "Result: 48"


def test_ablate_each_element_kind(v1) -> None:
    assert "m_001" not in {m["id"] for m in ablate(v1, "memory:m_001")["memory"]}
    assert "r_003" not in {r["id"] for r in ablate(v1, "rule:r_003")["rules"]}
    assert "unit_calc" not in ablate(v1, "tool_policy:unit_calc")["tool_policy"]
    assert ablate(v1, "workflow:unit_calc:compute")["workflow"]["unit_calc"] == ["final"]
    assert v1["workflow"]["unit_calc"] == ["compute", "final"]  # input untouched


def test_witness_from_verifier(env) -> None:
    w = witness_from_verifier(
        {"family": "clause_query", "input": "What is the min_length_mm of anchorage:bond?"}, env.kb
    )
    assert w.checker["expected"] == 410.0
    assert (
        witness_from_verifier(
            {"family": "clause_query", "input": "What is the x of nothing:here?"}, env.kb
        )
        is None
    )
    u = witness_from_verifier({"family": "unit_calc", "input": "CONVERT: 2.5 m -> mm"}, env.kb)
    assert u.checker["expected"] == 2500.0
    assert witness_from_verifier({"family": "safety_checklist", "input": "x"}, env.kb) is None


# ----------------------------------------------------------------- probes
def _patch(env, scope_subjects=("cover:severe",)):
    claim = Claim(subject="cover:severe", attribute="min_cover_mm", value=47.0)
    mem = {
        "id": "m_p",
        "subject": "cover:severe",
        "attribute": "min_cover_mm",
        "value": 47.0,
        "text": "",
        "protected": False,
        "source_patch": None,
    }
    return build_patch(
        "memory_note",
        [Op(op="add", path="memory/m_p", value=mem)],
        claim,
        witness_for_claim(claim, None),
        DeclaredScope(
            task_types=["clause_query"], conditions={"subject_keys": list(scope_subjects)}
        ),
        ["e"],
        "t",
        "high",
    )


def test_probe_kinds_and_scope(env) -> None:
    env.gate.ctx.base_config = env.active()
    p = _patch(env)
    probes = build_probes(p, env.gate.ctx)
    kinds = {x.kind for x in probes}
    assert kinds == {"directional", "regression", "boundary", "invariance"}
    assert all(x.in_scope for x in probes if x.kind == "directional")
    assert not any(x.in_scope for x in probes if x.family == "unit_calc")
    assert len({x.id for x in probes}) == len(probes)  # deduplicated
    assert in_scope(p, "clause_query", "cover:severe") and not in_scope(p, "clause_query", "x:y")
    assert not in_scope(p, "unit_calc", None)


def test_noise_floor_raises_the_change_threshold(env) -> None:
    """With a noisy backend, instability p_i keeps random flips from being blamed on the patch."""
    from maat.env import build_env

    noisy = build_env(Settings(), db_path=":memory:", backend=MockBackend(noise=0.5))
    ctx = noisy.gate.ctx
    ctx.base_config = noisy.active()
    p = _patch(noisy)
    ctx.patched_config = apply_patch(ctx.base_config, p.ops)
    res = impact.run(p, ctx)
    assert res.metrics["noise_floor_mean"] > 0.0
    # same patch on the deterministic backend has a zero floor
    quiet = make_env()
    quiet.gate.ctx.base_config = quiet.active()
    quiet.gate.ctx.patched_config = apply_patch(quiet.gate.ctx.base_config, p.ops)
    assert impact.run(p, quiet.gate.ctx).metrics["noise_floor_mean"] == 0.0


def test_impact_pass_fail_and_tolerance(env) -> None:
    ctx = env.gate.ctx
    ctx.base_config = env.active()
    good = _patch(env)
    ctx.patched_config = apply_patch(ctx.base_config, good.ops)
    r = impact.run(good, ctx)
    assert r.status == "pass" and r.metrics["scope_precision"] == 1.0
    assert r.metrics["scope_recall"] == 1.0 and r.metrics["changed_out_of_scope"] == []
    # declare too narrow a scope: the same behaviour change is now undeclared impact
    narrow = _patch(env, scope_subjects=("cover:mild",))
    r = impact.run(narrow, ctx)
    assert r.status == "fail" and "undeclared impact" in r.reasons[0]
    # a tolerance lets small leaks through (default is zero)
    ctx.settings = Settings(scope_tolerance=50)
    assert impact.run(narrow, ctx).status != "fail"


def test_low_coverage_is_inconclusive_never_a_pass(env) -> None:
    ctx = env.gate.ctx
    ctx.base_config = env.active()
    p = _patch(env)
    ctx.patched_config = apply_patch(ctx.base_config, p.ops)
    ctx.settings = Settings(n_min_probes=1000)
    r = impact.run(p, ctx)
    assert r.status == "inconclusive" and r.metrics["coverage"] < 0.75


def test_gate_outcome_inconclusive_leaves_patch_unadopted_and_trust_unchanged() -> None:
    env = make_env(Settings(n_min_probes=1000))
    t = env.ask("u1", "clause_query", "What is the min_cover_mm of cover:severe?")
    env.feedback("u1", t["task_id"], edit="The min_cover_mm of cover:severe is 47.")
    pid = env.propose()["patches"][0]
    [out] = env.decide()
    assert out.outcome == "inconclusive" and out.deciding_lock == "impact"
    assert env.repo.get_patch(pid)["status"] == "inconclusive"
    assert versions.active_version(env.repo) == 1
    assert env.trust.expected("u1", "structural_codes") == 0.5


# ------------------------------------------------------------ conflicts
def test_conflict_with_untrusted_sides_goes_to_humans_not_adoption() -> None:
    env = make_env()
    for user, v in (("a", 600), ("b", 750)):
        env.feedback(
            user,
            None,
            "comment",
            claim={"subject": "pile:head", "attribute": "min_dia_mm", "value": v},
        )
    env.propose()
    outs = env.decide()
    assert {o.outcome for o in outs} == {"quarantine"}  # nobody trusted, nothing adopted
    assert len(env.repo.list_human_queue()) == 2
    assert versions.active_version(env.repo) == 1


def test_kb_backed_conflict_rejects_the_wrong_side_normally() -> None:
    env = make_env()
    for user, v in (("good", 47), ("bad", 40)):
        env.feedback(
            user,
            None,
            "comment",
            claim={"subject": "cover:severe", "attribute": "min_cover_mm", "value": v},
        )
    env.propose()
    by = {o.patch_id: o for o in env.decide()}
    assert sorted(o.outcome for o in by.values()) == ["adopt", "reject"]
    assert next(o for o in by.values() if o.outcome == "reject").deciding_lock == "warrant"


# ----------------------------------------------------------- explanations
def test_explanation_and_passport_for_each_outcome() -> None:
    env = make_env()
    adopted = run_scenario(env, 1)
    exp = explain_patch(env.repo, adopted["patch_id"])
    assert exp["headline"].startswith("Adopted: cover:severe / min_cover_mm = 47")
    assert exp["decided_by"] == "decision" and len(exp["locks"]) == 6
    assert any("Statistics:" in line for line in exp["lines"])
    pp = passport(env.repo, adopted["patch_id"])
    assert pp["result"] == "Adopted" and pp["generated_by"] == "Safety Gate"
    assert pp["evidence"].startswith("source_lookup: kb:cover:severe")
    assert pp["method"] == "five-lock replay on a sandbox config"

    rej = run_scenario(env, 2, reset=True)
    pp = passport(env.repo, rej["patch_id"])
    assert pp["result"] == "Rejected at Warrant" and pp["method"] == "stopped before any replay"
    assert "Rejected at Warrant" in explain_patch(env.repo, rej["patch_id"])["headline"]

    q = run_scenario(env, 3, reset=True)
    assert explain_patch(env.repo, q["patch_id"])["decided_by"] == "invariants"
    with pytest.raises(KeyError):
        explain_patch(env.repo, "p_none")
    assert explain_rollback(env.repo, 99) is None
