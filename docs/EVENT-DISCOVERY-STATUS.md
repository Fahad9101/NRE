# Event discovery evidence and current block

The source review on 2026-09-20 established three useful observations, recorded in `reports/event-source-review.json`:

- IBM's issuer-distributed [wire release](https://www.prnewswire.com/news-releases/ibm-releases-fourth-quarter-results-302673165.html) displays January 28, 2026 at 16:08 ET. This improves date-only evidence to a publication minute. It does not prove an exact second or earliest publication across channels.
- Apple's [filing index](https://www.sec.gov/Archives/edgar/data/320193/000032019326000005/0000320193-26-000005-index.html) confirms accession 0000320193-26-000005, Item 2.02 and acceptance at 16:30:33 on January 29. Filing acceptance stays separate from release time.
- Apple's [primary filing](https://www.sec.gov/Archives/edgar/data/320193/000032019326000005/aapl-20260129.htm) identifies AAPL common shares listed on Nasdaq. Availability before first-public news still needs review.

These are exploratory source records, not the frozen acceptance ledger. The current builder requires second-precision verified first-public timestamps. No seconds were invented, no acceptance time was substituted for release time, and no event was promoted. Raw source bytes were not acquired for these pages; the report makes no raw-byte checksum claim.

## Input needed to complete discovery

The submissions feed remains inaccessible here, although selected filing pages can be read. Search results do not establish complete coverage. To resume the existing protocol without replacing it, supply original SEC submissions JSON files for a declared issuer set, plus their referenced historical continuation files covering the pilot window. Keep filenames, download timestamps, source URLs and the issuer-selection rationale. Uploading these files does not require credentials.

The existing offline parser can ingest each original file:

```sh
python -m nre discover-sec data/sec/CIK0000320193.json --cik 320193 --output data/sec/apple-candidates.json
```

This single-issuer example is not a sufficient cohort. Aggregate and reconcile the whole supplied issuer set, retain every Item 2.02 candidate and exclusion, and freeze membership before further outcome retrieval. The previously examined IBM prices must remain disclosed as exploratory. A complete census and enough eligible events still require verification; neither a ZIP upload nor successful parsing automatically satisfies the 100-event / 25-issuer gate.

The master protocol and milestone boundary are unchanged. Milestone 1 remains open, with zero accepted real event outcomes.
