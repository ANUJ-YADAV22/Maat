# Maat

Safe, warranted, reversible feedback-driven improvement of agentic AI **without retraining**.
An agent learns by editing only its config (memory, rules, tool policy, workflow). Every change is
a *Warranted Patch* that must pass five locks (Screen, Warrant, Witness, Invariants, Impact surface)
and a statistical decision rule, then rolls out in stages and can be rolled back.

## Setup
```
python3 -m venv .venv && . .venv/bin/activate
make install
```

## Commands
| Command | What it does | Available from |
|---|---|---|
| `make data` | regenerate synthetic KB, suites, config_v1 | Phase 1 |
| `make api` | run the API at http://127.0.0.1:8000/docs | Phase 1 |
| `make lint` | ruff check + format check | Phase 0 |
| `make test` | unit + integration tests | Phase 0 |
| `make scenarios` | the six demo scenarios (1-3 built) | Phase 3 |
| `make eval-smoke` | evaluation, 3 seeds x 5 rounds (about 90 s) | Phase 6 |
| `make eval` | full evaluation, 10 seeds x 10 rounds (about 12 min) | Phase 6 |
| `make web` | build the React dashboard into web/dist | Phase 5 |
| `make demo` | seed data, start API + worker, serve the dashboard at http://127.0.0.1:8000/app/ | Phase 5 |

## Status
| Feature | Status |
|---|---|
| Scaffold, settings, SQLite schema, repository layer, information-barrier test | Built |
| Synthetic KB, suites, charter, config model, apply_patch, MockBackend, agent runtime, /task | Built |
| Feedback collector, clustering, rule-based proposer, witness generation, versioning, rollback, /feedback /versions /rollback | Built |
| KB ingestion tool for real documents (`scripts/ingest_kb.py`) | Built |
| Safety gate Locks 1-4, decision engine, trust service, rejection ledger, human queue, scenarios 1-3 | Built |
| Lock 5 (probes, noise floor, scope veto), conflicts, blame localization, scenarios 4-8 | Built |
| Worker, explanations, Patch Passports, React + TypeScript dashboard | Built (UI not yet viewed in a browser) |
| Evaluation harness: six systems, six simulated personas, ablations, FAR/FRR, plots, report | Built; results in results/ |
| Ollama backend, LLM proposer, cost script, real-model run | Not started (Phase 7) |
| Docs polish, demo script | Not started (Phase 8) |

All simulated users and satisfaction numbers are labelled simulated. The knowledge base is synthetic.
