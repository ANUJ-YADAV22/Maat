# Progress

## Phase 0: scaffold (done)
- Repo layout, pyproject (src layout, ruff, pytest), Makefile targets, .gitignore.
- `settings.py` (all gate/trust parameters, `MAAT_*` env overrides).
- `db.py` (15-table schema with indices, status CHECK, FK on) and `repo.py` (repository layer).
- Tests: settings, schema, repo round-trips, information-barrier test. 13 passed.
- `make lint && make test && make scenarios` all pass.

## Phase 1: data, config model, agent (done)
- 30-entry synthetic KB, golden (40), held-out (25), invariants (8), charter.yaml, config_v1.json.
- `apply_patch` (pure, protected-item and charter enforcement), config hash, diff; checkers; tools.
- MockBackend (all hooks tested), Agent runtime with traces, `/task` and `/health` API.
- Config v1 fails exactly 10/25 held-out tasks (40%), passes all golden and invariant tasks.
- 74 tests pass; determinism test passes; `make lint && make test && make scenarios` green.

## Phase 2: feedback, proposals, versioning (done)
- Collector (agent-origin refused, rate limits, derived claims, edit diffs, monitor counts), clustering with per-account cap.
- Warranted Patch contract, RuleBasedProposer with witness generation, typed tool/workflow builders, proposal pipeline.
- adopt (one transaction, accumulated witness test), rollback as a new version copying the target, audit entries.
- API: /feedback, /proposals/run, /patches, /versions, /versions/{a}/diff/{b}, /rollback, /audit; scripts/ingest_kb.py.
- 97 tests pass; acceptance test: approved patch -> v2 improves the answer; rollback -> v3 restores v1 behaviour.

## Phase 3: safety gate Locks 1-4, decision, trust (done)
- Locks: Screen (injection, PII redaction, provenance, authoritative risk tier), Warrant (KB / unit / calculator verification, ledger, corroboration, quarantine), Witness (fails before, passes after, paraphrases), Invariants (static charter check + invariant suite, absolute veto).
- Decision engine: hard vetoes, then LCB(gain) - lambda_tier * UCB(harm) >= Bar with cluster bootstrap; trust service (Beta, decay, age weighting); rejection ledger; human queue; cached replayer.
- API: /gate/run, /queue, /trust/{user}; /approve and /reject now only for quarantined patches.
- Scenarios 1 (valid correction), 2 (wrong correction, no replay), 3 (invariant attack vetoed at Lock 4) pass on MockBackend; a full gate pass takes well under a second.
- 132 tests pass (129 unit/integration + 3 scenarios); lint clean. Next: Phase 4 (Lock 5, probes, noise floor, conflicts, blame).

## Phase 4: Lock 5, conflicts, blame (done)
- Lock 5: generated probes, A/A noise floor, changed-set rule, declared-scope veto, scope precision/recall, coverage (inconclusive below threshold).
- Head-to-head conflict handling; counterfactual blame localization with ablations and typed repairs; BlameProposer for redo and uncorrected edits.
- Explanations and Patch Passports built from stored records; eight scripted scenarios (1-8) shared by tests and the live dashboard.
- Scenarios 4 (silent regression vetoed at Lock 5), 5 (conflict), 6 (rollback note), 7 (tool-policy patch from a redo click), 8 (workflow-step patch) pass.
- 161 tests pass (144 unit/integration + 17 scenarios); lint clean.

## Phase 5: worker, explanations, API, React dashboard (done; UI visually unverified)
- Background worker (propose -> gate), request lock, /overview /kb /trust /tasks /explain /passport /demo/* endpoints, CORS, static serving of web/dist at /app/.
- React + TypeScript dashboard: Overview, Live scenarios, Playground, Patches (lock chain, evidence meter, Patch Passport, explanation), Approvals, Versions (diff, rollback), Trust board, Knowledge, Evaluation, Audit.
- scripts/seed_demo.py and scripts/run_demo.py behind `make demo`; `make web` builds the bundle.
- 159 unit/integration tests + 17 scenarios pass; strict typecheck and production build pass.
- Fixed a real determinism bug found by the scenario tests: same-second events were ordered by random ids; all processing now follows insertion order (regression test added).
- Not verified in a real browser (none installable here): open it and check the visuals before recording.

## Phase 6: evaluation harness (done)
- Six systems (S0-S5), six simulated personas, oracle, metrics, ablations (single and combined), FAR/FRR sweep, plots, attack table, report and summary.json for the dashboard.
- First run exposed real defects (S5 adopted 0/130): unpaired Lock 5 replays, strict witness threshold under noise, over-eager rejection ledger, oracle wiring. All fixed and disclosed in the report.
- Full run (10 seeds, 10 rounds, mock backend, 672 s): held-out success S5 0.884, S4 0.860 (paired diff 0.024 +- 0.009), S3 0.648, S2 0.564, S1 0.544, S0 0.596; bad-patch acceptance S5 0.000, S4 0.112, S3 0.499, S2 0.847, S1 0.997; S5 blocks 35% of good (mostly unverifiable) patches; honest-user satisfaction S5 0.716 vs S4 0.778 (the price of safety).
- Only Warrant shows marginal value in ablations; other locks overlap on this attack mix (reported as such).
- 170 unit/integration tests + 17 scenarios pass; lint clean.
