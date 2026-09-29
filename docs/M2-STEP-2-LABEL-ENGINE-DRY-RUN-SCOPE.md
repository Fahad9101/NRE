# Milestone 2 step 2 — label-engine dry run scope proposal (for the project owner's review)

**Status: proposed 2026-09-29. Corporate-action check complete (all 4 batches; 45 of 48 frozen
candidates carry a real, attested, pinned result — see `reference_nre_project.md` / this repo's own
commit history through `24a5079`). No cohort-level audit has run yet for Milestone 2 step 2; nothing
below is built yet.**

## Summary

Milestone 1's own order was: per-event acquisition and attestation (what the 4 corporate-action-check
batches just did for step 2) → one formal, cohort-level audit that recomputes every accepted event's
labels from a merged bundle and checks structural gates (window, identity, provider rights, minimum
counts, independent spot-checks) → the owner's own final acceptance decision. `nre/acceptance.py`'s
`audit_cohort()` and `nre/consolidated_audit.py` are that middle step for Milestone 1; both are already
fully generic (`consolidated_audit.py --spec/--protocol/--ledger/--review` all default to Milestone 1's
own files but accept overrides) — the same "no new module" situation the corporate-action check found
for `event_acquire.py`. **One additive code fix is needed** (same class as before), **two new files need
to be built** (both pure aggregation of evidence already on file — no new investigation), and **two real
judgment calls need your word**, not an assumption.

## 1. The one code fix needed

`nre/consolidated_audit.py`'s `main()` hardcodes `calendar = Calendar()` (2026-only) at line 115 — the
exact bug class the corporate-action check already found and fixed twice (`event_acquire.main()`,
`dataset.build()`). A third instance, one layer deeper: even if `main()` gets a `--calendar` arg,
`nre/acceptance.py`'s `audit_cohort(bundle, protocol, ledger, review)` calls `build(bundle)` internally
with no calendar at all (line 15), so a calendar threaded into `main()` still wouldn't reach the label
computation. Fix, purely additive, same pattern as before: `audit_cohort(..., calendar=None)` →
`build(bundle, calendar)`; `consolidated_audit.py main()` gets a `--calendar` arg exactly like
`event_acquire.py`'s. Neither `event-acquire.yml` nor `consolidated-audit.yml` (Milestone 1's own
workflows) pass `--calendar`, so their behavior is unchanged; a new `depth-consolidated-audit.yml`
would.

## 2. Two new files, both pure aggregation

**`reports/m2-step2-reviewed-candidate-ledger.json`** (mirrors `reports/m1-reviewed-candidate-ledger.json`
exactly): all 48 frozen candidates from `config/m2-step2-frozen-candidate-ledger.json`, each given a
`disposition` and (for included ones) an `event_id`:
- 45 `"included"`, `event_id` set — every event now in `config/m2-step2-events.json` with a
  `recorded_result`.
- `ASMB 2025-08-06` and `REKR 2025-10-14`: `"excluded"`, with the reason already on file
  (`reports/m2-step2-same-day-catalyst-review-2026-09-28.json`,
  `reports/m2-step2-eligibility-review-2026-09-28.json`).
- `PDFS 2025-08-07`: **proposed `"quarantined"`**, not `"excluded"` — mirroring Milestone 1's own GALT
  precedent exactly (`docs/M1-READINESS-ASSESSMENT.md`: "GALT's 8-K was accepted... it stays quarantined
  pending a decision about which source to treat as first public"). PDFS's case is a mechanical schema
  gap (a `bell_ambiguous` timestamp `validate_spec()` can't accept at minute precision), not a
  same-day-catalyst or eligibility judgment — the same category of "unresolved, not disqualified" GALT
  is in for Milestone 1. `audit_cohort()`'s own gate logic already treats a reasoned, event-id-less
  `quarantined` candidate as accounted for, same as `excluded`.

**`reports/m2-step2-acceptance-review.json`** (mirrors `reports/m1-acceptance-review.json` exactly):
`discovery_coverage_evidence`, `identity_history_evidence`, and `provider_rights_evidence` pointers into
already-written reports (the SEC-freeze report, the identity/exchange re-verification, and the original
scope authorization); `prices_first_accessed_at` from batch 1's dry-run timestamp; `frozen_membership_sha256`
copied from the frozen ledger; and `spot_checks` — the gate needs ≥2 independently-evidenced events per
release-timing class (premarket / after_hours), each with a named reviewer. Both classes already have
well more than 2 fully-documented events across the 4 batches' signoff packets and complete-events
reports, so this is a matter of pointing at existing files, not new review work.

## 3. New workflow

`.github/workflows/depth-consolidated-audit.yml`, mirroring `consolidated-audit.yml`, invoking
`python -m nre.consolidated_audit --spec config/m2-step2-events.json --protocol
config/m2-step2-protocol.json --ledger reports/m2-step2-reviewed-candidate-ledger.json --review
reports/m2-step2-acceptance-review.json --calendar config/m2-step2-merged-calendar.json`. Nothing
Milestone-1-frozen (`nre/consolidated_audit.py`'s defaults, `consolidated-audit.yml`,
`config/pilot.json`, either M1 report) is modified.

**Standalone, not merged with Milestone 1** — `config/m2-step2-protocol.json` already documents itself
as "a separate, parallel protocol... does not amend, extend or touch... any Milestone 1 record," and its
own thresholds (`minimum_eligible_events`/`minimum_unique_issuers` = 1) are set deliberately minimal
because this is a throughput pilot, not a coverage target. This proposal keeps that: one audit of step
2's 45 events under step 2's own protocol, a second, independent `STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED`
result alongside Milestone 1's own, not a combined 68-event cohort. Flagging this rather than assuming it,
since it's the kind of scope decision this project has always asked about rather than inferred.

## 4. What this does and doesn't do

Running it produces `gates`/`failed_gates`/`status` (`BLOCKED` or `STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED`)
and re-derived hashes — a mechanical, re-verifiable check, same as Milestone 1's own. `audit_cohort()`
**never** sets `milestone_accepted: true` itself (that field is hardcoded `False` in the return value,
always) — your own final Milestone 2 step 2 sign-off stays a distinct, later, human decision regardless
of this run's outcome, exactly like Milestone 1's.

## 5. The one gate very likely to fail, and why — needs your call, not an assumption

`candidate_source_hashes` checks every candidate's SEC-filing hash against the bundle's own `sources`
list. Milestone 1's workflow satisfies this by downloading its original SEC-freeze archive as a GitHub
Actions artifact (`consolidated-audit.yml`'s `--archive-dir`, pointed at a specific past run). **Milestone
2 step 2's own raw SEC discovery bytes were never uploaded anywhere durable** — `docs/MILESTONE-2-STEP-2-PILOT.md`
already says so explicitly ("This is not yet a durable archive anywhere else... the same limitation
Milestone 1's SEC freeze had before the owner was asked to keep a copy separately"). Without that archive,
`archive_sources()` returns `[]` (its own docstring: "the `candidate_source_hashes` gate then fails rather
than the run") — the dry run would very likely come back `BLOCKED` on exactly one gate, not because
anything is wrong, but because the raw bytes were never archived anywhere the audit can read them back
from.
