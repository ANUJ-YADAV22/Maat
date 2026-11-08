"""FastAPI application: tasks, feedback, proposals, patches, versions, rollback, audit."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from maat.api.schemas import (
    ApproveRequest,
    ErrorResponse,
    FeedbackResponse,
    RollbackRequest,
    TaskRequest,
    TaskResponse,
)
from maat.contracts import PatchContract
from maat.env import build_env
from maat.feedback.collector import FeedbackRejected
from maat.feedback.signals import FeedbackIn
from maat.llm.base import LLMBackend
from maat.scenarios import SCENARIOS, run_scenario
from maat.settings import Settings, get_settings
from maat.store import versions
from maat.store.explain import explain_patch, explain_rollback, passport
from maat.store.versions import VersionError
from maat.worker import run_worker


def create_app(
    settings: Settings | None = None,
    *,
    db_path: str | None = None,
    backend: LLMBackend | None = None,
) -> FastAPI:
    """Build the app. Tests pass an in-memory db and a MockBackend."""
    cfg = settings or get_settings()
    env = build_env(cfg, db_path=db_path, backend=backend)
    repo, kb, agent = env.repo, env.kb, env.agent
    collector, trust, gate = env.collector, env.trust, env.gate

    def locked() -> Iterator[None]:
        """Serialise requests with the background worker (one SQLite connection)."""
        with env.lock:
            yield

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if cfg.worker_enabled:
            task = asyncio.create_task(run_worker(env, env.lock, cfg.worker_interval_s))
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Maat", version="0.1.0", lifespan=lifespan, dependencies=[Depends(locked)])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.env, app.state.repo, app.state.agent, app.state.settings = env, repo, agent, cfg
    app.state.gate, app.state.trust = gate, trust

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        body = ErrorResponse(error={"code": "validation_error", "message": str(exc.errors())})
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "config_version": versions.active_version(repo), "kb_mode": kb.mode}

    @app.post("/task", response_model=TaskResponse, responses={422: {"model": ErrorResponse}})
    def post_task(req: TaskRequest) -> TaskResponse:
        version = versions.active_version(repo)
        config = versions.active_config(repo)
        task = {"family": req.family, "input": req.input}
        result = agent.run(task, config, cfg.seed)
        task_id = f"t_{uuid.uuid4().hex[:12]}"
        repo.log_task(
            task_id,
            req.user_id,
            req.family,
            req.input,
            result["answer"],
            result["trace"],
            version,
            result["latency_ms"],
        )
        return TaskResponse(
            task_id=task_id, answer=result["answer"], trace=result["trace"], config_version=version
        )

    @app.exception_handler(FeedbackRejected)
    async def _fb_rejected(_: Request, exc: FeedbackRejected) -> JSONResponse:
        body = ErrorResponse(error={"code": exc.code, "message": exc.message})
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(VersionError)
    async def _version_error(_: Request, exc: VersionError) -> JSONResponse:
        status = 404 if exc.code.startswith("unknown") else 409
        body = ErrorResponse(error={"code": exc.code, "message": exc.message})
        return JSONResponse(status_code=status, content=body.model_dump())

    def _not_found(what: str) -> HTTPException:
        return HTTPException(status_code=404, detail=f"{what} not found")

    @app.post("/feedback", response_model=FeedbackResponse)
    def post_feedback(fb: FeedbackIn) -> FeedbackResponse:
        return FeedbackResponse(event_id=collector.ingest(fb))

    @app.post("/proposals/run")
    def post_proposals_run() -> dict[str, Any]:
        """Turn pending feedback into proposed patches (Phase 3 adds the gate behind /gate/run)."""
        return env.propose()

    @app.get("/patches")
    def get_patches(status: str | None = None) -> list[dict[str, Any]]:
        rows = repo.list_patches(status)
        for r in rows:
            r["claim_text"] = _claim_text(r)
            r["users"] = repo.patch_users(r["patch_id"])
        return rows

    @app.get("/patches/{patch_id}")
    def get_patch(patch_id: str) -> dict[str, Any]:
        row = repo.get_patch(patch_id)
        if row is None:
            raise _not_found("patch")
        contract = PatchContract.from_row(row, repo.patch_sources(patch_id))
        return {
            "contract": contract.model_dump(),
            "status": row["status"],
            "gate_runs": repo.list_gate_runs(patch_id),
        }

    @app.post("/gate/run")
    def post_gate_run() -> list[dict[str, Any]]:
        """Run the safety gate on every proposed patch and apply each decision."""
        return [asdict(o) for o in gate.process_pending()]

    @app.post("/patches/{patch_id}/approve")
    def approve_patch(patch_id: str, req: ApproveRequest) -> dict[str, Any]:
        """Human gate: only quarantined patches can be approved; approval adopts them."""
        return asdict(gate.human_review(patch_id, True, req.reviewer, req.reason))

    @app.post("/patches/{patch_id}/reject")
    def reject_patch(patch_id: str, req: ApproveRequest) -> dict[str, Any]:
        return asdict(gate.human_review(patch_id, False, req.reviewer, req.reason))

    @app.get("/queue")
    def get_queue(status: str = "pending") -> list[dict[str, Any]]:
        return repo.list_human_queue(status)

    @app.get("/trust/{user_id}")
    def get_trust(user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "trust": trust.board(user_id)}

    @app.get("/versions")
    def get_versions() -> list[dict[str, Any]]:
        rows = repo.list_config_versions()
        for r in rows:
            r["claim_text"] = (
                _claim_text({"patch_id": r["created_from_patch"]})
                if r["created_from_patch"]
                else None
            )
            r["rollback_note"] = (
                explain_rollback(repo, r["version"]) if r["stage"] == "rollback" else None
            )
        return rows

    @app.get("/versions/{a}/diff/{b}")
    def get_diff(a: int, b: int) -> list[dict[str, Any]]:
        return versions.diff_versions(repo, a, b)

    @app.post("/rollback")
    def post_rollback(req: RollbackRequest) -> dict[str, Any]:
        new = versions.rollback(repo, req.to_version, req.reason, req.actor)
        return {"config_version": new, "restored_from": req.to_version}

    @app.get("/audit")
    def get_audit(event: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return repo.list_audit(event, limit)

    def _claim_text(row: dict[str, Any]) -> str:
        return explain_patch(repo, row["patch_id"])["claim"]

    @app.get("/overview")
    def overview() -> dict[str, Any]:
        q = repo.conn.execute
        counts = {
            r["status"]: r["c"] for r in q("SELECT status, COUNT(*) c FROM patches GROUP BY status")
        }
        secs = []
        for g in q("SELECT metrics_json FROM gate_runs WHERE lock='decision'"):
            m = json.loads(g["metrics_json"] or "{}")
            if "gate_seconds" in m:
                secs.append(m["gate_seconds"])
        return {
            "config_version": versions.active_version(repo),
            "patch_counts": counts,
            "kb_mode": kb.mode,
            "kb_entries": len(kb.entries),
            "backend": getattr(agent.backend, "name", "unknown"),
            "tasks": q("SELECT COUNT(*) c FROM tasks_log").fetchone()["c"],
            "feedback": q("SELECT COUNT(*) c FROM feedback_events").fetchone()["c"],
            "users": q("SELECT COUNT(*) c FROM users").fetchone()["c"],
            "rejections_remembered": q("SELECT COUNT(*) c FROM rejection_ledger").fetchone()["c"],
            "pending_approvals": len(repo.list_human_queue()),
            "avg_gate_seconds": round(sum(secs) / len(secs), 4) if secs else None,
            "replays": env.gate.ctx.replayer.snapshot(),
            "demo_mode": cfg.demo_mode,
            "worker": cfg.worker_enabled,
            "recent_audit": repo.list_audit(None, 8),
        }

    @app.get("/kb")
    def get_kb() -> dict[str, Any]:
        return {"mode": kb.mode, "entries": [e.model_dump() for e in kb.entries]}

    @app.get("/tasks")
    def get_tasks(limit: int = 30) -> list[dict[str, Any]]:
        rows = repo.conn.execute(
            "SELECT task_id,user_id,family,input,answer,config_version,latency_ms,ts "
            "FROM tasks_log ORDER BY rowid DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    @app.get("/trust")
    def get_trust_board() -> list[dict[str, Any]]:
        users = [r["user_id"] for r in repo.conn.execute("SELECT user_id FROM users ORDER BY 1")]
        return [{"user_id": u, "trust": trust.board(u)} for u in users]

    @app.get("/explain/{patch_id}")
    def get_explain(patch_id: str) -> dict[str, Any]:
        if repo.get_patch(patch_id) is None:
            raise _not_found("patch")
        return explain_patch(repo, patch_id)

    @app.get("/passport/{patch_id}")
    def get_passport(patch_id: str) -> dict[str, Any]:
        if repo.get_patch(patch_id) is None:
            raise _not_found("patch")
        return passport(repo, patch_id)

    @app.get("/rollback/{version}/note")
    def get_rollback_note(version: int) -> dict[str, Any]:
        note = explain_rollback(repo, version)
        if note is None:
            raise _not_found("rollback note")
        return note

    @app.get("/eval/summary")
    def get_eval_summary() -> dict[str, Any]:
        path = Path(cfg.results_dir) / "summary.json"
        if not path.exists():
            return {"available": False}
        return {"available": True, **json.loads(path.read_text())}

    def _demo_guard() -> None:
        if not cfg.demo_mode:
            raise HTTPException(status_code=403, detail="demo mode is off (MAAT_DEMO_MODE=1)")

    @app.get("/demo/scenarios")
    def list_scenarios() -> list[dict[str, Any]]:
        return [{"id": i, "title": t} for i, (t, _) in SCENARIOS.items()]

    @app.post("/demo/scenarios/{sid}/run")
    def run_demo_scenario(sid: int, reset: bool = True) -> dict[str, Any]:
        _demo_guard()
        if sid not in SCENARIOS:
            raise _not_found("scenario")
        return run_scenario(env, sid, reset)

    @app.post("/demo/reset")
    def demo_reset() -> dict[str, Any]:
        _demo_guard()
        env.reset()
        return {"config_version": versions.active_version(repo)}

    web = Path(__file__).resolve().parents[3] / "web" / "dist"
    if web.exists():
        app.mount("/app", StaticFiles(directory=web, html=True), name="web")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/app/")

    return app
