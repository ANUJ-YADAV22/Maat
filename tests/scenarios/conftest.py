"""Scenario harness: an in-memory deployment on MockBackend (shared maat.env.Env)."""

import pytest

from maat.env import Env, build_env
from maat.settings import Settings


def make_env(settings: Settings | None = None) -> Env:
    return build_env(settings or Settings(), db_path=":memory:")


@pytest.fixture
def env() -> Env:
    return make_env()
