# Milestone 4 — Phase 4: the one look at the final holdout (method and build record)

**Status: built 2026-10-07 on the owner's go-ahead for Phase 4 ("authorize phase 4", `reports/m4-phase4-authorization-2026-10-07.json`). This note is committed BEFORE the look, so the method it
describes cannot have been shaped by a result. No block-5 outcome had been read when it was written.** The results will be in `docs/M4-PHASE4-RESULTS.md` and the Milestone 4 report in
`docs/M4-REPORT.md`, written afterwards. The frozen protocol (`config/m4-protocol.json`, version 1, sha256 `a2e1a987528b7c84f479d79d17de7910b976380749c9d54065af7830547982a9`) is unchanged:
nothing here is an amendment.

## 1. What the look is

The protocol's rule (`holdout`): the final holdout, block 5 (the 23 Milestone 1 events), "is evaluated once, with every pre-registered predictor and target together, trained on blocks 1 to 4 and
under this protocol version. No predictor is selected for it: all are evaluated and all are reported." It is "a replication check on direction and a single, logged exposure of the frozen
pipeline to data it was not developed on; not a source of statistical power", and block 5 is entirely Milestone 1 events, "selected very differently from the rest (23 of 243 candidates kept,
against 91% to 94% for steps 2 and 3. Time and selection regime are confounded in it; every holdout result carries that statement)." The holdout alone never creates a claim.

- **Grid:** the five primary targets (`gap_ge_3pct`, `gap_ge_5pct`, `day1_close_return`, `extension_after_open_ge_5pct`, `loses_half_of_gap`) in both versions; six predictors for each binary target and
  five for the regression target, the sensitivities and the cell baselines included: 58 cells, each with a record in the experiment log (175 records become 233) and one access in the holdout log (1 becomes 2).
- **Training:** blocks 1 to 4 as each version sees them (105 events, fewer where the clean-window version masks caveated pairs). The predictors are exactly Phase 2's and Phase 3's: no tuning, no change.
- **A single call:** `python -m nre.m4_phase4 run --date YYYY-MM-DD` calls `Harness.look` once. The access record (number, reason, the 23 events, the protocol hash, the commit) is written to the hash-chained
  holdout log before any label is read. Everything after it is a pure function of the 23 events the look returned; the evaluation is made twice from them and must be identical, with no second access.
  No Phase 4 code unseals anything itself (a test scans for it), and the runner contains exactly one call of `look`.
- **The C0 clock needs the look too:** M2 on the C0 targets takes the test event's own opening gap, which is a block-5 outcome value (known at the open, but an outcome all the same). So even the
  *predictions* for the two C0 targets are made inside the look, never before it.

## 2. What a cell can be

| State | When | What is reported |
| --- | --- | --- |
| `EVALUATED` | the holdout test events with the target defined have at least 10 positives and 10 negatives (the regression target: at least 20 events), and the fold's training events pass the fold-level rule | every predictor is fitted on blocks 1 to 4 and scored on block 5: the development metrics on the one fold with K = 5 and 10 (K = 20 needs 40 events), reliability in min(4, floor(n / 10)) bins, each predictor's contrast against C1 and the pairs the harness lists (5000-replicate cluster bootstrap, protocol seeds, 95% interval, the wider of the reaction-session and issuer clusterings), and for the confirmatory model whether the **sign** of the contrast matches its development contrast in the same version |
| `COUNTS_ONLY` | fewer than 10 positives or fewer than 10 negatives (regression: fewer than 20 events) | nothing is fitted or scored: the counts, the base rate and its Wilson 95% interval. Each predictor still has a log record with this state and no predictions |
| `INSUFFICIENT_DATA` | the fold's training events fail the fold-level rule | as `COUNTS_ONLY`; none of the five primaries is expected to be in this state |
| `MODEL_FIT_FAILED` | a predictor does not converge (or a capped 5% model has no 3% predictions) | the state and the reason; nothing is substituted |

The protocol said in advance (`disclosures`) that `gap_ge_3pct`, `gap_ge_5pct` and `loses_half_of_gap` would have 3 to 5 positives in the holdout in both versions and so be `COUNTS_ONLY`, and that
`extension_after_open_ge_5pct` and `day1_close_return` would meet their thresholds. The look will show whether that held. Whatever it shows, nothing is selected, tuned or re-run, a result that
disagrees with the development result is reported as it is, and no status is assigned from the holdout.

## 3. The descriptive report and the Milestone 4 report

- **Descriptive report** (`reports/m4-phase4-descriptive-<date>.json`), computed inside the look from the 105 visible events and the 23 it returned: for all 19 targets in both versions the defined events,
  positives, negatives, the base rate with its Wilson 95% interval, the protocol's bucket (estimable at 30 and 30, thin at 10 and 10, insufficient below), positives by timing, issuers and sessions, and
  defined events and positives by block (1 to 5); for the five regression labels n, mean, standard deviation, standard error and the 10th, 50th and 90th percentiles; and the block table by source.
  Block 5's counts of positives were already visible in the scoping evidence before the freeze (the protocol's `not_blind_to_counts`); the holdout is sealed against model selection and tuning, not
  against its base rates.
- **The Milestone 4 report** is `docs/M4-REPORT.md` (plain language) and `reports/m4-report-<date>.json`, assembled by `nre/m4_report.py` from the committed artifacts only (it reads no label): what was
  estimable and what was not, every interval with its counts, the number of holdout accesses, the limits, the review items still open for the owner, and, criterion by criterion, the evidence for the protocol's
  `acceptance_of_the_m4_report`. It is evidence. **The acceptance decision is the owner's.**

## 4. The details this phase settled where the protocol is silent

Listed in `reports/m4-phase4-authorization-2026-10-07.json` (P4-1 to P4-14) before any Phase 4 code existed, outcome-independent, open to the owner's review. **The two that could move what is reported:**
P4-3 (the holdout fold's precision-at-K values are K = 5 and 10, the fold values, and its reliability bins min(4, floor(n / 10))) and P4-4 (the sign check: the holdout estimate of the confirmatory
contrast against the sign of the development estimate of the same version; zero has no sign; nothing to compare where the development result is `INSUFFICIENT_DATA`). The rest are procedural: the order of
operations inside the one look, what a technical rerun requires (a code change of its own, a further logged access, counted), the dress rehearsal, the pre-look audit, the 58 records, the tripwire turned on
and off again, and that nothing is selected. The details of Phases 2 and 3 (P2-1 to P2-10, P3-1 to P3-7) and Phase 1's (`docs/M4-HARNESS.md`, section 5) are still in force, and the owner has not
answered the review items that remain open (they are listed in the report).

## 5. What was checked before the look

- **A structure audit of the holdout fold**, `reports/m4-phase4-holdout-structure-audit-2026-10-07.json`: it reads which labels are defined for the *training* events and the metadata of the 23 test events
  (a test changes every label value and gets the identical audit), and no block-5 outcome. It found nothing that stops the look: no C2 or C3 cell falls back to the pooled value (the smallest training cell
  holds exactly 10 events, the "other" sector group in the clean-window version of `loses_half_of_gap`, which is the minimum that passes; 22 for the other targets), every test event has an earlier matured event, the regression target's issuer-history mean exists for every test event, no indicator
  feature is constant, and for `loses_half_of_gap` two of the 23 test events have no earlier event of their own issuer (the group or pooled prior is used for them). **The 23 events come from 23 different
  issuers**, so the issuer clusters of the holdout bootstrap are single events and its intervals will be wide.
- **A dress rehearsal on the real inputs** (`tests/test_m4_phase4_rehearsal.py`, a test that runs on every CI): the whole of `python -m nre.m4_phase4 run` against the real events' metadata, the real
  training labels, the real calendar and the real logs, in a temporary copy of `config/` and `reports/` cut back to what they held before the look, with the 23 block-5 record files destroyed and seeded
  synthetic labels behind the gate, in two regimes (every all-event cell scored; almost none). It shows that the plumbing (cells, history, views, the opening gap, the nested cap, the descriptive report,
  the logging) works on the real data without reading a block-5 outcome, and that the real logs and outputs are never touched.
- **Tests on synthetic data** (`tests/test_m4_phase4.py`): every state a cell can take; that predictions depend on no block-5 outcome except the opening gap on the C0 clock (swapping every block-5 outcome
  changes no prediction; shifting the opening gap changes exactly the C0 logistic models); that a fit sees blocks 1 to 4 only and a view has no labels; the descriptive counts against brute force; the sign
  check; the runner with all its refusals (tripwire off, tree dirty, logs not as expected, a second access, holdout experiments already present, a development result altered) happening *before* any
  block-5 outcome is read, and a failure after the look, which leaves the access on the record and writes nothing. `tests/test_m4_report.py` tests the report assembler on the rehearsed output.
- **The older phases' tests no longer depend on the real holdout log's length:** they reproduce their outputs against a copy of the log cut back to its genesis (the state those outputs were made in), and
  the invariant is now stated precisely: the log holds its genesis and at most the one authorized look, and the tripwire is on only while that look is still to come. Every test that calls `look`
  on a harness patches the tripwire explicitly.
- The mutation check (`scripts/m4_mutation_check.py`) now has 132 deliberate defects, 31 of them added for the Phase 4 code (the holdout evaluation in the harness, the runner and the report
  assembler); each of the 31 was caught on its first run, and the tally over all 132 on the final state is in the completion record.
- Two states of the repository were simulated and the whole suite run in each: the one between the tripwire commit and the look (tripwire on, logs not yet grown), to be sure no test can call
  `look` on a real harness, and the one after the look (logs grown, outputs present, tripwire off again). The first showed one older test that pinned the tripwire to `False`, now stated as the
  invariant; the second showed two tests that read the real log's length, now independent of it.

## 6. Running it

```
python -m nre.m4_phase4 audit [--output PATH]     # the holdout structure audit; reads no block-5 outcome
python -m nre.m4_phase4 run --date YYYY-MM-DD     # THE LOOK: needs ALLOW_HOLDOUT_LOOK, a clean committed tree, no earlier Phase 4 output, the experiment log as Phase 3 left it, the holdout log at its genesis
python -m nre.m4_report build --date YYYY-MM-DD   # the report as data, from the committed artifacts (after the look)
```

`ALLOW_HOLDOUT_LOOK` is turned on in a commit of its own after this note, and off again in a commit of its own after the look.

## 7. What it does not do

- It does not select, tune, re-run with other settings or amend anything after a holdout result is seen, and it creates no claim and assigns no status from the holdout.
- It does not declare Milestone 4 accepted, start Milestone 5, add data, or model `full_gap_fill`, the five-session returns or the other descriptive-only and `INSUFFICIENT_DATA` targets.
- It is a convenience sample of 23 issuers on one market regime, with SIC codes read on 2026-09-26 and no execution data, and the holdout is 23 events with a different selection regime. With 23 events from
  23 issuers it cannot add statistical power; it can show whether the direction of the development result repeats.
