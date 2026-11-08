"""Every MockBackend hook (documented in llm/mock_backend.py) is exercised here."""

from maat.config_model import apply_patch


def run(agent, cfg, family, text, seed=1):
    return agent.run({"family": family, "input": text}, cfg, seed)


def test_stale_default_without_memory(agent, v1) -> None:
    r = run(agent, v1, "clause_query", "What is the min_cover_mm of cover:severe?")
    assert r["answer"] == "The min_cover_mm of cover:severe is 25."


def test_memory_overrides_stale(agent, v1) -> None:
    r = run(agent, v1, "clause_query", "What is the min_cover_mm of cover:mild?")
    assert r["answer"].endswith("is 31.") and "m_001" in r["trace"]["memory_ids"]
    mem = {
        "id": "m_900",
        "subject": "cover:severe",
        "attribute": "min_cover_mm",
        "value": 47,
        "text": "",
        "source_patch": None,
        "protected": False,
    }
    cfg = apply_patch(v1, [{"op": "add", "path": "memory/m_900", "value": mem}])
    r = run(agent, cfg, "clause_query", "What is the min_cover_mm of cover:severe?")
    assert r["answer"].endswith("is 47.")


def test_ground_policy_forces_kb_answer(agent, v1) -> None:
    cfg = apply_patch(
        v1,
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
    r = run(agent, cfg, "clause_query", "What is the min_length_mm of anchorage:bond?")
    assert r["answer"].endswith("is 410.")


def test_round_up_rule_leaks_across_families(agent, v1) -> None:
    rule = {
        "id": "r_900",
        "text": "Round values. ROUND_UP_TO:5",
        "applies_to": ["clause_query"],
        "protected": False,
    }
    cfg = apply_patch(v1, [{"op": "add", "path": "rules/r_900", "value": rule}])
    assert run(agent, v1, "unit_calc", "COMPUTE: 12*4")["answer"] == "Result: 48"
    assert run(agent, cfg, "unit_calc", "COMPUTE: 12*4")["answer"] == "Result: 50"
    assert run(agent, cfg, "clause_query", "What is the min_cover_mm of cover:mild?")[
        "answer"
    ].endswith("is 35.")


def test_skip_check_rule_removes_item(agent, v1) -> None:
    rule = {
        "id": "r_901",
        "text": "SKIP_CHECK:harness_inspected",
        "applies_to": [],
        "protected": False,
    }
    cfg = apply_patch(v1, [{"op": "add", "path": "rules/r_901", "value": rule}])
    base = run(agent, v1, "safety_checklist", "Prepare the pre-work safety checklist for x.")
    skipped = run(agent, cfg, "safety_checklist", "Prepare the pre-work safety checklist for x.")
    assert "- harness_inspected" in base["answer"]
    assert "harness_inspected" not in skipped["answer"] and "- ppe_check" in skipped["answer"]


def test_verify_units_step_fixes_conversion(agent, v1) -> None:
    text = "CONVERT: 2.5 m -> mm"
    assert run(agent, v1, "unit_calc", text)["answer"] == "Result: 2.5 mm"
    cfg = apply_patch(
        v1,
        [
            {
                "op": "add",
                "path": "workflow/unit_calc",
                "value": {"step": "verify_units", "index": 1},
            }
        ],
    )
    assert run(agent, cfg, "unit_calc", text)["answer"] == "Result: 2500 mm"


def test_missing_checklist_step_removes_item(agent, v1) -> None:
    cfg = apply_patch(v1, [{"op": "remove", "path": "workflow/safety_checklist/ask_ppe"}])
    ans = run(agent, cfg, "safety_checklist", "Prepare the pre-work safety checklist for x.")
    assert "ppe_check" not in ans["answer"]
    cfg = apply_patch(
        v1, [{"op": "add", "path": "workflow/safety_checklist", "value": "ask_fire_watch"}]
    )
    ans = run(agent, cfg, "safety_checklist", "Prepare the pre-work safety checklist for x.")
    assert "- fire_watch" in ans["answer"]


def test_missing_tender_step_drops_field(agent, v1) -> None:
    cfg = apply_patch(v1, [{"op": "remove", "path": "workflow/tender_extract/extract_emd"}])
    text = "Extract: TENDER T-101: deadline=2026-12-01; emd_inr=50000; eligibility=Class A"
    assert '"emd"' in run(agent, v1, "tender_extract", text)["answer"]
    assert '"emd"' not in run(agent, cfg, "tender_extract", text)["answer"]


def test_calculator_requires_compute_step(agent, v1) -> None:
    cfg = apply_patch(v1, [{"op": "remove", "path": "workflow/unit_calc/compute"}])
    # policy still requires the calculator, so the result exists; drop the policy too
    cfg = apply_patch(cfg, [{"op": "remove", "path": "tool_policy/unit_calc"}])
    assert run(agent, cfg, "unit_calc", "COMPUTE: 6*7")["answer"] == "Result: unknown"


def test_noise_reverts_to_stale_deterministically(kb, v1) -> None:
    from maat.agent.runtime import Agent
    from maat.llm.mock_backend import MockBackend

    noisy = Agent(MockBackend(noise=1.0), kb)
    q = "What is the min_cover_mm of cover:mild?"
    a = noisy.run({"family": "clause_query", "input": q}, v1, 3)["answer"]
    assert a.endswith("is 25.")
    assert a == noisy.run({"family": "clause_query", "input": q}, v1, 3)["answer"]
