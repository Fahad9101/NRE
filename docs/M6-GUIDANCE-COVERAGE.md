# Milestone 6 — Public issuer guidance coverage

**Decision.** Stop this coverage screen on the existing development cohort. Original issuer releases supply comparable full-year revenue guidance in some cases. Even if every remaining event qualified, this feature could cover at most 32 clean held events across 11 issuers, below the planning floors of 40 events and 15 issuers.

## Feature and cohort

The proposed field is the relative change in the midpoint of an issuer's consolidated full-fiscal-year USD revenue outlook. The original earnings release must state a dollar point or two-sided range. Net sales qualifies when it represents the consolidated top line. The comparison requires an independently timestamped prior outlook for the same fiscal end and accounting scope, still in effect immediately before the update. An explicit same-basis reaffirmation can produce a zero revision. A new fiscal year, reinstatement after a withdrawal, or product-only forecast cannot substitute for a comparable pair.

For planning, both source values must be reconstructible strictly before the scheduled open minus 15 minutes, with the prior source already public before the current release. A displayed original wire minute plus one minute gives a historical availability proxy. This screen reviewed a necessary condition only, the existence of a comparable current metric in the original earnings release. It used public issuer releases and copies furnished to EDGAR. Separate slide decks, transcripts and conversion of growth percentages to implied dollar amounts were outside the screen. [SEC public EDGAR access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

The pinned 128-event development frame supplied 64 held events in blocks 3–5 with clean opening and closing label metadata. The screen used the prior audit's event clocks, caveats and block membership. It did not open market labels, access the Milestone 5 extension, acquire market prices or fit a model. [Pinned development frame](../config/m2-step3-combined-events.json) · [Coverage evidence and input digests](../reports/m6-guidance-coverage-result-2026-11-17.json)

## Observed exclusions and upper bound

| Held sample | Events | Issuers | Reaction sessions | Events by block 3 / 4 / 5 |
| --- | ---: | ---: | ---: | ---: |
| Starting clean metadata | 64 | 23 | 37 | 20 / 23 / 21 |
| Optimistic coverage ceiling | 32 | 11 | 25 | 11 / 11 / 10 |
| Planning minimum | 40 | 15 | 20 | At least 10 events in any two blocks |

Original releases rule out 32 rows. Twenty-one lack a bounded annual consolidated revenue outlook, five give only growth percentages, three guide only a single product, two exclude reimbursable expenses from revenue, and one guides first-quarter revenue only. The 32 remaining rows are an upper bound, since the review stopped before checking all prior guidance, timestamps and accounting bases. Even counting the eight growth-only, quarter-only and reimbursement-basis rows as potentially eligible would leave at most 40 events across 14 issuers. [Event-level exclusion evidence](../reports/m6-guidance-coverage-result-2026-11-17.json)

Two source pairs illustrate the measure. Alkami cut its fiscal 2025 consolidated revenue midpoint by 0.39% between July and October 2025. The RealReal raised its fiscal 2025 consolidated revenue midpoint by 2.68% between August and November 2025. The dates and ranges are present in the original releases. A full eligibility check would still reconcile intervening issuer disclosures. [Alkami July](https://www.prnewswire.com/news-releases/alkami-announces-second-quarter-2025-financial-results-302517660.html) · [Alkami October](https://www.prnewswire.com/news-releases/alkami-announces-third-quarter-2025-financial-results-302600234.html) · [The RealReal August](https://www.globenewswire.com/news-release/2025/08/07/3129634/0/en/The-RealReal-Announces-Second-Quarter-2025-Results.html) · [The RealReal November](https://www.globenewswire.com/news-release/2025/11/10/3185030/0/en/The-RealReal-Announces-Third-Quarter-2025-Results.html)

## Next research gate

Scope a broader development cohort using public disclosure history. Fix issuer inclusion and dates before opening market outcomes, and identify routine annual revenue guidance issuers from disclosures published before those dates. Measure coverage, revision variation and historical official opening availability on the same events. Any eventual validation would need a separate untouched cohort. The engine remains deferred, and the prospective 2027 study remains on hold. [Milestone 6 research closeout](M6-RESEARCH-CLOSEOUT.md)
