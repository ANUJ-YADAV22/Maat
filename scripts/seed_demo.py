"""Create the demo database and populate it with a few scenario runs so the dashboard has data.

Usage: python scripts/seed_demo.py [--db maat_demo.db]. Every seeded user is simulated (sim_*).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from maat.env import build_env
from maat.scenarios import SCENARIOS, run_scenario
from maat.settings import Settings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="maat_demo.db")
    ap.add_argument("--scenarios", default="1,2,3,4", help="comma list; the last ones stay visible")
    args = ap.parse_args()
    Path(args.db).unlink(missing_ok=True)
    env = build_env(Settings(db_path=args.db))
    env.reset()
    ids = [int(x) for x in args.scenarios.split(",") if x]
    for sid in ids:
        r = run_scenario(env, sid, reset=False)
        print(f"scenario {sid} {SCENARIOS[sid][0]:<20} -> {r['outcome']}")
    print(f"seeded {args.db}: active config v{env.active()['version']}")


if __name__ == "__main__":
    main()
