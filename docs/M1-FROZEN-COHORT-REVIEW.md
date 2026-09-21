# Milestone 1 frozen-cohort evidence review

Reviewed 2026-09-21 against source commit `2d37cd3b39d3449e492282b6f2ed26d030ff978f`.
Milestone 1 remains open; zero accepted events. This review does not authorize price acquisition or a later milestone.

## Acquisition evidence preserved and replayed

The original Actions artifact from run `35532616764`, artifact `10611313563`, has been downloaded, CRC-checked, and preserved separately as `NRE-M1-SEC-Freeze-Audit.zip`. The durable copy is no longer dependent on the Actions artifact's October 20 expiry. Its SHA256 is `f2e01b0ca572ade034c047c40fab44e7218e59601f757c372cc1c306e6cff2b2`.

`reports/m1-frozen-archive-audit.json` records verification of all 902 ZIP members, 300 observation records, payload/transport hashes, relay extraction, pre-freeze observation times, the historical frame hash and the pinned parquet hash. Offline replay reproduced all three published freeze outputs exactly except for the regenerated execution timestamp: 300 processed issuers, 243 candidates, 215 candidate issuers and unchanged membership hash.

This establishes integrity and replayability of the archived representations. It does not authenticate them as raw SEC bytes. The parquet-to-frame transformation itself is not rerun by this audit.

Run from the repository root with the preserved ZIP:

```bash
PYTHONPATH=. python scripts/audit_frozen_archive.py /path/to/NRE-M1-SEC-Freeze-Audit.zip --output /tmp/archive-audit.json
PYTHONPATH=. python scripts/review_frozen_candidates.py
```

## Primary filing screen

The first 16 candidates in ascending frozen accession order have been read through the web tool's rendered SEC filing text. These are source-screening notes, not signed independent reviews. Full raw filing bytes and release exhibits have not yet been archived in this pass. Each note has its canonical filing URL and section locator in `reports/m1-primary-source-notes.json`.

The queue accounts for every frozen candidate: 16 screened, 227 pending. It never changes frozen membership, makes automatic exclusions, or promotes a filing date into a first-public timestamp.

Material findings:

- Butler National lists no Section 12(b) securities and has contradictory release years in its body versus cover/signature. Both issues need resolution; exchange eligibility is unproved.
- Tenet has a preliminary guidance announcement and a later results release for the same fiscal period. These need related-event treatment, not an automatic duplicate merge. Its senior-note ticker is not common stock.
- FNB and Regal Rexnord announce results before their filing/signature dates.
- Marzetti's cover date concerns an acquisition; its earnings announcement has a different date. Both catalyst components need recording.
- NCR Voyix uses common-stock ticker VYX despite an `ncr` filename. Its conference-call time does not establish release time.
- DMC stock purchase rights and Tyson's unlisted Class B shares must remain distinct from their public common-stock securities.

Across the full metadata ledger, 56 candidates belong to issuers with multiple filings, and one filing is an amendment. These are review flags, not demonstrated duplicates or exclusions.

## Search exposure and outstanding work

A source-discovery search returned unrelated results, including unsolicited ARW post-event price/performance commentary. It was not used for selection, eligibility or labeling. No structured cohort price query was made. Preserve this exposure record: do not represent the entire review session as having seen no outcome information, and do not expand or alter membership based on it. Any later expansion requires explicit review of this exposure and the preregistered selection policy.

Next: review the remaining primary filings; follow exhibits and issuer release archives; resolve preliminary/final announcements, securities and timestamp intervals; preserve permitted source representations; and establish sufficient source-side eligibility before any outcome acquisition. All 16 screened cases still lack verified first-public time and pre-release identity availability. No event has been removed or accepted in this pass.

Price-feed/adjustment/session-volume semantics, corporate-action coverage, permissions and independent timing checks remain separate acceptance requirements. The pilot still requires at least 100 complete eligible events across 25 issuers.
