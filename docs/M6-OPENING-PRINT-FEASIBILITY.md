# Milestone 6 — Opening-print feasibility plan

The owner authorized planning with “go ahead” in reply to the opening-print feasibility proposal. This pilot asks whether the frozen v2 rules select different events when given verified opening observations. Its outputs are coverage and disagreement counts. The prospective outcome study remains subject to a separate protocol and owner decision.

## Cohort and schedule

Use the 23 CIKs in [v1](../config/m6-protocol.json) and the full quarterly-results eligibility and deduplication rules already specified there. The proposed fixed window is January 1 through June 30, 2027, inclusive, by first-public release date in New York. Follow an eligible final-day release through its first eligible opening session. Reconcile the release ledger to Item 2.02 filings, including delayed filings, during a fixed 15-calendar-day reconciliation period after June 30. Every verified candidate receives a disposition. An opening missed in real time remains missed.

Before the start, bind the benchmark membership and digest, official listing-exchange calendars, identity and trade-condition mappings, and capture configuration. The capture must be operational before the first day of the window. If readiness slips, record the missed launch and obtain approval for a new fixed window before observing its openings. End the pilot at its registered boundary regardless of coverage or disagreement. Exclude its events from any future confirmatory cohort.

## Opening evidence and data rights

Request separate authorization for a limited entitlement and timestamp check before deployment. Confirm real-time Alpaca SIP access for the relevant symbols, permitted storage of the necessary audit fields, and rights for the pilot's scale and aggregate reporting. Compare the opening condition and venue mapping against official exchange specifications and verify on preflight sessions outside the pilot. A delayed feed, uncertain opening semantics, or unavailable receipt-time evidence blocks launch. [Alpaca trade stream](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data) · [NYSE calendar](https://www.nyse.com/trade/hours-calendars)

Record verified first-public time and source, the pre-open cutoff and benchmark digest, historical identity and listing venue, scheduled session, prior regular-close reference and provenance, and the official opening trade ID, source timestamp, synchronized receipt time and condition. Apply the v1 timing limits of 60 seconds from scheduled open, five seconds from the feed timestamp to receipt and at most one second of clock error. Freeze allocations on receipt. Record corrections separately and report integrity exclusions without reconstructing a decision from hindsight. Prior-session close is an input to the opening gap. The reaction session's close and any later prices or returns are outside the pilot. Stop event-level capture after the opening observation window. Publish aggregate counts only, with audit fields retained subject to the confirmed rights.

## Frozen comparison and decision rule

Run both [v2 selectors](../config/m6-protocol-v2.json) on the same verified opening gaps. Keep the magnitude threshold at 15.962558421721595%, with its strict inequality. Use the pinned v1 pool and candidate boundaries without recalibration. The benchmark lock must precede capture. As a preflight check, derive the exact disagreement regions from the locked values and exercise boundary cases with synthetic openings. The published reference values imply two narrow disagreement bands near a negative 16% to 19% open and a positive 14% to 16% open. Recompute exact endpoints from the lock before launch.

At the end report the screened denominator, verified opening count, attrition by reason, both flag counts and rates, their signed allocation cross-tabulation, disagreement rate, and issuer and session counts. A disagreement means one rule flags and the other abstains. Show the two disagreement types separately. Use the full common verified cohort as denominator, including rows where both abstain.

Advance to **confirmatory study planning only** if all of these proposed feasibility floors are met:

- At least 30 common verified openings and at least 80% verified coverage among otherwise decision-eligible events for which an opening was required.
- At least five disagreements and disagreement on at least 10% of common verified openings.
- Disagreements span at least three issuers and four reaction sessions, with at least one unique flag from each selector.

Determine pre-opening eligibility before classifying capture failures. Count missing or unverified opens in the coverage denominator. Report insufficient coverage when the first floor fails and low disagreement when coverage passes but an overlap floor fails. Even a pass estimates selection disagreement only. A later proposal still needs a defensible paired-return variance assumption, clustered precision plan, a new cohort that begins after freezing that plan, and separate authorization.

These thresholds and the six-month window are planning defaults. The universe can produce at most roughly 46 regular quarterly releases over six months if every issuer remains eligible, before attrition. The pilot may therefore end with insufficient coverage or too few disagreements.
