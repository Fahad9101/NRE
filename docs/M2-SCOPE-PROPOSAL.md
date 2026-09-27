# Milestone 2 — scope proposal (for the project owner's review)

**Status: scope confirmed by the project owner on 2026-09-26 ("confirm and push", taking all six defaults in section 6). Building step 1 is authorized; step 2 is not. Nothing described here was built when this status was written; step 1 has since been built and awaits the owner's review (section 8).** Written 2026-09-26, after the owner replied "approve" to the recommendation quoted in section 1. Records: `reports/m2-authorization-2026-09-26.json` and `reports/m2-scope-confirmation-2026-09-26.json`. Any change to a confirmed default needs the owner's approval first.

## Summary

- **Proposed (step 1):** build Milestone 2's two components offline on the 23 accepted events: reaction fingerprints (grouped base rates with counts and uncertainty) and analogue retrieval (point-in-time comparable events), with the leakage tests and sparse-data suppression the Milestone 0 contract requires. No prediction, no models, and no change to any Milestone 1 record.
- **What checking the data showed:** with 23 events, one per issuer, most answers will be "insufficient data". Treating each event as a historical target at its own cutoff, a day-1 label has at least five matured events to draw on for 17 of 23 targets, but the session-20 label for only 7 (section 3.3). Step 1 can show that the machinery obeys the contract. It cannot show defensible comparable events for a typical target, as the recommendation you approved already said, and I would not call Milestone 2 accepted on step 1 alone.
- **What I need from you:** confirm step 1 (the defaults in sections 4 and 6; a one-line reply is enough), and decide step 2, the data-depth push (section 5), whenever you choose.

## 1. What "approve" is taken to mean

The owner's reply, on 2026-09-26, was the single word "approve". It answered this recommendation:

> I'd approve Milestone 2 in two steps: first the fingerprint machinery and leakage tests on what exists, with sparse-suppression on. Its outputs will mostly say "insufficient data". Then decide separately whether to fund the depth push, which is the real work. If you approve, I'll write a scope proposal for you to review before touching anything.

The reading taken here: **step 1 is approved, subject to the owner's review of this proposal; step 2 is not approved.** The reading is the assistant's. If "approve" meant something else, say so and `reports/m2-authorization-2026-09-26.json` will be corrected. Nothing in this changes the accepted Milestone 1 state, the frozen BOE, SOE and IEE rules, or the rule that no predictive claim is made.

## 2. Target and what "defensible" means

The master prompt's Milestone 2 asks for company-level event histories, sector histories, event-type histories, reaction statistics and analogue retrieval, accepted when: "Given a historical/new event, the system can return defensible comparable historical events and reaction distributions."

The Milestone 0 contract (section 10 for fingerprints and analogues, section 11 for anti-leakage, section 6 for labels) already fixes what defensible means, and this proposal adds nothing to it:

- Point-in-time: only matured labels are used, and analogue selection never looks at realized returns.
- Sample counts and uncertainty are always reported. Broad event-category and sector base rates come first, and partial pooling or shrinkage replaces a ticker-specific model when data are sparse.
- Every analogue is exposed with its security, date, category, source, distance, feature values and outcomes. Weighted samples report an effective sample size, and correlated event clusters do not inflate counts.
- Sparse quantiles are suppressed or marked unreliable, and the system abstains explicitly when there is not enough data.

How each build item is handled in step 1, and what today's data gives it:

| Master-prompt build item | Step 1 | Today's data |
| --- | --- | --- |
| Company-level event histories | Issuer cells | Empty by construction: one event per issuer |
| Sector histories | SIC major-group and division cells | Two of 13 major groups have more than one event (six each) |
| Event-type histories | The category cell | One type only (earnings results); other types need Milestone 3 |
| Reaction statistics | Counts, Wilson intervals, mean, median and quantiles behind thresholds, partial pooling | Reportable at coarse levels only |
| Analogue retrieval | Point-in-time retrieval with an audit and explicit abstention | See section 3.3 |

## 3. What today's data can and cannot support

### 3.1 The accepted dataset

| Property | Value |
| --- | --- |
| Events and issuers | 23 events, 23 issuers; 22 are eligible for the Milestone 1 minimums (a dividend suppresses CXT's session-20 label) |
| Events per issuer | Exactly one |
| Event types | Earnings results only |
| Timing classes | 7 premarket, 16 after-hours |
| Reaction sessions | 2026-01-22 to 2026-04-01: 16 distinct dates for 23 events, five dates shared by 12 events |
| Features per event | 16 derived labels (8 return labels and 8 boolean labels) plus metadata; no pre-event numeric features |
| SIC divisions | Manufacturing 10, Services 8, Retail 2, Wholesale 1, Transport and communications 1, Mining 1 |
| SIC major groups | 13 distinct: 28 (chemicals and pharma) 6, 73 (business services and software) 6, and eleven groups of one |

SIC codes were read from SEC company records on 2026-09-26. They are the current assignment, not point-in-time.

<details><summary>SIC by issuer</summary>

SLSN 2844, CXT 3490, ACHV 2835, COLL 2834, LOVE 5712, ASPN 5030, LNSR 3841, ASMB 2834, TECX 2836, REKR 3669, TTWO 7372, JBSS 2060, NBIX 2836, CACI 7373, VSAT 4899, HURN 8742, PARR 1311, KLC 8351, PDFS 7372, ALKT 7372, OKTA 7372, REAL 5900, PAYO 7389.

</details>

### 3.2 What the proposed thresholds allow at today's group sizes

This is for a new event queried now, when every label has matured. The thresholds are in section 4: gap-flag proportions need n of at least 5 and are flagged unreliable below 10; return mean and median need 10 and are flagged below 20; quantiles need 20.

| Group | Events | Gap-flag proportions | Return mean and median | Return quantiles |
| --- | --- | --- | --- | --- |
| All earnings results | 23 (22 for session 20) | reported | reported | reported |
| After-hours | 16 (15 for session 20) | reported | reported, unreliable | withheld |
| Premarket | 7 | reported, unreliable | withheld | withheld |
| SIC division Manufacturing | 10 (9 for session 20) | reported | reported, unreliable (session 20: withheld) | withheld |
| SIC division Services | 8 | reported, unreliable | withheld | withheld |
| Major group 28 | 6 | reported, unreliable | withheld | withheld |
| Major group 73 | 6 | reported, unreliable | withheld | withheld |
| Everything else: the four other divisions (Retail 2, Wholesale 1, Transport 1, Mining 1), the eleven other major groups, and all 23 issuers | 1 to 2 | withheld | withheld | withheld |

Two boolean labels, `positive_gap_retained_half` and `positive_gap_filled`, exist only for events that opened at least 0.5% above the prior close: 12 of the 23 overall and no more than 12 in any group, so they are withheld in more groups than the table shows.

### 3.3 Point-in-time pools for historical targets

A historical target sees only events whose labels had matured by its own cutoff, and the events sit close together in time, so its pool is far smaller than the table above. Each of the 23 events was treated as a target at its own recorded cutoff. The count is how many other events' labels had matured by then. It comes from calendar dates and cutoffs alone; no return value enters it.

| Label | Targets with 5 or more matured events | 10 or more | 20 or more | None |
| --- | --- | --- | --- | --- |
| Day-1 (returns and gap flags) | 17 of 23 | 13 | 3 | 1 |
| Session 2 | 16 | 10 | 3 | 1 |
| Session 5 | 16 | 8 | 0 | 1 |
| Session 10 | 10 | 7 | 0 | 3 |
| Session 20 | 7 | 4 | 0 | 7 |

The earliest target has no matured events at all, and no target reaches 20 matured session-5, session-10 or session-20 labels. Step 1 reproduces this table as a test.

### 3.4 Dependence and input integrity

- **Shared dates.** Twelve of the 23 events share a reaction session with another event, so their raw returns share market-wide moves. The labels are raw returns, not market-adjusted. Every cell therefore reports events, issuers and distinct reaction sessions side by side, and the contract's date-block concern is a stated limit rather than a hidden one.
- **Integrity.** All 23 committed per-event records reproduce the label digests pinned in `config/m1-events.json` when recomputed from their committed values (checked 2026-09-26). The two 2026-09-23 records (SLSN and CXT) predate the field that records why a label is null, and the engine's documented null reasons reproduce their pins. Step 1's loader repeats the check and refuses to run on any mismatch.

### 3.5 What this means for acceptance

Step 1 can show that when the system answers, the answer obeys the contract, and that it abstains when it should. It cannot show that comparable events exist for a typical target. Whether Milestone 2's acceptance criterion is met in substance therefore depends on step 2, or on the owner accepting a transparent, abstaining system as "defensible" on this dataset. That is the owner's decision and is not made here.

## 4. Step 1 — proposed scope

**Files** (standard library only, deterministic, offline):

- `nre/fingerprints.py`: loading with the integrity check, grouping, statistics, pooling and suppression.
- `nre/analogues.py`: point-in-time eligibility, distance, retrieval, the exclusion audit and abstention.
- `config/fingerprint-policy.json`: every threshold and weight in the table below; its hash is stamped into every output.
- `config/sector-map.json`: SIC by CIK for the 23 issuers, with the source and hash of the SEC payload each came from. The source is the frozen archive payloads that the cohort freeze already hash-pins, if the archive is available; otherwise a fresh retrieval whose hash is recorded.
- Two subcommands in `nre/cli.py` (`fingerprints`, `analogues`), derived-only reports under `reports/`, tests, and a runbook section.

**Inputs.** The 23 committed per-event records and `config/m1-events.json`. No network, no prices, no credentials. Nothing in Milestone 1's acceptance logic, protocol or records is modified. (`nre/dataset.py`'s `write_snapshot` was later touched, 2026-09-27, only to close a leaked SQLite connection handle before renaming/removing its directory — Windows enforces file locks that POSIX doesn't, so the unclosed handle blocked cleanup there. This fixed the three Windows-only test errors this section originally referenced; it is a portability fix with no bearing on labels, hashes or any accepted output, and `write_snapshot` is still not used anywhere in the real acquisition or audit path.)

**Queries.** A target is either a historical event (by id, at its own recorded cutoff, excluded from its own pool) or a new event described by category, release timing, sector and an as-of timestamp. Only attributes known at the cutoff are used.

**Point-in-time rule.** As Milestone 1 defines it: a label becomes available at the close of the last session in its window plus one minute, recomputed from the calendar and never from prices. An event enters a statistic only for labels that had matured by the target's cutoff, so its day-1 label can be used earlier than its session-20 label. A label available exactly at the cutoff is usable, as in Milestone 1. Events in the same cluster count once.

**Fingerprints.** Grouping levels are all earnings results, timing class, SIC division, SIC major group and issuer. For each label in each group: counts (events, issuers, distinct reaction sessions, and non-null n per label); boolean labels as proportions with Wilson 95% intervals; return labels as mean and median and, at higher counts, quantiles; and partial pooling toward the parent group with a fixed prior strength. The strength is a policy parameter and not fitted, because estimating a between-group variance from 23 events would only add noise. A withheld cell shows no estimate of its own and names the parent it falls back to.

**Analogue retrieval.** For a target and one label, the pool is every event whose label had matured at the cutoff, other than the target's own cluster. Each pool member gets a categorical distance from the target using only attributes known at the cutoff: a timing mismatch, plus a sector mismatch that is 0 for the same major group, 0.5 for the same division and 1 otherwise. The analogue set is the closest members, expanding through distance levels only as far as needed to reach the minimum member count and never beyond the maximum distance; ties enter together. The output lists every member with its attributes, distance and outcome, names the distance reached, gives the count and the Kish effective sample size (equal to the count while weights are uniform), applies the same reporting thresholds to summaries, and lists every excluded event with its reason (the target itself, the same cluster, label not yet matured, label absent). If the set falls short of the minimum, the state is `INSUFFICIENT_ANALOGUES`: members are still listed, and no summary is given. Selection uses no outcome field, and a test proves it.

**Proposed policy defaults** (all in `config/fingerprint-policy.json`, so a change is visible in the diff and in every output's stamped hash):

| Parameter | Default |
| --- | --- |
| Gap-flag proportion reported from n / flagged unreliable below | 5 / 10 |
| Return mean and median reported from n / flagged unreliable below | 10 / 20 |
| Return quantiles (10th, 25th, 50th, 75th, 90th percentile) reported from n | 20 |
| Partial-pooling prior strength (pseudo-observations toward the parent) | 10 |
| Analogue minimum members / maximum distance | 5 / 1.0 |
| Distance weights: timing mismatch; sector mismatch by same group, same division, other | 1.0; 0, 0.5, 1.0 |
| Count unit for thresholds | events (one per cluster); the alternative is distinct reaction sessions |

These are judgement calls, set before any statistic is computed and never tuned on outcomes. Any tuning belongs to Milestone 4's walk-forward folds.

**Tests and acceptance for step 1:**

1. **Determinism:** the same inputs and policy give byte-identical reports with a pinned hash.
2. **Leakage:**
   - the target never appears in its own pool;
   - an event whose label matures after the cutoff is excluded, and one that matures exactly at it is included (a mutation test injects both);
   - maturity is per label, so a matured day-1 label can be used while the same event's session-20 label is excluded;
   - same-cluster events count once;
   - analogue selection and distances are identical when every outcome value is replaced with junk.
3. **Suppression:** every threshold boundary (n of 4, 5, 9, 10, 19, 20) on synthetic data; on the real 23 events, the output matches the tables in sections 3.2 and 3.3, which are also hand-computed independently of the code.
4. **Pooling:** an empty cell returns its parent, a shrunk value lies between the raw and parent values, and n never inflates.
5. **Input integrity:** a tampered label value in a copy of a record fails the digest check.
6. **Milestone 1 untouched:** the protocol, membership, ledger and review hashes in the Milestone 1 declaration still recompute equal.
7. CI green on Python 3.12 and 3.13.

**Explicit non-goals of step 1:** any prediction, score, ranking or model (Milestones 4 to 7); expected-versus-observed gaps (Milestone 6); text or catalyst extraction (Milestone 3); pre-event numeric features; other event types; and any change to Milestone 1 records, code or protocol.

## 5. Step 2 — data depth (not approved; a separate decision)

Three levers, as in the recommendation:

1. **Depth: prior quarters for the same issuers.** This is what fills company-level histories. It needs the session calendar extended beyond 2026 (it fails closed outside it) with verified holidays and early closes, and a new frozen candidate set for those periods. That is a protocol amendment and must be frozen before any prices are accessed.
2. **Breadth: the 205 frozen candidates never reviewed.** This adds issuers, but each is one earnings season, so at most one event per issuer and no company-level depth.
3. **Throughput: chronology at a scale one reviewer cannot sign event by event.** The Milestone 1 ledger records 23 accepted and 15 excluded with reasons among the candidates it examined (the other 205 were never reviewed), and 21 of the 23 accepted events were recorded in a single long session. Sizing option S below, at that acceptance rate, would mean on the order of 150 to 300 candidate reviews unless the review standard changes, for example in-depth review of a random sample with automated checks for the rest. That changes what a sign-off means, so it is the owner's decision. Provider rights at the larger scale would also need a fresh explicit answer.

Sizing options: **S**, the same 23 issuers with four to eight prior quarters each (about 90 to 180 events); **M**, S plus the unreviewed candidates and prior quarters for about sixty issuers; **L**, all 300 frozen issuers over several quarters. I recommend S first, because company-level event histories are the first item in the milestone's build list and are empty today. None of this is started.

## 6. Decisions requested

Defaults are proposed for each, so a one-line reply is enough.

1. Confirm step 1 only, with step 2 decided later.
2. Sector taxonomy: SIC major group and division from SEC records, as proposed (free). GICS would be a paid source.
3. Policy defaults: accept the table in section 4 or change it, including the count unit. Counting distinct reaction sessions is the more conservative choice: today's all-events count would fall from 23 to 16, below the quantile threshold, so no quantiles would be reported anywhere.
4. CXT contributes its day-1 through session-10 labels and no session-20 label, per the per-label availability rule.
5. Outputs are committed as derived statistics only, within the existing provider-rights authorization.
6. No pre-event numeric features in step 1.

## 7. Risks and guardrails

- **Convenience sample.** Events are in the dataset because a minute-stamped wire release and a clean SEC neighbourhood existed, so every output states that it describes this sample and not the market.
- **One event per issuer.** Issuer-level statistics are withheld by construction.
- **SIC is not point-in-time.** It is the current SEC assignment, pinned by source and hash, and outputs state the limitation.
- **Shared dates and raw returns.** Same-day events share market moves that no label adjusts for; counts of reaction sessions are shown beside event counts.
- **No significance claims.** Outputs report counts and intervals; nothing is tested or ranked.
- **Scope creep.** Anything that ranks, scores or predicts stays out until a later milestone is separately approved.

## 8. Implementation notes (added after step 1 was built)

Step 1 was built as specified, in the files named in section 4, and is described in `docs/MILESTONE-2-RUNBOOK.md` and recorded in `reports/m2-step-1-build-record-2026-09-26.json`. The pool table in section 3.3 and the suppression table in section 3.2 are reproduced by the code exactly, and the tests pin them.

**Two findings for the owner.**

1. *The analogue minimum was below the mean and median minimum.* With the originally confirmed defaults an analogue set needed 5 members but a return mean or median needed 10. Analogue sets existed for 13, 12, 11, 8 and 4 of the 23 targets at the day-1, session 2, 5, 10 and 20 return labels (fewer than the matured pools in section 3.3, because of the maximum distance), and a mean and median was reported for only 3, 1, 1, 2 and 1 of them; quantiles were never reported. **The owner instructed "raise the analogue minimum to 10" on 2026-09-27** (`reports/m2-policy-amendment-2026-09-27.json`); `analogues.min_members` is now 10, equal to the mean/median minimum. Sets now exist for 6, 4, 4, 3 and 1 targets, and every one of them carries a mean and median. The members are always listed, as the contract requires, even when a set is insufficient. One side effect, verified rather than assumed: the two conditional gap labels (finding 2, below) fell to zero targets with a found set, from 7, because they exist for only 12 of the 23 events and reaching 10 analogues from that thin a pool is harder.
2. *One label's existence depends on an outcome.* `positive_gap_retained_half` and `positive_gap_filled` exist only after an opening gap of at least 0.5%, so for those two labels the confirmed exclusion "label absent" is decided by an outcome. It is those labels' definition and is reported as `LABEL_ABSENT`, and the test that replaces every label value with junk shows that no other choice of analogue depends on an outcome. Section 4 said selection uses no outcome field; this is the one qualification.

**Choices inside the confirmed scope.** A cell whose every statistic is withheld is written compactly, with its counts and per-label n and no estimates, and a withheld cell names its parent. Partial pooling shrinks toward the nearest reported ancestor, recursively, and never changes the cell's own n. The effective sample size equals the count while weights are uniform, as section 4 said. The exclusion audit also uses `BEYOND_EXPANSION`, `BEYOND_MAX_DISTANCE` and `CLUSTER_ALREADY_COUNTED`. The SIC codes were taken from a fresh retrieval, the alternative section 4 allowed, because the frozen archive is not on this machine; every response's hash is recorded and 23 of 23 hashes and codes were confirmed by a second read.

**Not done, and not claimed.** Milestone 2 is not accepted, step 2 has not been started, and nothing predicts, scores or ranks.
