# Milestone 5 — Advanced Models: scope proposal (for the project owner's review)

**Status: proposed 2026-10-08, after the owner's "authorize m5 scoping" (`reports/m5-scoping-authorization-2026-10-08.json`, which also says how those words were read); its six decisions were then made the same
day, each at the recommended default (the owner's "take your defaults for all six", `reports/m5-scope-confirmation-2026-10-08.json`). Nothing for Milestone 5 is built and no phase of section 3 is authorized: each
needs its own go-ahead. This document, the planning arithmetic beneath it and the two records of the owner's words are all that exists. Milestones 0 to 4 and Milestone 2 steps 2 and 3 are the only ones declared
accepted (Milestone 4 on 2026-10-08, `reports/m4-acceptance-declaration-2026-10-08.json`).** The arithmetic is `reports/m5-scoping-evidence-2026-10-08.json`, built by `nre/m5_scoping_evidence.py` from three
committed artifacts. It fits nothing, predicts nothing, reads no event-level outcome and acquires no data, and it uses no result of the Milestone 4 holdout.

## Summary

- **What Milestone 5 is.** The master prompt's section: test gradient boosting, ensembles, and ticker-reaction, analogue, market-structure and market-regime features; "Perform calibration and ablation studies.
  Promote only improvements that survive out-of-sample testing." The Milestone 0 technical contract (sections 10 to 13 and 16) and master prompt sections 18 to 21, 25, 26, 39, 43 and 44 supply the method:
  ordered training, selection, calibration and test periods, ablations without retuning, and a final holdout frozen before iterative research. Section 1 lists what it requires.
- **What the data can support.** Not a confirmatory test of an advanced model. Milestone 4's confirmatory contrasts had 99% half-widths of 12% to 28% of the comparator's score on the main
  targets: a better model would have to improve on the baseline by about that much before its interval could exclude zero. To see an improvement of 5% at that level would take about 248 to 1,349 test
  events, 6 to 31 times the pooled test sets Milestone 4 had and 2 to 11 times the whole dataset of 128. And on development, no flexible Milestone 4
  model (logistic or ridge) had the best score in any evaluated cell: a simple rate or quantile baseline did. A boosted or ensembled model on the same events has more ways to fit noise and fewer events per
  parameter.
- **What blocks a clean promotion.** Milestone 4's holdout is spent: it was looked at once and its results are known, so it cannot be the untouched final holdout the contract requires. A fresh one has to come
  from events the project does not yet hold, and the dataset's own rate suggests about 48 such events exist since the data ended (an estimate, not a count). That is too few to confirm a modest
  improvement; at best it is a consistency check on direction.
- **What I recommend.** Scope Milestone 5 as a *bounded, pre-registered comparison* whose valid outcomes include "no improvement could be shown": stage the data work (an availability probe, an outcome-blind
  forward extension for a fresh holdout, a small derived-features fetch) before any model is fit, implement the models in the standard library with independent recomputation, keep Milestone 4's confirmatory
  structure, and define "promotion" narrowly. Do not make "an advanced model beats the strongest baseline" the acceptance test: at these counts that cannot be demonstrated whether or not it is true.
  If the owner prefers to pay for statistical power first, pausing Milestone 5 for a universe expansion is the honest alternative (decision 1).
- **Decisions:** made on 2026-10-08, all six at the recommended default (section 6).

## 1. What Milestone 5 requires

| Requirement | Where it comes from | What it means for this data |
| --- | --- | --- |
| Gradient boosting and ensembles; the ladder runs logistic and quantile baselines, then random forest, then gradient boosting (XGBoost or LightGBM are named), then calibrated ensembles, "only with incremental out-of-sample evidence"; "the production model should win on out-of-sample performance, not complexity" | master prompt Milestone 5 and 18; contract 10 | the named libraries conflict with the project's no-runtime-packages rule (README): decision 4. At 55 to 105 training events (the four main targets) a model's capacity is tiny (section 2.3) |
| Four feature families, each facing ablation: ticker-reaction, analogue, market-structure, market-regime (the ablation list adds float, short interest, technical structure, premarket volume, valuation, sentiment/NLP) | master prompt Milestone 5, 8 to 11 and 25; contract 10 | availability differs sharply by family (section 2.5) |
| Calibration: Platt scaling, isotonic regression, reliability diagrams, Brier; "calibration matters more than flashy classification accuracy" | master prompt 19; contract 11 | needs a held-out calibration period inside every fold: 11 to 21 events here (section 2.3) |
| Ablation studies without retuning against test outcomes; remove a feature that adds complexity without out-of-sample gain | master prompt 25; contract 10 and 11 | doable, but the number of comparisons must be controlled (section 2.6) |
| Chronological walk-forward with ordered training, hyperparameter-selection, calibration and test periods; purge and embargo; clusters kept together; matured labels only | master prompt 21; contract 11 | Milestone 4's harness covers most of it (five blocks, no purge needed); the periods get smaller |
| A final chronological holdout frozen before iterative research; every experiment and holdout access logged; avoid "repeated tuning against the same holdout period" | master prompt 44; contract 11 | Milestone 4's holdout is spent (section 2.4) |
| Comparators: event-category and sector rates, simple surprise, RVOL-only, momentum-only, seeded random ranking, the strongest relevant baseline | master prompt 24; contract 11 | rates and random exist; surprise (held for only a handful of events), RVOL and momentum need data the project does not hold (section 2.5) |
| Metrics: PR-AUC, precision and recall, Brier, reliability bins with counts, precision at K, quantile coverage and loss, baseline-relative lift, cluster-aware intervals; raw accuracy is not a promotion metric | master prompt 20; contract 11 | Milestone 4's metric and bootstrap code is reusable as it stands |
| Promotion: preregister horizons, universe and cutoffs on development data; show improvement over the strongest baseline with uncertainty; calibration compatible with use; positive incremental economics under conservative costs; no unresolved leakage; explain tail dependence and regime weakness; cutoffs frozen before the final holdout is examined | contract 11 | economics needs execution data (none) and regime stability needs more than one regime (one in the span): the full promotion cannot be reached here (section 2.7) |
| Explainability for tree models (SHAP), as associations and not causes | master prompt 26; contract 10 | no SHAP package; ablation and permutation importance are the standard-library route, and only for models worth explaining |
| No production ranking; research signals only; no trading, sizing or execution | master prompt 40 | nothing here ranks or selects candidates |

## 2. What the data and Milestone 4's results can and cannot support

### 2.1 What Milestone 4 found

Under the frozen protocol, four of the five primary targets were `NOT_DISTINGUISHABLE` from the pooled base rate and `loses_half_of_gap` was `INSUFFICIENT_DATA`; none of the 77 pooled development contrasts
excluded zero (`docs/M4-REPORT.md`). On development, the best-scoring Milestone 4 predictor in every evaluated cell was a simple baseline: the issuer-history rate for the 3% and 5% gaps and `loses_half_of_gap`,
the sector-group quantiles for the Day-1 return, the pooled rate for the extension target. The logistic and ridge models never led. That is development evidence only, from out-of-fold predictions; nothing in this
proposal uses a holdout result.

### 2.2 How large a gain could even be seen

The table takes Milestone 4's confirmatory contrast in each evaluated development cell, its 99% half-width, and asks how large that is next to the comparator's score and how many test events would make a stated
improvement equal it (the planning approximation and its assumptions are in the evidence file: the half-width shrinks with the square root of the test events).

| Target | Version | Test events | Comparator (pooled) score | 99% half-width | Half-width as a share of the score | Events for a 5% / 10% improvement to equal it | The share at 128 / 256 / 512 / 1,024 test events |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gap_ge_3pct` | clean-window | 43 | 0.2214 | 0.0294 | 13% | 304 / 76 | 8% / 5% / 4% / 3% |
| `gap_ge_3pct` | all-event | 44 | 0.2185 | 0.0312 | 14% | 359 / 90 | 8% / 6% / 4% / 3% |
| `gap_ge_5pct` | clean-window | 43 | 0.1787 | 0.0390 | 22% | 820 / 205 | 13% / 9% / 6% / 4% |
| `gap_ge_5pct` | all-event | 44 | 0.1757 | 0.0307 | 17% | 537 / 135 | 10% / 7% / 5% / 4% |
| `day1_close_return` | clean-window | 43 | 0.03489 | 0.00419 | 12% | 248 / 62 | 7% / 5% / 3% / 2% |
| `day1_close_return` | all-event | 44 | 0.03440 | 0.00486 | 14% | 352 / 88 | 8% / 6% / 4% / 3% |
| `extension_after_open_ge_5pct` | clean-window | 43 | 0.2450 | 0.0615 | 25% | 1,085 / 272 | 15% / 10% / 7% / 5% |
| `extension_after_open_ge_5pct` | all-event | 44 | 0.2433 | 0.0673 | 28% | 1,349 / 338 | 16% / 11% / 8% / 6% |
| `loses_half_of_gap` | all-event | 23 | 0.2612 | 0.1141 | 44% | 1,754 / 439 | 19% / 13% / 9% / 7% |

Reading: on today's pooled development test sets (43 to 44 events) an improvement has to be about 12% to 28% of the comparator's score before a 99% interval like Milestone 4's could exclude zero,
and 44% for `loses_half_of_gap`, whose test set is 23 events. Seeing a 5% improvement would take about 248 to 1,349 test events; a 10% improvement, about 62 to 338.
Even a test set the size of the whole dataset (128 events) would leave half-widths of 7% to 16%. The interval an advanced model gets could differ, but the order of magnitude is
set by the number of events and the noise in the targets, not by the model class.

### 2.3 Capacity, and the shrinking fit set

The contract wants ordered training, hyperparameter-selection, calibration and test periods inside every fold. Cutting a fifth of each training set for selection and another fifth for calibration (arithmetic, not a
proposed design) leaves this for the extension target, the one with the most positives:

| Fold | Training events | Training positives | Held back for selection / for calibration | Left to fit | Leaves at most, smallest leaf 3 / 5 / 10 events |
| --- | --- | --- | --- | --- | --- |
| tested on block 3 | 55 | 24 | 11 / 11 | 33 | 11 / 6 / 3 |
| tested on block 4 | 75 | 31 | 15 / 15 | 45 | 15 / 9 / 4 |
| tested on block 5 (now development data) | 98 | 42 | 19 / 19 | 60 | 20 / 12 / 6 |

A tree whose smallest leaf holds 5 events can have at most the number of leaves shown. A boosted ensemble of such trees, with 11 to 19 events to calibrate on, can support a two-parameter Platt fit at most; isotonic
regression, with up to one step per event, would memorize. Hyperparameters would have to come from a tiny pre-registered grid chosen inside the training folds. The other targets are in the evidence file.

### 2.4 The holdout problem

Milestone 4's final holdout (block 5, the 23 Milestone 1 events) was evaluated once and its results are known. The contract says "Freeze a final chronological holdout before iterative research", and master prompt
44 warns against "repeated tuning against the same holdout period". So block 5 cannot be Milestone 5's untouched holdout. Its seal ended with Milestone 4; in Milestone 5 it can be ordinary development data, and the 25
counted accesses are a fact about Milestone 4 that stays as recorded. **A disclosure:** the assistant writing this proposal has seen the block-5 results. Nothing here is motivated by them, the evidence module is
tested to ignore every holdout field but the sizes of the training and test sets, and Phase 0 would record in the protocol itself that the block-5 results were known when it was frozen (section 3). A promotion statement needs a fresh holdout:
events after 2026-04-01 (the data ends at the reaction session of 2026-04-01), collected outcome-blind and sealed before the Milestone 5 protocol is frozen, or events that have not happened yet. At the dataset's
own rate (128 events over 512 days, 190 days since the last reaction session) about 48 events would have occurred since, from the same issuers if they kept reporting and stayed eligible; nothing was enumerated, so that is an estimate. A fresh holdout of
that size could do no more than the Milestone 4 protocol said of its own holdout: "a replication check on direction and a single, logged exposure of the frozen pipeline to data it was not developed on; not a
source of statistical power" (section 2.2 shows why).

### 2.5 Feature families

| Family | What the master prompt lists | What exists now | What is missing | Point-in-time status |
| --- | --- | --- | --- | --- |
| Ticker reaction | issuer-level reaction history, shrunk when sparse | the issuer-history rate (Milestone 2 fingerprints; Milestone 4's C4) | depth: 4 to 6 events per issuer (none has the 10 needed for a mean or median, or the 20 for quantiles) | safe: earlier matured events only |
| Analogue | nearest historical events with exposed members | Milestone 2 analogues (at least 10 members; the distance has only timing and sector terms) | other dimensions to be similar on; with two, the sets carry no more information than the timing and sector cells Milestone 4 already used | safe by construction |
| Catalyst strength and surprise | earnings surprise, catalyst strength | Milestone 3 code (surprise against the prior period only; consensus and guidance surprise are out of scope by decision) | real values for most events: SEC's XBRL API returned HTTP 403 to the live fetch from GitHub Actions (as Milestone 3 recorded), so a computed surprise exists only for a handful of worked examples (`reports/m3-worked-example-jbss-catalyst-features-2026-09-30.json`) and most events would carry `NOT_COMPUTED`; `surprise_magnitude_band` is deferred | would be safe (filing-dated) if acquired |
| Market regime | SPY, QQQ, Russell 2000 trend, VIX, sector ETFs, breadth | nothing held | daily bars of index and sector ETF symbols through the Alpaca connector path (derived values only, per the provider-rights review); VIX is not an equity symbol, so a proxy or another source | safe if computed from bars up to the cutoff; availability of each symbol unverified |
| Market structure, from daily bars | ATR, realized volatility, average dollar volume, relative volume on daily volume, distance from 52-week high or low, previous gaps, momentum | nothing held | pre-event daily bars for each event's security (derived values only) | safe if cut at the cutoff |
| Market structure, other | float, short interest, institutional and insider ownership, premarket volume, options, implied volatility, gamma | nothing held | the contract lists "absent historical consensus and market-structure vintages" among its open risks; shares outstanding from SEC cover pages is plausible, the rest is unverified | not established: a probe is needed before any commitment |
| Text and sentiment | sentiment/NLP in the ablation list; embeddings "where justified" | nothing | a justification: events are earnings releases from a convenience sample of 23 issuers | out of scope for Milestone 5 |

Of the families, two exist and add little (ticker, analogue), one is mostly blocked (surprise), and two are obtainable with a small authorized fetch (regime, and the daily-bar part of market structure); the rest cannot be
had point-in-time from what the project holds, as far as anyone has verified.

### 2.6 Multiple comparisons

The master prompt's list multiplies: model classes, feature families as ablation units, hyperparameter settings, five targets, two versions. With intervals this wide, anything selected afterwards is noise. The
protocol would pre-register one confirmatory advanced model per primary target (chosen by a rule applied to development data only) against one pre-registered strongest baseline, keep Milestone 4's 99% level and
cluster-aware intervals, and label everything else exploratory and report it in full.

### 2.7 What "promotion" can mean in Milestone 5

The contract's promotion requirements, which it writes "for later milestones", include positive incremental economics under conservative costs and an explanation of regime weakness. This span holds one market regime and no execution data
(as the Milestone 4 report says), so those cannot be tested here; the master prompt's milestone list has the project collect realistic-entry and slippage evidence in Milestone 8. A narrow meaning is proposed: a model is *promoted* only if, on development folds, its pre-registered confirmatory contrast against the strongest pre-registered
baseline excludes zero at the claim level in the clean-window version, its calibration is within a pre-registered tolerance, and on the fresh holdout its contrast has the same direction as on development, with no significant degradation against the baseline. Promotion
would mean "carried forward as a candidate expected-reaction model for Milestone 6", not "validated for use".

### 2.8 Where this leaves the milestone

The most likely result of a faithful Milestone 5 on this data is `NOT_DISTINGUISHABLE` for every advanced model, as in Milestone 4. That is a legitimate result under "promote only improvements that survive out-of-sample
testing". What the milestone would then leave behind is a pre-registered harness extension (trees, forests, boosting, ensembles, calibration, ablation) that has been validated against independent recomputation, a
fresh sealed holdout, derived regime and market features, and a calibrated, honest record of what these events can and cannot show. The binding constraint is the number of events, not the model class.

## 3. Proposed scope

Phases, each needing its own go-ahead, as in Milestones 2 to 4. With the data steps of Phase 1 that is up to seven go-aheads (0, 1a, 1b, 1c, 2, 3 and 4), against five for Milestone 4. The numbers name the
phases; they are not the order the phases would run in. An order is proposed here after the decisions, and is not itself a decision: 1a, 1b, 0, 1c, 2, 3, 4, so that the probe shows which feature families Phase 0 can
pre-register, the fresh holdout is collected and sealed before the protocol is frozen (section 2.4), and the derived features are computed as the frozen protocol defines them:

- **Phase 0 — pre-registration (documents only).** `config/m5-protocol.json` and a short note, hashed and committed before any model is fit: targets (the five Milestone 4 primaries by default), model families (a
  small fixed list), feature families as ablation units, the tiny hyperparameter grids, the nested walk-forward design with block 5 as ordinary development data, the strongest-baseline rule, the confirmatory
  contrast per target, the promotion rule of section 2.7, the fresh holdout and its seal, the thresholds, seeds and log formats. It would also say, as Milestone 4's did, what the authors knew when it was frozen,
  including that the block-5 results are known.
- **Phase 1 — data steps, each its own go-ahead, only if decision 2 asks for them.** *1a*, an availability probe (no acquisition into the dataset): which regime and market-structure fields can be had point-in-time
  and under the provider's terms. *1b*, a forward extension, "Milestone 2 step 4": an outcome-blind enumeration and freeze of candidate events since 2026-04-01 under the same procedure and review standard as steps 2
  and 3, labels sealed from the design. *1c*, derived-feature acquisition for all events: regime and daily-bar features, derived values only.
- **Phase 2 — harness extension.** Reuse Milestone 4's data, feature, metric, registry and harness code; add standard-library decision trees, random forest, gradient boosting, bagged or stacked ensembles, Platt
  scaling (isotonic only if justified), permutation importance and the ablation runner. Leakage tests come first (inject a future label or feature and check that no earlier prediction changes), with independent
  recomputation of fits, determinism tests, abstention states and a mutation check.
- **Phase 3 — development comparison and the studies.** Walk-forward on the development folds only: the confirmatory contrast per target, calibration, ablation per feature family, full reports of everything.
- **Phase 4 — one look at the fresh holdout and the Milestone 5 report.** The frozen protocol is run once and the access logged; the report states what was estimable, what was promoted (probably nothing), every
  interval with its counts, and the limits. The acceptance decision is the owner's.

**Proposed meaning of "Milestone 5 done":** the protocol was frozen before evaluation; the leakage tests, including injected-future tests, pass; every output reproduces deterministically from committed inputs;
every result is reported with counts and cluster-aware intervals; calibration is shown; an ablation is reported for every feature family obtained; the holdout was looked at once. **It does not mean an advanced
model is promoted.**

**What Milestone 5 will not do:** rank or select candidates or produce a candidate list (Milestone 7), compute a reaction gap (Milestone 6), run a paper-trading validation (Milestone 8), backtest or model
transaction costs (no execution data exists; master prompt sections 22 and 23), make a live prediction, fit text or deep models, add a SHAP package, or acquire data beyond what the owner authorizes in Phase 1.

## 4. The data question

- **Option A: the existing 128 events only, with the features already held.** No acquisition. Block 5 becomes development data and there is no fresh holdout, so promotion is impossible by the rule of section 2.7;
  the milestone would produce a development-only comparison and say so. It is the cheapest and the least informative.
- **Option B (recommended, with C): a forward extension for a fresh holdout.** About 48 events since the data ended (an estimate), collected outcome-blind and sealed. The procedure exists
  (`docs/MILESTONE-2-STEP-2-PILOT.md` and the step 3 documents) but is real work: authorization, a cohort freeze, a review at the Milestone 1 standard, the label engine. It buys a clean holdout and some development
  data, not power.
- **Option C (with B): derived features.** Regime features from index and sector ETF bars and daily-bar market-structure features, as derived values only (the provider-rights review records that raw prices are
  never committed). It needs its own authorization, including the provider-rights-at-scale answer that earlier scale-ups needed (`docs/M2-STEP-2-CORPORATE-ACTION-CHECK-SCOPE.md`, section 3), and a probe of which symbols are available. Float, short interest, institutional ownership, options and premarket volume stay out of reach unless a point-in-time
  source is found (decision 6).
- **Option D: a larger or different universe.** The only route to real statistical power (section 2.2 puts a modest improvement at hundreds to over a thousand test events). It means a new Milestone 1 and 2 style
  pipeline for new issuers, with its own selection-bias questions, and is a project-level decision, not a precondition for a bounded Milestone 5.

## 5. Risks and how the proposal handles them

| Risk | Handling |
| --- | --- |
| No model can show a gain at these counts; over-reading noise | pre-registered confirmatory contrasts (one per primary target); everything else exploratory and fully reported; "no promotion" is a valid result; the detectability arithmetic is in the document |
| Researcher degrees of freedom: models × features × targets × versions × settings | small fixed lists and grids chosen inside training folds only; ablations exploratory; every experiment logged |
| The spent holdout contaminates design choices | block 5 is treated as development data; no choice may cite a Milestone 4 holdout result; the protocol states what was known; a fresh sealed holdout decides promotion |
| Small fit and calibration sets: unstable trees, unusable isotonic fits | tiny hyperparameter grids, Platt scaling first, abstention states, results reported with fold sizes |
| Point-in-time leakage in new features (regime, market structure, any revised data) | features cut at each event's cutoff; injected-future tests; unverified vintages declared out of scope |
| Provider terms for market data | derived values only are stored; a probe before any fetch; the owner decides on any new source; and the aggregate-at-scale question, which the project's provider attestation carries forward and the owner has answered at each scale-up, is put to the owner again before 1b or 1c |
| Issuer survivorship and a convenience sample of 23 issuers | stated in every report; nothing is described as a market base rate |
| A hand-written boosting or forest implementation has bugs | independent recomputation of fits, property tests (loss decreases, determinism, permutation invariance), a mutation check |
| Dependence (73 reaction sessions, 23 issuers) | cluster-aware intervals; events of one reaction session kept in one fold |

## 6. Decisions needed

Made on 2026-10-08, all six at the recommended default (`reports/m5-scope-confirmation-2026-10-08.json`). The items below are the proposal as it was decided; the recommended default of each is what was taken.

1. **Shape of Milestone 5.** Recommended: the bounded, pre-registered comparison of section 3 on the five Milestone 4 primary targets, with promotion defined as in section 2.7 and "no improvement shown" accepted as
   a valid outcome. Alternatives: pause Milestone 5 until a universe expansion (Option D) can grow the dataset by an order of magnitude; or the full list in the master prompt, including bought market-structure data.
2. **Data.** Recommended: Options B and C, staged and each with its own go-ahead, preceded by the availability probe. Alternatives: Option A only (no promotion possible), or Option D first.
3. **Holdout.** Recommended: a fresh sealed holdout from events since 2026-04-01, with block 5 as ordinary development data. Alternatives: reuse block 5 (against the contract; contaminated), or no separate holdout.
4. **Implementation.** Recommended: standard-library implementations validated by independent recomputation, consistent with the no-runtime-packages rule. Alternatives: pinned numpy and scikit-learn as development
   dependencies, or LightGBM or XGBoost as the master prompt names (this changes the rule).
5. **Claim level and structure.** Recommended: keep Milestone 4's structure (99% level, cluster-aware intervals, one confirmatory contrast per primary target) so results are comparable. Note that Milestone 4's
   review item on the 99% level was never answered and the defaults remain; an alternative is 95% with a correction across the confirmatory set.
6. **Market-structure features.** Recommended: probe availability first and declare float, short interest, institutional ownership, options and premarket volume out of reach unless a point-in-time source is found.
   Alternative: purchase or license a point-in-time dataset (new provider terms and cost).

## 7. What this document does not do

It writes no model code and makes no prediction, score or ranking. It acquires no data, enumerates no events and uses no new provider. It reads no event-level outcome and uses no Milestone 4 holdout result. It
does not decide any of section 6, it does not pre-register anything, and the evidence code it cites is planning arithmetic only. It does not claim that Milestone 5 can show an edge, and it does not start Milestone 5,
Milestone 6 or any later milestone. Acceptance of Milestone 5, if it is ever built, would be the owner's own declaration, as with every milestone before it.
