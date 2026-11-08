import json
from collections import Counter

from maat.checkers import run_checker
from maat.suites import load_suite


def pass_rate(agent, cfg, tasks, seed=1) -> float:
    ok = 0
    for t in tasks:
        r = agent.run(t.model_dump(), cfg, seed)
        ok += run_checker(t.checker, r["answer"], r["trace"])
    return ok / len(tasks)


def test_suite_sizes(data_dir) -> None:
    golden, held, inv = (load_suite(data_dir, n) for n in ("golden", "heldout", "invariants"))
    assert len(golden) == 40 and set(Counter(t.family for t in golden).values()) == {8}
    assert len(held) == 25 and set(Counter(t.family for t in held).values()) == {5}
    assert len(inv) == 8
    ids = [t.id for t in golden + held + inv]
    assert len(ids) == len(set(ids))


def test_kb_has_30_entries_in_three_domains(kb) -> None:
    assert len(kb.entries) == 30
    assert {e.domain for e in kb.entries} == {"structural_codes", "site_safety", "tender_docs"}
    assert all("DEMO-CODE" in e.source_doc for e in kb.entries)


def test_v1_fails_about_forty_percent_of_heldout(agent, v1, data_dir) -> None:
    rate = pass_rate(agent, v1, load_suite(data_dir, "heldout"))
    assert 0.56 <= rate <= 0.64, rate


def test_v1_passes_golden_and_invariants(agent, v1, data_dir) -> None:
    assert pass_rate(agent, v1, load_suite(data_dir, "golden")) == 1.0
    assert pass_rate(agent, v1, load_suite(data_dir, "invariants")) == 1.0


def test_determinism_same_seed_same_output(agent, v1, data_dir) -> None:
    tasks = load_suite(data_dir, "golden") + load_suite(data_dir, "heldout")
    first = [agent.run(t.model_dump(), v1, 7) for t in tasks]
    second = [agent.run(t.model_dump(), v1, 7) for t in tasks]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_trace_lists_config_elements(agent, v1) -> None:
    from maat.agent.runtime import trace_elements

    r = agent.run(
        {"family": "clause_query", "input": "What is the min_cover_mm of cover:mild?"}, v1, 1
    )
    elems = trace_elements(r["trace"])
    assert "memory:m_001" in elems and "tool_policy:clause_query" in elems
    assert "workflow:clause_query:lookup_clause" in elems and "rule:r_001" in elems
    assert r["trace"]["tool_calls"][0]["tool"] == "clause_lookup"


def test_data_files_are_reproducible(tmp_path, data_dir, monkeypatch) -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "build_data", Path(data_dir).parent / "scripts" / "build_data.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.build_config() == json.loads((data_dir / "config_v1.json").read_text())
    assert mod.build_heldout() == json.loads((data_dir / "suites" / "heldout.json").read_text())
