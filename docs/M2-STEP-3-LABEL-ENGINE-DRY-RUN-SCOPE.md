# Milestone 2 step 3 — label-engine dry run: scope as built (for the project owner's review)

**Status: built 2026-10-02 on the owner's "yes build it"
(`reports/m2-step3-label-engine-dry-run-scope-authorization-2026-10-02.json`). All 66 frozen candidates
are dispositioned: 60 are attested, computed and pinned, 6 are excluded. This document describes what was
built; it claims no audit result. The real result is recorded separately, after the workflow has run, in
`reports/m2-step3-label-engine-dry-run-result-2026-10-02.json`.**

**Update 2026-10-02, after the audit ran:** the owner decided the flagged choice in section 2.B ("Keep the
23 archived payloads", 2026-10-02T18:55:54.262Z) and, in the same message, accepted step 3; both are
recorded in `reports/m2-step3-acceptance-declaration-2026-10-02.json`. Sections 2.A to 2.D below are left
as written.

## Summary

Milestone 1's order, repeated for step 2 and again here: per-event acquisition and attestation (the six
batches) → one formal, cohort-level audit that recomputes every accepted event's labels from a merged
bundle and checks structural gates → the owner's own acceptance decision. The middle step reuses
`nre/acceptance.py`'s `audit_cohort()` and `nre/consolidated_audit.py` **unchanged** — the `--calendar`
fix made for step 2 already carries step 3's merged calendar through to the label computation. No `nre/`
code was touched. What was added is one workflow, two reviewed records built from evidence already on
file (plus one small piece of new independent checking), one archive directory, and one offline test.

## 1. What was built

- **`reports/m2-step3-reviewed-candidate-ledger.json`** — all 66 frozen candidates, each with a
  `disposition`: 60 `included` (each with the `event_id` of its pinned event) and 6 `excluded` (each with
  its reason and no `event_id`). Nothing is `quarantined`; unlike step 2's PDFS, no step-3 candidate is
  left unresolved. The six exclusions are the ones the owner signed off in the batch packets: CACI 4/24
  (an 8-K/A amendment), OKTA 2/4 (a guidance reaffirmation), REAL 2/10 and REKR 3/17 (explicitly
  preliminary pre-announcements), ALKT 2/27 (same-day competing catalyst), SLSN 3/26 (OTCQB, outside the
  exchange scope).
- **`reports/m2-step3-acceptance-review.json`** — pointers to the discovery/coverage, identity-history and
  provider-rights evidence already on file; `prices_first_accessed_at` (2026-10-01T20:57:25Z, the first
  run that fetched step-3 bars — the freeze, 18:06:49Z, precedes it); `frozen_membership_sha256`; and four
  timing spot checks, two per release-timing class.
- **`reports/m2-step3-independent-timing-spot-checks-2026-10-02.json`** — the one piece of new checking.
  Step 2's review only pointed at evidence already in the batch packets. For step 3 the four spot-checked
  events' first-public timestamps were re-verified against a third source that the original evidence had
  not used (company investor-relations pages and Yahoo's syndication copies). All four agree. Its stated
  limits include that two of the four company pages show only a date, not a time of day.
- **`archive/m2-step3-sec-freeze/`** — the 23 payloads the cohort freeze hashed (see decision B).
- **`.github/workflows/depth3-consolidated-audit.yml`** — mirrors `depth-consolidated-audit.yml`, pointed
  at step 3's spec, protocol, ledger, review and merged calendar, plus `--archive-dir`.
- **`tests/test_step3_audit.py`** — runs the whole pipeline offline over the committed records with
  synthetic flat bars (no real prices are committed or needed): the records are mutually consistent, every
  gate passes with the archive, and *only* `candidate_source_hashes` fails without it.

## 2. Decisions that were Claude's own — flagged, not asked

**A. Standalone, not merged with Milestone 1 or step 2.** One audit of step 3's 60 events under step 3's
own protocol (`config/m2-step3-protocol.json`; thresholds of 1 event and 1 issuer, a throughput pilot, not
a coverage target), as step 2 did. A third independent result, not a combined cohort.

**B. The SEC-source archive, and a correction.** In offering this work I said the
`candidate_source_hashes` gate would probably be blocked because "there's nothing durable to hash
against." That overstated the problem, and I had not checked it. The exact 23 filtered 8-K payloads that
the freeze hashed still existed in this session's scratch space (not in the repository) and reproduce all
23 candidate source hashes byte for byte. I archived them under `archive/` (not `data/`, which is
gitignored) so the gate can be evaluated. What a pass means and does not mean:

- It shows that the archived bytes are the bytes the freeze hashed, so the ledger's source hashes are
  reproducible rather than merely asserted.
- It does **not** show that those bytes equal SEC's raw `submissions.json`. The freeze used a
  browser-fetched, filtered, re-serialized 8-K subset because `data.sec.gov/submissions` returned HTTP 403
  from GitHub Actions in all six dispatches. Each payload's metadata says so
  (`source_representation: browser_fetched_8k_filtered_subset`, `note`) and records SEC's full-response
  hash and size separately. Milestone 1's archive held the actual raw bytes; this one cannot.
- To reverse the choice: delete `archive/m2-step3-sec-freeze/` and the `--archive-dir` argument in the
  workflow. The audit then fails `candidate_source_hashes`, exactly as step 2's did.

**C. Spot-check selection and attribution.** The four events are chosen by a rule fixed before looking at
any outcome: of the 57 events with a non-null `session_20_close_return` (the audit's own "complete"), the
two latest by `published_at` in each timing class. That also keeps the spot checks off CXT's three
dividend-suppressed events, the trap step 2 hit. The named reviewer on each check is the owner, on the
same basis step 2's review used: the owner's "yes go ahead" sign-off on the batch packet containing the
event. The independent re-verification was done by Claude afterwards and was not part of what the owner
signed off on; the review's `_note` says so.

**D. How "yes build it" was read.** I had offered to put a short scope proposal in front of the owner
first and to wait for "start the step-3 audit". The reply was "yes build it". I read that as a go-ahead to
build directly, so this document is the record of what was built, not a proposal ahead of the build. If a
proposal first was meant, nothing here is accepted by having been built and each piece is reversible.

## 3. What running it does and doesn't do

The run refetches every accepted event's bars and corporate actions inside GitHub Actions (the same
Alpaca access and the same standing, redacted-derived-data-only authorization as every earlier step),
recomputes the labels, and prints only gates, counts and hashes — no prices. It produces `gates`,
`failed_gates` and `status` (`BLOCKED` or `STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED`).
`audit_cohort()` **never** sets `milestone_accepted: true` (the field is hardcoded `False`), and a clean
result is explicitly "review required": hashes and declarations establish internal consistency, not
genuine publication, permission or review.

The offline test shows the committed records are consistent with each other. It says nothing about real
prices; only the Actions run touches those.

## 4. What remains the owner's

- The decision whether to accept Milestone 2 step 3, and any declaration record for it — separate, later,
  and requiring the owner's explicit word whatever this run shows.
- Milestone 4 and everything past it remain unauthorized.
