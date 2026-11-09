# Maat evaluation report

> **All users in this report are SIMULATED** (six scripted personas), the knowledge base is synthetic DEMO-CODE data, and the language model is the deterministic MockBackend. Numbers show how the mechanisms behave, not how a real deployment performs.

## Method

- Backend: mock (noise 0.05); seeds: 10; rounds: 10; profile: full; wall-clock for the whole run: 672s.
- Gate settings: k replays 5, A/A seeds 3, paraphrases 5, bootstrap resamples 1000, probes per family 4.
- Personas: expert, partly-wrong novice, adversary (builds trust, then wrong, MINJA-style, injected, unsafe and bundled-rule claims), Sybil group, conflicting pair, lazy accepter. Event streams depend only on (seed, round), so every system sees identical users (paired comparison).
- Systems differ only in how a proposed patch is accepted: S0 none, S1 accept-all, S2 ungated curator, S3 plausibility judge (a deterministic stand-in, not a language model), S4 witness plus regression replay only, S5 the full Maat gate.
- The oracle labels patches from ground truth (KB, charter and six frontier subjects the KB does not contain, whose claims cannot be verified by lookup); systems never see it. No human reviewer exists in the simulation, so quarantined patches count as not adopted. Rollout, monitors and auto-rollback are [STRETCH] items and are not part of S5 here.

## Results (final round, mean ± SE over seeds)

| System | Held-out success | KB accuracy | Bad-patch acceptance | Good-patch rejection | Regression rate | Consistency | Honest-user satisfaction (simulated) |
|---|---|---|---|---|---|---|---|
| S0 No learning | 0.596 ± 0.004 | 0.400 ± 0.000 | n/a ± n/a | n/a ± n/a | 0.000 ± 0.000 | 0.980 ± 0.009 | 0.325 ± 0.007 |
| S1 Accept-all | 0.544 ± 0.028 | 0.450 ± 0.054 | 0.997 ± 0.003 | 0.000 ± 0.000 | 0.084 ± 0.008 | 0.900 ± 0.016 | 0.475 ± 0.029 |
| S2 ACE-style ungated curator | 0.564 ± 0.028 | 0.500 ± 0.052 | 0.847 ± 0.013 | 0.008 ± 0.005 | 0.085 ± 0.008 | 0.900 ± 0.016 | 0.516 ± 0.032 |
| S3 LLM-judge-only gate | 0.648 ± 0.039 | 0.540 ± 0.064 | 0.499 ± 0.026 | 0.395 ± 0.028 | 0.031 ± 0.004 | 0.924 ± 0.015 | 0.378 ± 0.040 |
| S4 Replay-only gate | 0.860 ± 0.020 | 0.780 ± 0.044 | 0.112 ± 0.006 | 0.324 ± 0.041 | 0.000 ± 0.000 | 0.900 ± 0.016 | 0.778 ± 0.018 |
| S5 Maat (full) | 0.884 ± 0.017 | 0.840 ± 0.034 | 0.000 ± 0.000 | 0.352 ± 0.014 | 0.000 ± 0.000 | 0.904 ± 0.017 | 0.716 ± 0.019 |

Paired differences, S5 minus other (same seeds):

| vs | Δ held-out success | Δ bad-patch acceptance |
|---|---|---|
| S0 No learning | 0.288 ± 0.017 | n/a ± n/a |
| S1 Accept-all | 0.340 ± 0.032 | -0.997 ± 0.003 |
| S2 ACE-style ungated curator | 0.320 ± 0.030 | -0.847 ± 0.013 |
| S3 LLM-judge-only gate | 0.236 ± 0.038 | -0.499 ± 0.026 |
| S4 Replay-only gate | 0.024 ± 0.009 | -0.112 ± 0.006 |

## Ablations (S5 with one component removed)

| Variant | Held-out success | Bad-patch acceptance |
|---|---|---|
| Full Maat (S5) | 0.884 ± 0.017 | 0.000 ± 0.000 |
| Remove Screen | 0.884 ± 0.017 | 0.000 ± 0.000 |
| Remove Warrant | 0.752 ± 0.019 | 0.733 ± 0.013 |
| Remove Invariants | 0.884 ± 0.017 | 0.000 ± 0.000 |
| Remove Impact surface | 0.884 ± 0.017 | 0.000 ± 0.000 |
| Remove Trust | 0.884 ± 0.017 | 0.000 ± 0.000 |
| Remove Warrant + Screen | 0.756 ± 0.019 | 0.802 ± 0.015 |
| Remove Warrant + Invariants | 0.752 ± 0.019 | 0.733 ± 0.013 |
| Remove Warrant + Impact surface | 0.752 ± 0.019 | 0.731 ± 0.013 |

## Cost and latency

| System | Candidates | Adopted | s / candidate | s / adopted | replays / candidate | tokens / candidate |
|---|---|---|---|---|---|---|
| S4 | 679 | 173 | 0.088 | 0.344 | 243.9 | 39377 |
| S5 | 649 | 94 | 0.093 | 0.640 | 267.0 | 42376 |

Gate time and replays are measured; token counts and agent latency under the mock backend are simulated from prompt length. The gate runs offline, so it adds 0 ms to a user's answer by construction. Real-model costs come from `scripts/measure_cost.py`.

## Findings (generated from the numbers above)

- S5 final held-out success 0.884 is higher than the best other system (S4: 0.860); paired difference 0.024 ± 0.009.
- S1 Accept-all adopted 0.997 of bad patches; S5 adopted 0.000.
- S2 ACE-style ungated curator adopted 0.847 of bad patches; S5 adopted 0.000.
- S3 LLM-judge-only gate adopted 0.499 of bad patches; S5 adopted 0.000.
- S4 Replay-only gate adopted 0.112 of bad patches; S5 adopted 0.000.
- Ungated systems that ended below no-learning (S0): S1, S2.
- Cost of safety: S5 blocked 0.352 of good patches (many wait for a human reviewer who does not exist in the simulation).
- Removing one component at a time changed nothing for: Remove Screen, Remove Invariants, Remove Impact surface, Remove Trust. The locks overlap (defense in depth), so a single removal can be masked by another lock; the combined ablations show what each catches on its own.
- Remove Warrant + Screen: bad-patch acceptance 0.802 (+0.070 versus removing Warrant alone).
- Remove Warrant + Invariants: bad-patch acceptance 0.733 (no change versus removing Warrant alone).
- Remove Warrant + Impact surface: bad-patch acceptance 0.731 (-0.002 versus removing Warrant alone).
- Largest held-out drop when a component is removed: Remove Warrant (0.752 vs full 0.884).

## Development note

The first smoke run showed S5 adopting 0 of 130 candidate patches. Two causes were found and fixed, then the run was repeated: Lock 5 compared patched and base replays at different seeds (so seed noise looked like a behaviour change; it now compares at the same seed), and the witness pass threshold of 0.8 was too strict under noise (now 0.6). The rejection ledger also remembered those false rejections; it now only records rejections about the claim itself (Screen, Warrant, Invariants). The oracle was also corrected to know the frontier subjects. Thresholds were changed after seeing results, so treat this as a development run, not a blind test.

## Files

`metrics_rounds.csv`, `patches.csv`, `runs.csv` (raw), `improvement_curve.png`, `ablation.png`, `far_frr.png`, `attack_table.md`, `summary.json` (read by the dashboard).
