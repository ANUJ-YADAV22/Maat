"""Scenarios 4-8 on MockBackend: silent regression, conflict, rollback, tool-policy, workflow."""

import pytest

from maat.scenarios import SCENARIOS, run_scenario
from maat.store import versions


def locks(env, pid):
    return {g["lock"]: g for g in env.repo.list_gate_runs(pid)}


def test_scenario_4_silent_regression_vetoed_at_lock_5(env) -> None:
    r = run_scenario(env, 4)
    g = locks(env, r["patch_id"])
    assert r["outcome"] == "reject" and r["passport"]["result"] == "Rejected at Impact surface"
    # it passes everything up to Lock 5, including its own witness
    assert [g[k]["result"] for k in ("screen", "warrant", "witness", "invariants")] == ["pass"] * 4
    assert g["impact"]["result"] == "fail"
    assert g["decision"]["metrics_json"]["deciding_lock"] == "impact"
    assert "unit_calc" in r["leaked_families"] and "clause_query" in r["leaked_families"]
    assert versions.active_version(env.repo) == 1 and env.active()["version"] == 1
    m = g["impact"]["metrics_json"]
    assert m["scope_precision"] < 1.0 and m["noise_floor_mean"] == 0.0
    ans = env.ask("sim_x", "unit_calc", "COMPUTE: 12*4")["answer"]
    assert ans == "Result: 48"  # the leaking rule never reached the live config


def test_scenario_5_conflict_head_to_head(env) -> None:
    r = run_scenario(env, 5)
    assert r["outcome"] == "adopt" and "lost head-to-head" in r["loser_reason"]
    win, lose = r["patch_id"], r["loser"]
    assert env.repo.get_patch(win)["status"] == "adopted"
    assert env.repo.get_patch(lose)["status"] == "rejected"
    gw = locks(env, win)["decision"]["metrics_json"]
    gl = locks(env, lose)["conflict"]["metrics_json"]
    assert gl["winner"] == win and gl["margin"] < gw["margin"]  # bob's group had lower trust
    assert env.active()["memory"][-1]["value"] == 600.0
    # the loser was not a lie: no ledger entry and its senders' trust is untouched
    assert env.repo.conn.execute("SELECT COUNT(*) c FROM rejection_ledger").fetchone()["c"] == 0
    assert env.trust.expected("sim_bob", "structural_codes") == pytest.approx(0.8)
    assert env.trust.expected("sim_alice", "structural_codes") > 0.9


def test_scenario_6_rollback_with_generated_note(env) -> None:
    r = run_scenario(env, 6)
    assert r["adopted_outcome"] == "adopt" and r["config_version"] == 3
    assert r["restored_answer"].endswith("is 25.") and r["before"].endswith("is 25.")
    note = r["rollback_note"]
    assert note["restored_from"] == 1 and "more redo clicks" in note["reason"]
    assert any("cover:extreme" in line for line in note["lines"])
    assert env.repo.get_patch(r["patch_id"])["status"] == "rolled_back"
    assert env.repo.list_tests("accumulated") == []


def test_scenario_7_tool_policy_patch_from_redo(env) -> None:
    r = run_scenario(env, 7)
    assert r["outcome"] == "adopt" and r["before"].endswith("is 25.")
    assert r["after"].endswith("is 410.") and r["generalised"].endswith("is 62.")
    p = env.repo.get_patch(r["patch_id"])
    assert p["type"] == "tool_policy" and p["proposer"] == "blame" and p["risk_tier"] == "high"
    assert env.active()["tool_policy"]["clause_query"]["ground"] == ["clause_lookup"]
    g = locks(env, r["patch_id"])
    assert g["warrant"]["metrics_json"]["verifier_state"] == "match"
    assert g["impact"]["metrics_json"]["scope_recall"] == 1.0


def test_scenario_8_workflow_step_patch_from_edit(env) -> None:
    r = run_scenario(env, 8)
    assert r["outcome"] == "adopt" and r["before"] == "Result: 2.5 mm"
    assert r["after"] == "Result: 2500 mm"
    assert env.active()["workflow"]["unit_calc"] == ["compute", "verify_units", "final"]
    p = env.repo.get_patch(r["patch_id"])
    assert p["type"] == "workflow_step" and p["proposer"] == "blame"
    # other families untouched: protected checklist workflow and clause behaviour intact
    assert env.ask("sim_x", "clause_query", "What is the min_cover_mm of cover:mild?")[
        "answer"
    ].endswith("is 31.")


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_every_scenario_is_deterministic_and_resettable(env, sid) -> None:
    first = run_scenario(env, sid)
    second = run_scenario(env, sid)  # reset=True wipes state and replays
    strip = lambda r: {k: v for k, v in r.items() if k not in ("steps", "passport", "explanation")}  # noqa: E731
    assert strip(first) == strip(second)
    assert first["steps"] and first["simulated"] is True
    assert env.repo.list_audit()  # every state change is audited


def test_scenarios_use_only_simulated_users(env) -> None:
    for sid in SCENARIOS:
        run_scenario(env, sid)
        users = {r["user_id"] for r in env.repo.list_feedback()}
        assert users and all(u.startswith("sim_") for u in users)
