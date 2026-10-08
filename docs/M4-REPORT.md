# Milestone 4 — Baseline predictive models: the report

**Status: evidence, not a decision.** Written 2026-10-08 from the committed artifacts. Whether Milestone 4 is accepted is the owner's decision, as the protocol says; nothing here declares it. The owner then declared it accepted ("accepted", 2026-10-08T07:31:38Z;
[declaration](../reports/m4-acceptance-declaration-2026-10-08.json)); this report is the evidence they decided on, and is otherwise unchanged. The data
form of this report is `reports/m4-report-2026-10-07.json` (`python -m nre.m4_report build --date 2026-10-07`), assembled by code from the committed results and records; it reads no label. The protocol
(`config/m4-protocol.json`, version 1, sha256 `a2e1a987528b7c84f479d79d17de7910b976380749c9d54065af7830547982a9`) was frozen on 2026-10-06 at 14:45:11Z, before any evaluation, and has never been amended.

## 1. The short answer

- **No predictor could be told apart from the pooled base rate.** Four of the five primary targets are `NOT_DISTINGUISHABLE`; the fifth, `loses_half_of_gap`, is `INSUFFICIENT_DATA` (its clean-window
  version has 9 training positives in one fold where 10 are needed). None of the 77 pooled development contrasts has an interval that excludes zero, at 95% or at 99%. The 99% level is the one a claim
  would need.
- **The protocol said to expect this.** In its words: "For most targets the result is expected to be NOT_DISTINGUISHABLE from the pooled base rate, and the final holdout is expected to support counts
  only for most targets. Both are acceptable, reportable outcomes of this protocol." It also says the report does not require that any predictor beats the base rate.
- **The holdout (block 5, the 23 Milestone 1 events) was evaluated once, in one logged look.** Three primary targets had too few positives to score and are counts only, as the protocol predicted. For the two that were
  scored, the confirmatory model did slightly better than the base rate on the holdout where it had done slightly worse in development: the direction did not repeat, and every interval includes zero.
  One of the 32 holdout contrasts (an exploratory one) has a 95% interval that excludes zero (none does at 99%); about 1.6 of 32 would by chance alone. No claim comes out of the holdout.
- **What this does not mean.** It is not a finding that nothing predicts the reaction to an earnings release. 128 events from 23 issuers in one market regime cannot show that, and the intervals are wide.
  It is also not evidence about any market: the events are a convenience sample.
- **The holdout was read more than once, and the owner decided to count that.** The look is one access in the hash-chained log. The tests that replay it to verify it re-read the same outcomes
  through the same gate; on the owner's decision of 2026-10-07 ("Count the replays as accesses.") those are counted too: **25 accesses in all** (section 7). Since 2026-10-08 ("make the replay tests
  opt-in") they run only on request, so routine runs and CI read nothing sealed. Whether the 25 still satisfy the protocol's "the holdout was looked at once" is left to the owner (section 9).

## 2. What was done

Five phases, each authorized in the owner's words before it started, each ending in a closing record. The protocol, the harness and the tripwires came before any evaluation; the holdout stayed sealed
until the last phase.

| Phase | Owner's words | What | Commits | Suite tests | Mutation defects caught |
| --- | --- | --- | --- | --- | --- |
| 0 | document-only phase authorized (`reports/m4-phase0-authorization-2026-10-03.json`) | the protocol: targets, folds, holdout, metrics, caveat rule, INSUFFICIENT_DATA thresholds, frozen and hashed | `7dc900b` | | |
| 1 | "okay authorize Phase 1" | the evaluation harness, its eight leakage and integrity tests, the sealed holdout, the hash-chained logs, the pooled base rate C1; synthetic data and dry runs only | `a1f6c2c`, `200a4ea` | 742 | 45 |
| 2 | "authorize phase 2" | the baselines C2 to C4, the logistic model M2 and the ridge model M3 on the three B-clock targets, development folds only | `b1549c9`, `595736b`, `304c783`, `5d50813` | 835 | 80 |
| 3 | "authorize phase 3" | the same predictors on the two C0-clock targets (M2 also taking the opening gap), development folds only | `2080e01`, `14e3e1d`, `50086ed`, `350f7da` | 896 | 101 |
| 4 | "authorize phase 4" | the one look at the holdout, the descriptive report with block-5 counts, and this report; then, on later words, counting the replays, the closing work, and making the replay tests opt-in | `40e1744`, `85fee6c`, `0e26ac9`, `85d3239`, `0e11dfc`, `c4a524d`, `0bcdeac` and the opt-in commit | 1,000 at the closing pass | 142 |

The data: 128 accepted events from 23 issuers in 73 reaction sessions, cut into five time blocks of 17, 44, 21, 23 and 23 events. The two development folds test on block 3 (training on blocks 1 and 2) and on
block 4 (training on blocks 1 to 3); the holdout fold tests on block 5 (training on blocks 1 to 4). Every result is computed twice: `all_event` (every label as recorded) and `clean_window` (labels the
events' recorded caveats name are treated as absent), and the clean-window version drives any status. There are 19 targets: five primary and 14 reported with counts only.

## 3. The five primary targets

How to read the tables: a **difference** is the confirmatory model's score minus the comparator's (C1, the pooled base rate, or the pooled quantiles for the return), and lower scores are better, so
**negative means the model did better**. Scores are the Brier score for yes/no targets and the mean pinball loss for the return. Development intervals are at the 99% level the protocol uses for a claim; holdout
intervals are at 95%, because the holdout alone never creates a claim. Events are in parentheses.

| Target | Version | Development: model minus C1, 99% interval (events) | Holdout: model minus C1, 95% interval (events) |
| --- | --- | --- | --- |
| `gap_ge_3pct` | clean-window | -0.0027 (-0.0259 to +0.0329) (43) | counts only: 4 of 21 events |
| `gap_ge_3pct` | all-event | -0.0101 (-0.0347 to +0.0276) (44) | counts only: 5 of 23 events |
| `gap_ge_5pct` | clean-window | +0.0157 (-0.0255 to +0.0525) (43) | counts only: 4 of 21 events |
| `gap_ge_5pct` | all-event | +0.0062 (-0.0233 to +0.0381) (44) | counts only: 5 of 23 events |
| `extension_after_open_ge_5pct` | clean-window | +0.0283 (-0.0345 to +0.0885) (43) | -0.0189 (-0.0662 to +0.0282) (21) |
| `extension_after_open_ge_5pct` | all-event | +0.0228 (-0.0436 to +0.0911) (44) | -0.0034 (-0.0539 to +0.0492) (23) |
| `loses_half_of_gap` | clean-window | not evaluated: 5 positives among 10 defined events (at least 10 needed) | counts only: 3 of 10 events |
| `loses_half_of_gap` | all-event | +0.0581 (-0.0547 to +0.1734) (23) | counts only: 3 of 12 events |
| `day1_close_return` | clean-window | +0.00048 (-0.00331 to +0.00507) (43) | -0.00129 (-0.00546 to +0.00293) (21) |
| `day1_close_return` | all-event | +0.00042 (-0.00375 to +0.00597) (44) | -0.00083 (-0.00452 to +0.00389) (23) |

The development status of each primary target (it follows from the clean-window version):

| Target | Confirmatory model | Comparator | Development status |
| --- | --- | --- | --- |
| `gap_ge_3pct` | M2_logistic | C1_pooled_rate | `NOT_DISTINGUISHABLE` |
| `gap_ge_5pct` | M2_logistic | C1_pooled_rate | `NOT_DISTINGUISHABLE` |
| `extension_after_open_ge_5pct` | M2_logistic | C1_pooled_rate | `NOT_DISTINGUISHABLE` |
| `loses_half_of_gap` | M2_logistic | C1_pooled_rate | `INSUFFICIENT_DATA` |
| `day1_close_return` | M3_ridge_linear | C1_pooled_quantiles | `NOT_DISTINGUISHABLE` |

What the tables show:

- **Development:** every interval includes zero. In 7 of the 9 evaluated development cells the model scored slightly worse than the base rate, in 2 slightly better. The 18 per-fold development contrasts (reported for transparency, not
  for claims) include 2 whose 95% interval excludes zero.
- **Holdout:** `gap_ge_3pct`, `gap_ge_5pct` and `loses_half_of_gap` have 3 to 5 positives and are counts only. For `extension_after_open_ge_5pct` and `day1_close_return` the sign of the holdout difference is
  the opposite of the development one in all four cells, and every interval includes zero. That is a statement about direction only; neither sample can separate it from no difference.
- The details of the holdout, including every other predictor's score, are in `docs/M4-PHASE4-RESULTS.md`.

## 4. The other 14 targets

They are reported with counts, base rates and Wilson 95% intervals, and nothing is modelled for them: nine are descriptive only, five have too few positives by the protocol's rule. The bucket
is the protocol's reading of how much the count can support (the five regression labels are described in `reports/m4-report-2026-10-07.json`, section `regression_labels`).

| Target | Role | Defined events | Positives | Base rate (Wilson 95%) | Bucket | Positives by block 1 to 5 |
| --- | --- | --- | --- | --- | --- | --- |
| `gap_ge_10pct` | descriptive only | 128 | 14 | 11% (7% to 18%) | thin | 2, 3, 2, 4, 3 |
| `day1_high_ge_10pct` | descriptive only | 128 | 33 | 26% (19% to 34%) | estimable with wide uncertainty | 5, 11, 5, 7, 5 |
| `day1_high_ge_20pct` | descriptive only | 128 | 12 | 9% (5% to 16%) | thin | 3, 4, 2, 2, 1 |
| `day1_close_ge_10pct` | descriptive only | 128 | 22 | 17% (12% to 25%) | thin | 3, 7, 4, 5, 3 |
| `extension_after_open_ge_10pct` | descriptive only | 128 | 23 | 18% (12% to 26%) | thin | 4, 9, 2, 6, 2 |
| `session5_close_ge_10pct` | descriptive only | 128 | 27 | 21% (15% to 29%) | thin | 3, 9, 4, 4, 7 |
| `session5_close_ge_20pct` | descriptive only | 128 | 16 | 12% (8% to 19%) | thin | 3, 5, 3, 2, 3 |
| `full_gap_fill` | descriptive only | 60 | 28 | 47% (35% to 59%) | thin | 3, 6, 7, 4, 8 |
| `closes_below_open` | descriptive only | 128 | 72 | 56% (48% to 65%) | estimable with wide uncertainty | 11, 24, 13, 12, 12 |
| `gap_ge_15pct` | insufficient data by rule | 128 | 5 | 4% (2% to 9%) | insufficient | 0, 1, 1, 2, 1 |
| `gap_ge_20pct` | insufficient data by rule | 128 | 3 | 2% (1% to 7%) | insufficient | 0, 0, 1, 1, 1 |
| `gap_ge_30pct` | insufficient data by rule | 128 | 0 | 0% (0% to 3%) | insufficient | 0, 0, 0, 0, 0 |
| `day1_high_ge_30pct` | insufficient data by rule | 128 | 5 | 4% (2% to 9%) | insufficient | 1, 1, 2, 1, 0 |
| `day1_close_ge_20pct` | insufficient data by rule | 128 | 6 | 5% (2% to 10%) | insufficient | 2, 1, 1, 1, 1 |

## 5. What could be estimated and what could not

- **Development:** 9 of the 10 target-by-version cells were evaluated. The tenth, `loses_half_of_gap` in the clean-window version, is `INSUFFICIENT_DATA`: 5 positives among 10 defined events in the pooled test
  set where 10 are needed, and 9 training positives in fold 3. Its all-event results are exploratory.
- **Holdout:** 4 cells were scored (`extension_after_open_ge_5pct` and `day1_close_return`, both versions) and 6 are counts only (`gap_ge_3pct`, `gap_ge_5pct`, `loses_half_of_gap`, both versions).
- **Not modelled:** 14 targets, by design.
- **What the intervals cover:** "uncertainty from the finite test sample and its clustering; it does not cover variability of the fitted models across training sets".
- **What no number here can establish:** stability across market regimes (one regime in the span), performance after execution costs (no execution data), high-confidence precision (no validated confidence threshold).

## 6. How it was checked

- **Frozen first, never amended:** the protocol's hash is pinned in a freeze record and checked by every run; the first experiment record is later than the freeze; the list of amendments is empty.
- **The protocol's eight leakage and integrity tests** are implemented in `tests/test_m4_harness.py` and run in every phase: label maturity, an injected future that changes no earlier prediction, history
  features that use only training-block events, holdout sealing, protocol integrity, determinism, clusters never split between training and test, and abstention (`INSUFFICIENT_DATA` and
  `MODEL_FIT_FAILED` give null predictions with reasons, never substitutes).
- **The test suite grew with each phase:** 742, 835, 896 and 1,000 tests, each phase closing with a full pass and the real exit status. It has 1,011 tests now; nine of them,
  the replay tests, are skipped unless asked for.
- **A mutation check:** the script `scripts/m4_mutation_check.py` makes one deliberate defect at a time in a copy of the code (history that ignores the earlier-session rule, a reversed contrast sign, a predictor
  shown the labels, a counted replay left out of the total, and so on) and requires the tests to fail. The list grew to 45, 80, 101 and 142 defects over the four phases (138 when Phase 4 closed; the four added with the opt-in change were
  run together with the report defects that change touched), and each phase's closing run caught all of them (in Phases 1 and 2 a few were not caught on a first run, and tests were added until they were; those closing records list them).
- **Deterministic:** each phase's evaluation was run twice from scratch before anything was recorded, and the two were identical; tests re-run each phase from the committed inputs and compare with the
  committed results (the holdout by replaying the look through the same gate against temporary logs: a test that runs only on request, last run on purpose at the closing pass).
- **Independent arithmetic:** the pooled scores, contrasts and bootstrap intervals were recomputed from the predictions and labels without the harness in Phase 2 (40 quantities) and Phase 3 (45 quantities and 48
  sets of predictions and fits), with no problems. In Phase 4 the tests recompute the scores, contrasts and intervals of both scored targets, and the C1 to C4 predictions and the M2 fits of the extension target. **The
  Day-1 return's quantile and ridge predictions were never recomputed independently, in any phase**; they were reproduced by the replay and scored by the independent arithmetic.
- **The holdout was sealed:** no predictor was fitted or scored on a block-5 outcome before the look; every read goes through a gate that writes the hash-chained access record first; the tripwire that allows
  a look was turned on in a commit of its own and off again in the next; a dress rehearsal on the real inputs with the real block-5 files destroyed and synthetic labels behind the gate came first. The
  experiment log (233 records) and the access log (its genesis and one access) both verify.
- **The cross-check of the results note** (`docs/M4-PHASE4-RESULTS.md`) against the committed files found four mistakes in its first draft; they are corrected and listed there.

## 7. How often the holdout was read

| What | Accesses | Where it is recorded |
| --- | --- | --- |
| The look, 2026-10-07 at 13:38:13Z, commit `0e26ac9`: 23 events, 46 loads, none denied | 1 | the hash-chained access log, written before the outcomes were read |
| Replay runs found in the session transcript and the CI API when the owner decided to count them: seven local runs (two accesses each) and CI run #232 (four: its two jobs each ran them) | 18 | `reports/m4-phase4-replay-accesses-2026-10-07.json` |
| The closing whole-suite pass (two) and CI run #233 of the closing push (four) | 6 | the same record |
| **In all** | **25** | |

The replays read the outcomes to reproduce the look and compare it with the committed outputs; they select, tune and change nothing, and nothing was decided from them. The protocol says every read of a
block-5 outcome is logged and that the report states the number of accesses; the owner decided to count the replays, and this is the number. The replay design had been disclosed before the look (it
touches temporary logs only) but not that it would be counted. The count is a lower bound: it rests on the session transcript and the CI API.

**A correction.** The first version of this report said 21 accesses. It counted each CI run once, but the workflow's matrix runs the whole suite in two jobs (Python 3.12 and 3.13) and both ran the replay tests in
CI runs #232 and #233, so each was four accesses, not two. This was found on 2026-10-08 when the jobs of a CI run were read; the accounting record's `corrections` entry has the details.

Since the owner's word of 2026-10-08, "make the replay tests opt-in", the replay tests are skipped unless the environment variable `M4_REPLAY_HOLDOUT` is exactly `1`. The default suite and CI read nothing
sealed, so a push no longer adds accesses. A run made on purpose (`M4_REPLAY_HOLDOUT=1 python -m unittest tests.test_m4_phase4_results.ReplayTests`) is still two counted accesses, added to the record when it is
made (a CI run with the switch set would be two for each job of the matrix). Making them opt-in did not run them, so the count stands at 25.

## 8. Limits

From the protocol's disclosures:

- A convenience sample of 23 issuers, conditioned on survival to 2026 and on reviewability; not a market sample, and no base rate here is a market base rate.
- SIC codes read on 2026-09-26, not as of the event dates.
- Time and selection regime are confounded in block 5: it is entirely Milestone 1 events, "selected very differently from the rest (23 of 243 candidates kept, against 91% to 94% for steps 2 and 3)", and
  it is the latest block in time. Every holdout result carries that statement.
- Events share 73 reaction sessions and come from 23 issuers; intervals are cluster-aware but remain approximate at these sizes. The holdout is one new event from each issuer already in the training blocks:
  new events, not new issuers.
- One market regime in the span; no execution data.
- Rare large moves (gaps of 15% and more) are out of reach of this dataset; it contains earnings releases only.

## 9. The protocol's eight acceptance criteria

The protocol lists what makes the report acceptable. The column says whether the evidence meets each one; the decision is the owner's.

| # | Criterion | Met by the evidence |
| --- | --- | --- |
| 1 | this protocol was frozen before evaluation | yes |
| 2 | the integrity tests above pass | yes |
| 3 | every output reproduces deterministically from committed inputs | yes |
| 4 | every target is reported with counts and cluster-aware intervals or as INSUFFICIENT_DATA | yes |
| 5 | every predictor is compared with the pooled comparator C1 and, for binary targets, the seeded random ranking, clean-window and all-event side by side | yes |
| 6 | calibration is shown with coarse bins and their counts | yes |
| 7 | the holdout was looked at once | **for the owner to judge** |
| 8 | the limits are stated | yes |

Seven are met by the evidence. The seventh, "the holdout was looked at once", is marked for the owner to judge: the evaluation look was one and is the only access in the chained log, but counting
the replays the holdout's outcomes were read 25 times, and the protocol says reruns are further accesses that the report states. The facts are in section 7; the judgment is not made here. The owner then declared Milestone 4 accepted without singling that criterion out; the declaration records how the word was read
(`reports/m4-acceptance-declaration-2026-10-08.json`), and this report, being evidence, still marks the criterion for the owner to judge.

## 10. Open for the owner

Decided since this report was first written, so no longer open: the replay tests are opt-in (section 7), and Milestone 4 is accepted (`reports/m4-acceptance-declaration-2026-10-08.json`; "accepted",
2026-10-08T07:31:38Z).

1. **Criterion 7** (section 9), which the acceptance is read as covering.
2. **The four review items the protocol flagged**, still unanswered, defaults in force:
   - whether the two thin primaries (`gap_ge_5pct` with 29 positives, `loses_half_of_gap` with 25) belong among the primaries;
   - the 99% claim level, which makes any claim very hard at these sample sizes;
   - that the holdout would mostly be counts only (it was);
   - the issuer-history and sector features, given the point-in-time limits and small cells.
3. **Five protocol-silent details that could move a result**, listed in `docs/M4-HARNESS.md` section 5 with the defaults used: the headline interval is the wider of the two by width (reaction session on a tie);
   a regression history mean with no earlier event is a `ProtocolGap`, with no default; standardization of the model features uses the population standard deviation of the training events (the protocol does not say
   which; the list was written before the models existed, and they use the population one); a predictor that fails in one fold takes that state for its whole pooled result; the group prior obeys the same maturity and
   earlier-session rules as the issuer's own history. Changing any of them now would be a new protocol version, stated to follow results.
4. Parked, not part of Milestone 4 and not touched: a latent default `Calendar()` in `nre/alpaca.py`, noted in earlier sessions.

Not authorized and not done: a second evaluation look at the holdout, any selection or tuning after a holdout result, any protocol amendment, new data, Milestone 5 or later, any ranking, candidate list,
trading or backtest.

## 11. Where everything is

- The protocol and its freeze: `config/m4-protocol.json`, `reports/m4-protocol-freeze-2026-10-06.json`.
- The harness and the phases: `nre/m4_*.py`; the notes `docs/M4-HARNESS.md`, `docs/M4-PHASE2.md` to `docs/M4-PHASE4.md`; the results notes `docs/M4-PHASE2-RESULTS.md` to `docs/M4-PHASE4-RESULTS.md`.
- The results: `reports/m4-phase2-results-2026-10-07.json`, `reports/m4-phase3-results-2026-10-07.json`, `reports/m4-phase4-holdout-results-2026-10-07.json`,
  `reports/m4-phase4-descriptive-2026-10-07.json`, and the predictions files beside them.
- The two logs: `reports/m4-experiment-log.jsonl` (233 records) and `reports/m4-holdout-access-log.jsonl` (its genesis and the look).
- The accounting of the replays, and the opt-in switch: `reports/m4-phase4-replay-accesses-2026-10-07.json` (field `replay_tests_policy`); the replay tests themselves are `ReplayTests` in `tests/test_m4_phase4_results.py`.
- The authorizations and the closing records: `reports/m4-phase{1,2,3,4}-authorization-*.json` and `reports/m4-phase{1,2,3,4}-completion-*.json`.
- The owner's acceptance: `reports/m4-acceptance-declaration-2026-10-08.json`.
- This report as data: `reports/m4-report-2026-10-07.json`.

**This report does not declare Milestone 4 accepted; the owner's declaration is `reports/m4-acceptance-declaration-2026-10-08.json`.**
