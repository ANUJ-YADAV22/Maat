import sqlite3

import pytest

from maat.db import PATCH_STATUSES, connect, transaction

EXPECTED = {
    "users",
    "tasks_log",
    "feedback_events",
    "clusters",
    "patches",
    "patch_sources",
    "tests",
    "gate_runs",
    "config_versions",
    "trust",
    "rejection_ledger",
    "human_queue",
    "monitor_windows",
    "replay_cache",
    "audit_log",
}


def test_all_tables_exist() -> None:
    conn = connect()
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED <= names


def test_patch_status_constraint() -> None:
    conn = connect()
    ins = (
        "INSERT INTO patches(patch_id,type,ops_json,risk_tier,status,created_ts) "
        "VALUES ('p','memory_note','[]','low',?, 't')"
    )
    for i, st in enumerate(PATCH_STATUSES):
        conn.execute(ins.replace("'p'", f"'p{i}'"), (st,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ins, ("bogus",))


def test_foreign_keys_enforced() -> None:
    conn = connect()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tasks_log(task_id,user_id,family,input,ts) "
            "VALUES ('t','nobody','f','i','x')"
        )


def test_transaction_rolls_back() -> None:
    conn = connect()
    with pytest.raises(RuntimeError), transaction(conn):
        conn.execute("INSERT INTO users VALUES ('u1', NULL, 't')")
        raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0
