# Milestone 5 Phase 3 — Development comparison

The registered comparison used 128 development events and evaluated the eligible out-of-fold rows in blocks 3, 4 and 5. Zero targets passed the development gate. The 43-event forward holdout remained sealed.

| Target | Clean-window scored / eligible | Paired loss difference | 99% cluster interval envelope |
| --- | ---: | ---: | ---: |
| Opening gap of at least 3% | 21 / 64 | Insufficient data | — |
| Opening gap of at least 5% | 21 / 64 | Insufficient data | — |
| Day-1 close return | 44 / 64 | -0.000085 | [-0.006544, 0.005757] |
| Extension of at least 5% after the open | 64 / 64 | -0.009324 | [-0.055164, 0.041032] |
| Loses half of the opening gap | 10 / 33 | Insufficient data | — |

Differences are advanced-model loss minus the selected baseline loss. Both estimable intervals span zero in both caveat versions. Day-1 close return had 79.5% coverage for the nominal 80% interval, but the earliest fold missed the fit minimum. The post-open extension target missed the binary calibration gate. The two gap targets and the gap-retention target each had fewer than ten scored positives.

Removing daily market structure increased clean-window Day-1 return pinball loss by 0.004743. Removing market regime increased clean-window post-open extension Brier loss by 0.008264. These ablations are descriptive. The [results](../reports/m5-phase3-results-2026-11-13.json) contain all four ablations for estimable comparisons, both caveat versions and the nested-gap sensitivity. The [experiment journal](../reports/m5-phase3-experiments-2026-11-13.jsonl) contains fold-level selections, coverage, calibration and paired rows, including folds with inadequate pooled support.

Two runs from the same clean code revision produced byte-identical results and journals. To reproduce, check out the code commit in the [replay record](../reports/m5-phase3-replay-2026-11-13.json) and run the following with the verified Phase 1c archive.

```text
python -m nre.m5_phase3 --artifact PATH_TO_PHASE_1C_ZIP --output PATH_OUTSIDE_CHECKOUT
```

Phase 4 requires separate owner authorization.
