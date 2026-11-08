import json
from pathlib import Path

import pytest

from maat.agent.runtime import Agent
from maat.config_model import normalize
from maat.kb import load_kb
from maat.llm.mock_backend import MockBackend

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA


@pytest.fixture(scope="session")
def kb():
    return load_kb(DATA, "synthetic")


@pytest.fixture
def v1() -> dict:
    return normalize(json.loads((DATA / "config_v1.json").read_text()))


@pytest.fixture
def agent(kb) -> Agent:
    return Agent(MockBackend(), kb)
