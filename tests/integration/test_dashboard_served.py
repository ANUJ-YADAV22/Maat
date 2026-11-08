"""The built React dashboard is served by the API under /app/ with every asset resolvable."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maat.api.app import create_app
from maat.llm.mock_backend import MockBackend
from maat.settings import Settings

WEB = Path(__file__).resolve().parents[2] / "web"
DIST = WEB / "dist"
pytestmark = pytest.mark.skipif(not DIST.exists(), reason="run `make web` to build the dashboard")


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(), db_path=":memory:", backend=MockBackend()))


def test_index_and_assets_are_served(client) -> None:
    page = client.get("/app/")
    assert page.status_code == 200 and '<div id="root">' in page.text
    refs = re.findall(r'(?:src|href)="(/app/[^"]+)"', page.text)
    assert any(r.endswith(".js") for r in refs) and any(r.endswith(".css") for r in refs)
    for ref in refs:
        assert client.get(ref).status_code == 200, ref


def test_root_redirects_and_api_still_reachable(client) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200


def test_every_endpoint_the_dashboard_calls_exists(client) -> None:
    """Guards API/UI drift: each root path the frontend fetches is a real route."""
    src = "\n".join(p.read_text() for p in (WEB / "src").rglob("*.ts*"))
    pat = r"""['"`]/(overview|kb|tasks|trust|queue|audit|patches|versions|task|feedback|"""
    pat += r"""proposals|gate|rollback|demo|eval|explain|passport)\b"""
    called = set(re.findall(pat, src))
    roots = {p.split("/")[1] for p in client.get("/openapi.json").json()["paths"]}
    assert called and called <= roots, called - roots
