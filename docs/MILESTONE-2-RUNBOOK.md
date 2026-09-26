# Milestone 2 runbook — step 1: reaction fingerprints and analogue retrieval

**Status: step 1 is built and awaits the project owner's review. Milestone 2 is not accepted, and step 2 (data depth) is undecided.** The scope is `docs/M2-SCOPE-PROPOSAL.md` as the owner confirmed it (`reports/m2-authorization-2026-09-26.json`, `reports/m2-scope-confirmation-2026-09-26.json`). The build is recorded in `reports/m2-step-1-build-record-2026-09-26.json`.

## What it does and does not do

It describes the 23 accepted Milestone 1 events. For a target, which is either an accepted event at its own cutoff or a new event described by what is known about it, it returns grouped base rates with counts and uncertainty (fingerprints) and comparable earlier events (analogues), and it says so plainly when there is not enough to answer. It reads only committed files, uses no network, prices or credentials, and modifies no Milestone 1 record.

It does not predict, score or rank, has no model, uses no pre-event numeric features, and covers earnings results only. Nothing it prints is a statement about the market.

## Inputs and integrity

| Input | What it is |
| --- | --- |
| `config/m1-events.json` and the per-event records it names | The accepted events and their derived labels |
| `config/sector-map.json` | SIC code of each issuer, read from SEC on 2026-09-26, with each response's SHA-256 |
| `config/fingerprint-policy.json` | Every threshold and weight; the values the owner confirmed |

Loading refuses to run when a record's labels do not reproduce the digest pinned in the spec (all 23 do), when a record's identity or timing disagrees with the spec, when a label is missing, or when an issuer has no SIC entry. Every output stamps the policy hash, the sector-map hash, a hash of the event table and each event's label digest.

## Commands

```bash
python -m nre fingerprints --output reports/m2-fingerprints-2026-09-26.json
python -m nre fingerprints --event rekr-2026-03-31 --output chain.json
python -m nre analogues --event rekr-2026-03-31 --label session_5_close_return --output query.json
python -m nre analogues --descriptor tests/fixtures/m2_new_event_example.json --output query.json
python -m nre analogues --all-targets --output reports/m2-analogue-pools-2026-09-26.json
```

- `fingerprints` without a target writes the whole table as of `--as-of` (default: once every label has matured). With `--event` or `--descriptor` it writes the chain of groups the target belongs to, from earlier matured events only.
- `analogues` answers for one target and any number of `--label` options (default: all sixteen). `--all-targets` treats every accepted event as a historical target and reports how many matured events each could draw on.
- A new-event descriptor holds `release_timing` (`premarket` or `after_hours`), `as_of`, and `sic` or a mapped `cik`; it may add `cluster_id` and `category`.
- Errors print a structured JSON message to stderr and exit 2.

## Reading an output

**A statistic** has a state. `REPORTED` means the count met the reliable minimum, `REPORTED_UNRELIABLE` that it met the reporting minimum but not the reliable one, and `WITHHELD` that it did not, in which case no estimate is given. The thresholds are in the policy file: proportions from 5 (reliable from 10), mean and median from 10 (from 20), quantiles from 20. `n` is the number of events with the label, `gate_n` the number the thresholds were compared with (events or distinct reaction sessions, per `count_unit`), and `n_absent` the events whose label does not exist, with reasons.

**A cell** is one group at one level. It carries `counts` (events, issuers, distinct reaction sessions) and `parent`. When every statistic of every label is withheld it is written compactly with its counts and `n_by_label` and no estimates; read the parent cell instead. `pooled` (or `pooled_mean`) shrinks a reported estimate toward the nearest reported ancestor with a fixed prior strength; it names that ancestor in `toward` and never changes `n`.

**An analogue query** has a `state`: `ANALOGUES_FOUND`, or `INSUFFICIENT_ANALOGUES` (members are still listed, and there is no summary). `distance_reached` is how far it had to look. Distance counts a release-timing mismatch and a sector mismatch (same major group 0, same division 0.5, other 1) and never uses a label. `members` lists each analogue with its attributes, distance, weight and the outcomes that had matured by the target's cutoff. `excluded` lists every other event with its reason: `SELF`, `SAME_CLUSTER`, `LABEL_NOT_YET_MATURED`, `LABEL_ABSENT`, `CLUSTER_ALREADY_COUNTED`, `BEYOND_EXPANSION` (eligible but not needed to reach the minimum) or `BEYOND_MAX_DISTANCE`.

**The pool report** gives, for each accepted event as a target and each label, how many matured events existed (`eligible`), how many became analogues, and whether an answer was possible, plus a summary by horizon.

## The point-in-time rule

A label becomes available at the close of the last session in its window plus one minute, recomputed from the calendar as Milestone 1 does; a test builds a bundle through the Milestone 1 engine and checks every label's availability against this rule. An event enters a statistic only for labels available at the target's cutoff, so a day-1 label is usable earlier than the same event's session-20 label. A label available exactly at the cutoff is usable. The target's own cluster is never used, and events in one cluster count once. An absent label is reported as absent only once its window has closed.

Tests cover each of these, including a mutation-style test around the exact cutoff, an injected future event, and a test that replaces every label value with junk and shows that the choice of analogues does not change. A separate check on a scratch copy applied 26 deliberate bugs to the two modules and each made at least one test fail.

## Limits to keep in mind

- **Convenience sample, one event per issuer.** The 23 events were chosen because a minute-stamped wire release and a clean SEC neighbourhood existed. Issuer-level statistics are withheld by construction, and only seven cells report anything: all events, the two timing classes, the divisions Manufacturing and Services, and major groups 28 and 73.
- **SIC is not point-in-time.** It is each issuer's assignment when read on 2026-09-26.
- **Raw returns and shared dates.** Labels are not market-adjusted and 12 of the 23 events share a reaction session with another, so same-day market moves are shared; counts and intervals treat events as independent.
- **Two conditional labels.** `positive_gap_retained_half` and `positive_gap_filled` exist only after an opening gap of at least 0.5%; that is those labels' definition and the one place where an outcome decides whether a label exists.
- **Little history at early cutoffs.** Treated as targets at their own cutoffs, the earliest accepted event has nothing matured to draw on, and session-20 labels have five or more matured events for only 7 of 23 targets (`reports/m2-analogue-pools-2026-09-26.json`).
- **The analogue minimum is below the mean and median minimum.** With the confirmed defaults an analogue set needs 5 members but a mean or median needs 10, so an analogue set exists for 13, 12, 11, 8 and 4 of 23 targets at the day-1, session 2, 5, 10 and 20 return labels, and a mean or median is reported for only 3, 1, 1, 2 and 1 of those. The members are always listed. Raising the minimum to 10 would make every set that exists carry a mean and median, for fewer targets; that is the owner's decision and has not been made.

## Changing the policy

The values in `config/fingerprint-policy.json` are the ones the owner confirmed. A change needs the owner's approval first; it changes the policy hash stamped into every output, and the tests that pin the confirmed values and the committed reports fail until both are updated on purpose.

## Regenerating the committed reports

The tests regenerate every committed `reports/m2-*` file from the inputs and compare. To refresh them after an intended change:

```bash
python -m nre fingerprints --output reports/m2-fingerprints-2026-09-26.json
python -m nre analogues --all-targets --output reports/m2-analogue-pools-2026-09-26.json
python -m nre analogues --event rekr-2026-03-31 --label day1_close_return --label session_5_close_return --label session_20_close_return --label positive_gap_filled --output reports/m2-analogue-example-historical-2026-09-26.json
python -m nre analogues --descriptor tests/fixtures/m2_new_event_example.json --label day1_close_return --label session_5_close_return --label session_20_close_return --label positive_gap_filled --output reports/m2-analogue-example-new-event-2026-09-26.json
```

The historical example is the latest accepted event by cutoff, which has the most matured events to draw on; the new-event example is an illustrative descriptor (an after-hours software issuer asked about on 2026-09-26), not a real event.
