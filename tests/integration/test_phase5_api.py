"""Worker, overview, explain/passport, demo scenarios and the request lock."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from maat.api.app import create_app
from maat.llm.mock_backend import MockBackend
from maat.settings import Settings
from maat.worker import tick

Q = "What is the min_cover_mm of cover:severe?"


def mk(**kw) -> TestClient:
    return TestClient(create_app(Settings(**kw), db_path=":memory:", backend=MockBackend()))


def correct(c, user="u1"):
    t = c.post("/task", json={"user_id": user, "family": "clause_query", "input": Q}).json()
    c.post(
        "/feedback",
        json={
            "user_id": user,
            "task_id": t["task_id"],
            "signal_type": "edit",
            "edit": "The min_cover_mm of cover:severe is 47.",
        },
    )


def test_tick_runs_the_whole_offline_pipeline() -> None:
    c = mk()
    correct(c)
    res = tick(c.app.state.env)
    assert res["decided"] == ["adopt"] and len(res["proposed"]) == 1
    assert tick(c.app.state.env) == {"proposed": [], "decided": []}  # idempotent


def test_background_worker_adopts_without_any_gate_call() -> None:
    with mk(worker_enabled=True, worker_interval_s=0.05) as c:
        correct(c)
        for _ in range(100):
            if c.get("/health").json()["config_version"] == 2:
                break
            time.sleep(0.05)
        assert c.get("/health").json()["config_version"] == 2
        assert c.get("/overview").json()["worker"] is True


def test_overview_kb_trust_tasks_explain_passport() -> None:
    c = mk()
    correct(c)
    c.post("/proposals/run")
    c.post("/gate/run")
    o = c.get("/overview").json()
    assert o["config_version"] == 2 and o["patch_counts"] == {"adopted": 1}
    assert o["kb_entries"] == 30 and o["backend"] == "mock" and o["users"] == 1
    assert o["avg_gate_seconds"] > 0 and len(o["recent_audit"]) == 6
    kb = c.get("/kb").json()
    assert kb["mode"] == "synthetic" and kb["entries"][0]["source_doc"] == "DEMO-CODE-A"
    assert c.get("/tasks").json()[0]["user_id"] == "u1"
    assert c.get("/trust").json()[0]["trust"]["structural_codes"] > 0.5
    pid = c.get("/patches").json()[0]["patch_id"]
    patch = c.get("/patches").json()[0]
    assert patch["claim_text"] == "cover:severe / min_cover_mm = 47" and patch["users"] == ["u1"]
    assert c.get(f"/explain/{pid}").json()["headline"].startswith("Adopted")
    assert c.get(f"/passport/{pid}").json()["result"] == "Adopted"
    assert c.get("/explain/p_x").status_code == 404 and c.get("/passport/p_x").status_code == 404
    v = c.get("/versions").json()
    assert v[1]["claim_text"] == "cover:severe / min_cover_mm = 47" and v[0]["claim_text"] is None
    assert c.get("/eval/summary").json() == {"available": False}


def test_rollback_note_endpoint() -> None:
    c = mk()
    correct(c)
    c.post("/proposals/run")
    c.post("/gate/run")
    c.post("/rollback", json={"to_version": 1, "reason": "demo"})
    note = c.get("/rollback/3/note").json()
    assert note["restored_from"] == 1 and note["undone"] == ["cover:severe / min_cover_mm = 47"]
    assert c.get("/versions").json()[2]["rollback_note"]["reason"] == "demo"
    assert c.get("/rollback/2/note").status_code == 404


def test_demo_endpoints_guarded_by_demo_mode() -> None:
    off = mk()
    assert off.post("/demo/scenarios/1/run").status_code == 403
    assert off.post("/demo/reset").status_code == 403
    on = mk(demo_mode=True)
    assert [s["id"] for s in on.get("/demo/scenarios").json()] == list(range(1, 9))
    r = on.post("/demo/scenarios/3/run").json()
    assert r["outcome"] == "reject" and r["simulated"] is True and r["passport"]["result"]
    assert on.post("/demo/scenarios/99/run").status_code == 404
    assert on.post("/demo/reset").json() == {"config_version": 1}
    assert on.get("/overview").json()["tasks"] == 0


def test_concurrent_requests_do_not_corrupt_state() -> None:
    c = mk()
    errors: list[Exception] = []

    def hit() -> None:
        try:
            for _ in range(10):
                assert (
                    c.post(
                        "/task", json={"user_id": "u", "family": "clause_query", "input": Q}
                    ).status_code
                    == 200
                )
                assert c.get("/overview").status_code == 200
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=hit) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and c.get("/overview").json()["tasks"] == 40


@pytest.mark.parametrize("path", ["/health", "/overview", "/kb", "/versions", "/audit"])
def test_cors_allows_the_dev_frontend(path) -> None:
    c = mk()
    r = c.get(path, headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
