# Prompt to continue the build with Claude Code

Save your full spec text as MAAT_SPEC.md in the repo root, open a terminal there, run `claude`,
then paste everything below the line.

---

You are continuing the Maat build in this repository. First read README.md, DECISIONS.md and
PROGRESS.md, then read the whole of MAAT_SPEC.md. Phases 0 and 1 are done and green. Continue with Phase 2, then 3, and so on
through Phase 8, in order.

Rules:
- After each phase: run its acceptance commands (`make lint && make test && make scenarios`,
  plus any phase-specific command), fix failures, commit, and append a 5-line status to
  PROGRESS.md. Never skip or weaken tests to get green.
- Do not ask me questions unless truly blocked. Record every assumption in DECISIONS.md.
- Never fabricate results. Every number in results/ must come from running the code. Simulated
  users and satisfaction are labelled simulated everywhere.
- Keep the information barrier: agent/, proposal/ and gate/ never import maat.eval or touch the
  held-out suite or oracle labels (tests/unit/test_barrier.py must stay green).
- Hard vetoes (definite injection, invariant violation, witness not fixed, undeclared impact)
  can never be overridden by trust. Every state change writes an audit entry.
- All unit and scenario tests run on MockBackend. Real-model runs (Ollama) are Phase 7.
- Real data: `MAAT_KB_MODE=real` loads facts from data/clause_kb/real/*.json, each with source
  document, section, verbatim quote and a named verifier. Never invent real engineering values.
  Build scripts/ingest_kb.py in Phase 2 to extract candidate facts from documents I supply.
- Skip [STRETCH] items until all core phases pass.

Start with Phase 2: feedback collector and signals, clustering, RuleBasedProposer with witness
generation, versioning (adopt, rollback as a new version copying the target), audit, and the
/feedback and /versions endpoints. Acceptance: a manually approved patch creates v2 and improves
a task; rollback restores v1's behaviour.
