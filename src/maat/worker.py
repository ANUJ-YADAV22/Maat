"""Background learning loop: propose patches from new feedback, then gate them (async path)."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from typing import Any

from maat.env import Env


def tick(env: Env, lock: threading.RLock | None = None) -> dict[str, Any]:
    """One pass of the offline pipeline: feedback -> proposals -> gate decisions."""
    with lock or contextlib.nullcontext():
        proposed = env.propose()
        decided = env.decide() if proposed["patches"] or env.repo.list_patches("proposed") else []
    return {"proposed": proposed["patches"], "decided": [d.outcome for d in decided]}


async def run_worker(env: Env, lock: threading.RLock, interval: float) -> None:
    """Poll forever; the gate never sits on the user-facing path."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(tick, env, lock)
        except Exception as exc:  # keep the loop alive; the failure is audited
            with lock:
                env.repo.audit("worker.error", "worker", {"error": repr(exc)})
