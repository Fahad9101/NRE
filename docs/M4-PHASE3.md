# Milestone 4 — Phase 3: the baselines on the C0 clock (method and build record)

**Status: built 2026-10-07 on the owner's go-ahead for Phase 3 ("authorize phase 3", `reports/m4-phase3-authorization-2026-10-07.json`). This note is committed BEFORE the first real
C0-clock evaluation, so the method it describes cannot have been shaped by a result.** The results are in `docs/M4-PHASE3-RESULTS.md`, written afterwards. The frozen protocol
(`config/m4-protocol.json`, version 1, sha256 `a2e1a987528b7c84f479d79d17de7910b976380749c9d54065af7830547982a9`) is unchanged: nothing here is an amendment.

## 1. Scope

- **Targets:** the two C0-clock primaries.
  - `extension_after_open_ge_5pct` — the day-1 high is at least 5% above the open (H/O − 1 ≥ 5%); every event is eligible.
  - `loses_half_of_gap` — among gaps of at least 0.5% only, the day-1 close keeps less than half of the gap.

  `full_gap_fill` is descriptive-only in the frozen protocol, so no predictor is fitted for it (the scope proposal's Phase 3 text named it; the protocol governs). The five-session returns, the
  descriptive report and the regression target are not part of this phase.
- **The clock:** C0 is the regular open of the reaction session (09:30 New York). At that moment the opening print (`day1_open_return`, the event's own gap) is known; the day's high, low and
  close are not. Every prediction record is stamped with the regular open from the calendar, not with the B clock's cutoff.
- **Versions:** every predictor in both `all_event` and `clean_window`. **`loses_half_of_gap` cannot get a clean-window status:** its clean-window training has 9 positives in development fold 3
  (the protocol's threshold is 10), so that version is `INSUFFICIENT_DATA` by the protocol's own rule, gets no predictions, and the target's status is `INSUFFICIENT_DATA`. Its all-event version
  is run and reported as exploratory. This is not adjusted. (The protocol records 60 defined events for this target at freeze, 25 positive and 35 negative; the audit below shows how they fall in the folds.)
- **Folds:** the two development folds only (test block 3 trained on blocks 1 and 2; test block 4 trained on blocks 1 to 3), pooled. The holdout, block 5, is sealed and not touched;
  `ALLOW_HOLDOUT_LOOK` stays `False` and the holdout access log keeps only its genesis record.
- **Before the tripwire commit** the two targets are refused on the real inputs: `REAL_EVALUATION_TARGETS` in `nre/m4_harness.py` lists the three B-clock targets and nothing else. The commit that
  extends it by exactly these two is made on its own, after this note.

## 2. The predictors

The six binary predictors of Phase 2 (`docs/M4-PHASE2.md`, section 2), unchanged: `C1_pooled_rate`, `C2_timing_rate`, `C3_sector_group_rate`, `C4_issuer_history_rate`, `M2_logistic`,
`M2_without_sector`. The one difference, which is the protocol's: **M2 (both variants) also takes the opening gap** as a continuous feature, the event's own `day1_open_return`. It is standardized like
every non-intercept feature (the training mean and the population standard deviation), penalized like them, and it is the last feature. For a training event it is read from the event's own labels;
for a test event it is supplied in the view, because it is known at the open. **C1, C2, C3 and C4 never use it**, and no B-clock model does. If an event had no opening gap, M2 would stop with a
`ProtocolGap` naming the event rather than leave the row out or fill one in (the protocol gives no default); the audit below shows there is no such event.

The fit set and the test set are the events with the target defined in the version being run: for `extension_after_open_ge_5pct` every event with its open and high defined; for `loses_half_of_gap`
the events with `positive_gap_retained_half` defined. No nested threshold exists among the C0 primaries, so the monotone repair of Phase 2 does not apply.

## 3. One run

As in Phase 2 (`docs/M4-PHASE2.md`, section 3), with these differences.

1. The runner is Phase 2's (`nre/m4_phase2.py`) given Phase 3's targets (`nre/m4_phase3.py`); Phase 2's committed outputs still reproduce from it, byte for byte or to the stated tolerance.
2. A version whose pooled development test fails the thresholds (10 positives and 10 negatives) is `INSUFFICIENT_DATA` and has no predictions; a fold whose training events fail the fold-level threshold is left out
   of the pooled set, as before.
3. **The one confirmatory contrast per target is the clean-window `M2_logistic` against C1.** Its all-event contrast is its companion in the status rule only where the clean-window version can be evaluated;
   where it cannot (`loses_half_of_gap`), the all-event contrast is labelled exploratory and says why. Every other contrast is exploratory.
4. The status of each target is `DISTINGUISHABLE_BETTER` only if the clean-window 99% headline interval lies entirely below zero and the all-event point estimate is below zero; `NOT_DISTINGUISHABLE` otherwise;
   `INSUFFICIENT_DATA` where the clean-window thresholds were not met. **No status is a claim of an edge.**
5. The run starts only from the experiment log exactly as Phase 2 left it (its genesis record and 102 experiment records, all on the three B-clock targets) and the holdout log holding only its genesis,
   and appends 72 records (two targets, two versions, six predictors, two folds and the pooled set) to make 175. It runs the whole evaluation twice from scratch and records nothing unless the two are identical.
   The results report is `reports/m4-phase3-results-<date>.json` and the predictions `reports/m4-phase3-predictions-<date>.jsonl`.

## 4. The details this phase settled where the protocol is silent

Listed in `reports/m4-phase3-authorization-2026-10-07.json` (P3-1 to P3-7) before any C0-clock evaluation, outcome-independent, open to the owner's review. **The one that could move a result is P3-1:** the opening
gap is the event's own `day1_open_return`, standardized with the training mean and population standard deviation, and kept in both M2 variants (the without-sector sensitivity removes only the two sector indicators).
The rest are procedural: the fit set for `loses_half_of_gap` (P3-2), the exploratory label for an all-event contrast whose clean-window version cannot be evaluated (P3-3), no monotone repair (P3-4), the prediction time (P3-5),
the audit's extra counts (P3-6), and the starting point of the run (P3-7). The details Phase 2 settled (P2-1 to P2-10) and the Phase 1 details (`docs/M4-HARNESS.md`, section 5) are still in force.

## 5. What the structure audit found, before anything was evaluated

`reports/m4-phase3-structure-audit-2026-10-07.json` counts which labels are defined and reads no outcome value, not even the opening gap's (a test changes every value and gets the identical audit). It reports, for all
eight combinations of target, version and fold:

- **Every training row and test event has its opening gap**, so M2 never meets an event without one.
- **`extension_after_open_ge_5pct` needs no fallback:** it is defined for every event (61 training and 21 test events in fold 3, 82 and 23 in fold 4; 55 and 20, and 75 and 23, in the clean-window version),
  the smallest C2 or C3 cell holds 11 events, and every test event's issuer has an earlier matured event of its own.
- **`loses_half_of_gap` is small and falls back where its cells are thin.** It has 25 training and 13 test events in fold 3 and 38 and 10 in fold 4 (23 and 13, and 36 and 10, in the clean-window version). In fold 3 the
  premarket timing cell has 5 training events and sector groups I and other have 9 and 6, so those cells fall back to the pooled rate (as the protocol says) for 5 (C2) and 8 (C3) of the 13 test events; in fold 4 nothing falls back
  in the all-event version, and in the clean-window version the "other" group (8) falls back for 2 test events. Two to four test events per fold have no earlier matured event of their own issuer, so C4 gives them the group prior.
  (The count of defined events is itself a fact about the opening gaps: an event is in this target only if its gap is at least 0.5%. It was already part of the frozen protocol.)
- **No indicator feature is constant in training**, so no feature is dropped; every test event has an earlier matured event.

## 6. How it was checked

- Tests on synthetic data: `tests/test_m4_models.py` (`OpeningGapTests`: the gap is the last feature of both M2 variants and of no B-clock model; a training event's gap is its own label, a test event's is the supplied one; the
  fit satisfies the penalized optimality conditions and matches an independent Newton solver with the gap column standardized; the prediction moves with the gap; the baselines never use it; a missing gap in the view fails loudly; an
  event with no opening return stops the fit and the prediction), `tests/test_m4_phase3.py` (the two phases' targets, the contrast role where the clean-window version cannot be evaluated, both targets through the runner, the
  prediction time, the audit's counts and that it reads no value, and `run()` in a temporary directory with logs shaped as Phase 2 leaves them, including its refusals) and `tests/test_m4_phase3_record.py` (the authorization record, and the
  committed audit reproduced from the committed inputs with its findings pinned).
- Phase 2's tests and committed outputs are unchanged and still pass after the runner was generalized.
- The mutation check (`scripts/m4_mutation_check.py`) now has 101 deliberate defects, 21 of them added for Phase 3 and two of Phase 2's rewritten for the changed role logic; the tally is in the completion record.

## 7. Running it

```
python -m nre.m4_phase3 audit [--output PATH]       # the structure audit; reads which labels are defined, never an outcome
python -m nre.m4_phase3 run --date YYYY-MM-DD       # the evaluation: needs ALLOW_REAL_EVALUATION for these targets, a clean committed tree, no earlier Phase 3 output and the experiment log as Phase 2 left it
```

## 8. What it does not do

- It does not touch the holdout, model `full_gap_fill` or the five-session returns, amend the protocol, add data, or accept Milestone 4. It makes no claim of a predictive edge; the protocol expects most primaries to be
  `NOT_DISTINGUISHABLE`.
- Knowing the opening gap makes the C0 question different from the B-clock one: the models see something the cutoff clock cannot. A C0 result says nothing about the B-clock results and the reverse.
- It is a convenience sample of 23 issuers on one market regime, with SIC codes read on 2026-09-26 and no execution data (the protocol's disclosed limits all apply).
