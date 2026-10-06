# Milestone 4 — pre-registered evaluation protocol, version 1 (a readable summary)

**Status: frozen 2026-10-06T14:45:11Z on the owner's go-ahead for Phase 0 (`reports/m4-phase0-authorization-2026-10-03.json`). The protocol is
`config/m4-protocol.json`; its canonical sha256 is `a2e1a987528b7c84f479d79d17de7910b976380749c9d54065af7830547982a9`, recorded in `reports/m4-protocol-freeze-2026-10-06.json` together with the pinned inputs, what had
been seen before freezing and a pre-freeze count check. Nothing has been fitted, scored or evaluated, and the sealed holdout has not been touched. This note summarizes the
protocol; where it and the JSON differ, the JSON governs. The only code added with the freeze is a guard test that fails if the frozen file or its pinned inputs change.**

## 1. What the protocol is for

It fixes, before any baseline exists, how simple baselines will be evaluated on the 128 accepted earnings events, and what counts as a statement about them. It measures what
the data can and cannot show; it is not designed to demonstrate an edge. It says in advance that **most targets are expected to be NOT_DISTINGUISHABLE from the pooled base
rate, and that the holdout is expected to support counts only for most targets.** Both are acceptable outcomes.

The owner's four scope decisions are encoded as rules: all four families with rare targets as `INSUFFICIENT_DATA`; block 5 sealed as the holdout; clean-window and all-event
results side by side with clean-window driving; the existing 128 events, labels only. The primary-target list and every numeric constant are the assistant's defaults and open to
review (section 9).

## 2. Targets

| Primary target | Family | Clock | Eligible events | At freeze |
| --- | --- | --- | --- | --- |
| `gap_ge_3pct` | opening gap | B | all events | 40 positives of 128 |
| `gap_ge_5pct` | opening gap | B | all events | 29 positives of 128 |
| `day1_close_return` | Day-1 move | B | all events | 128 events, regression (10th, 50th, 90th percentiles) |
| `extension_after_open_ge_5pct` | continuation/fade | C0 | all events | 54 positives of 128 |
| `loses_half_of_gap` | gap retention | C0 | events whose opening gap is at least 0.5% (positive_gap_retained_half is defined) | 25 positives of 60 |

- **Descriptive only** (counts, base rates, Wilson intervals, per-block counts; nothing fitted, no statement about skill): `gap_ge_10pct` (14), `day1_high_ge_10pct` (33), `day1_high_ge_20pct` (12), `day1_close_ge_10pct` (22), `extension_after_open_ge_10pct` (23), `session5_close_ge_10pct` (27), `session5_close_ge_20pct` (16), `full_gap_fill` (28), `closes_below_open` (72).
- **`INSUFFICIENT_DATA` by rule** (fewer than 10 positives or negatives; counts, the base rate and its interval are still reported, and nothing is modelled): `gap_ge_15pct` (5), `gap_ge_20pct` (3), `gap_ge_30pct` (0), `day1_high_ge_30pct` (5), `day1_close_ge_20pct` (6).

## 3. Clocks and features

- **B, at the release.** The event's cutoff (release plus three or five minutes). Features: `after_hours`; the sector group (SIC division D, I or other; read 2026-09-26, so each
  model is also run without it); and the issuer's own earlier outcomes on the same target, shrunk toward a group prior with strength 10. All computed from the fold's training
  blocks only.
- **C0, at the regular open.** The same, plus `open_gap` (the opening print as a return). A separately registered clock, not Model C, whose clock (open plus 15 minutes) needs
  intraday data. Model A needs a schedule that was never captured. Neither is built.
- No other feature may enter a model: no surprise, consensus, volume, momentum, volatility, float, short interest, market-structure or regime feature.

## 4. Folds and the holdout

The events fall in five blocks of 17, 44, 21, 23, 23 events, cut wherever consecutive reaction sessions are more than 28 days apart. Expanding window:

| Test block | Trained on | Role |
| --- | --- | --- |
| 2 | block 1 (17 events) | not used: below the 40 events needed to fit anything |
| 3 | blocks 1, 2 (61) | development |
| 4 | blocks 1 to 3 (82) | development |
| 5 | blocks 1 to 4 (105) | sealed final holdout, one look |

No purge or embargo is needed: at every boundary all training labels are available before the next block's first cutoff, with 9 to 19 days to spare, and the harness must assert
it. Development metrics use the two folds' out-of-fold predictions pooled (44 events). **The holdout is Milestone 1's 23 events, selected very differently from the rest, so
time and selection regime are confounded in it, and every holdout result says so.** Its outcome counts were already visible in the scoping evidence: it is sealed against
model selection and tuning, not against knowledge of its base rates. It is read once, with every predictor, and every read is logged.

## 5. The caveat rule

Everything is computed twice. **Clean-window** treats the caveated (event, label) pairs, plus the labels derived from them, as absent: for the target, for training, for test
outcomes and for the issuer-history feature. **All-event** uses every label. The clean-window version drives the claim rule (and any selection, though none is planned); the
all-event version is always shown beside it and can only disagree with a claim, never create one. The caveated pairs are pinned by hash.

## 6. Predictors, metrics and the claim rule

- **Comparators:** C1 pooled training rate (the headline comparator), C2 by timing, C3 by sector group, C4 the issuer-history rate, and a seeded random ranking. **Models:** M2, a
  ridge logistic regression (lambda fixed at 1, no tuning), and for the Day-1 close return M3, a ridge linear regression with quantile outputs from training residuals. Each
  is also run without the sector feature. Nothing else: no trees, no ensembles, and no calibration transform (it could not be fitted or validated at these sizes).
- **Primary metric:** Brier score for binary targets and mean pinball loss at the 10th, 50th and 90th percentiles for the Day-1 close return; the contrast is the model minus C1.
  Secondary: log-loss, PR-AUC, precision at K, reliability bins with counts, false positives and negatives, expected return by tercile, interval coverage.
- **Intervals:** a cluster bootstrap (5000 replicates) by reaction session and by issuer, taking the wider; 95% for reporting and **99% for claims** (five primary targets, one
  contrast each). It covers test-sample uncertainty, not variability across training sets.
- **Claim rule:** `DISTINGUISHABLE_BETTER` only if the clean-window 99% interval lies entirely below zero and the all-event point estimate is also below zero (symmetrically for
  `DISTINGUISHABLE_WORSE`); otherwise `NOT_DISTINGUISHABLE`, or `INSUFFICIENT_DATA` if the thresholds below are not met. Every other contrast is exploratory and cannot support a
  claim, and no status is a claim of a tradable edge. The holdout alone never creates a claim.

## 7. `INSUFFICIENT_DATA` thresholds

| Level | Rule | Result |
| --- | --- | --- |
| Target | fewer than 10 positives or negatives among its defined events | not modelled |
| Fold | fewer than 10 positives or negatives among the fold's training events | no predictor evaluated for that target, fold and version |
| Pooled development test | fewer than 10 positives or negatives | `INSUFFICIENT_DATA`, counts only |
| Holdout | fewer than 10 positives or negatives | `COUNTS_ONLY` |
| Regression | fewer than 40 training or 20 test events | `INSUFFICIENT_DATA` (development), `COUNTS_ONLY` (holdout) |
| Metrics | PR-AUC needs 10 pooled positives; precision at K needs 2K events; bins need 10 predictions each | not computed |

A result that cannot be computed is reported as missing and is never filled with a default, a pooled value or a zero.

## 8. States, logs and seeds

Every prediction record carries `MODEL_NOT_VALIDATED`, `NO_QUALIFIED_OPPORTUNITY` and confidence `VERY_LOW`; `QUALIFIED` and any higher tier are never emitted. Experiments and
holdout accesses go to two append-only JSONL logs whose records chain by hash. Seeds are fixed in the protocol (410001, 410002, 410003). Eight leakage and integrity tests must
exist before any evaluation, including a refusal to run if the protocol or a pinned input does not match its hash.

## 9. What the freeze says to expect, and what to review

The pre-freeze count check (labels only, fitting nothing) gives these statuses:

| Primary target | Development, all-event | Development, clean-window | Holdout, all-event | Holdout, clean-window |
| --- | --- | --- | --- | --- |
| `gap_ge_3pct` | EVALUABLE | EVALUABLE | COUNTS_ONLY | COUNTS_ONLY |
| `gap_ge_5pct` | EVALUABLE | EVALUABLE | COUNTS_ONLY | COUNTS_ONLY |
| `day1_close_return` | EVALUABLE | EVALUABLE | EVALUABLE | EVALUABLE |
| `extension_after_open_ge_5pct` | EVALUABLE | EVALUABLE | EVALUABLE | EVALUABLE |
| `loses_half_of_gap` | EVALUABLE | INSUFFICIENT_DATA | COUNTS_ONLY | COUNTS_ONLY |

- `loses_half_of_gap` has 9 training positives in development fold 3 in the clean-window version, one under the threshold, so it cannot support a clean-window claim. The
  thresholds were not changed to rescue it.
- `gap_ge_5pct` has exactly 10 positives in the pooled development test set, the minimum that passes.
- With 43 or 44 pooled test events and a 99% interval, a `DISTINGUISHABLE_BETTER` status needs a very large improvement; most primaries are expected to be `NOT_DISTINGUISHABLE`.

**Worth the owner's review before Phase 1:** whether the two thin primaries (`gap_ge_5pct`, `loses_half_of_gap`) belong among the primaries; the 99% claim level; that the holdout
will mostly be counts only; and the issuer-history and sector features given their point-in-time limits. The numeric constants are listed in the protocol under
`disclosures.numeric_constants_chosen_by_the_assistant`.

## 10. Amendments

Any change is a new protocol version with its own hash, committed with a record of what changed, why, and what had been looked at. Before a development fold is evaluated it
needs the owner's instruction; afterwards it must also state that earlier results were seen. After the holdout look, the holdout is reported under the version in force at the
look. Version 1 has none.
