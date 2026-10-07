# Milestone 4 — Phase 3 results: what the development folds can and cannot tell on the C0 clock

**Status: run 2026-10-07 from a clean committed tree at commit `14e3e1d`, under protocol version 1 and the method committed beforehand in `docs/M4-PHASE3.md` and
`reports/m4-phase3-authorization-2026-10-07.json`. `extension_after_open_ge_5pct` is `NOT_DISTINGUISHABLE`; `loses_half_of_gap` is `INSUFFICIENT_DATA`, as the protocol's thresholds said it would be. No
status here is a claim of a tradable or production-ready edge, and the holdout (block 5) was not touched.** Results: `reports/m4-phase3-results-2026-10-07.json`; every prediction:
`reports/m4-phase3-predictions-2026-10-07.jsonl`; every experiment: `reports/m4-experiment-log.jsonl` (72 more records, 174 after the genesis); the closing record: `reports/m4-phase3-completion-2026-10-07.json`.

## 1. The answer

The two C0-clock targets are decided at the regular open, when the opening gap is known, so the logistic model (M2) here also takes the opening gap. Each is evaluated on the pooled out-of-fold
predictions of the two development folds and compared with the pooled base rate (C1). A difference is the model's score minus C1's, so **negative means the model did better**; a status needs the 99%
interval to lie entirely on one side of zero.

| Target | Version | Events (positives) | C1 | M2 | Difference | 95% interval | 99% interval | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `extension_after_open_ge_5pct` (Brier) | clean-window, the confirmatory contrast | 43 (18) | 0.2450 | 0.2734 | +0.0283 | -0.0206 to +0.0752 | -0.0345 to +0.0885 | `NOT_DISTINGUISHABLE` |
| | all-event, its companion | 44 (18) | 0.2433 | 0.2662 | +0.0228 | -0.0288 to +0.0742 | -0.0436 to +0.0911 | |
| `loses_half_of_gap` (Brier) | clean-window | 10 (5) | not evaluated: 5 positives among 10 events, at least 10 needed | | | | | `INSUFFICIENT_DATA` |
| | all-event, exploratory | 23 (12) | 0.2612 | 0.3193 | +0.0581 | -0.0283 to +0.1500 | -0.0547 to +0.1734 | |

In words: on the extension target the model with the opening gap scored worse than the pooled base rate, by about a tenth of the score (0.023 to 0.028), but the 99% intervals reach from -0.03 or -0.04 below zero to +0.09 above it, so
the data cannot tell "somewhat better" from "somewhat worse"; the pooled test events are 44 (43), from 23 issuers on 22 reaction sessions. `loses_half_of_gap` has only 60 events at all (gaps of at least 0.5%): in
the clean-window version fold 3's training has 9 positives where 10 are needed, so only fold 4's 10 test events (5 and 5) are left, below the thresholds; the protocol gives no status then and none is given. Its
all-event version (23 events from 16 issuers on 13 sessions) was run and is exploratory: its M2 contrast is labelled so, with the reason.

For scale: about two events in five extend 5% above the open (the training folds 41% and 39%; the pooled test events 18 of 44), and about half of the gaps of at least 0.5% give back more than half of the gap (training
40% and 45%; test 12 of 23). The opening gap itself has a standard deviation of about 9 to 10 percentage points across all events and 4 to 5 among the gaps of at least 0.5%.

## 2. The other baselines (exploratory: reported with their intervals, none can support a claim)

Scores, lower is better:

| Predictor | `extension_after_open_ge_5pct`, clean-window | all-event | `loses_half_of_gap`, all-event |
| --- | --- | --- | --- |
| C1 pooled rate | 0.2450 | 0.2433 | 0.2612 |
| C2 timing rate | 0.2821 | 0.2722 | 0.2704 |
| C3 sector-group rate | 0.2491 | 0.2472 | 0.2758 |
| C4 issuer-history rate | 0.2563 | 0.2613 | 0.2539 |
| M2 logistic (with the opening gap) | 0.2734 | 0.2662 | 0.3193 |
| M2 without sector | 0.2731 | 0.2664 | 0.3063 |

- **No pooled contrast of the 27 reported (every predictor against C1, the pairs the protocol lists, in the three evaluable versions) has a 95% or a 99% interval that excludes zero, and none of the 6 per-fold contrasts has a 95% interval that excludes zero.**
- On the extension target the pooled base rate scores best of the six in both versions; the nearest, the sector-group rate, is 0.004 worse. The model that knows the opening gap did not beat the base rate: M2 is worse than C1 by
  0.023 to 0.028, and dropping its sector indicators changes nothing (-0.0003 and +0.0002).
- In all 12 fitted M2 models the opening gap's standardized coefficient is negative (a larger gap goes with a lower chance of extending 5% above the open, and with a lower chance of giving back half the gap): small for the
  extension target (-0.02 to -0.24 in log-odds per standard deviation of the gap, after the ridge penalty) and larger for `loses_half_of_gap` (-0.33 to -0.61), and not stable in size between the two folds. That describes the fitted models, not the held-out
  events, where the score is no better than the base rate's.
- On `loses_half_of_gap` (all-event) only C4, the issuer-history rate, scores better than C1, by 0.007 (99% interval -0.035 to +0.021); M2 is the worst of the six, which is not surprising for a five-feature model fitted on 25 to 38 events.
  C4's PR-AUC of 0.72 is the highest of the PR-AUC values reported, on 23 events with 12 positives; it is not part of the decision rule, and the Brier score of the same predictor is only marginally better than C1's.
- Of the 30 pooled precision-at-K values (K = 10 and 20 for the extension target; only K = 10 for `loses_half_of_gap`, whose 23 events are below the protocol's 2K rule for K = 20), none lies outside the range of 1,000 seeded random rankings.

## 3. What was checked

- The pooled scores, the contrasts and the bootstrap intervals were recomputed from the predictions file and the development labels with plain arithmetic, separately from the harness: 45 quantities, no difference. For this phase
  the predictions themselves were recomputed too: C1, C2, C3 and C4 rebuilt from the training events' labels, and for each M2 fit the training means and standard deviations rebuilt, the stored coefficients checked against the
  penalized optimality conditions (the largest gradient component is below 1e-7), and the predictions recomputed from the stored parameters: 48 checks, no difference. The same check also reproduces Phase 2's committed predictions
  and fits (64 checks, no difference). Tests now repeat both recomputations on every run (`tests/m4_independent.py`, used by the Phase 2 and Phase 3 results tests), and another runs the whole evaluation again from the
  committed inputs and compares it with the committed results.
- The evaluation was run twice from scratch before anything was recorded; the two were identical.
- All 12 logistic fits converged, in 4 to 6 iterations. No cell baseline fell back to the pooled value for the extension target. For `loses_half_of_gap` (all-event) fold 3, C2 fell back for 5 of 13 test events and C3 for 8 of 13, and in both
  folds 2 test events had no earlier event of their own issuer (C4 then uses the group or pooled prior alone), exactly as the structure audit had counted before anything was evaluated.
- The experiment log holds the 72 new experiments after Phase 2's 102, each naming the commit of the clean tree that produced it; 18 of them (the clean-window `loses_half_of_gap` version) are recorded as `INSUFFICIENT_DATA` with no predictions.
  The chain verifies. The holdout: 23 events sealed, no refused read, no load, and its access log still holds only its genesis record.

## 4. What this does and does not tell us

- It tells us that on 44 events from 23 issuers on one market regime, neither release timing, sector group, the issuer's own earlier outcomes, nor a regularized model that also knows the opening gap can be separated from the pooled
  base rate for a 5% extension above the open. It does not tell us the opening gap carries no information: the intervals are wide, and a five-feature model fitted on 55 to 82 events has more ways to be wrong than to help.
- For giving back half the gap the protocol's own thresholds leave the claim rule inapplicable, and the all-event results rest on 23 events; they are a description, not evidence.
- It does not tell us anything about a market. The events are a convenience sample (23 issuers conditioned on survival to 2026 and on reviewability), the folds are two, the SIC codes were read on 2026-09-26 and not as of the event dates, and
  the intervals reflect the finite test sample and its clustering, not the variability of the fitted models across training sets.
- Nothing here is Milestone 4 acceptance, a ranking or a recommendation. With Phase 2, all four primary targets that could be evaluated are `NOT_DISTINGUISHABLE` and the fifth is `INSUFFICIENT_DATA`; the protocol expected most primaries to be like that.
- Still to do, none authorized: Phase 4 (the one look at the holdout, the descriptive report with block-5 counts, and the Milestone 4 report).
