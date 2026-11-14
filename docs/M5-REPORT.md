# NRE Milestone 5 — Advanced models

Phase 3 compared the registered advanced models with baselines selected on earlier data across 128 development events. Zero targets cleared the development gate. Phase 4 used the frozen development pipeline for the single authorized look at the 43-event extension. The [workflow](https://github.com/Fahad9101/NRE/actions/runs/43405024484) logged access before contacting Alpaca and verified all 43 label commitments and the Phase 1c holdout feature commitment.

| Target | Clean-window support | Candidate minus baseline loss | 99% cluster interval envelope |
| --- | ---: | ---: | ---: |
| Opening gap of at least 3% | 37 scored | +0.003853 | [-0.020841, 0.030962] |
| Opening gap of at least 5% | 37 eligible, 9 positives | Counts only | — |
| Day-1 close return | 37 scored | +0.000640 | [-0.003369, 0.006253] |
| Extension of at least 5% after the open | 37 scored | -0.005446 | [-0.042291, 0.032420] |
| Loses half of the opening gap | 17 eligible, 3 positives | Counts only | — |

Loss is Brier for binary targets and mean pinball loss for Day-1 return quantiles. Negative differences favor the candidate. Every estimable clean-window interval includes zero. Post-open extension favored the candidate in both development and holdout, with uncertainty spanning improvement and degradation. Day-1 return changed direction between development and holdout in the clean-window comparison. The 5% opening gap was estimable in the all-event sensitivity, where candidate loss was higher. Zero targets qualified for promotion.

The [aggregate results](../reports/m5-phase4-results-2026-11-13.json) include both caveat variants, cluster intervals and calibration. The [development report](M5-PHASE3-REPORT.md) records ablations, support and deterministic replay. The [access record](../reports/m5-phase4-access-2026-11-13.json) and [development lock](../reports/m5-phase4-development-lock-2026-11-13.json) bind the one-look evidence. Raw bars and event-level holdout outcomes and predictions stayed in memory.

The project owner [declared Milestone 5 accepted](../reports/m5-acceptance-declaration-2026-11-14.json) on 2026-11-14.
