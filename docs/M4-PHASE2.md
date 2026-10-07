# Milestone 4 — Phase 2: the baselines on the B clock (method and build record)

**Status: built 2026-10-07 on the owner's go-ahead for Phase 2 ("authorize phase 2", `reports/m4-phase2-authorization-2026-10-07.json`). This note is committed BEFORE the first real
evaluation, so the method it describes cannot have been shaped by a result.** The results are in `docs/M4-PHASE2-RESULTS.md`, written afterwards. The frozen protocol
(`config/m4-protocol.json`, version 1, sha256 `a2e1a987528b7c84f479d79d17de7910b976380749c9d54065af7830547982a9`) is unchanged: nothing here is an amendment.

## 1. Scope

- **Targets:** the three B-clock primaries, `gap_ge_3pct` and `gap_ge_5pct` (binary) and `day1_close_return` (regression). The two C0-clock primaries (`extension_after_open_ge_5pct`,
  `loses_half_of_gap`) are Phase 3 and are refused on the real inputs: `REAL_EVALUATION_TARGETS` in `nre/m4_harness.py` lists the three and nothing else.
- **Versions:** every predictor in both `all_event` and `clean_window`, as the protocol requires.
- **Folds:** the two development folds only (test block 3 trained on blocks 1 and 2; test block 4 trained on blocks 1 to 3), pooled. The holdout, block 5, is sealed and not touched;
  `ALLOW_HOLDOUT_LOOK` stays `False` and the holdout access log keeps only its genesis record.

## 2. The predictors (all built to the protocol's words; `nre/m4_models.py`)

| Id | Target kind | What it is |
| --- | --- | --- |
| `C1_pooled_rate`, `C1_pooled_quantiles` | binary, regression | The comparator: the training rate, or the 10th, 50th and 90th percentiles (type 7) of the training values. Built in Phase 1. |
| `C2_timing_rate`, `C2_timing_quantiles` | binary, regression | The same within the event's release timing (after hours or premarket); the pooled value if the cell has fewer than 10 defined training events. |
| `C3_sector_group_rate`, `C3_sector_group_quantiles` | binary, regression | The same within the event's sector group (SIC division D, I, or other: B, E, F, G); same fallback. |
| `C4_issuer_history_rate` | binary | The issuer's own earlier outcomes on the same target, shrunk toward a group prior, used directly as the probability: (k + 10 p) / (n + 10). |
| `M2_logistic`, `M2_without_sector` | binary | Ridge-penalized logistic regression on `after_hours`, `is_I`, `is_other` and the logit of the issuer-history rate clipped to [0.01, 0.99]; without the two sector indicators for the sensitivity. Penalty 1 on every standardized coefficient but the intercept; Newton-Raphson from zero, converged when the largest coefficient change is below 1e-8, at most 100 iterations, otherwise `MODEL_FIT_FAILED`. |
| `M3_ridge_linear`, `M3_without_sector` | regression | Ridge linear regression (penalty 1, intercept unpenalized, closed form) on `after_hours`, `is_I`, `is_other` and the issuer-history mean; the quantile outputs are the fitted mean plus the 10th, 50th and 90th percentiles of the training residuals. |

There is no other feature. A predictor is handed the training events (with their labels) to fit, and for each test event a view without its labels or their digest.

## 3. One run

1. `Harness.from_repository` verifies the protocol and every pinned input; the folds are built and every leakage assertion is made (clusters whole, labels mature) before anything is fitted.
2. For each target, version and fold: if the fold's training events fail the fold-level threshold (10 positives and 10 negatives; 40 events for the regression) the fold is `INSUFFICIENT_DATA`
   for every predictor and is left out; otherwise every predictor is fitted on the training events with the target defined and predicts the test events with it defined. Predictions are rounded
   to 12 decimals. A predictor that cannot be fitted has state `MODEL_FIT_FAILED` or `INSUFFICIENT_DATA` and null predictions; nothing is substituted.
3. The folds that passed are pooled. If the pooled test events fail the thresholds (10 positives and 10 negatives; 20 events), the target and version are `INSUFFICIENT_DATA`: no metric is computed.
4. Metrics (Brier or mean pinball loss as the primary; log-loss, PR-AUC, precision at K with the seeded random ranking, reliability, false positives and negatives, terciles; interval coverage and
   the median's absolute error for the regression), pooled, by fold and by source.
5. Contrasts, each model minus comparator with a 5000-replicate cluster bootstrap over reaction sessions and over issuers (the wider interval is the headline) at 95% and 99%.
   **The one confirmatory contrast per target is the clean-window `M2_logistic` (or `M3_ridge_linear`) against C1;** its all-event contrast is its companion in the status rule; every other contrast is
   exploratory and labelled so: every predictor against C1; M2 against C2, C3, C4 and its without-sector sensitivity; M3 against C2, C3 and its sensitivity; and M2 or M3 against C1 in each fold.
6. The status of each target is `DISTINGUISHABLE_BETTER` only if the clean-window 99% headline interval lies entirely below zero and the all-event point estimate is below zero (`DISTINGUISHABLE_WORSE`
   the mirror image); `NOT_DISTINGUISHABLE` otherwise; `INSUFFICIENT_DATA` where the clean-window thresholds were not met. **No status is a claim of an edge.**
7. The whole evaluation runs twice from scratch and the two must be identical before anything is recorded. Every experiment (each predictor, fold and the pooled set) is then appended to the
   hash-chained experiment log, with the commit of the clean tree that produced it, and the results report and every prediction (as a protocol prediction record, all `MODEL_NOT_VALIDATED`,
   `NO_QUALIFIED_OPPORTUNITY`, `VERY_LOW`) are written.

## 4. The details this phase settled where the protocol is silent

Listed in `reports/m4-phase2-authorization-2026-10-07.json` before any real evaluation, outcome-independent, open to the owner's review. The ones that could move a result: standardization uses the
**population** standard deviation; **the ridge model leaves out the few earliest training rows that have no earlier matured event** (the protocol gives the regression history mean no default), counted and
logged, and they still serve as history; a training row's history features are **point-in-time inside the training set**; the **monotone repair** caps each M2 variant's 5% probability at its own 3% probability
(a missing 3% prediction makes the 5% model `MODEL_FIT_FAILED`). The rest: the optimizer's start and linear solver, rounding, which contrasts are reported, fallback counting, and the fact that the
without-sector sensitivities remove only the two indicators (the issuer feature's group prior still uses the SIC major group where at least 10 earlier events share it). The Phase 1 details
(`docs/M4-HARNESS.md`, section 5) are still in force.

## 5. What the structure audit found, before anything was evaluated

`reports/m4-phase2-structure-audit-2026-10-07.json` counts which labels are defined and reads no outcome value (a test changes every value and gets the identical audit). For all twelve combinations
of target, version and fold:

- **No baseline will fall back to the pooled value:** the smallest C2 or C3 cell holds 11 defined training events (premarket in clean-window fold 3; the "other" sector group has 12).
- **Every test event has an earlier matured event**, and every test event's issuer has an earlier matured event of its own, so no test event is left without a history mean.
- **Two or three training rows per fold have no earlier matured event** (the very first events): the ridge model leaves those out and nothing else changes.
- **No indicator feature is constant in training**, so no feature is dropped.

## 6. How it was checked

- Tests on synthetic data (`tests/test_m4_models.py`, `tests/test_m4_phase2.py`): the logistic fit against an independent Newton solver that uses Cramer's rule, and against the penalized
  optimality conditions (including nearly separable problems); the ridge fit against the normal equations; the cell baselines' fallback at 9, 10 and an unseen cell; the monotone repair with a binding
  cap, an empty cap and a missing event; the left-out rows; determinism; the guard on the real inputs; and `run()` in a temporary directory with its own logs, including its refusals (not authorized,
  dirty tree, outputs exist, logs beyond their genesis, two evaluations that differ).
- The mutation check (`scripts/m4_mutation_check.py`) now has 80 deliberate defects, 34 of them in the Phase 2 code; the tally is in `reports/m4-phase2-completion-2026-10-07.json`.

## 7. Running it

```
python -m nre.m4_phase2 audit [--output PATH]       # the structure audit; reads which labels are defined, never an outcome
python -m nre.m4_phase2 run --date YYYY-MM-DD       # the evaluation: needs ALLOW_REAL_EVALUATION, a clean committed tree, no earlier Phase 2 output and logs holding only their genesis
```

## 8. What it does not do

- It does not touch the holdout, run a C0 target, amend the protocol, add data, or accept Milestone 4. It makes no claim of a predictive edge; the protocol expects most primaries to be
  `NOT_DISTINGUISHABLE`.
- It is a convenience sample of 23 issuers on one market regime, with SIC codes read on 2026-09-26 and no execution data (the protocol's disclosed limits all apply).
