# Attack table (SIMULATED adversarial users, 10 seeds, mean ± SE)

| System | Bad-patch acceptance | Good-patch rejection | Regression rate |
|---|---|---|---|
| S1 Accept-all | 0.997 ± 0.003 | 0.000 ± 0.000 | 0.084 ± 0.008 |
| S2 ACE-style ungated curator | 0.847 ± 0.013 | 0.008 ± 0.005 | 0.085 ± 0.008 |
| S3 LLM-judge-only gate | 0.499 ± 0.026 | 0.395 ± 0.028 | 0.031 ± 0.004 |
| S4 Replay-only gate | 0.112 ± 0.006 | 0.324 ± 0.041 | 0.000 ± 0.000 |
| S5 Maat (full) | 0.000 ± 0.000 | 0.352 ± 0.014 | 0.000 ± 0.000 |

Bad = the oracle says the patch is wrong or harmful. Regression rate = share of previously passing held-out and golden tasks that fail after a round.
