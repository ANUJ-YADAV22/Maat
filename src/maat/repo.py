"""Thin repository layer over the SQLite schema.

All JSON-valued columns are (de)serialised here so callers work with plain Python objects.
Every state-changing helper that matters for explanation also writes an audit entry via
``Repo.audit`` (callers decide the event name).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from maat.db import PATCH_STATUSES, transaction


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def dumps(obj: Any) -> str:
    """Stable JSON encoding (sorted keys) used for every JSON column."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


def _row(row: sqlite3.Row | None, json_cols: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for col in json_cols:
        if col in out:
            out[col] = _loads(out[col])
    return out


class Repo:
    """Repository facade. One instance per connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------------ audit
    def audit(self, event: str, actor: str, details: dict[str, Any] | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO audit_log(event, actor, details_json, ts) VALUES (?,?,?,?)",
            (event, actor, dumps(details or {}), now_iso()),
        )
        return int(cur.lastrowid or 0)

    def list_audit(self, event: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM audit_log", []
        if event:
            sql += " WHERE event = ?"
            args.append(event)
        sql += " ORDER BY entry_id DESC LIMIT ?"
        args.append(limit)
        return [_row(r, ("details_json",)) for r in self.conn.execute(sql, args)]  # type: ignore[misc]

    # ------------------------------------------------------------------ users
    def ensure_user(self, user_id: str, team: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO users(user_id, team, created_at) VALUES (?,?,?)",
            (user_id, team, now_iso()),
        )

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return _row(self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone())

    # ------------------------------------------------------------- tasks/feedback
    def log_task(
        self,
        task_id: str,
        user_id: str,
        family: str,
        input_text: str,
        answer: str,
        trace: dict[str, Any],
        config_version: int,
        latency_ms: float,
    ) -> None:
        self.ensure_user(user_id)
        self.conn.execute(
            "INSERT INTO tasks_log VALUES (?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                user_id,
                family,
                input_text,
                answer,
                dumps(trace),
                config_version,
                latency_ms,
                now_iso(),
            ),
        )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM tasks_log WHERE task_id=?", (task_id,)).fetchone()
        return _row(row, ("trace_json",))

    def log_feedback(
        self,
        event_id: str,
        user_id: str,
        signal_type: str,
        *,
        task_id: str | None = None,
        config_version: int | None = None,
        origin: str = "user",
        text: str | None = None,
        edit_diff: str | None = None,
        claim: dict[str, Any] | None = None,
        edit_text: str | None = None,
    ) -> None:
        self.ensure_user(user_id)
        self.conn.execute(
            "INSERT INTO feedback_events(event_id,user_id,task_id,config_version,signal_type,"
            "origin,text,edit_diff,claim_json,ts,edit_text,processed) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,0)",
            (
                event_id,
                user_id,
                task_id,
                config_version,
                signal_type,
                origin,
                text,
                edit_diff,
                dumps(claim) if claim is not None else None,
                now_iso(),
                edit_text,
            ),
        )

    def list_feedback(self, user_id: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM feedback_events", []
        if user_id:
            sql += " WHERE user_id=?"
            args.append(user_id)
        return [_row(r, ("claim_json",)) for r in self.conn.execute(sql + " ORDER BY rowid", args)]  # type: ignore[misc]

    def count_recent_feedback(self, user_id: str, minutes: int = 60) -> int:
        since = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM feedback_events WHERE user_id=? AND ts>=?", (user_id, since)
        ).fetchone()
        return int(row["c"])

    # ---------------------------------------------------------------- patches
    def insert_patch(self, patch: dict[str, Any], event_ids: list[str] | None = None) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "INSERT INTO patches(patch_id,type,ops_json,claim_json,warrant_json,witness_json,"
                "scope_json,risk_tier,status,proposer,expiry_json,created_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    patch["patch_id"],
                    patch["type"],
                    dumps(patch["ops"]),
                    dumps(patch.get("claim")),
                    dumps(patch.get("warrant")),
                    dumps(patch.get("witness_test")),
                    dumps(patch.get("declared_scope")),
                    patch["risk_tier"],
                    patch.get("status", "proposed"),
                    patch.get("proposer"),
                    dumps(patch.get("expiry")),
                    now_iso(),
                ),
            )
            for eid in event_ids or []:
                self.conn.execute(
                    "INSERT OR IGNORE INTO patch_sources VALUES (?,?)", (patch["patch_id"], eid)
                )

    def get_patch(self, patch_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM patches WHERE patch_id=?", (patch_id,)).fetchone()
        return _row(
            row,
            ("ops_json", "claim_json", "warrant_json", "witness_json", "scope_json", "expiry_json"),
        )

    def list_patches(self, status: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT patch_id FROM patches", []
        if status:
            sql += " WHERE status=?"
            args.append(status)
        ids = [r["patch_id"] for r in self.conn.execute(sql + " ORDER BY rowid", args)]
        return [self.get_patch(i) for i in ids]  # type: ignore[misc]

    def set_patch_status(self, patch_id: str, status: str) -> None:
        if status not in PATCH_STATUSES:
            raise ValueError(f"unknown patch status: {status}")
        cur = self.conn.execute("UPDATE patches SET status=? WHERE patch_id=?", (status, patch_id))
        if cur.rowcount == 0:
            raise KeyError(patch_id)

    def patch_sources(self, patch_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT event_id FROM patch_sources WHERE patch_id=? ORDER BY rowid", (patch_id,)
        )
        return [r["event_id"] for r in rows]

    def log_gate_run(
        self,
        patch_id: str,
        lock: str,
        result: str,
        metrics: dict[str, Any] | None = None,
        reasons: list[str] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO gate_runs(patch_id,lock,result,metrics_json,reasons_json,ts) "
            "VALUES (?,?,?,?,?,?)",
            (patch_id, lock, result, dumps(metrics or {}), dumps(reasons or []), now_iso()),
        )

    def list_gate_runs(self, patch_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM gate_runs WHERE patch_id=? ORDER BY run_id", (patch_id,)
        )
        return [_row(r, ("metrics_json", "reasons_json")) for r in rows]  # type: ignore[misc]

    # --------------------------------------------------------------- tests
    def upsert_test(
        self,
        test_id: str,
        suite: str,
        family: str,
        input_text: str,
        checker: dict[str, Any],
        tags: list[str] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO tests VALUES (?,?,?,?,?,?)",
            (test_id, suite, family, input_text, dumps(checker), dumps(tags or [])),
        )

    def list_tests(self, suite: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM tests WHERE suite=? ORDER BY test_id", (suite,))
        return [_row(r, ("checker_json", "tags_json")) for r in rows]  # type: ignore[misc]

    # --------------------------------------------------------- config versions
    def insert_config_version(
        self,
        version: int,
        parent: int | None,
        config: dict[str, Any],
        config_hash: str,
        created_from_patch: str | None = None,
        stage: str = "full",
    ) -> None:
        self.conn.execute(
            "INSERT INTO config_versions VALUES (?,?,?,?,?,?,?)",
            (version, parent, dumps(config), config_hash, created_from_patch, stage, now_iso()),
        )

    def get_config_version(self, version: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM config_versions WHERE version=?", (version,)
        ).fetchone()
        return _row(row, ("config_json",))

    def latest_version(self) -> int | None:
        row = self.conn.execute("SELECT MAX(version) v FROM config_versions").fetchone()
        return row["v"]

    # ------------------------------------------------------------------ trust
    def get_trust_row(self, user_id: str, domain: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM trust WHERE user_id=? AND domain=?", (user_id, domain)
        ).fetchone()
        return _row(row)

    def put_trust_row(
        self, user_id: str, domain: str, alpha: float, beta: float, updated_at: str | None = None
    ) -> None:
        self.ensure_user(user_id)
        self.conn.execute(
            "INSERT INTO trust VALUES (?,?,?,?,?) ON CONFLICT(user_id,domain) DO UPDATE SET "
            "alpha=excluded.alpha, beta=excluded.beta, updated_at=excluded.updated_at",
            (user_id, domain, alpha, beta, updated_at or now_iso()),
        )

    # ------------------------------------------------------- rejection ledger
    def ledger_get(self, claim_hash: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM rejection_ledger WHERE claim_hash=?", (claim_hash,)
        ).fetchone()
        return _row(row)

    def ledger_bump(self, claim_hash: str, reason: str, lock: str) -> int:
        """Record a rejection (or a repeat of one); return the new count."""
        self.conn.execute(
            "INSERT INTO rejection_ledger(claim_hash,reason,lock,count,last_seen) "
            "VALUES (?,?,?,1,?) ON CONFLICT(claim_hash) DO UPDATE SET "
            "count=count+1, last_seen=excluded.last_seen",
            (claim_hash, reason, lock, now_iso()),
        )
        return int(self.ledger_get(claim_hash)["count"])  # type: ignore[index]

    # ------------------------------------------------------------ human queue
    def enqueue_human(self, patch_id: str, reason: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO human_queue(patch_id,reason,status,ts) VALUES (?,?, 'pending', ?)",
            (patch_id, reason, now_iso()),
        )
        return int(cur.lastrowid or 0)

    def list_human_queue(self, status: str = "pending") -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM human_queue WHERE status=? ORDER BY item_id", (status,)
        )
        return [dict(r) for r in rows]

    def resolve_human(self, item_id: int, status: str, reviewer: str) -> None:
        self.conn.execute(
            "UPDATE human_queue SET status=?, reviewer=? WHERE item_id=?",
            (status, reviewer, item_id),
        )

    # ----------------------------------------------------------- replay cache
    def cache_get(self, key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT result_json FROM replay_cache WHERE key=?", (key,)
        ).fetchone()
        return None if row is None else json.loads(row["result_json"])

    def cache_put(self, key: str, result: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO replay_cache VALUES (?,?,?)", (key, dumps(result), now_iso())
        )

    # ---------------------------------------------------------- phase 2 helpers
    def unprocessed_feedback(self, signals: tuple[str, ...]) -> list[dict[str, Any]]:
        marks = ",".join("?" for _ in signals)
        rows = self.conn.execute(
            f"SELECT * FROM feedback_events WHERE processed=0 AND signal_type IN ({marks}) "
            "ORDER BY rowid",
            signals,
        )
        return [_row(r, ("claim_json",)) for r in rows]  # type: ignore[misc]

    def mark_processed(self, event_ids: list[str]) -> None:
        for eid in event_ids:
            self.conn.execute("UPDATE feedback_events SET processed=1 WHERE event_id=?", (eid,))

    def save_cluster(self, cluster_id: str, key: str, event_ids: list[str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO clusters VALUES (?,?,?,?)",
            (cluster_id, key, dumps(event_ids), now_iso()),
        )

    def list_config_versions(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT version,parent,config_hash,created_from_patch,stage,ts "
            "FROM config_versions ORDER BY version"
        )
        return [dict(r) for r in rows]

    def delete_test(self, test_id: str) -> None:
        self.conn.execute("DELETE FROM tests WHERE test_id=?", (test_id,))

    def record_signal(self, version: int, signal: str) -> None:
        """Count accept/redo/edit signals in the version's monitor window (created on demand)."""
        col = {"accept": "accepts", "redo": "redos", "edit": "edits"}.get(signal)
        row = self.conn.execute(
            "SELECT window_id FROM monitor_windows WHERE version=? ORDER BY window_id DESC LIMIT 1",
            (version,),
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO monitor_windows(version,accepts,redos,edits,n,ts) "
                "VALUES (?,0,0,0,0,?)",
                (version, now_iso()),
            )
            row = self.conn.execute("SELECT last_insert_rowid() w").fetchone()
            wid = row["w"]
        else:
            wid = row["window_id"]
        sets = "n=n+1" + (f", {col}={col}+1" if col else "")
        self.conn.execute(f"UPDATE monitor_windows SET {sets} WHERE window_id=?", (wid,))

    def get_monitor_window(self, version: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM monitor_windows WHERE version=? ORDER BY window_id DESC LIMIT 1",
            (version,),
        ).fetchone()
        return None if row is None else dict(row)

    def update_patch_fields(self, patch_id: str, **fields: Any) -> None:
        """Update JSON/scalar patch columns by name (ops, claim, warrant, risk_tier ...)."""
        cols = {
            "ops": "ops_json",
            "claim": "claim_json",
            "warrant": "warrant_json",
            "witness": "witness_json",
            "scope": "scope_json",
            "risk_tier": "risk_tier",
        }
        for key, value in fields.items():
            col = cols[key]
            self.conn.execute(
                f"UPDATE patches SET {col}=? WHERE patch_id=?",
                (value if key == "risk_tier" else dumps(value), patch_id),
            )

    def patch_users(self, patch_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT f.user_id u FROM patch_sources s JOIN feedback_events f "
            "ON f.event_id=s.event_id WHERE s.patch_id=? ORDER BY u",
            (patch_id,),
        )
        return [r["u"] for r in rows]

    def patch_events(self, patch_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT f.* FROM patch_sources s JOIN feedback_events f ON f.event_id=s.event_id "
            "WHERE s.patch_id=? ORDER BY s.rowid",
            (patch_id,),
        )
        return [_row(r, ("claim_json",)) for r in rows]  # type: ignore[misc]
