# Milestone 4 — the evaluation harness (Phase 1)

**Status: built and dry-run on 2026-10-06 on the owner's go-ahead for Phase 1 (`reports/m4-phase1-authorization-2026-10-06.json`). Nothing has been fitted, scored or evaluated on
any real event, and no holdout outcome has been read.** The harness is built to the frozen protocol (`config/m4-protocol.json`, version 1, sha256
`a2e1a987528b7c84f479d79d17de7910b976380749c9d54065af7830547982a9`). It is the machinery the protocol requires before any evaluation, plus the pooled base rate (C1), the comparator
every other predictor will be measured against, which is exercised on synthetic data only. Phase 2 (the other baselines) and Phase 4 (the holdout look) each need the owner's go-ahead.

**Update 2026-10-07, after Phase 2:** the owner authorized Phase 2 and the harness now evaluates the B-clock baselines on the real development folds (`docs/M4-PHASE2.md`, results in
`docs/M4-PHASE2-RESULTS.md`). Two things in this note describe Phase 1's state and are no longer current: `ALLOW_REAL_EVALUATION` is `True`, restricted to the three B-clock primaries by
`REAL_EVALUATION_TARGETS` (every other target is still refused on the real inputs), and the harness has evaluated real events. `ALLOW_HOLDOUT_LOOK` is still `False`, the holdout is still sealed (23 events,
no read, no load), and the details in section 5 are in force as written. The protocol is unchanged.

**Update 2026-10-07, after Phase 3:** the owner authorized Phase 3 and the harness now also evaluates the two C0-clock primaries (`docs/M4-PHASE3.md`, results in `docs/M4-PHASE3-RESULTS.md`).
`REAL_EVALUATION_TARGETS` lists all five primaries; the nine descriptive-only and five `INSUFFICIENT_DATA` targets are still refused on the real inputs. Two harness behaviours changed for this phase:
an all-event contrast is labelled the confirmatory contrast's companion only where the clean-window version can be evaluated (otherwise it is exploratory and says why), and M2 stops with a `ProtocolGap` naming any
event that has no opening return instead of failing on `None`. `ALLOW_HOLDOUT_LOOK` is still `False` and the holdout still sealed (23 events, no read, no load). The protocol is unchanged.

**Update 2026-10-08, after Phase 4:** the owner authorized Phase 4 and the harness took the one look at the holdout on 2026-10-07 (`docs/M4-PHASE4.md`, results in `docs/M4-PHASE4-RESULTS.md`, the Milestone 4 report in
`docs/M4-REPORT.md`). Two things in this note are no longer current. The holdout is **not sealed any more**: the chained access log holds one access (`reports/m4-holdout-access-log.jsonl`, commit `0e26ac9`, 23 events,
46 loads) and the block-5 outcomes have been read. And `ALLOW_HOLDOUT_LOOK` was turned on for that look in a commit of its own and turned off again in the next, so it is `False` again; another look needs a new
go-ahead. The tests that verify the look re-read the outcomes through the same gate against temporary logs; on the owner's decision those replays are counted as accesses
(`reports/m4-phase4-replay-accesses-2026-10-07.json`: 25 accesses in all; an earlier version of this note said 21, which counted each CI run once although its two jobs both ran them). Since the owner's word of 2026-10-08 ("make the replay tests opt-in") those replay tests are skipped unless
`M4_REPLAY_HOLDOUT=1` is set, so the default suite and CI read nothing sealed; a run made on purpose is two more counted accesses. The details in section 5 are in force as written, and the protocol is unchanged. Milestone 4 was declared accepted by the owner on 2026-10-08 (`reports/m4-acceptance-declaration-2026-10-08.json`).

## 1. What it is

```
python -m nre.m4_harness verify        # recompute the protocol hash and every pinned input hash; refuse on any mismatch
python -m nre.m4_harness plan          # the folds, thresholds and leakage assertions, as a report
python -m nre.m4_harness dry-run       # verify + plan + the cross-check against the freeze record  (--output PATH writes it)
python -m nre.m4_harness verify-logs   # check both hash-chained logs
python -m nre.m4_harness init-logs     # write the two genesis records (once, from a clean tree)
python scripts/m4_mutation_check.py    # does the test suite notice deliberate defects in the harness?
```

There is no command that evaluates anything. The real inputs support `verify`, `plan` and `dry-run` only: two module constants, `ALLOW_REAL_EVALUATION` and `ALLOW_HOLDOUT_LOOK`
in `nre/m4_harness.py`, are `False`, and a test fails if either is turned on without that test being changed too. Phase 2 and Phase 4 each turn one on, in a commit of their own.

| Module | What it does |
| --- | --- |
| `nre/m4_protocol.py` | Loads the protocol; recomputes its canonical sha256 and the hash of every input it pins (events spec, calendar, policy, sector map, event table, labels digests, block assignment, caveated labels, the two evidence reports); checks the freeze record; and checks that every number the code uses (thresholds, K, replicates, seeds, clip bounds, levels, quantiles) is the number the protocol states in its own words. |
| `nre/m4_data.py` | Loads the events with the holdout sealed; builds the all-event and clean-window versions; defines the targets, the folds, the thresholds and the leakage assertions (clusters and blocks whole, labels mature). |
| `nre/m4_features.py` | The release-timing and sector indicators, and the issuer-history rate with its group prior (and the regression analogue), computed only from earlier training events whose labels were already available. No model uses them yet. |
| `nre/m4_metrics.py` | Brier, log-loss, PR-AUC, precision at K with the seeded random ranking, reliability bins, false positives and negatives, terciles, pinball loss, interval coverage, the cluster bootstrap with its headline interval, and the decision rule. Pure functions: they are handed predictions and outcomes and nothing else. |
| `nre/m4_registry.py` | The experiment log and the holdout access log: JSON lines, each carrying the sha256 of the line before it, each starting with a genesis record. |
| `nre/m4_harness.py` | The runner: verify, plan, dry-run; C1 (the pooled rate, and the pooled quantiles for the Day-1 return); development-fold evaluation with fold states, pooled predictions, metrics, contrasts and log records; the holdout gate. |

## 2. The eight tests the protocol requires

Each is a test in `tests/test_m4_harness.py` (the real-input versions need only identities, times and the labels of blocks 1 to 4).

| Protocol requirement | How it is tested |
| --- | --- |
| Label maturity | Every fold, every target and all sixteen labels are checked before anything is fitted, on the real folds (the smallest slack is 12.01 days, the protocol states 9 to 19 at the block boundaries) and on synthetic folds with a label made to mature late. A violation stops the run before any `fit`. |
| Injected future | Reversing the labels inside every later block changes no earlier prediction or model, and flipping the labels of every event on or after an event's session changes none of that event's history features; the thresholds are unchanged by the change, so the comparison is real. |
| History features | For every fold, target and event (real and synthetic), the history used is training-block only, reacted on an earlier session, and was available at the event's cutoff. A later or same-session event with a wrongly early availability stamp is still excluded. |
| Holdout sealing | See section 3. |
| Protocol integrity | Changing any one of the protocol, the freeze record's hashes, the events spec, the calendar, the policy, the sector map or either evidence report makes `from_repository` refuse, naming the failing check. A changed constant in the code, or a changed derivation map, is caught against the protocol's text. |
| Determinism | The same inputs and seeds give identical canonical output and hash (a binary target with a second predictor, the regression target, and the real dry run); changing a seed changes the interval it seeds and nothing else. |
| Clusters | No reaction session, cluster or block is split between a fold's training and test events; the check is exercised on deliberately split data and holds on the real folds. |
| Abstention | A predictor that cannot be fitted, or a target below the thresholds, gives null predictions with a reason and the state `MODEL_FIT_FAILED` or `INSUFFICIENT_DATA`; no prediction, metric or contrast is substituted. |

## 3. What "sealed" means here, and what it does not

- **No outcome is read at load time.** The ordinary loader (`fp.load_inputs`) opens every event's record to check its labels against the pinned digest, block 5's included. The harness
  does not use it. The 23 holdout events are built from the spec alone (identity, timing, sector and the pinned digest) and carry a `SealedLabels`, which raises on every way of reading
  it. Their record files are opened only by a loader the gate holds, and only when the gate unseals them. A test destroys all 23 record files and shows that the whole dry run still
  works and produces a byte-identical report.
- **The only way to the labels is `Harness.look`,** which first checks the tripwire, then writes an access record (number, reason, the events, the protocol hash, the commit) to the
  hash-chained holdout log, and only then unseals. If the record cannot be written, nothing is read. Each look is a further record, so the report can state the number of accesses. A
  source-scan test asserts that no other code in the harness calls `unseal`.
- **A predictor never sees a test event's outcome.** It is handed the training events (with their labels) to fit, and for each test event a view without `labels` or their digest
  (and, for the C0 clock only, the opening gap, which is known at the open).
- **What it cannot do.** This is a process control inside a Python program, not secrecy: anyone can open the record files. What it guarantees is that no code path in the harness
  does so except the logged look, that every look is on the record, and that the repository's history shows when the tripwire changed. The protocol's own disclosure stands: block
  5's counts of positives were visible in the scoping evidence before the freeze, so the holdout is sealed against model selection and tuning, not against knowing its base rates.

## 4. What the dry run showed

`reports/m4-harness-dry-run-2026-10-06.json` (reproduced by a test from the committed inputs). It evaluates nothing.

- All 18 integrity checks pass on the real inputs.
- For the five primary targets, both versions and all three folds, the training counts, the development test counts (defined events, positives, negatives), the fold-level threshold
  results and the development statuses computed by this harness agree exactly with those frozen in `reports/m4-protocol-freeze-2026-10-06.json`, which were computed by a different
  code path. No disagreement. (The holdout's own test counts are not recomputed: that would read block 5.)
- The consequences the protocol stated in advance reproduce: `loses_half_of_gap` in the clean-window version has 9 training positives in development fold 3 (that fold is
  `INSUFFICIENT_DATA`), its pooled development test is then the 10 events of fold 4, and so the target is `INSUFFICIENT_DATA` for the clean-window claim rule; `gap_ge_5pct` has exactly
  10 positives in the pooled development test in both versions, the minimum that passes.
- Every fold clears the label-maturity assertion, with 12.01 to 19.0 days of slack (9.01 to 19.0 at the four block boundaries). No purge is needed, as the protocol said.
- The holdout: 23 events sealed, 0 refused reads, 0 loads. The holdout fold is shown with its training counts and a seal where its test counts would be.

## 5. Where the protocol is silent, and what the code does

The harness had to decide these. None depends on an outcome; each is documented here so that the owner can amend the protocol (a new version, with a record) before Phase 2 if any is
unwanted. **The first five could move a result.**

1. **The headline interval.** "The wider of the two intervals" is read as the interval of greater width (high minus low) at each level, `reaction_session` on a tie. A union of the two
   would be a wider and more conservative choice.
2. **Regression history mean with no earlier event.** The protocol gives the binary rate a default (p = 0.5) but gives the regression history mean none. The code raises
   `ProtocolGap`: the ridge model (M3) cannot be completely specified until this is decided (drop those training events, use the pooled mean, or something else).
3. **Standardization.** "The standard deviation of the training events" is not said to be the population or the sample one. Not implemented yet; it changes the ridge and logistic
   penalties slightly.
4. **A predictor that fails in one fold.** Its whole pooled result takes that state and its contrast is withheld; nothing is pooled over the folds that did fit. The comparator is still
   evaluated.
5. **The group prior and maturity.** The earlier-session and label-availability conditions apply to the group prior as well as to the issuer's own history ("earlier than this event" is read
   as an earlier reaction session). The group is the same SIC major group and includes the issuer's own earlier events.
6. **"At least 40 training events" for regression** counts the training events with the target defined (stricter), and any fold also needs 40 events in its training blocks.
7. **Ties.** Equal scores are ordered by event id (ascending) for precision at K; reliability bins and terciles order by (score, event id) ascending, cut into equal parts with the remainder
   to the first. PR-AUC is tie-invariant. For C1, whose predictions are constant within a fold, precision at K is therefore uninformative by construction; the seeded random ranking is the yardstick.
8. **Lift base for a pooled K** is the mean of the events' fold training base rates; false positives and negatives use each event's own fold's base rate as its threshold.
9. **Random rankings and bootstraps.** Each context starts a fresh generator at the protocol's seed, using `random.random()` only (the stream is the same on every supported Python); a
   ranking draws one number per event in event-id order.
10. **A sector division the protocol does not name** (it names D, I and B, E, F, G; the data has no other) is a `ProtocolGap`.
11. **A pooled test below its thresholds makes no predictions at all** (they are not computed and hidden).
12. **Terciles** count events without a Day-1 return but average only those with one. **The C0 prediction time** is the regular open from the calendar.

## 6. How the tests were checked

The tests were run against 45 deliberately introduced defects (`scripts/m4_mutation_check.py`): history that ignores maturity or the earlier-session rule, a fold that trains on its test
block, a fit that sees the test events, a predictor shown the labels or their digest, a sealed read that returns instead of raising, a look that reads before it logs or ignores its tripwire,
a loader that opens the holdout records, thresholds off by one, a sign or a headline choice reversed, unseeded random draws, an unchecked protocol or input hash, a log that does not chain.
The script reports each as CAUGHT or NOT CAUGHT and never modifies the repository; a test asserts that every defect's source text still matches, so a refactor cannot turn the check into a
silent pass. Four defects were not caught on the first run (the earlier-session rule standing alone, a holdout block that is not the last, a log that starts without its genesis, an unchecked derivation map) and the missing tests were added; the final run's tally is in `reports/m4-phase1-completion-2026-10-06.json`.

## 7. What it does not do

- It evaluates no predictor on any real event, and no baseline beyond C1 exists: C2, C3, C4, the logistic and ridge models and their sensitivities are Phase 2, and the C0 baselines Phase 3.
- It does not read, score or look at the holdout; that is Phase 4. Nor does it yet produce the descriptive report (counts, base rates and Wilson intervals for the descriptive-only and
  `INSUFFICIENT_DATA` targets): its counts include block 5's, so it belongs with the final report.
- It does not amend the protocol, add data, or accept Milestone 4.
- It says nothing about whether any predictor beats the base rate. The protocol expects most primaries to be NOT_DISTINGUISHABLE and the holdout to support counts only for most targets.
