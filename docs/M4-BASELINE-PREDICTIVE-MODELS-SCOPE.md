# Milestone 4 — Baseline Predictive Models: scope proposal (for the project owner's review)

**Status: proposed 2026-10-03, after the owner's "ok authorize m4 scoping" and "not only scoping everything you recomended"
(`reports/m4-scoping-authorization-2026-10-03.json`, which also says how those words were read). Nothing for Milestone 4 is built: this
document and the descriptive evidence beneath it are all that exists. Milestones 0 to 3 and Milestone 2 steps 2 and 3 are the only ones
declared accepted. The evidence is `reports/m4-scoping-evidence-2026-10-03.json` and `reports/m4-caveat-sensitivity-2026-10-03.json`; both
reproduce from committed inputs, read labels and never prices, and fit nothing. Every decision in section 6 was open when this was written.**

**Update 2026-10-03, after the owner answered section 6** (`reports/m4-scope-decisions-2026-10-03.json`): decisions 1, 3, 4 and 5 were put to the
owner and each recommended default was chosen: all four families with rare targets as `INSUFFICIENT_DATA`; block 5 sealed as the final holdout;
clean-window and all-event results reported side by side, with the clean-window version driving model selection; the existing 128 events, labels
only. Decision 2, the primary-target list, was not asked and stays the recommended default until Phase 0. **Phase 0 is not yet authorized and
nothing is built.** The text below is left as written.

## Summary

- **What Milestone 4 is.** The master prompt's section, in full: "Build baseline models for: opening gap, Day-1 move, gap retention,
  continuation/fade. Perform walk-forward validation. No production ranking yet." The Milestone 0 technical contract (read in full for this
  proposal, along with master prompt sections 1 to 3, 12 to 14, 16 to 21, 24 to 28, 34, 35 and 39 to 44) supplies the method: prediction
  clocks, folds, a frozen holdout, metrics and comparators. Section 1 lists what it requires.
- **What the 128 accepted events support.** A small, honest Milestone 4: an evaluation harness with leakage tests, plus base-rate and simple
  regression baselines, evaluated walk-forward. They can estimate the opening gap at 3% (40 positives of 128) and
  thinly at 5% (29) and 10% (14). They cannot support the rare-move targets the master
  prompt cares most about (gaps of 15%, 20% and 30% have 5, 3 and
  0 positives), the continuation/fade model's own clock (it needs intraday bars), or any claim of edge: with
  44 development test events, a top-20 selection must hit about twice the base rate before its interval even
  excludes it.
- **What I recommend.** Scope Milestone 4 as a validated *measurement* milestone: pre-register the protocol, build the harness and its leakage
  tests first, run the first three rungs of the contract's model ladder on the estimable targets, give rare targets an explicit
  `INSUFFICIENT_DATA` state, look at the sealed holdout once, and report the limits plainly. Do not make "a baseline beats the base rate" the
  acceptance test: at these counts that cannot be demonstrated whether or not it is true.
- **What I need from you:** the five decisions in section 6, each with a recommended default.

## 1. What Milestone 4 requires

| Requirement | Where it comes from | What it means for this data |
| --- | --- | --- |
| Targets: opening gap at 3/5/10/15/20/30%; Day-1 high at 10/20/30% and close at 10/20%; continuation (+5/+10% after the open, 5-day return at 10/20%); fade (loses half the gap, full fill, closes below the open); regression targets | master prompt 12; contract 6 | 18 binary targets, all expressible from the 16 labels (section 2.1) |
| Prediction clocks: A before a scheduled event, B at the release (only already-observed prices), C at the open plus 15 minutes | contract 2 | B-type targets are expressible; C as defined is not; A is not (section 2.2) |
| Ladder: base rates, then logistic and linear/quantile baselines, then trees, then calibrated ensembles | master prompt 18; contract 10 | Milestone 4 covers the first three rungs only |
| Comparators: event-category and sector rates, simple surprise, RVOL-only, momentum-only, seeded random | master prompt 24; contract 11 | rates and random exist; surprise, RVOL and momentum need data we do not have (section 2.5) |
| Chronological walk-forward; purge and embargo of at least the 20-session horizon; event clusters kept together; a final holdout frozen before iterating; every experiment and holdout access logged | master prompt 21, 44; contract 11 | feasible: five blocks and no purge needed (section 2.3) |
| Metrics: PR-AUC, precision/recall, Brier, reliability bins with counts, precision@K, false positives/negatives, baseline-relative lift, cluster-aware intervals; raw accuracy is not a promotion metric | master prompt 19, 20; contract 11 | computable, but mostly noise at these counts (section 2.4) |
| Clean-window and all-event results side by side; robustness cuts including top winners removed | contract 5, 11 | the caveat check (section 2.7) |
| Confidence tiers; `NO_QUALIFIED_OPPORTUNITY`, `INSUFFICIENT_DATA`, `MODEL_NOT_VALIDATED` states | master prompt 27, 28; contract 13 | mandatory; Milestone 4 uses them and never emits `QUALIFIED` |
| Versioned models, an experiments registry, leakage, reproducibility and abstention tests | master prompt 34, 35; contract 8, 14 | a file-based registry (JSON records and hashes), as every earlier milestone |
| No production ranking; research signals only; no trading, sizing or execution | master prompt M4 text, 40 | nothing here ranks or selects candidates |

## 2. What the data can and cannot support

Computed by `nre/m4_scoping_evidence.py` over the 128 accepted events (23 from Milestone 1, 45 from step 2, 60 from step 3), using labels only.
The yardsticks it applies (30 positives and 30 negatives for "estimable", 10 for "thin", 40 training events to "fit anything") are declared in
the report and are proposals for the protocol, not results.

### 2.1 Targets

| Family | Target | Definition | Defined | Positives | Base rate | Reading |
| --- | --- | --- | --- | --- | --- | --- |
| Opening gap | `gap_ge_3pct` | opening gap O/Cprev - 1 >= 3% | 128 | 40 | 31.2% | estimable, wide uncertainty |
| Opening gap | `gap_ge_5pct` | opening gap O/Cprev - 1 >= 5% | 128 | 29 | 22.7% | thin |
| Opening gap | `gap_ge_10pct` | opening gap O/Cprev - 1 >= 10% | 128 | 14 | 10.9% | thin |
| Opening gap | `gap_ge_15pct` | opening gap O/Cprev - 1 >= 15% | 128 | 5 | 3.9% | insufficient |
| Opening gap | `gap_ge_20pct` | opening gap O/Cprev - 1 >= 20% | 128 | 3 | 2.3% | insufficient |
| Opening gap | `gap_ge_30pct` | opening gap O/Cprev - 1 >= 30% | 128 | 0 | 0.0% | insufficient |
| Day-1 move | `day1_high_ge_10pct` | event-relative day-1 high H/P0 - 1 >= 10% | 128 | 33 | 25.8% | estimable, wide uncertainty |
| Day-1 move | `day1_high_ge_20pct` | event-relative day-1 high H/P0 - 1 >= 20% | 128 | 12 | 9.4% | thin |
| Day-1 move | `day1_high_ge_30pct` | event-relative day-1 high H/P0 - 1 >= 30% | 128 | 5 | 3.9% | insufficient |
| Day-1 move | `day1_close_ge_10pct` | event-relative day-1 close C/P0 - 1 >= 10% | 128 | 22 | 17.2% | thin |
| Day-1 move | `day1_close_ge_20pct` | event-relative day-1 close C/P0 - 1 >= 20% | 128 | 6 | 4.7% | insufficient |
| Continuation | `extension_after_open_ge_5pct` | opening-anchored day-1 high H/O - 1 >= 5% | 128 | 54 | 42.2% | estimable, wide uncertainty |
| Continuation | `extension_after_open_ge_10pct` | opening-anchored day-1 high H/O - 1 >= 10% | 128 | 23 | 18.0% | thin |
| Continuation | `session5_close_ge_10pct` | close of reaction session 5 / P0 - 1 >= 10% | 128 | 27 | 21.1% | thin |
| Continuation | `session5_close_ge_20pct` | close of reaction session 5 / P0 - 1 >= 20% | 128 | 16 | 12.5% | thin |
| Fade / gap retention | `loses_half_of_gap` | positive gaps of at least 0.5% only: the day-1 close keeps less than half of the gap | 60 | 25 | 41.7% | thin |
| Fade / gap retention | `full_gap_fill` | positive gaps of at least 0.5% only: the day-1 low reaches the previous close | 60 | 28 | 46.7% | thin |
| Fade / gap retention | `closes_below_open` | day-1 close below the day-1 open, C/O - 1 < 0 | 128 | 72 | 56.2% | estimable, wide uncertainty |

Only the 3% opening gap has 30 or more positives and 30 or more negatives; the 5% and 10% gaps and most others are thin, and the 15%, 20% and
30% gaps are not estimable at all. The master prompt itself says large gaps are uncommon. At today's base rates, 30 positives would take
about 275 events for the 10% gap, 770 for the 15% gap and 1,280 for the 20% gap: 2, 6, 10 times today's dataset. More earnings quarters for these 23 issuers could in principle reach the 10% gap (roughly two to three more steps the size of step 3) but not the 15% or 20% gaps. The events that produce large moves are mostly not earnings
(FDA decisions, trial readouts), and this dataset contains earnings releases only. So Milestone 4 on this data can validate the *machinery* on
earnings; it cannot speak to the rare-move use case.

### 2.2 Clocks

- **B-type targets are expressible.** Each event's cutoff is a few minutes after its release (106 events three minutes, 22 five),
  and every opening-gap, Day-1 and 5-session label is computed from daily bars after it. All 128 releases precede the next open
  (96 after hours, 32 premarket).
- **C as defined is not.** The contract puts C's clock at the open plus 15 minutes and says daily bars "cannot establish post-09:45 fill ordering
  or stop/target ordering"; the pilots' protocols are "daily regular-session ... labels only; intraday events quarantined". A different clock can
  be registered instead, **C0 = the regular open**: the open print is known, and the Day-1 high, low and close are the targets. That supports
  loses-half, full fill and extension after the open, but only for gaps of at least 0.5%, which is 60 events,
  and it is a separate registered clock, not Model C.
- **A is not expressible.** It needs a schedule known at the clock; no earnings-date schedule has been captured for any event.

### 2.3 Time structure and folds

Four gaps of 42 to 49 days between consecutive reaction sessions cut the events into five blocks:

| Block | Reaction sessions | Events | Source |
| --- | --- | --- | --- |
| 1 | 2024-11-05 to 2024-12-12 | 17 | Milestone 2 step 3: 17 |
| 2 | 2025-01-23 to 2025-06-12 | 44 | Milestone 2 step 2: 1, Milestone 2 step 3: 43 |
| 3 | 2025-07-31 to 2025-09-11 | 21 | Milestone 2 step 2: 21 |
| 4 | 2025-10-23 to 2025-12-11 | 23 | Milestone 2 step 2: 23 |
| 5 | 2026-01-22 to 2026-04-01 | 23 | Milestone 1: 23 |

The 20-session label horizon is a little under 28 calendar days, so each block's longest labels have matured before the next block's first
cutoff, with 9, 19, 14, 12 days to spare at the four boundaries. **A block-wise expanding walk-forward therefore needs no purge or embargo**, which the
harness would assert rather than assume. The folds, with the test positives for three key targets:

| Test block | 40+ training events | Train | Test | Test positives, 5% gap | Test positives, 10% gap | Test positives, loses half | Role |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | no | 17 | 44 | 9 | 3 | 6 | too little training |
| 3 | yes | 61 | 21 | 5 | 2 | 7 | development |
| 4 | yes | 82 | 23 | 5 | 4 | 5 | development |
| 5 | yes | 105 | 23 | 5 | 3 | 3 | final holdout |

Only blocks 3 to 5 have enough events behind them to fit anything. The contract wants a final chronological holdout frozen before iterating.
Sealing block 5 leaves two development folds with 44 test events in all, and a holdout of 23.

### 2.4 Uncertainty

- A plain binomial interval around an observed 25% is ±7.4 points at 128 events, ±12.4 at 44 and
  ±17.0 at 23. A half-width of ±10 points around an observed 50% needs about
  93 selected events.
- The smallest observed precision whose lower bound clears the base rate, when the top K events are selected:

| Target | Base rate | K = 10 | K = 20 | K = 40 |
| --- | --- | --- | --- | --- |
| `gap_ge_3pct` | 31.2% | 6 of 10 (1.9x) | 11 of 20 (1.8x) | 19 of 40 (1.5x) |
| `gap_ge_5pct` | 22.7% | 5 of 10 (2.2x) | 9 of 20 (2.0x) | 15 of 40 (1.7x) |
| `gap_ge_10pct` | 10.9% | 4 of 10 (3.7x) | 5 of 20 (2.3x) | 9 of 40 (2.1x) |

  So a model must roughly double the base rate at K = 20 before it can be told apart from it, and these are the narrowest intervals there are.
- The events are not independent: 128 events share 73 reaction sessions (up to
  6 on one), come from 23 issuers, and 50%
  sit in two SIC major groups (services 73 and chemicals/pharma 28). The contract requires cluster-aware intervals, which are wider.
- Return noise dwarfs any plausible simple signal: the standard deviation of the Day-1 close return is 13.6%
  (standard error of its mean 1.2%), of the 5-session close 17.2%
  and of the 20-session close 22.7%.

### 2.5 Features available at the cutoff

| Available | Not available |
| --- | --- |
| Release timing (premarket or after hours) | Earnings surprise: the code exists, its live fetch is blocked from GitHub Actions and this machine (HTTP 403), and the only value ever computed is JBSS's worked example |
| Sector (SIC), but read on 2026-09-26, not as of the event: a small leakage that must be disclosed or removed | Analyst consensus: skipped by the owner's decision |
| Issuer identity and its earlier matured labels (the fingerprints machinery enforces maturity) | RVOL, momentum, volatility, prior run-up: no price history before the anchor session has been acquired, and only derived labels are committed, never prices |
| The 8-K item list of the release's filing (candidate ledgers) | Float, short interest, market-structure and regime features: never acquired |

So the comparators "simple surprise", "RVOL-only" and "momentum-only" cannot be built from what exists. The master prompt files those inputs under
Milestone 5, which is where they belong.

### 2.6 Selection and representativeness

| Source | Candidates | Candidate issuers | Included | Share included |
| --- | --- | --- | --- | --- |
| Milestone 1 | 243 | 215 | 23 | 9.5% |
| Milestone 2 step 2 | 48 | 23 | 45 | 93.8% |
| Milestone 2 step 3 | 66 | 23 | 60 | 90.9% |

The 23 issuers are the ones with accepted Milestone 1 events, drawn from 215 candidate issuers and observed
over a window that ends in 2026, so the sample is conditioned on survival to 2026 and on reviewability: a convenience sample, not a market sample. Milestone 1 kept
9.5% of its candidates (205 were quarantined as unresolved) while steps 2 and 3 kept 91% to 94% of theirs.
**Block 5, the natural final holdout, is entirely Milestone 1's events**, so time and selection regime are confounded in any walk-forward over
this data. That has to be disclosed with every holdout result, not designed away.

### 2.7 Caveats

38 of the 128 events carry label-level caveats (competing catalysts, earlier disclosures), and the
fingerprints machinery never reads them. They fall mostly on the longer horizons: 7.0% of Day-1 values,
11.7% of session-5, 17.2% of session-10 and 31.1% of
session-20 values. `reports/m4-caveat-sensitivity-2026-10-03.json` re-ran the pools with them treated as absent:

- **Labels only, as recorded or with derived labels:** the Day-1 close and gap-flag statistics, in the whole pool and in each timing pool, move
  by at most 0.25 standard errors, but the pooled mean 20-session return moves from +2.41% to
  -0.03% (-1.19 standard errors).
- **Whole caveated events dropped:** the pool falls to 90 events and 18 of
  30 headline comparisons move by half a standard error or more, partly because it also removes the more
  eventful names.

The contract does not leave this to taste: it requires "clean-window and all-event sensitivities without cherry-picking". Milestone 4 should
report both for every target and pre-register which one drives any model selection.

## 3. Proposed scope

Phases, each needing its own go-ahead, as in Milestones 2 and 3:

- **Phase 0 — pre-registration (documents only).** `config/m4-protocol.json` and a short protocol note, hashed and committed before any fold is
  evaluated: the eligible universe (the 128 events, labels only); at most six primary targets, with every other target descriptive; the clocks
  (B for opening-gap, Day-1 and 5-session targets, C0 for fade and extension); the folds and the sealed holdout; the models; the comparators; the
  metrics and how their intervals are made (a reaction-session block bootstrap); the caveat treatment; the thresholds that make a target
  `INSUFFICIENT_DATA`; the seeds; and the experiment and holdout-access log format.
- **Phase 1 — harness and leakage tests.** The walk-forward runner over blocks, with the maturity filter and an assertion at every boundary that
  no purge is needed; the metric functions with their intervals; the seeded random comparator; the experiments registry. The leakage tests come
  first and include injecting a future label or event and checking that no earlier prediction changes. No model beyond the pooled base rate yet.
- **Phase 2 — baselines on the B clock.** The first three rungs: category, timing and sector base rates with shrinkage (reusing the existing
  fingerprint pooling); a regularized logistic regression on a few point-in-time features (timing, sector division, the issuer's own shrunk
  history); and linear and quantile regression for the Day-1 and 5-session returns. Development folds only; block 5 stays sealed.
- **Phase 3 — baselines on the C0 clock.** The same for loses-half, full fill and extension after the open, on the 60
  positive-gap events, with `INSUFFICIENT_DATA` wherever the declared thresholds are not met.
- **Phase 4 — one look at the holdout and the Milestone 4 report.** The frozen protocol is run once on block 5 and the access is logged. The
  report states what was estimable, what was not, every interval with its counts, and the limits above. The acceptance decision is the owner's.

**Proposed meaning of "Milestone 4 done":** the protocol was frozen before evaluation; the leakage tests, including the injected-future tests,
pass; every output reproduces deterministically from committed inputs; every target is reported with counts and cluster-aware intervals, or as
`INSUFFICIENT_DATA`; each baseline is compared with the pooled base rate and the seeded random ranking, clean-window and all-event side by side;
calibration is shown with coarse bins and their counts; the holdout was looked at once. **It does not mean a baseline beats the base rate**, and
it cannot establish the master prompt's section-39 criteria (stability across regimes, performance after execution costs, high-confidence
precision): this span covers one market regime and no execution data exists.

**What Milestone 4 will not do:** rank or select candidates, produce a candidate list, backtest or model costs (Milestones 7 and 8), fit trees or
ensembles (Milestone 5), compute a reaction gap (Milestone 6), make a live prediction, or acquire any new data.

## 4. The data question

- **Option A (recommended): use the existing 128 events, labels only.** No new acquisition, no new provider terms, and it is exactly what
  "baseline" means: category, timing, sector and issuer-history baselines. The harness will also measure what more data would buy (how the
  results move as training grows), which is better evidence for any later data decision than a guess.
- **Option B: acquire features first.** Earnings surprise against the prior period (code exists; the live fetch would go through the built-in
  browser as the cohort freeze did) and price and volume history before each event (a new Alpaca fetch for derived ratios only). That would
  enable the surprise, RVOL and momentum comparators, but it is a new acquisition for 128 events, needs its own authorization and review, and
  the master prompt lists those inputs under Milestone 5.
- **Option C: a different event universe.** Large-move catalysts (FDA decisions, trial readouts) are where the master prompt's rare-move targets live.
  Milestone 3's Phase C pieces are the starting point. That is a separate project-level decision, not a precondition for Milestone 4.

## 5. Risks and how the proposal handles them

| Risk | Handling |
| --- | --- |
| Samples too small to show any lift; over-reading noise | pre-registered primary targets (at most six); rare targets reported as `INSUFFICIENT_DATA`; one holdout look; intervals and counts everywhere |
| Multiple comparisons (18 targets, several baselines) | everything is reported; only the pre-registered primaries can support a statement |
| Time and selection regime confounded in the holdout (block 5 is Milestone 1's events) | disclosed with every holdout result; results also reported by source |
| Issuer survivorship; convenience sample | stated in every report; nothing is described as a market base rate |
| SIC read on 2026-09-26, not as of the event | disclosed, or the sector feature is dropped if a leakage test flags it |
| Caveated labels contaminate pooled outcomes | both clean-window and all-event results for every target |
| Dependence (73 reaction sessions, 23 issuers) | cluster-aware intervals; events of one reaction session kept in one fold |
| Label leakage through maturity | block boundaries asserted to need no purge; training uses matured labels only; injected-future tests |

## 6. Decisions needed

1. **Shape of Milestone 4.** Recommended: all four families, with rare targets as `INSUFFICIENT_DATA`. Alternatives: only the estimable targets, or
   pause Milestone 4 until different data exists.
2. **Primary targets.** Recommended default (the owner may edit it in Phase 0): `gap_ge_3pct`, `gap_ge_5pct`, the Day-1 close return,
   `extension_after_open_ge_5pct`, `loses_half_of_gap`. Everything else descriptive.
3. **Final holdout.** Recommended: block 5 (Milestone 1's 23 events), sealed, with the selection-regime disclosure. Alternatives: no separate
   holdout (against the contract), or blocks 4 and 5 together (one development fold left).
4. **Caveats.** Recommended: report clean-window (caveated labels and their derived labels treated as absent) and all-event results side by side, with the
   clean-window version as the one that drives model selection. Alternatives: all-event primary, or drop caveated events.
5. **Data.** Recommended: Option A, the existing events, labels only.

*Status 2026-10-03: decisions 1, 3, 4 and 5 were decided as recommended; decision 2 stays open until Phase 0
(`reports/m4-scope-decisions-2026-10-03.json`).*

## 7. What this document does not do

It writes no model code and makes no prediction, score or ranking. It acquires no data and uses no new provider. It does not decide any of
section 6; the evidence code it cites is descriptive only. It does not claim Milestone 4 can show an edge, and it does not start Milestone 5 or
any later milestone. Acceptance of Milestone 4, if it is ever built, would be the owner's own declaration, as with every milestone before it.
