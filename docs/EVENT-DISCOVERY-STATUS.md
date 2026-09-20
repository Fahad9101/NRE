# Event discovery evidence and current block

The four imported candidates have now undergone [source and price validation](FOUR-CANDIDATE-VALIDATION.md). All four remain quarantined; the pipeline results and additional intake blockers are recorded in `reports/four-candidate-review.json`. This supersedes any implication that only additional issuer uploads are needed to finish validation.

## Three additional uploads imported

Microsoft, IBM and NVIDIA uploads were parsed on 2026-09-20: 1,002, 1,002 and 1,000 filing records respectively. The full supplied histories contain 238 8-K/8-K-A records, preserved in `reports/additional-eight-k-ledger.json`. Source hashes, date ranges and continuation metadata are in `reports/additional-submissions-import.json`. All referenced history files end before 2026; none overlap this pilot.

The three new Item 2.02 candidates have release dates January 28 (Microsoft and IBM) and February 25 (NVIDIA), corroborated by their linked primary filings. Those filings also provide contemporaneous security-listing evidence, but not proof of identity availability before first news publication. Acceptance times remain distinct from release times. IBM's previously observed 16:08 ET wire minute precedes its 21:10:27 UTC SEC acceptance; this reinforces why acceptance cannot substitute for first-public timing.

Across the four uploaded issuers, 4,005 filing records yield ten 8-K records in the pilot filing-date window: four earnings candidates and six non-Item-2.02 records. The combined screen is `reports/discovery-progress.json`. Zero events are accepted. This remains an exploratory source-access batch; it has not been represented as a frozen or representative cohort. More issuer coverage and release-time evidence are still required.

## Apple upload imported

On 2026-09-20 the user supplied Apple's submissions JSON inside a Markdown code fence. Removing that fence produced valid JSON with 1,001 filing rows from July 24, 2015 through September 17, 2026. All columns have equal length. The existing `discover-sec` command produced 105 8-K/8-K-A records: 45 earnings candidates, 58 non-Item-2.02 records and two amendments requiring review across the full supplied history. See `reports/apple-submissions-import.json` and `reports/apple-eight-k-ledger.json`.

Within the pilot filing-date window, the January 29 earnings filing is the only Item 2.02 candidate; the February 24 filing reports voting results and is recorded as non-Item-2.02. This is a filing-date screen, not a completed release-date census. Original source-download time and first-public release time remain unverified. Zero events are accepted.

The referenced continuation file ends July 22, 2015, so it does not overlap the 2026 pilot. Full-history completeness remains false, while the requested pilot dates are present in the supplied recent-history range. There is no need to request that old continuation to investigate this pilot. Apple is now imported; the remaining discovery input is submissions data for additional issuers. The original upload is retained separately and its hash is recorded; it has not been represented as a direct SEC download by NRE.

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
