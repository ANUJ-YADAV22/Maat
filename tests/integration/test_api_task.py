import pytest
from fastapi.testclient import TestClient

from maat.api.app import create_app
from maat.llm.mock_backend import MockBackend


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(db_path=":memory:", backend=MockBackend()))


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body == {"status": "ok", "config_version": 1, "kb_mode": "synthetic"}


def test_task_roundtrip_and_logging(client: TestClient) -> None:
    r = client.post(
        "/task",
        json={
            "user_id": "u1",
            "family": "clause_query",
            "input": "What is the min_cover_mm of cover:mild?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].endswith("is 31.") and body["config_version"] == 1
    assert body["trace"]["tool_calls"][0]["tool"] == "clause_lookup"
    logged = client.app.state.repo.get_task(body["task_id"])
    assert logged["answer"] == body["answer"] and logged["user_id"] == "u1"


def test_consistent_error_body(client: TestClient) -> None:
    r = client.post("/task", json={"user_id": "u1", "family": "nonsense", "input": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_openapi_docs_available(client: TestClient) -> None:
    assert "/task" in client.get("/openapi.json").json()["paths"]
