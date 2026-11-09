# Decisions and assumptions

1. **Spec source.** `MAAT_SPEC.md` was not present on disk; the spec text was pasted in the task
   message, so that text is treated as MAAT_SPEC.md.
2. **Venv.** The system Python is externally managed (PEP 668); the project uses `.venv`. Run
   `. .venv/bin/activate` before `make` targets.
3. **Streamlit** is an optional extra (`pip install -e ".[dashboard]"`), installed in Phase 5.
4. **SQLite** uses autocommit (`isolation_level=None`) with explicit `transaction()` blocks;
   WAL mode for file databases.
5. **Extra column** `feedback_events.origin` (default `user`) added so agent-origin events can be
   rejected at ingestion and audited (spec section 9.1).
6. **Trust/gate parameters** live in `settings.py` with the spec defaults. `tau`, `margin`,
   `n_min_probes`, `coverage_min`, `cluster_*`, `n_corr`, `corr_trust_threshold` were not given
   numbers in the spec; initial values are tunable placeholders to be calibrated in Phase 4.
7. **Barrier test** forbids `agent/`, `proposal/`, `gate/` from importing `maat.eval*` or
   mentioning `heldout` / `oracle_label` string literals. Gate code must therefore take suite
   names as arguments rather than hard-coding the held-out name.
8. **`make demo`** calls `scripts/seed_demo.py` and `scripts/run_demo.py`, built in Phase 5.
9. **`make scenarios`** treats "no tests collected" (pytest exit 5) as success until Phase 3.
10. **Real data (supersedes spec rule 2 for the video demo).** The KB is pluggable
    (`MAAT_KB_MODE=synthetic|real`). Synthetic stays the default for tests and CI so they are
    deterministic. The demo and real evaluation run in `real` mode on facts extracted from real
    documents the team supplies, each with source document, section, verbatim quote and a named
    human verifier. Maat never writes real engineering values from model memory. Tasks and suites
    (golden, held-out, invariants) for real mode are built from the same documents.
11. **Real users vs simulated adversaries.** Live demo feedback comes from real people (teammates)
    through the dashboard. Adversarial behaviour (wrong claims, injection, sybil) is role-played
    or scripted and labelled as such in every table; real users alone will not stress the gate.
12. **Tool policy split.** `tool_policy.<family>` has `require` (tools that must be called; the
    charter protects `clause_lookup` here), `ground` (tools whose output the answer must use) and
    `order`. The spec hook "require clause_lookup forces answers from the KB" is implemented by
    `ground`, because the charter forces the call in v1 while v1 must still leave headroom. The
    tool-policy patch scenario therefore adds `ground: [clause_lookup]`.
13. **Mock reads the prompt.** `MockBackend` parses the same line-oriented prompt a real model
    sees (sections RULES, MEMORY, TOOLS, WORKFLOW, TASK), so config sensitivity is genuine and no
    side channel exists. Latency and tokens from the mock are simulated, not wall-clock.
14. **Leaky directive.** `select_rules` includes out-of-scope rules that contain `ROUND_UP_TO:`,
    modelling real-LLM over-generalisation; this powers the silent-regression scenario.
15. **Hash ignores `version`.** Identical content shares replay-cache entries.
16. **Rollback (Phase 2 plan).** Rollback creates a new version that copies the target config, so
    "active = latest version" holds and history is never rewritten.
17. **Templated inputs.** Tasks use templates (`What is the <attr> of <subject>?`, `COMPUTE:`,
    `CONVERT:`, `key=value;` tender text). Real-mode tasks must follow the same templates or the
    parsers in `textparse.py` must be extended.
18. **Module placement.** `checkers.py` and `suites.py` live at top level (not under `eval/`)
    because the gate needs them and the barrier test forbids gate/agent/proposal importing `eval`.
19. **Data is generated.** `scripts/build_data.py` writes the synthetic KB, suites and config_v1;
    a test checks the committed files match the generator.
20. **Claims in `claim_json`.** Factual claim `{subject, attribute, value, source?}` or rule claim
    `{rule_text, applies_to}`. Edits on question-style families derive the claim automatically
    from the corrected answer; free comments need a structured claim or are logged as
    "no structured claim" and skipped (never guessed).
21. **Extra columns.** `feedback_events.processed` (each event proposes once) and `edit_text`
    (the corrected content, needed to derive witness tests for rule patches).
22. **Witness for rule patches** comes from the user's edit: added checklist items must appear and
    removed ones must be absent (regex lookaheads). A rule claim without a task and an edit has no
    witness and is rejected before the gate with a logged reason.
23. **Tender claims** cannot yet yield a memory witness (memory does not affect tender extraction),
    so they are rejected before the gate with a logged reason.
24. **Provisional risk tier** is set at proposal time; Lock 1 (Phase 3) recomputes it.
25. **Approve in Phase 2** adopts directly (no gate exists yet). From Phase 3, `/approve` is only
    valid for quarantined patches; everything else must go through the gate.
26. **Patch ids** are deterministic hashes of (type, ops, claim); the same proposal from several
    users merges sources instead of creating duplicates. Memory/rule ids derive from the claim hash.
27. **Ingestion** (`scripts/ingest_kb.py`): `extract` finds numeric-requirement sentences with
    quote, section and page; `promote` writes only reviewer-approved, fully filled entries as
    verified by the named reviewer. PDF support needs `pypdf` (in the dev extra).
28. **MAAT_SPEC.md** is not in the repo; the spec text from the task message is the reference.
29. **Pipeline semantics.** Only `fail` stops the gate. `quarantine` (Lock 2) and `inconclusive`
    keep running later locks, so a quarantined attack still meets the Lock 4 veto (scenario 3).
    Final order: any fail -> reject; score < bar -> reject; inconclusive; quarantine; adopt.
30. **Warrant for behavioural patches** (rules, tool policy, workflow): there is no factual claim,
    so the witness's expected answer is verified against the KB (question families) or the unit
    table / calculator (unit_calc). Checklist and tender witnesses have no independent verifier
    and go to corroboration or quarantine; the charter is enforced at Lock 4, not Lock 2.
31. **Repeat proposals.** A repeat of a rejected/expired/rolled-back patch gets a new id
    (`<id>-rN`) so the rejection ledger fast-fails it and trust is updated again.
32. **Trust.** Pass weight is multiplied by an account-age factor (0.25 new account -> 1.0 after
    7 days); fail is not discounted. Every reject counts as a fail for each distinct source user.
    E[trust] for the bar is the mean over the patch's source users in the patch's domain.
33. **Witness thresholds.** Base pass rate must be <= 0.2, patched >= 0.8; at least 80% of 5
    template paraphrases must pass. A witness that already passes on the base config is rejected.
34. **Risk tiers (Lock 1, authoritative).** Memory notes on clause_query values are high per the
    spec; incident/other factual notes medium; safety-checklist, protected, policy-flagged and
    tool-policy patches high; non-safety rules low; workflow steps medium.
35. **`apply_patch(enforce=False)`** exists only to build a throw-away sandbox config so a
    violating patch can be measured and then vetoed by Lock 4; it is never persisted.
36. **Human approval** of a quarantined patch adopts it directly: it already passed Locks 3-4 and
    the statistical rule before being queued. Rejection writes the ledger and lowers trust.
37. **Bootstrap.** Two-stage cluster bootstrap (resample families, then tasks within them), 1000
    resamples, one-sided z=1.645 mapped to the 5th/95th percentiles, seeded from the patch id.
38. **Regression set in Phase 3** is golden + accumulated; Lock 5 (Phase 4) adds generated probes,
    the A/A noise floor and the declared-scope check.
39. **Lock 5 probes need no checker.** Probes are compared base-vs-patched by normalised output
    change, so generated invariance probes (other families, other subjects, same subject other
    attribute) never need ground truth. Directional probes are template paraphrases of the witness.
40. **Noise floor.** A/A replays on the base config (3 seeds, offset from the replay seeds) give each
    probe an instability p_i; a probe counts as changed only above max(tau, p_i + margin) with
    tau=0.2, margin=0.1. Scope tolerance defaults to 0 (any out-of-scope change is a veto).
41. **Coverage** = min(1, (in-scope + boundary probes) / n_min_probes); below 0.75, or fewer than 3
    in-scope probes, the lock is `inconclusive`. Boundary = out-of-scope probes of the same family;
    for family-wide scopes it falls back to all out-of-scope probes.
42. **Redundant witness is inconclusive, not a failure.** A witness that already passes on the base
    config (e.g. another patch fixed it first) gives no evidence either way and costs no trust.
43. **Blame localization** scores two things with the same counterfactual formula: ablation of each
    trace element (rule/memory/tool policy/workflow step; protected and charter-required elements
    are never ablated) and typed repairs (ground clause_lookup; insert verify_units, ask_fire_watch,
    ask_gas_test). Ranking: blame, then repairs before ablations, then workflow > tool > rule > memory.
44. **When blame runs.** On `redo` events (expected behaviour comes from an independent verifier:
    KB or unit table/calculator, never from the user) and on edit events that the claim-based
    proposer did not turn into a patch. A single correction still gets its targeted memory note.
45. **Behaviour claims** (`tool_policy`, `workflow_step`) are not factual claims; Lock 2 verifies
    their witness expectation instead of looking them up in the KB.
46. **Head-to-head.** Pending memory patches with different values for the same (subject,
    attribute) are evaluated on the same base config, suites and seeds. The adoptable one with
    the largest margin (score - bar) wins; losers are rejected at "conflict" with the reason
    logged, no ledger entry (a lost contest is not a falsehood) and no trust change. A KB-refuted
    side is rejected on its own. If nobody is adoptable, each follows its own outcome (usually
    quarantine). Scoped variants (stretch) are not built.
47. **Scenario 4** feeds a bundled two-op patch (memory + leaky rounding rule), standing in for
    the multi-op patches an LLM proposer can emit; the rule-based proposer emits single ops.
48. **Shared `Env`** (`maat/env.py`) builds the full deployment for the API, scenarios, worker and
    tests. `maat/scenarios.py` holds the eight scripted scenarios that tests assert on and the
    dashboard runs live (users prefixed `sim_`, results flagged simulated).
49. **Frontend** is React + TypeScript (Vite) instead of Streamlit, per the project owner; it is
    served by the API under /app and consumes the same JSON endpoints.
50. **Dashboard stack.** Vite + React 18 + TypeScript (strict), framer-motion, recharts,
    lucide-react, self-hosted variable fonts (Inter, Fraunces, JetBrains Mono) so the demo works
    offline. HashRouter, so deep links work when the API serves the bundle under `/app/`.
    Dev: `cd web && npm run dev` (proxies API paths to :8000). Prod: `make web`, then the API serves
    `web/dist` at `/app/`.
51. **Request lock.** One SQLite connection is shared by request threads and the background
    worker, so every request and every worker tick takes `Env.lock` (serialised, correctness over
    throughput; a PoC trade-off).
52. **Demo mode** (`MAAT_DEMO_MODE=1`) enables `/demo/*`, which resets state before each scenario.
    It is off by default so a real deployment can never be wiped from the UI. `make demo` turns it
    on, plus the worker, against `maat_demo.db`.
53. **UI verification limits.** A headless browser could not be installed in the build sandbox, so
    the dashboard is verified by `tsc --noEmit` (strict), a production build, tests that the API
    serves the bundle and every asset, a test that every endpoint the UI calls exists, and a check
    that response shapes match the TypeScript types. Visual polish has NOT been checked in a real
    browser; do that before recording.
54. **Lock 5 compares paired replays.** Patched and base answers are compared at the *same*
    seeds (common random numbers); the A/A replays on other seeds only estimate each probe's own
    instability p_i. The spec's "differs from the base modal output" let seed noise masquerade as
    a behaviour change: the first smoke run adopted 0 of 130 patches because of it.
55. **Witness threshold 0.6, not 0.8.** One noisy replay in three failed correct patches. Base pass
    rate must still be <= 0.2. Thresholds were adjusted after seeing eval results (development
    run, disclosed in the report), not tuned on a blind test.
56. **Ledger scope.** The rejection ledger only records rejections about the claim itself (Screen,
    Warrant, Invariants, human). Witness, impact and statistical rejections are about a patch or
    a measurement, and remembering them blocked correct claims forever.
57. **Evaluation design.** Six personas emit event streams that depend only on (seed, round), so
    all systems face identical users (paired comparison). Systems share the front end (collector,
    clustering, proposer, blame) and differ only in acceptance logic. The oracle labels *patches*
    from ground truth: KB, charter, and six "frontier" subjects the KB lacks (claims no lookup can
    verify). Without the frontier set the Warrant lock would simply look answers up, flattering S5.
58. **No human in the loop in the simulation.** Quarantined patches count as not adopted, so
    S5's good-patch rejection includes correct but unverifiable claims awaiting review. That is the
    honest price of safety, reported rather than hidden.
59. **S3 is a stand-in.** The "LLM judge" is a deterministic plausibility heuristic (surface
    features, citations, injection and unsafe-wording checks, repeated claims). S3 numbers
    describe that heuristic, not a specific model. A real judge model is a Phase 7 option.
60. **Bundled attacks.** A claim carrying both a fact and a rule becomes a two-op patch (fact +
    rule) in the rule-based proposer, so the silent-regression attack exists in the simulation.
61. **Shared replay cache.** Replay results are cached in-process across systems and ablation
    variants (key: backend tag incl. noise, config hash, test id, seed). Identical configs reuse
    work; nothing else is shared.
62. **Ablations.** Leave-one-out for Screen, Warrant, Invariants, Impact, Trust, plus Warrant
    removed together with each other lock (single removals are masked by overlap). Rollout and
    rollback ablations are not run because those are [STRETCH] items not built.
