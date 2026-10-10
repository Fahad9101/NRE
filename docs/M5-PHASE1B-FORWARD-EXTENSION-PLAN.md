# Milestone 5 — Phase 1b: the forward extension (plan)

**Status: the plan and the rules of Phase 1b, fixed on 2026-10-09 before any run, and updated the same day after S1. The owner authorized the phase ("authorize phase 1b") and answered two questions
(`reports/m5-phase1b-authorization-2026-10-09.json`). S1 is done: the candidate pool is frozen (section 4). S2 is done too: the same-day sweep of the 47 candidates and the review of the filings' text, and the owner has decided the three things it left (`reports/m5-phase1b-s2-decisions-2026-10-09.json`), so 45 candidates stand. S3, the sealed mode of the event acquisition, is built. S4 and S5 have run for batch 1: its event specs were built in the dry-run state, the sealed dry run ran, the signoff packet was prepared and the owner has signed it off (`reports/m5-phase1b-batch1-signoff-2026-10-09.json`): eight events are attested, NBIX's second dry run listed its one action and the owner then attested NBIX too (`reports/m5-phase1b-nbix-signoff-2026-10-10.json`), and ASMB stays quarantined. S6 has run for batch 1: the attested sealed run printed the eight commitments (`reports/m5-phase1b-batch1-sealed-run-2026-10-10.json`) and a second run confirmed those pins and printed NBIX's (`reports/m5-phase1b-batch1-pin-verification-2026-10-10.json`), so all nine are pinned in the events file. Batch 2 has begun: the owner permitted reading its ten releases' wire pages (`reports/m5-phase1b-batch2-permission-2026-10-10.json`) and its ten event specs are built in the dry-run state after batch 1's nine (`reports/m5-phase1b-batch2-sources-2026-10-10.json`). No label, return or event price has been read; one inadvertent exposure to a company's quarterly average repurchase price, through a search-tool summary, is disclosed in `reports/m5-phase1b-batch1-sources-2026-10-09.json`. Nothing later has started. The rules are in
`config/m5-phase1b-protocol.json` and `config/m5-phase1b-cohort-spec.json`, which this plan explains.**

## 1. What Phase 1b is

The proposal words it so: a forward extension, "Milestone 2 step 4": an outcome-blind enumeration and freeze of candidate events since 2026-04-01 under the same procedure and review standard as steps 2 and 3, labels sealed
from the design (`docs/M5-ADVANCED-MODELS-SCOPE.md`, section 3). Its purpose (section 2.4 there) is a fresh holdout for a promotion statement: Milestone 4's holdout is spent, and a statement needs events collected
outcome-blind and sealed before the Milestone 5 protocol is frozen. At the dataset's own rate (128 events over 512 days) about 48 events would have occurred since the data ended; that is the proposal's estimate, and the freeze
will count them.

## 2. What the owner decided

- **The go-ahead:** "authorize phase 1b" (2026-10-09T07:12:36.854Z), read as the phase worded above and nothing later.
- **Provider rights at scale:** "Yes, provider rights fine", read as covering this phase's scale only: about 48 more events, run as sealed commitments until Phase 4, on the same Alpaca account and SIP feed, derived values only,
  never raw prices. The question is put to the owner again before Phase 1c.
- **The seal:** "Hash-only seal (Recommended)", described in section 3.
- **Chosen by the assistant, open to the owner's veto before the freeze:** the end of the window, below.

## 3. The rules, fixed before the first run

**The pool.** The same 23 issuers as Milestone 1 and steps 2 and 3, and no others. Every Item 2.02 8-K or 8-K/A filed from 2026-04-01 to 2026-09-10, found in the SEC's submissions by filing metadata alone. Every exclusion is
recorded. No price, return or label is read before the freeze. The freeze found 47 candidates: 22 issuers have two, REKR has three, and one candidate is an 8-K/A.

**The window.** It starts the day after Milestone 1's event window ended (2026-03-31). It ends on 2026-09-10, the last release date whose 20-session label window is complete as of the latest session when the window was fixed
(2026-10-08), even for an after-hours release; one date later it would not be. The rule uses the calendar, not a price. Releases after 2026-09-10 are not part of this step. No candidate of the 23 issuers in Milestone 1's frozen
ledger is dated on or after 2026-04-01 (three candidates of other issuers are), so the candidate pools do not overlap.

**The review standard.** As in steps 2 and 3: an eligibility review and a same-day-competing-catalyst sweep of the frozen candidates; event specs built in batches; a dry run that quarantines every event until it is attested;
a signoff packet for each batch; and the owner's own attestation of first-public timing, historical identity and corporate actions for each batch. The assistant attests nothing, and no event enters the sealed set without it.

**The seal.** The label engine runs on each attested event, so a missing session or a dividend in a window surfaces now. A sealed run reports only an event's state, its quarantine reasons, its window facts, its missing and
zero-volume sessions, its corporate actions, the SHA-256 commitment of its labels, and whether each of the four session-return labels exists and, if not, why. It never reports a label value, a price, a return or a ratio, or whether
any day-1 label or gap label is true or false. It also hides the engine's reason `NOT_POSITIVE_GAP_GE_0_5PCT`, which the engine gives exactly when the opening gap is below +0.5% and which would therefore reveal the gap's sign. The
protocol lists both sets. The commitment is the hash the earlier steps already pin (`labels_sha256`). At Phase 4 the labels are recomputed once and checked against the commitments (a mismatch is reported, never overwritten), and
that look is the only one. The seal is a procedure, not secrecy: the same public prices exist elsewhere, and the seal binds this project's own runs, logs, annotations, reports and commits. The assistant will not seek those prices.
**A disclosure:** the assistant has seen the Milestone 4 block-5 results (the proposal says so); it has seen no outcome, price or label of any event since 2026-04-01.

**Provider terms.** Derived values only, never raw prices, as the project's provider-rights review records. The exposed derived-data footprint is 128 events today (23 from Milestone 1, 45 from step 2 and 60 from step 3). Phase 1b
adds about 48 events whose values stay sealed until Phase 4, so what is exposed grows by commitments and availability facts, not by values.

## 4. The stages

| Stage | What happens | Needs from the owner |
| --- | --- | --- |
| S1 | Freeze the candidate pool: the SEC filing lists of the 23 issuers, the Item 2.02 filings in the window frozen with hashes, and the SEC data committed with them. Done on 2026-10-09 through the built-in browser, because the SEC refused the one-time workflow (`reports/m5-phase1b-sec-cohort-freeze-result-2026-10-09.json`) | the owner's permission to download (given), then "push" |
| S2 | Eligibility review and same-day-competing-catalyst sweep of the frozen candidates. Both are done on 2026-10-09. The sweep (`reports/m5-phase1b-same-day-sweep-2026-10-09.json`) found no candidate with another 8-K or 8-K/A on its filing date. The review of the filings' text (`reports/m5-phase1b-eligibility-review-2026-10-09.json`, read with the owner's permission) found 44 results releases with no issue and three decisions for the owner: a pre-announcement, a header-only amendment and a pending cash take-private. The owner made them the same day (`reports/m5-phase1b-s2-decisions-2026-10-09.json`): exclude the pre-announcement, keep the amendment with a caveat, exclude the pending take-private; 45 candidates stand | nothing further |
| S3 | The sealed mode of the event acquisition: a whitelist report, its workflow, and offline tests that inject distinctive prices and prove none reaches a log, an annotation or a report. Built on 2026-10-09: the `--sealed` flag of `nre/event_acquire.py`, the workflow `.github/workflows/m5-phase1b-event-acquire.yml` and `tests/test_event_acquire_sealed.py` (section 5) | "push" |
| S4 | Event specs in batches of about ten (wire timestamps, identity, cutoffs), validated offline. Batch 1 is built on 2026-10-09 (`reports/m5-phase1b-batch1-sources-2026-10-09.json`, `config/m5-phase1b-events.json`): nine sealed events, built in the dry-run state; the tenth candidate, ASMB, was released at the 16:00 ET close, which the calendar classes as bell-ambiguous, so it is left quarantined for the owner's word. Batch 2 is built on 2026-10-10 (`reports/m5-phase1b-batch2-permission-2026-10-10.json`, `reports/m5-phase1b-batch2-sources-2026-10-10.json`): ten more sealed events, appended to the same file in the dry-run state; none is bell-ambiguous, and ACHV carries a caveat for a separate same-day release | "push" for each batch |
| S5 | A sealed dry run for each batch (every event quarantined until attested), then a signoff packet. Batch 1's ran on 2026-10-09 (`reports/m5-phase1b-batch1-dry-run-2026-10-09.json`): eight events quarantined as a dry run should, and NBIX errored on a corporate action with no ex-date; the packet (`reports/m5-phase1b-batch1-signoff-packet-2026-10-09.json`) asked for the eight attestations and put two decisions to the owner. The owner answered the same day (`reports/m5-phase1b-batch1-signoff-2026-10-09.json`): the eight are attested, with the packet's caveats; NBIX gets an additive change to `fetch_actions` (an action with no ex-date is dated by its effective, payable or process date; `tests/test_event_acquire_action_dates.py`) and stays unattested until its second dry run has listed its action; ASMB stays quarantined | the attestations and decisions (given); NBIX's attestation (given on 2026-10-10, after the owner had seen its listed action) |
| S6 | A sealed attested run for each batch, and each event's commitment pinned. Batch 1's ran on 2026-10-10 (`reports/m5-phase1b-batch1-sealed-run-2026-10-10.json`): the eight attested events are MAPPED with a commitment each (CXT's session_20 label does not exist, because of its dividend), and NBIX, then unattested, lists its one action; the owner attested NBIX on 2026-10-10 (`reports/m5-phase1b-nbix-signoff-2026-10-10.json`), the eight commitments were pinned, and a second run (`reports/m5-phase1b-batch1-pin-verification-2026-10-10.json`) matched all eight and printed NBIX's commitment (its session_10 and session_20 labels do not exist, because of the merger item's date), which is pinned too | "push" for NBIX's pin |
| S7 | A sealed audit of the whole extension and a registry of its events and commitments | the owner's declaration that the extension is complete |

Step 2 took four batches and step 3 six; about 48 events is about five. The frozen pool has 47 candidates, none of which is an event until it has been reviewed.

## 5. What is built first

S1: the protocol and the cohort spec above, an additive option in the freeze validation (`window_relation_to_milestone_1`, which lets a window start after Milestone 1's instead of ending before it, and changes nothing for the
earlier steps), the one-time freeze workflow (`.github/workflows/m5-phase1b-sec-cohort-freeze.yml`, which stops whenever any frozen file exists on main; the SEC refused its run, so it is now dispatch-only and kept as the record) and their
tests. The freeze itself was then run, as step 3's was, on SEC data fetched through the built-in browser: what was fetched, what was kept and what was checked are in the result record named in section 4. The sweep of S2 followed, from the archived lists alone (`tests/test_m5_phase1b_sweep.py` repeats it); the review of the filings' text followed, with the owner's permission to read the filings in the built-in browser (`tests/test_m5_phase1b_review.py` binds its record).

S3 followed, before the first batch's dry run. `nre/event_acquire.py` takes `--sealed`: the report of each event is rebuilt from an allowlist (state, window facts, missing and zero-volume sessions, corporate actions, the commitment, and for each of the four
session-return labels only whether it exists and a reason that names no price), every reason and error is checked against a fixed list and anything else becomes OTHER, an exception prints no message, and an output that holds a decimal number or
the gap reason is refused whole. An event marked `seal: hash_only` in its spec refuses to run without the flag, before anything is fetched. The sealed workflow runs on dispatch or when the events file is pushed, uploads nothing and uses no
calendar argument. `tests/test_event_acquire_sealed.py` injects four-decimal prices through a fake provider, looks for them and for every label computed from them in everything a run prints, and runs price histories that differ in everything the seal hides
(the sign and size of the gap, the day-1 move, the later drift) and requires identical sealed reports except the commitment. Pushing it also starts the Milestone 1 event acquisition, which watches that file; its pinned matches are the real-data check that the unsealed path is unchanged.

The signoff of batch 1 added one change to that module, the owner's answer (A) on NBIX: `fetch_actions` dates an action that has no ex_date by the first of its effective, payable and process dates that is present, and says which in a `date_field` entry that the sealed view shows only when the date is not an ex-date. An action with none of them still fails closed, and a date that is present but unusable is an error, never a reason to try the next one. It changes nothing for an input that worked before, because such an input has a valid ex_date, which still decides. `tests/test_event_acquire_action_dates.py` pins it and `tests/test_m5_phase1b_attestations.py` binds the signoff record and the attested events file. Pushing it starts the Milestone 1 event acquisition again, whose pinned matches are the same real-data check.

S6 followed for batch 1's eight attested events. `tests/test_m5_phase1b_sealed_run.py` binds the sealed-run record to the events file and the calendar and checks that the pins are the record's commitments; `tests/test_m5_phase1b_batch1.py` runs the pinned file with injected prices and requires each mapped event to report a mismatch, so a pin does catch a different history. The same file binds the second record: the eight pins matched, nothing else about them changed, and NBIX's commitment is the events file's ninth pin. The owner's later answer on NBIX is bound by `tests/test_m5_phase1b_attestations.py`, which checks the answer as given, the action the owner saw against the sealed-run record, and NBIX's attestations and caveats in the events file.

S4 of batch 2 followed. `tests/test_m5_phase1b_batch2.py` quotes the owner's permission as given, recomputes the ten candidates from the S2 records, checks the ten events against the frozen ledger, the eligibility review, the Milestone 1 events, the calendar and the archived SEC lists, recovers their dry-run state byte for byte, and runs them through a sealed run with injected prices.

## 6. What this plan does not do

It runs and fetches nothing itself and pushes nothing. The work it describes enumerates candidates by filing metadata only, reads no price or label, and attests no event. It does not start Phase 0, 1c, 2, 3 or 4, and it does
not answer the provider-rights question for Phase 1c.
