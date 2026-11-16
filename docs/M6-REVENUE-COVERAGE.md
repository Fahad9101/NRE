# Milestone 6 — Pre-open quarterly revenue coverage

**Coverage decision.** Year-over-year quarterly revenue growth supports planning one new offline development comparison at a fixed later pre-open cutoff. The original event news cutoff supplies too few rows. The 2027 study stays on hold.

## Measured coverage

The audit screened the 128 pinned development event specifications covering 23 issuers. It used only event metadata, the existing caveat definitions and publicly reported financial figures. It made no market-data requests, loaded no market outcome labels and excluded the Milestone 5 forward extension.

| Availability deadline | Usable events out of 128 | Clean rows in test blocks 3–5 | Issuers / reaction sessions in those clean test rows | Clean rows in earliest fit blocks 1–2 |
| --- | ---: | ---: | ---: | ---: |
| Existing event news cutoff | 37 | 25 | 14 / 17 | 12 |
| Scheduled reaction open | 88 | 51 | 21 / 32 | 35 |

The 51 clean pre-open rows divide into 17, 18 and 16 in test blocks 3, 4 and 5. Each has a distinct growth value, with 42 increases and nine decreases. All 51 pass the availability proxy more than 95 minutes before the scheduled open. They meet the planning screen of 40 clean rows across at least 15 issuers and 20 sessions, with two or more folds contributing at least ten rows. The intersection with the official opening-print sample remains unmeasured because the earlier diagnostic stored aggregate counts. The rows screened here are a coverage count based on caveat metadata. A later test must check actual pair eligibility and report missingness. [Event-level coverage record](../reports/m6-revenue-coverage-result-2026-11-16.json)

## Input and timing evidence

The feature is current-quarter consolidated revenue or net sales divided by the comparable prior-year quarter's amount, minus one. Both amounts come from one publication. Use the reported USD figures. Withhold a row when the prior amount is zero, the quarter pair is ambiguous, or an exhibit identifies a different number of weeks in the two quarters. This measures year-over-year growth. It uses no analyst-consensus benchmark.

Download SEC public submissions and company facts for the pinned issuers. Use the original 10-Q or 10-K accession, filer identity, recorded acceptance timestamp and comparability checks to bind the quarter pair. The periodic filings alone yielded 41 usable events by the open and 22 clean test rows. A targeted follow-up checked original wire tables and earnings exhibits for coverage gaps, plus the existing JBSS worked example. The final 88 use 33 wire releases, 15 SEC earnings exhibits and 40 periodic filings. Source selection used missing coverage and block assignment. Related SEC and wire copies were counted once. No paid feed was used. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [Wire evidence](../reports/m6-revenue-wire-evidence-2026-11-16.json) · [Exhibit evidence](../reports/m6-revenue-exhibit-evidence-2026-11-16.json)

Use the recorded wire publication minute plus one minute. For SEC filings, use acceptance plus two minutes and honor the recorded filing date in New York. Exclude filings accepted at or after 5:30 p.m. New York time due to possible next-business-day dissemination. This reconstructs availability from public records. It does not establish the original feed receipt time or guarantee the contents of a point-in-time data snapshot. The report binds the downloaded response hashes, source URLs and selected values. Repeated execution against the same cached inputs produced identical output. A later SEC re-download can differ as the public feeds are updated. [SEC dissemination guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data#business-hours-and-dissemination) · [Audit method](../config/m6-revenue-coverage.json)

## Proposed next experiment

Pre-register a new, fixed feature cutoff 15 minutes before the scheduled open. Use chronological earlier-block fitting and the same opening-to-close target and identical eligible rows in both arms. Compare the prior opening-gap size-and-direction baseline with the same baseline plus one revenue-growth feature. Before scoring, freeze the source priority, outlier handling, common eligibility, minimum support, and an improvement and uncertainty gate. Report sign imbalance and whether source coverage is selective by issuer, quarter and release timing. Use accepted daily-open proxies for an explicitly exploratory comparison, or separately verify the official-opening join before requiring it. The available evidence supports proposing this test. A model has yet to be fitted or scored on the measure, and any later confirmation needs a separate untouched cohort.
