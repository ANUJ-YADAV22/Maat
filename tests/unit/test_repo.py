import pytest

from maat.db import connect
from maat.repo import Repo


@pytest.fixture
def repo() -> Repo:
    return Repo(connect())


def _patch(pid: str = "p1") -> dict:
    return {
        "patch_id": pid,
        "type": "memory_note",
        "ops": [{"op": "add", "path": "memory/m_9", "value": {"id": "m_9"}}],
        "claim": {"subject": "cover:severe", "attribute": "min_cover_mm", "value": 50},
        "risk_tier": "medium",
        "proposer": "rule",
    }


def test_audit_roundtrip(repo: Repo) -> None:
    repo.audit("patch.adopted", "gate", {"patch_id": "p1"})
    entries = repo.list_audit("patch.adopted")
    assert entries[0]["details_json"] == {"patch_id": "p1"}


def test_task_and_feedback(repo: Repo) -> None:
    repo.log_task("t1", "u1", "clause_query", "q", "a", {"memory": ["m_001"]}, 1, 12.5)
    assert repo.get_task("t1")["trace_json"] == {"memory": ["m_001"]}
    repo.log_feedback("e1", "u1", "edit", task_id="t1", claim={"value": 50}, edit_diff="-45 +50")
    ev = repo.list_feedback("u1")
    assert ev[0]["claim_json"] == {"value": 50} and ev[0]["origin"] == "user"
    assert repo.count_recent_feedback("u1") == 1


def test_patch_lifecycle(repo: Repo) -> None:
    repo.log_feedback("e1", "u1", "comment")
    repo.insert_patch(_patch(), ["e1"])
    assert repo.get_patch("p1")["status"] == "proposed"
    assert repo.patch_sources("p1") == ["e1"]
    repo.set_patch_status("p1", "adopted")
    assert [p["patch_id"] for p in repo.list_patches("adopted")] == ["p1"]
    with pytest.raises(ValueError):
        repo.set_patch_status("p1", "nonsense")
    with pytest.raises(KeyError):
        repo.set_patch_status("missing", "adopted")
    repo.log_gate_run("p1", "screen", "pass", {"risk": "medium"}, ["ok"])
    assert repo.list_gate_runs("p1")[0]["reasons_json"] == ["ok"]


def test_config_versions(repo: Repo) -> None:
    repo.insert_config_version(1, None, {"version": 1}, "h1")
    repo.insert_config_version(2, 1, {"version": 2}, "h2")
    assert repo.latest_version() == 2
    assert repo.get_config_version(2)["parent"] == 1


def test_trust_upsert_and_ledger(repo: Repo) -> None:
    repo.put_trust_row("u1", "site_safety", 2.0, 1.0)
    repo.put_trust_row("u1", "site_safety", 3.0, 1.0)
    assert repo.get_trust_row("u1", "site_safety")["alpha"] == 3.0
    assert repo.ledger_bump("h", "contradicts KB", "warrant") == 1
    assert repo.ledger_bump("h", "contradicts KB", "warrant") == 2


def test_human_queue_and_cache(repo: Repo) -> None:
    repo.insert_patch(_patch())
    item = repo.enqueue_human("p1", "unverifiable")
    assert repo.list_human_queue()[0]["item_id"] == item
    repo.resolve_human(item, "approved", "reviewer1")
    assert repo.list_human_queue() == []
    repo.cache_put("k", {"ok": True})
    assert repo.cache_get("k") == {"ok": True} and repo.cache_get("nope") is None


def test_processing_order_is_insertion_order_not_random_id_order(repo: Repo) -> None:
    """Same-second events must be processed in the order they arrived (determinism)."""
    for eid in ("e_zzz", "e_aaa", "e_mmm"):
        repo.log_feedback(eid, "u1", "comment", text=eid)
    assert [e["event_id"] for e in repo.unprocessed_feedback(("comment",))] == [
        "e_zzz",
        "e_aaa",
        "e_mmm",
    ]
    assert [e["event_id"] for e in repo.list_feedback()] == ["e_zzz", "e_aaa", "e_mmm"]
    for pid in ("p_z", "p_a"):
        repo.insert_patch({**_patch(pid)}, [])
    assert [p["patch_id"] for p in repo.list_patches()] == ["p_z", "p_a"]
    for eid in ("e_mmm", "e_zzz", "e_aaa"):
        repo.conn.execute("INSERT INTO patch_sources VALUES ('p_z', ?)", (eid,))
    assert repo.patch_sources("p_z") == ["e_mmm", "e_zzz", "e_aaa"]
