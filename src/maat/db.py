"""SQLite schema and connection helpers (stdlib sqlite3)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

PATCH_STATUSES = (
    "proposed",
    "gating",
    "adopted",
    "rejected",
    "quarantined",
    "inconclusive",
    "rolled_back",
    "expired",
)

_STATUS_LIST = ", ".join(f"'{s}'" for s in PATCH_STATUSES)

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS users(
  user_id TEXT PRIMARY KEY, team TEXT, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS tasks_log(
  task_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id),
  family TEXT NOT NULL, input TEXT NOT NULL, answer TEXT, trace_json TEXT,
  config_version INTEGER, latency_ms REAL, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_tasks_user ON tasks_log(user_id);

CREATE TABLE IF NOT EXISTS feedback_events(
  event_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id),
  task_id TEXT REFERENCES tasks_log(task_id), config_version INTEGER,
  signal_type TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'user',
  text TEXT, edit_diff TEXT, claim_json TEXT, ts TEXT NOT NULL,
  edit_text TEXT, processed INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_fb_user ON feedback_events(user_id);
CREATE INDEX IF NOT EXISTS ix_fb_task ON feedback_events(task_id);

CREATE TABLE IF NOT EXISTS clusters(
  cluster_id TEXT PRIMARY KEY, key TEXT NOT NULL, event_ids_json TEXT NOT NULL, ts TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS patches(
  patch_id TEXT PRIMARY KEY, type TEXT NOT NULL, ops_json TEXT NOT NULL,
  claim_json TEXT, warrant_json TEXT, witness_json TEXT, scope_json TEXT,
  risk_tier TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed'
    CHECK(status IN ({_STATUS_LIST})),
  proposer TEXT, expiry_json TEXT, created_ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_patches_status ON patches(status);

CREATE TABLE IF NOT EXISTS patch_sources(
  patch_id TEXT NOT NULL REFERENCES patches(patch_id),
  event_id TEXT NOT NULL REFERENCES feedback_events(event_id),
  PRIMARY KEY(patch_id, event_id));
CREATE INDEX IF NOT EXISTS ix_ps_event ON patch_sources(event_id);

CREATE TABLE IF NOT EXISTS tests(
  test_id TEXT PRIMARY KEY, suite TEXT NOT NULL, family TEXT NOT NULL,
  input TEXT NOT NULL, checker_json TEXT NOT NULL, tags_json TEXT);
CREATE INDEX IF NOT EXISTS ix_tests_suite ON tests(suite);

CREATE TABLE IF NOT EXISTS gate_runs(
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, patch_id TEXT NOT NULL REFERENCES patches(patch_id),
  lock TEXT NOT NULL, result TEXT NOT NULL, metrics_json TEXT, reasons_json TEXT, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_gate_patch ON gate_runs(patch_id);

CREATE TABLE IF NOT EXISTS config_versions(
  version INTEGER PRIMARY KEY, parent INTEGER REFERENCES config_versions(version),
  config_json TEXT NOT NULL, config_hash TEXT NOT NULL,
  created_from_patch TEXT REFERENCES patches(patch_id),
  stage TEXT NOT NULL DEFAULT 'full', ts TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS trust(
  user_id TEXT NOT NULL, domain TEXT NOT NULL, alpha REAL NOT NULL DEFAULT 1.0,
  beta REAL NOT NULL DEFAULT 1.0, updated_at TEXT NOT NULL, PRIMARY KEY(user_id, domain));

CREATE TABLE IF NOT EXISTS rejection_ledger(
  claim_hash TEXT PRIMARY KEY, reason TEXT, lock TEXT, count INTEGER NOT NULL DEFAULT 1,
  last_seen TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS human_queue(
  item_id INTEGER PRIMARY KEY AUTOINCREMENT, patch_id TEXT NOT NULL REFERENCES patches(patch_id),
  reason TEXT, status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_hq_status ON human_queue(status);

CREATE TABLE IF NOT EXISTS monitor_windows(
  window_id INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL,
  accepts INTEGER NOT NULL DEFAULT 0, redos INTEGER NOT NULL DEFAULT 0,
  edits INTEGER NOT NULL DEFAULT 0, n INTEGER NOT NULL DEFAULT 0, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_mw_version ON monitor_windows(version);

CREATE TABLE IF NOT EXISTS replay_cache(
  key TEXT PRIMARY KEY, result_json TEXT NOT NULL, ts TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS audit_log(
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, actor TEXT NOT NULL,
  details_json TEXT, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_audit_event ON audit_log(event);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Open a connection with foreign keys on and dict-like rows; create the schema."""
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_SQL)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block atomically; roll back on any exception."""
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
