# Milestone 3 — Catalyst-strength features scope proposal (for the project owner's review)

**Status: proposed 2026-09-30, following the owner's "continue finishing M3" and the explicit
choice to scope this before writing any code. Nothing built yet.** Phase A (corporate-event
normalization), Phase C (biotech/device catalyst classification, now connected to 6 real issuers),
and Phase B's real, structured earnings-surprise magnitude (EPS and revenue) are the only parts of
M3 built so far -- catalyst-strength is explicitly the last of M3's five scope items, and the
master prompt says why: *"Do not rely exclusively on opaque LLM-generated scores... scoring rules
and downstream models must be testable and auditable."*

## Summary

Master prompt sections 7, 8, 9, and 13 (read in full before writing this) all mention "catalyst
strength," but at two different layers that are easy to conflate:

- **Section 13 (Model Output)** shows catalyst strength as a single number in a final candidate
  display -- `Catalyst strength: 92/100` -- alongside model-estimated gap probabilities. That
  number is explicitly the output of a **model** (a later milestone's job: M4 Baseline Predictive
  Models onward), calibrated against real outcome data, not something invented standalone here.
- **Sections 7-9** describe the *inputs* such a model would need: structured features like
  magnitude vs. prior guidance, novelty, event category, that a later model combines. Section 7's
  own example ("Scientific significance: 94/100, Commercial significance: 78/100...") is aspirational
  -- illustrating the KIND of dimension a mature system might reason about, not a spec for what M3
  itself must fabricate now.

**This proposal scopes only the structured, auditable features section 6-9 actually support from
real data already in this project -- never a combined score.** Full M3 acceptance ("raw public
announcements reliably become structured machine-readable event features") is satisfied by real,
auditable *features*; the eventual scalar display in section 13 is downstream work this phase does
not attempt.

## 1. What real, already-computed data exists to draw from

- **Phase A** (`nre/corporate_events.py`): `category`/`subtype` for every real SEC 8-K item,
  deterministic, already applied to all 291 candidates across M1/M2.
- **Phase B** (`nre/earnings_surprise.py`): `surprise_pct` -- a real, quantitative year-over-year
  magnitude, computed from real XBRL facts (EPS, and as of today, revenue too). Live-fetch is
  currently blocked from GitHub Actions (SEC's own XBRL API returns HTTP 403), so only a handful of
  real computed values exist yet (the JBSS worked-example fixtures) -- this bounds what's possible
  in section 3 below.
- **Phase C** (`nre/biotech_trials.py`, `nre/fda_approvals.py`, `nre/device_clearances.py`):
  `status_category`/`decision_category`/`pathway`, deterministic classifications of real trial and
  regulatory records, connected to 6 of this project's 23 issuers.

## 2. A real structural mismatch, found while connecting Phase C, that this phase must resolve first

None of the 68 real events in `config/m2-combined-events.json` is itself a clinical-trial-result or
FDA-action announcement -- every one is a plain earnings release (confirmed by reading each event's
own real wire headline before Phase C was connected). Phase C's own real trials/applications/
clearances are **issuer-level** discoveries (found by searching a company's own name), not tied to
any specific M1/M2 event date. So for the 68 real earnings events, only Phase A + Phase B currently
have anything to attach *to that event* -- Phase C data has no date-anchored link to any of them.

**Open question:** should catalyst-strength features cover only the 68 real earnings events (Phase
A + Phase B only, leaving Phase C's biotech/device data as separate issuer-level context, not
fused in), or should this phase also build the date-matching needed to check whether a real Phase C
regulatory milestone fell inside a specific event's own window (a new capability, not yet built,
and its own source of false-precision risk if a real trial-status change and an earnings release
happen to land near each other without being related)?

## 3. Proposed concrete feature set -- structured signals, not a score

Drawing only from Phase A + Phase B (pending the decision in section 2), per real event:

- `corporate_event_category` / `corporate_event_subtype` -- straight from Phase A, already computed.
- `earnings_surprise_pct` / `earnings_surprise_state` -- straight from Phase B, real when the
  underlying XBRL fact is reachable; honestly `null`/`SOURCE_UNAVAILABLE` while the live-fetch block
  stands, never estimated.
- `surprise_direction`: `positive`/`negative`/`flat`, derived directly from `surprise_pct`'s own
  sign -- no new judgment.
- `surprise_magnitude_band` (small/medium/large or similar): **not proposed yet.** A real,
  data-driven bucket boundary would need a real sample of computed `surprise_pct` values large
  enough to set a defensible threshold from -- which doesn't exist yet given Phase B's live-fetch
  block (only 1-2 real worked examples so far). Building this now would mean inventing round-number
  thresholds from nothing, the same opaque-guess problem this whole proposal exists to avoid.
  Revisit once enough real surprise data exists, or if the owner names a citable external
  convention (e.g. a specific, sourced industry threshold) to use instead.

All of these are discrete/categorical, matching how `nre/fingerprints.py`'s own `cell_keys()`
already buckets events by `timing`/`sic_division`/`sic_major_group` -- these could plug into that
same machinery as new dimensions later (master prompt section 9 names "catalyst strength" as one
of several comparable dimensions for the analogue engine), without redesigning it.

## 4. Explicit non-goals

- No single combined "catalyst strength" scalar of any kind (0-100 or otherwise) -- that belongs to
  a later, calibrated model (M4+), not this phase.
- No subjective dimensions section 7's own example names (scientific significance, commercial
  significance, safety quality, dilution risk, addressable market impact, ...) -- none has a real,
  verifiable source in this project's actual data; inventing weights for them would be exactly the
  opaque scoring the master prompt prohibits.
- No LLM/NLP-based scoring of any kind.
- Not M4's own job -- this phase produces features only, never a prediction or probability.

## 5. What this does not do

No code is written by this document. `surprise_magnitude_band` is explicitly deferred, not silently
dropped. Section 2's own open question is not decided here. Full Milestone 3 acceptance is not
claimed by this document -- it only proposes how the last of M3's five scope items could start.
