# Milestone 4 — Phase 2 results: what the development folds can and cannot tell

**Status: run 2026-10-07 from a clean committed tree at commit `595736b`, under protocol version 1 and the method committed beforehand in `docs/M4-PHASE2.md` and
`reports/m4-phase2-authorization-2026-10-07.json`. The answer for all three primary targets is `NOT_DISTINGUISHABLE`. No status here is a claim of a tradable or production-ready edge, the
holdout (block 5) was not touched, and the C0-clock targets were not run.** Results: `reports/m4-phase2-results-2026-10-07.json`; every prediction:
`reports/m4-phase2-predictions-2026-10-07.jsonl`; every experiment: `reports/m4-experiment-log.jsonl` (102 records after the genesis); the closing record: `reports/m4-phase2-completion-2026-10-07.json`.

## 1. The answer

Each primary target is evaluated on the pooled out-of-fold predictions of the two development folds: 44 events in the all-event version and 43 in the clean-window version, from 23 issuers
on 22 reaction sessions, all from Milestone 2 step 2. The logistic model (M2) for the two gap targets and the ridge model (M3) for the Day-1 return are each compared with the pooled
base rate (C1). A difference is the model's score minus C1's, so **negative means the model did better**; a status needs the 99% interval to lie entirely on one side of zero.

| Target | Version | Events (positives) | C1 | Model | Difference | 95% interval | 99% interval | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gap_ge_3pct` (Brier) | clean-window, the confirmatory contrast | 43 (14) | 0.2214 | 0.2187 | -0.0027 | -0.0204 to +0.0226 | -0.0259 to +0.0329 | `NOT_DISTINGUISHABLE` |
| | all-event, its companion | 44 (14) | 0.2185 | 0.2084 | -0.0101 | -0.0292 to +0.0168 | -0.0347 to +0.0276 | |
| `gap_ge_5pct` (Brier) | clean-window | 43 (10) | 0.1787 | 0.1944 | +0.0157 | -0.0144 to +0.0431 | -0.0255 to +0.0525 | `NOT_DISTINGUISHABLE` |
| | all-event | 44 (10) | 0.1757 | 0.1818 | +0.0062 | -0.0156 to +0.0286 | -0.0233 to +0.0381 | |
| `day1_close_return` (mean pinball loss) | clean-window | 43 | 0.03489 | 0.03537 | +0.00048 | -0.00248 to +0.00399 | -0.00331 to +0.00507 | `NOT_DISTINGUISHABLE` |
| | all-event | 44 | 0.03440 | 0.03482 | +0.00042 | -0.00299 to +0.00464 | -0.00375 to +0.00597 | |

In words: with 44 events, a difference in Brier score of a few hundredths cannot be told from zero (the 99% intervals reach 0.02 to 0.05 on either side), and the models' point estimates differ from the
base rate by less than half of that, in either direction. The development folds are too small to separate a logistic or ridge model from the pooled base rate. That is the outcome the protocol said to expect.

For scale: the base rate of a 3% opening gap is about one event in three (14 of 44 in the pooled test events; the training folds used 34% and 35%), a 5% gap about one in four (10 of 44; the training folds 23%), and
the Day-1 close return has a median of about -3% with an 80% band of about -18% to +16%, so the median forecast is off by about 10 percentage points on average (its mean absolute error is 0.10).

## 2. The other baselines (exploratory: reported with their intervals, none can support a claim)

Scores, lower is better (clean-window version; the all-event version is in the results file and tells the same story):

| Predictor | `gap_ge_3pct` | `gap_ge_5pct` | | Predictor | `day1_close_return` |
| --- | --- | --- | --- | --- | --- |
| C1 pooled rate | 0.2214 | 0.1787 | | C1 pooled quantiles | 0.03489 |
| C2 timing rate | 0.2279 | 0.1814 | | C2 timing quantiles | 0.03573 |
| C3 sector-group rate | 0.2145 | 0.1929 | | C3 sector-group quantiles | 0.03456 |
| C4 issuer-history rate | 0.2117 | 0.1779 | | M3 ridge | 0.03537 |
| M2 logistic | 0.2187 | 0.1944 | | M3 without sector | 0.03461 |
| M2 without sector | 0.2235 | 0.1815 | | | |

- **No pooled contrast of the 50 reported (every predictor against C1, the pairs the protocol lists, in both versions and for all three targets) has a 95% or a 99% interval that excludes zero.**
- On the 3% gap the point estimates lean toward the sector-group and issuer-history information (C3, C4 and M2 all score better than C1, by 0.003 to 0.014 across the two versions; the timing rate is worse), but
  the data cannot tell that from noise. On the 5% gap C4 is marginally better (by 0.001 clean-window, 0.006 all-event) while M2 and the sector rate are worse. On the Day-1 return no predictor differs from C1 by more than about 2.5% of its loss.
- Of the 12 per-fold contrasts (M2 or M3 against C1 in each development fold), two have a 95% interval that excludes zero: M2 better on the 3% gap in fold 3 (all-event: -0.031, interval -0.051 to -0.011, 21 events) and
  M2 worse on the 5% gap in fold 4 (clean-window: +0.032, interval +0.002 to +0.066, 23 events). About 0.6 of 12 would be expected by chance alone, they point in opposite directions, and each rests on 20 to 23 events.
- Of the 48 pooled precision-at-K values, 2 lie outside the range of 1,000 seeded random rankings, both the issuer-history rate (C4) at K = 20 on the 3% gap (0.50 against a random 95% range of 0.15 to 0.45), in both versions: about what chance gives
  for 48 values, and essentially one finding seen in two versions.

## 3. What was checked

- The pooled scores, the contrasts and the confirmatory bootstrap intervals were recomputed from the predictions file and the development labels with plain arithmetic, separately from the harness: 40 quantities, no difference. A test now does this on every run, and
  another runs the whole evaluation again from the committed inputs and compares it with the committed results.
- The evaluation was run twice from scratch before anything was recorded; the two were identical.
- All 16 logistic fits converged, in 4 to 6 iterations. No cell baseline fell back to the pooled value. The ridge model left out the three earliest training events (two in the clean-window version), which have no earlier event to learn from, as the structure audit had
  predicted. The monotone repair was used once (M2, 5% gap, clean-window, fold 3, one event).
- The experiment log holds the 102 experiments after its genesis, each naming the commit of the clean tree that produced it; the chain verifies. The holdout: 23 events sealed, no refused read, no load, and its access log still holds only its genesis record.

## 4. What this does and does not tell us

- It tells us that on 44 events from 23 issuers on one market regime, none of three kinds of cheap information (release timing, sector group, the issuer's own earlier outcomes), alone or combined in a regularized model, can be separated from the pooled base rate for
  a 3% gap, a 5% gap or the Day-1 return. It does not tell us they carry no information: the intervals are wide relative to any plausible difference.
- It does not tell us anything about a market. The events are a convenience sample (23 issuers conditioned on survival to 2026 and on reviewability), the folds are two, the SIC codes were read on 2026-09-26 and not as of the event dates, and the intervals reflect the finite test sample
  and its clustering, not the variability of the fitted models across training sets.
- Nothing here is Milestone 4 acceptance, a ranking or a recommendation. The protocol expected most primaries to be `NOT_DISTINGUISHABLE` and the holdout to support counts only for several targets; both stand.
- Still to do, none authorized: Phase 3 (the two C0-clock targets) and Phase 4 (the one look at the holdout, the descriptive report with block-5 counts, and the Milestone 4 report).
