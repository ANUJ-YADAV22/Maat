"""Gate over the API: adopt, reject, quarantine -> human review, trust and determinism."""

import json

import pytest
from fastapi.testclient import TestClient

from maat.api.app import create_app
from maat.llm.mock_backend import MockBackend

Q = "What is the {attr} of {subj}?"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(db_path=":memory:", backend=MockBackend()))


def submit(client, user, attr, subj, value):
    q = Q.format(attr=attr, subj=subj)
    t = client.post("/task", json={"user_id": user, "family": "clause_query", "input": q}).json()
    r = client.post(
        "/feedback",
        json={
            "user_id": user,
            "task_id": t["task_id"],
            "signal_type": "edit",
            "edit": f"The {attr} of {subj} is {value}.",
        },
    )
    assert r.status_code == 200


def test_gate_run_decisions_and_trust(client) -> None:
    submit(client, "good", "min_cover_mm", "cover:severe", 47)
    submit(client, "bad", "min_cover_mm", "cover:extreme", 10)  # KB says 62
    assert len(client.post("/proposals/run").json()["patches"]) == 2
    out = {d["outcome"] for d in client.post("/gate/run").json()}
    assert out == {"adopt", "reject"}
    assert client.get("/versions").json()[-1]["version"] == 2
    assert client.get("/trust/good").json()["trust"]["structural_codes"] > 0.5
    assert client.get("/trust/bad").json()["trust"]["structural_codes"] < 0.5
    assert client.post("/gate/run").json() == []  # nothing left to decide
    rejected = client.get("/patches", params={"status": "rejected"}).json()
    detail = client.get(f"/patches/{rejected[0]['patch_id']}").json()
    assert [g["lock"] for g in detail["gate_runs"]] == ["screen", "warrant", "decision"]
    assert detail["gate_runs"][1]["result"] == "fail"


def test_quarantine_then_human_approve_and_reject(client) -> None:
    # claims the KB cannot verify (no KB entry) and no corroboration -> quarantine
    submit(client, "u1", "min_strength_mpa", "rebar:grade", 500)
    submit(client, "u2", "min_dia_mm", "pile:head", 600)
    client.post("/proposals/run")
    decided = client.post("/gate/run").json()
    assert {d["outcome"] for d in decided} == {"quarantine"}
    queue = client.get("/queue").json()
    assert len(queue) == 2 and all(q["status"] == "pending" for q in queue)
    a, b = (d["patch_id"] for d in decided)

    ok = client.post(f"/patches/{a}/approve", json={"reviewer": "lead", "reason": "checked"}).json()
    assert ok["outcome"] == "adopt" and ok["config_version"] == 2
    no = client.post(f"/patches/{b}/reject", json={"reviewer": "lead", "reason": "wrong"}).json()
    assert no["outcome"] == "reject"
    assert client.get("/queue").json() == []
    assert len(client.get("/queue", params={"status": "approved"}).json()) == 1
    assert client.post(f"/patches/{a}/approve", json={}).status_code == 409  # not quarantined now
    audit = {e["event"] for e in client.get("/audit").json()}
    assert {"patch.quarantined", "patch.adopted", "patch.rejected", "gate.started"} <= audit


def test_decisions_are_deterministic() -> None:
    def run():
        c = TestClient(create_app(db_path=":memory:", backend=MockBackend()))
        submit(c, "u1", "min_cover_mm", "cover:severe", 47)
        submit(c, "u2", "min_cover_mm", "cover:extreme", 10)
        c.post("/proposals/run")
        res = c.post("/gate/run").json()
        return json.dumps(
            [{k: v for k, v in d.items() if k != "patch_id"} for d in res], sort_keys=True
        )

    assert run() == run()
