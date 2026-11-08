"""Phase 2 acceptance: a manually approved patch creates v2 and improves a task; rollback
restores v1's behaviour."""

import pytest
from fastapi.testclient import TestClient

from maat.api.app import create_app
from maat.llm.mock_backend import MockBackend

Q = "What is the min_cover_mm of cover:severe?"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(db_path=":memory:", backend=MockBackend()))


def ask(client, user="u1"):
    return client.post("/task", json={"user_id": user, "family": "clause_query", "input": Q}).json()


def test_feedback_to_v2_and_rollback(client: TestClient) -> None:
    before = ask(client)
    assert before["answer"].endswith("is 25.") and before["config_version"] == 1

    fb = client.post(
        "/feedback",
        json={
            "user_id": "u1",
            "task_id": before["task_id"],
            "signal_type": "edit",
            "edit": "The min_cover_mm of cover:severe is 47.",
        },
    )
    assert fb.status_code == 200
    run = client.post("/proposals/run").json()
    assert len(run["patches"]) == 1 and run["rejected"] == []
    pid = run["patches"][0]

    detail = client.get(f"/patches/{pid}").json()
    assert detail["status"] == "proposed" and detail["contract"]["type"] == "memory_note"
    assert [
        p["patch_id"] for p in client.get("/patches", params={"status": "proposed"}).json()
    ] == [pid]

    decided = client.post("/gate/run").json()
    assert [(d["patch_id"], d["outcome"]) for d in decided] == [(pid, "adopt")]
    assert decided[0]["config_version"] == 2
    after = ask(client)
    assert after["answer"].endswith("is 47.") and after["config_version"] == 2

    diff = client.get("/versions/1/diff/2").json()
    assert [d["change"] for d in diff] == ["added"] and diff[0]["path"].startswith("memory/")

    rb = client.post("/rollback", json={"to_version": 1, "reason": "demo rollback"}).json()
    assert rb == {"config_version": 3, "restored_from": 1}
    restored = ask(client)
    assert restored["answer"].endswith("is 25.") and restored["config_version"] == 3
    versions = client.get("/versions").json()
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert versions[0]["config_hash"] == versions[2]["config_hash"]
    events = {a["event"] for a in client.get("/audit").json()}
    assert {"feedback.logged", "patch.proposed", "patch.adopted", "config.rollback"} <= events


def test_error_paths(client: TestClient) -> None:
    assert (
        client.post(
            "/feedback", json={"user_id": "u", "signal_type": "comment", "origin": "agent"}
        ).status_code
        == 400
    )
    assert client.get("/patches/p_nope").status_code == 404
    assert client.post("/patches/p_nope/approve", json={}).status_code == 404
    assert client.post("/patches/p_nope/reject", json={}).status_code == 404
    assert client.post("/rollback", json={"to_version": 9, "reason": "x"}).status_code == 404
    assert client.post("/rollback", json={"to_version": 1, "reason": "x"}).status_code == 409
    assert client.get("/versions/1/diff/9").status_code == 404
    rej = client.post(
        "/feedback",
        json={
            "user_id": "u",
            "signal_type": "comment",
            "claim": {"subject": "cover:severe", "attribute": "min_cover_mm", "value": 40},
        },
    )
    pid = client.post("/proposals/run").json()["patches"][0]
    assert rej.status_code == 200
    # approve/reject are for quarantined patches only; a merely proposed patch is refused
    assert client.post(f"/patches/{pid}/reject", json={"reason": "no"}).status_code == 409
    assert client.post(f"/patches/{pid}/approve", json={}).status_code == 409
