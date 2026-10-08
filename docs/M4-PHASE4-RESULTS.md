# Milestone 4 — Phase 4 results: what the one look at the holdout can and cannot tell

**Status: cross-checked against the committed files on 2026-10-07 (section 5); updated on 2026-10-08 for the owner's decisions about the replays.** The holdout (block 5, the 23 Milestone 1 events) was looked at once, on 2026-10-07 at 13:38:13Z, from a clean committed
tree at commit `0e26ac9`, under protocol version 1 and the method committed beforehand in `docs/M4-PHASE4.md` and `reports/m4-phase4-authorization-2026-10-07.json`. The real holdout access log holds its genesis record and
that one access. The tripwire was turned off again in the next commit (`85d3239`). The holdout alone creates no claim and no status, and none is given.

Results: `reports/m4-phase4-holdout-results-2026-10-07.json`; the 484 predictions: `reports/m4-phase4-holdout-predictions-2026-10-07.jsonl`; the descriptive report: `reports/m4-phase4-descriptive-2026-10-07.json`; 58
holdout experiment records were appended to `reports/m4-experiment-log.jsonl` (233 records in all).

## 1. The answer

The protocol stated the shape of this in advance (`disclosures.known_consequences_stated_in_advance`): in the holdout, `gap_ge_3pct`, `gap_ge_5pct` and `loses_half_of_gap` have 3 to 5 positives in both versions and so
are `COUNTS_ONLY`, while `extension_after_open_ge_5pct` and `day1_close_return` meet their thresholds. That is what the look showed. The counts were not hidden from the protocol's author either: the protocol records
(`holdout.not_blind_to_counts`) that the descriptive counts of block-5 outcomes were visible in the scoping evidence before the freeze.

| Target | Version | Events | Positives | Base rate (Wilson 95%) | State |
| --- | --- | --- | --- | --- | --- |
| `gap_ge_3pct` | clean-window | 21 | 4 | 19% (8% to 40%) | `COUNTS_ONLY` |
| `gap_ge_3pct` | all-event | 23 | 5 | 22% (10% to 42%) | `COUNTS_ONLY` |
| `gap_ge_5pct` | clean-window | 21 | 4 | 19% (8% to 40%) | `COUNTS_ONLY` |
| `gap_ge_5pct` | all-event | 23 | 5 | 22% (10% to 42%) | `COUNTS_ONLY` |
| `extension_after_open_ge_5pct` | clean-window | 21 | 10 | 48% (28% to 68%) | scored |
| `extension_after_open_ge_5pct` | all-event | 23 | 11 | 48% (29% to 67%) | scored |
| `loses_half_of_gap` | clean-window | 10 | 3 | 30% (11% to 60%) | `COUNTS_ONLY` |
| `loses_half_of_gap` | all-event | 12 | 3 | 25% (9% to 53%) | `COUNTS_ONLY` |
| `day1_close_return` | clean-window | 21 | not applicable (a return) | | scored |
| `day1_close_return` | all-event | 23 | not applicable (a return) | | scored |

The three `COUNTS_ONLY` targets get counts and nothing else: each predictor's entry says `COUNTS_ONLY` with its reason (for example "5 positives among 23 defined events (at least 10 needed)") and `predictions: null`.
Equal counts for the 3% and the 5% gap mean that no holdout event had a gap between the two. `loses_half_of_gap` is defined only for events with a positive gap of at least 0.5% (the protocol's eligibility rule): 12 of the 23
holdout events, 10 of 21 in the clean-window version.

The 23 holdout events come from 23 different issuers and fall in 16 reaction sessions (21 events and 15 sessions in the clean-window version), so the issuer clusters of the bootstrap are single events and the intervals are
wide. The protocol records that all 128 events come from 23 issuers (`disclosures.limits`), and the two development test blocks alone already contain all 23 (`issuers: 23` in the Phase 3 results), so the holdout is one new event from each issuer already present in the training blocks: new events, not new issuers.

For the two scored targets, the confirmatory model (M2 for the extension target, M3 for the Day-1 return) is set against the pooled base rate (C1). A difference is the model's score minus C1's, so **negative means the
model did better**. The protocol asks whether the holdout contrast has the sign of its development contrast.

| Target | Version | Events (positives) | C1 | Model | Difference | 95% interval | Development difference | Same direction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `extension_after_open_ge_5pct` (Brier) | clean-window | 21 (10) | 0.2517 | 0.2328 | -0.0189 | -0.0662 to +0.0282 | +0.0283 | no |
| `extension_after_open_ge_5pct` (Brier) | all-event | 23 (11) | 0.2543 | 0.2509 | -0.0034 | -0.0539 to +0.0492 | +0.0228 | no |
| `day1_close_return` (mean pinball loss) | clean-window | 21 | 0.03722 | 0.03593 | -0.00129 | -0.00546 to +0.00293 | +0.00048 | no |
| `day1_close_return` (mean pinball loss) | all-event | 23 | 0.03589 | 0.03507 | -0.00083 | -0.00452 to +0.00389 | +0.00042 | no |

In words: **the direction did not repeat.** In development the confirmatory model scored slightly worse than the base rate in all four cells; on the holdout it scored slightly better in all four. Every holdout
interval includes zero, and the development statuses were `NOT_DISTINGUISHABLE`, so neither direction can be told apart from no difference. The development statuses stand as they were: `NOT_DISTINGUISHABLE` for four
targets, `INSUFFICIENT_DATA` for `loses_half_of_gap`.

## 2. The other predictors (exploratory; none can support a claim)

Scores on the holdout, lower is better.

`extension_after_open_ge_5pct` (Brier)

| Predictor | clean-window | all-event |
| --- | --- | --- |
| C1 pooled rate | 0.2517 | 0.2543 |
| C2 timing rate | 0.2478 | 0.2500 |
| C3 sector-group rate | 0.2483 | 0.2531 |
| C4 issuer-history rate | 0.2302 | 0.2347 |
| M2 logistic (with the opening gap) | 0.2328 | 0.2509 |
| M2 without sector | 0.2308 | 0.2448 |

`day1_close_return` (mean pinball loss)

| Predictor | clean-window | all-event |
| --- | --- | --- |
| C1 pooled quantiles | 0.03722 | 0.03589 |
| C2 timing quantiles | 0.03493 | 0.03445 |
| C3 sector-group quantiles | 0.03736 | 0.03476 |
| M3 ridge | 0.03593 | 0.03507 |
| M3 without sector | 0.03570 | 0.03540 |

- Of the 18 contrasts against C1, the other predictor scored better than C1 in 17 (the exception is the sector-group quantiles in the clean-window Day-1 return, by 0.00014).
- **The order of the predictors moved between the samples.** On the holdout C1 had the highest (worst) Brier score of the six in both versions of the extension target and the highest loss in the all-event Day-1 return (second
  highest in the clean-window version, after the sector-group quantiles). In development the order had been different: on the extension target C1 had the lowest Brier score of the six in both versions (0.2450 clean-window,
  0.2433 all-event, against 0.2734 and 0.2662 for the confirmatory M2, which ranked fifth and fourth); on the Day-1 return the sector-group quantiles had the lowest loss in both versions and C1 ranked third of five.
- C1 predicts the training rate, so its holdout Brier score is the sample's p(1-p) plus the square of the miss between the holdout rate and the training rate. All-event: 11 of 23 (48%) on the holdout against 43 of 105
  (41%) in training gives 0.2495 + 0.0047 = 0.2543. Clean-window: 10 of 21 (48%) against 42 of 98 (43%) gives 0.2494 + 0.0023 = 0.2517. Both equal C1's reported scores; this is an identity, not a cause.
- The holdout has 32 contrasts (18 against C1, 14 among the models). One has a 95% interval that excludes zero: the timing-cell quantiles against C1 for the Day-1 return, clean-window version (-0.0023, 95% interval
  -0.00503 to -0.00004; the 99% interval, -0.00603 to +0.00051, includes zero). It is exploratory; its development counterpart was +0.00083 with an interval (-0.00061 to +0.00259) that spanned zero. None of the 32
  excludes zero at 99%. Thirty-two intervals at a nominal 5% error rate would put about 1.6 outside zero by chance alone, and these contrasts are not independent of one another.
- The lowest Brier score on the extension target is C4's (the issuer's own earlier outcomes) in both versions: 0.2302 and 0.2347. Its contrasts against C1 are -0.0215 (95% interval -0.0639 to +0.0256, clean-window) and
  -0.0195 (-0.0546 to +0.0180, all-event); both include zero. It is a description of one small sample, not a selection: nothing was selected for any use.
- Ranking and calibration say little at this size. Of the 24 precision-at-K values for the extension target (six predictors, two versions, K = 5 and 10), none lies outside the 2.5th to 97.5th percentile range of 1,000
  seeded random rankings of the same events (seed 410003). The reliability table has two bins; for M2 on all events (12 and 11 events) the mean predictions of 0.35 and 0.51 sit against observed rates of 0.42 and 0.55
  (Wilson 95% intervals 0.19 to 0.68 and 0.28 to 0.79).

## 3. What was checked

- **The look was replayed (on request).** `ReplayTests` (in `tests/test_m4_phase4_results.py`; opt-in, with `M4_REPLAY_HOLDOUT=1`) runs the whole look again through `Harness.look`, against temporary logs and a temporary copy of the development files, and compares the
  outputs with the committed ones: the results, the descriptive report and the predictions agree in structure and, in every number, to 1e-9; the experiment records agree in their identity fields (experiment, target,
  clock, predictor, version, fold, event-id hashes, state, commit, protocol hash).
- **Plain arithmetic agrees, with one limit.** The scores, contrasts and bootstrap intervals of both scored targets (5000 replicates; seed 410001 for reaction-session clusters, 410002 for issuer clusters; both levels)
  were recomputed from the stored predictions and the labels without the harness, to 9 decimal places, and the descriptive counts and their Wilson bounds were recomputed from all the events. For the extension target the
  predictions of C1 to C4 and the M2 fits were also recomputed from the training labels (training means and standard deviations to 1e-9, the penalized optimum to a gradient of 1e-7, the predictions to 1e-9). **For the
  Day-1 return the quantile and ridge predictions were not recomputed independently, here or in an earlier phase** (the independent check covers the binary targets, and Phase 2's covered scores, contrasts and
  intervals): they were reproduced by the replay and scored by the independent arithmetic.
- **The counts agree with the frozen protocol.** The all-event counts of defined events, positives and negatives of the 18 binary targets, block 5 included, equal the counts frozen in the protocol on 2026-10-06
  (`counts_at_freeze_all_event`): 18 of 18 equal. The Day-1 return is a regression label and has no such counts.
- **The logs.** Both hash chains verify (`m4_registry.verify_chain`): 233 experiment records and the holdout log's genesis plus one access (number 1, commit `0e26ac9`, 23 events read, the protocol's hash). The 175 experiment
  records present before the look are identical to the build commit's file; 58 were appended. The results record one access, no technical rerun, 46 label loads (23 events in each of the two versions) and no denied read.
- **Accesses, counted.** The look is access 1 in the chained log. On the owner's decision ("Count the replays as accesses.", 2026-10-07 at 19:14:34Z) the replays that re-read the block-5 outcomes to verify the look
  are counted too: eight runs found in the session transcript and the CI API when the decision was made (seven local runs of two accesses each, and CI run #232, whose two jobs, Python 3.12 and 3.13, each ran the
  replay tests: four), so 18 replay accesses and 19 accesses with the look; the closing whole-suite pass (two) and CI run #233 (four) were two more runs, so **25 accesses in all**
  (`reports/m4-phase4-replay-accesses-2026-10-07.json`; an earlier version of this note and of that record said 17 and 21 because it counted each CI run once, which the record's `corrections` entry explains). Since the owner's word of 2026-10-08
  ("make the replay tests opt-in") the replay tests are skipped unless `M4_REPLAY_HOLDOUT=1` is set, so routine runs and CI read nothing sealed; a run made on purpose is two more accesses, added to that record.
  The results file was written by the look and records its own single access and no technical rerun; it is not changed.
- **The evaluation was run twice from the look's events before anything was recorded; the two were identical** (`determinism.identical`).
- **The look's code was not changed after the look.** Between the build commit (`85fee6c`) and the commit of the outputs (`0e11dfc`) the only change under `nre/`, `config/` and `scripts/` is the comment on the tripwire
  constant, which is `False` at both ends. After that commit the only changes follow the owner's two decisions about the replays: the report assembler reads the replay accounting and its replay-test policy (it
  reads no label and depends on no holdout result), the replay tests are gated behind the switch, and the mutation check lists the defects of those changes.

## 4. What this does and does not tell us

- On 21 to 23 events from 23 issuers in one selection regime, the two scorable targets show no difference between the baselines and the pooled base rate that the sample can separate from zero, and the direction of the
  development result did not repeat. The protocol's own description of the holdout is "a replication check on direction and a single, logged exposure of the frozen pipeline to data it was not developed on; not a
  source of statistical power".
- Block 5 is entirely Milestone 1 events, "selected very differently from the rest (23 of 243 candidates kept, against 91% to 94% for steps 2 and 3)", in the protocol's words. It is also the latest block in time: its
  reaction sessions run from 2026-01-22 to 2026-04-01, block 4's from 2025-10-23 to 2025-12-11. Time and selection regime are confounded in it, and every holdout result carries that statement. The events are, again in
  the protocol's words, a convenience sample of 23 issuers, conditioned on survival to 2026 and on reviewability, not a market sample.
- The holdout is now spent. Any further evaluation on these 23 events is no longer a holdout evaluation, and another look would need the owner's go-ahead and would be counted. Nothing was selected, tuned or amended
  after the result was seen.
- Nothing here is Milestone 4 acceptance, a ranking or a recommendation. That decision is the owner's.

## 5. How this note was checked, and one open point

On 2026-10-07 every figure in sections 1 to 4 was compared with the committed files: the tables of sections 1 and 2 row by row, with a script that regenerates them from the results file (no difference); the states and
the counts with the protocol's `disclosures`; the development comparisons with `reports/m4-phase2-results-2026-10-07.json` and `reports/m4-phase3-results-2026-10-07.json`; the logs with `m4_registry.verify_chain` and with
`git show 85fee6c:reports/m4-experiment-log.jsonl`; the frozen counts with the descriptive report. The cross-check read no sealed label file: only committed outputs, the protocol, the logs and the test code.

It corrected my first draft in four places: the Brier identity for C1 (I had written 0.2495 + 0.0046 = 0.2541; it is 0.2495 + 0.0047 = 0.2543), the scope of the frozen-count comparison (the defined events of each
target, not 128 for every target), an account of why C1 scored worst that went further than the arithmetic supports (now only the identity above), and the reach of the independent recomputation, which I had described as
covering the M3 fits (it covers the binary targets; section 3).

**The open point of the first draft, settled by the owner.** The protocol says (`holdout.sealing`) "Every read of a block-5 outcome by the harness is logged to the holdout access log", and (`holdout.a_technical_rerun`) "Each rerun is a further
logged access, and the report states the number of accesses". The real access log holds one access and the results state no technical rerun. But `ReplayTests` reads the block-5 outcomes through `Harness.look` again each
time the class is set up: once for a full replay of the look and once more for a replayed look "for verification", with the access records going to temporary logs that are thrown away (a test checks that the real logs are
untouched). The suite has run since the look, locally and in CI, and the number of runs was not recorded at the time. These reads select, tune and change nothing and depend on no result, and nothing was decided from them,
but they are reads of the holdout that the real log does not count. The design had been disclosed before the look (P4-11: temporary logs, the real log untouched); it did not say the replays would be counted.

The owner decided on 2026-10-07 at 19:14:34Z: "Count the replays as accesses." They are counted in `reports/m4-phase4-replay-accesses-2026-10-07.json`, reconstructed from the session transcript and the CI API:
8 runs (7 local, 2 accesses each, and CI run #232 with two jobs, 4 accesses), 18 replay accesses and 19 accesses in all with the look when the decision was made. The closing whole-suite pass (2) and CI run #233
(4, two jobs again) were two more runs: 25 accesses in all. The first version of this note said 17 and 21: it counted each CI run once, but the workflow's matrix runs the whole suite in two jobs and both ran the replay
tests; this was found on 2026-10-08 and is corrected here and in the record. The chained access log is unchanged and still holds the look only. The Milestone 4 report states the 25 and leaves the protocol's
criterion "the holdout was looked at once" to the owner to judge.

Whether the replays should keep running automatically or only on request was offered with that decision and not chosen then. The owner decided it on 2026-10-08 at 06:47:34Z: "make the replay tests opt-in". `ReplayTests`
are skipped unless the environment variable `M4_REPLAY_HOLDOUT` is exactly `1`; the default suite and CI skip them and read nothing sealed. A run made on purpose (`M4_REPLAY_HOLDOUT=1 python -m unittest
tests.test_m4_phase4_results.ReplayTests`) is still two counted accesses and is added to the accounting record when it is made. Making them opt-in did not run them, so the count is unchanged.

Not authorized and not done: a second look, any selection or amendment, Milestone 5 and later, declaring Milestone 4 accepted.
