# Milestone 3 — News/Catalyst Intelligence scope proposal (for the project owner's review)

**Status: proposed 2026-09-29, following the owner's "lets finish m3." Nothing built yet.
Milestones 0-2 are the only ones declared accepted; this is the first attempt at scoping M3, a
structurally new kind of work for this project (structured extraction from raw text and new
public data sources, not a data-depth extension of what M1/M2 already built).**

## Summary

The master prompt's own M3 section is a two-line summary; sections 6, 7, 15, 29 and 32 (read in
full before writing this) give the real detail. Five sub-areas, of very different difficulty:

1. **Structured event extraction** (general corporate/capital-markets taxonomy, section 6) — low
   risk, directly extends `nre/ingestion.py`'s already-proven SEC EDGAR pipeline.
2. **Corporate-event normalization** — same as above; SEC 8-K items already map cleanly onto most
   of section 6's "General Corporate Events" and "Capital Markets Events" taxonomies.
3. **Earnings surprise normalization** — partially blocked. SEC filings and issuer press releases
   give real EPS/revenue *actuals*; **consensus estimates do not exist anywhere in this project's
   data access, and no free/public/legitimate source for them is named in the master prompt or
   found by checking** (see section 2 below). Surprise *vs. prior guidance* is buildable now from
   real data; surprise *vs. consensus* is not, without a new decision.
4. **Biotech catalyst extraction** — needs two new, real, verified-free data sources (FDA,
   ClinicalTrials.gov — see section 1) plus new parsing logic for trial/regulatory language SEC
   filings don't structure on their own.
5. **Catalyst-strength features** — a derived layer built from 1-4, deliberately built last. The
   master prompt is explicit here: *"Do not rely exclusively on opaque LLM-generated scores...
   scoring rules and downstream models must be testable and auditable."*

**What I need from you:** a decision on sequencing (section 3) and on the consensus-data gap
(section 4) before any code gets written — the same two-decisions pattern every prior phase of
this project has used.

## 1. Data sources checked for real, not assumed

Rather than guess, I checked each candidate source directly before writing this:

- **SEC EDGAR**: already this project's core infrastructure since Milestone 1. No new work needed
  to *reach* the data; new work is needed to *classify* 8-K items into section 6's taxonomy.
- **openFDA** (`api.fda.gov`): live, free, no authentication required, government-run, clear terms
  at `open.fda.gov/terms`. Confirmed with a real request just now (`/drug/drugsfda.json`, 29,357
  results, `last_updated: 2026-09-28`). Never used by this project before.
- **ClinicalTrials.gov API v2** (`clinicaltrials.gov/api/v2`): live, free, no authentication
  required, government-run. Confirmed with a real request just now. Never used before.
- **Alpaca Historical/Real-time News**: Alpaca's own Market Data API (already this project's
  authorized provider for prices) lists a documented "Historical News Data" / "Real-time News"
  category, separate from the price/corporate-actions endpoints already in use. This is worth
  serious consideration as the `news_ingestion/` source, instead of building bespoke wire-service
  scraping — but its own terms and actual coverage need their own dedicated review before use,
  exactly the way Alpaca's price data got its own dedicated review
  (`reports/m1-alpaca-provider-rights-review-2026-09-23.json`) before Milestone 1 used it. Not
  reviewed yet; flagged as the first concrete task if this phase is approved.
- **Consensus estimates (EPS/revenue consensus, consensus guidance)**: **no source found.** Not in
  Alpaca's own product lineup (checked: their Market Data API covers stock/option/crypto/forex/
  fixed-income prices and news, nothing described as fundamentals or estimates). Not named
  anywhere in the master prompt's own Data Sources section (15). The commercial products that
  normally provide this (I/B/E/S, FactSet, Zacks, Visible Alpha) are paid, and this project's own
  rule (section 36: *"Do not invent data... never substitute fabricated values"*) rules out any
  proxy or scraped approximation without knowing its provenance and terms.

## 2. What "corporate-event normalization" concretely reuses

SEC 8-K items already map cleanly onto section 6's taxonomy, and this project has direct,
extensive experience reading them (every M1/M2-step-2 candidate's chronology work): Item 1.01
(material agreements), 2.03/3.02 (debt/securities issuance), 5.02 (officer/director changes),
5.07 (shareholder votes), 7.01/8.01 (Reg FD/other events), 3.03/5.03 (corporate actions, already
consumed by `nre/event_acquire.py`). A `corporate_event_parser/` reading already-fetched 8-K text
and classifying it against this taxonomy is a natural, low-risk extension of existing code, not a
new capability area.

## 3. Proposed sequencing — open question, not a decision

Mirroring how every prior phase asked about pacing rather than assuming it:

- **Phase A** (lowest risk, most reuse): `event_normalization/` core schema +
  `corporate_event_parser/`, built entirely on SEC EDGAR data this project already has full,
  proven access to. No new provider, no new terms review.
- **Phase B**: `earnings_parser/` for SEC/issuer-sourced *actuals* and guidance-based surprise
  (vs. prior guidance, vs. prior period) — real data, no new provider, but deliberately does not
  attempt consensus-based surprise (see section 4).
- **Phase C**: `fda/` + `clinical_trials/` + `biotech_parser/`, using the two verified-live
  government APIs from section 1. Needs its own new-provider review (terms, rate limits, what's
  genuinely usable) before building against them, the same weight of review Alpaca itself got.
- **Phase D** (blocked on section 4's decision): true consensus-based earnings surprise.
- **Catalyst-strength features**: only after enough of A-C exists to build structured, auditable
  inputs from — not before, and not as an opaque score.

Default recommendation, if you'd rather I just proceed on a reasonable basis: Phase A first (it's
the only phase needing zero new data-source decisions), but I'm not treating that as decided.

## 4. The consensus-data gap — needs your explicit word, not an assumption

Three real options, not a false choice:

- **Skip it for now.** Build "surprise" only against prior guidance/prior period (real, available
  data), explicitly labeled as such rather than as consensus surprise, and revisit consensus
  specifically later if a legitimate source turns up.
- **Investigate further before building anything in Phase B/D.** I haven't exhaustively searched
  for a free, ToS-compliant consensus-estimates source — only checked the two most obvious
  candidates (this project's own existing provider, and the master prompt's own named sources). A
  deeper search might turn up something real; it might also turn up nothing, since consensus
  estimates are a commercial product almost everywhere.
- **Name a provider you already have access to or are willing to acquire.** If you know of a
  source (paid or otherwise) you want used, tell me and I'll scope its own terms review the way
  Alpaca's was scoped.

## 5. What this does not do

No code is written by this document. No provider is used without its own terms review, the same
discipline every real-data source in this project has gotten. No catalyst-strength score is
built before the structured inputs it would rest on exist. Full Milestone 3 acceptance (*"Raw
public announcements reliably become structured machine-readable event features"*) is a long way
from a single phase; this document only proposes how to start, not a claim about when M3 finishes.
