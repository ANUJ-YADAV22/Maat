"""Start the demo: API + background worker + the built dashboard at http://127.0.0.1:8000/app/."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    os.environ.setdefault("MAAT_DB_PATH", "maat_demo.db")
    os.environ.setdefault("MAAT_DEMO_MODE", "1")
    os.environ.setdefault("MAAT_WORKER_ENABLED", "1")
    if not (ROOT / "web" / "dist").exists():
        print(
            "note: dashboard not built; run `make web` first (API docs at /docs still work)",
            file=sys.stderr,
        )
    print("Maat demo: http://127.0.0.1:8000/app/   API docs: http://127.0.0.1:8000/docs")
    uvicorn.run("maat.api.app:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
