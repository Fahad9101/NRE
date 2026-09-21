# Milestone 1 frozen-cohort evidence review

Reviewed 2026-09-21 against the freeze at `2d37cd3b39d3449e492282b6f2ed26d030ff978f`; expanded from the initial screen at `2293af7aad889c8b6510a7767e1b4940f7fd147f`.
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

All 243 candidates have been attempted in ascending frozen accession order. Rendered SEC filing bodies were screened for 241 candidates, focusing on the registration table, Item 2.02 and related sections. These are source-screening notes, not full exhibit reviews or signed independent reviews. Full raw filing bytes and release exhibits have not yet been archived in this pass. Each note has its canonical filing URL and section locator in `reports/m1-primary-source-notes.json`. Null fields remain unresolved; a stated period end is recorded as the source presents it, including flagged inconsistencies.

The queue accounts for every frozen candidate: 241 screened, two pending. It never changes frozen membership, makes automatic exclusions, or promotes a filing date into a first-public timestamp. All 241 screened cases still require eligibility and timing review. A date in a release description, a cover date, a conference-call time or a filing-acceptance time is not verified first-public time.

`reports/m1-primary-retrieval-issues.json` records the two unresolved retrievals: FS KKR accession `0001104659-26-019719` exceeded the service's content-length limit, and accession `0001539638-26-000004` remained inaccessible after a retry. Mirum's initial timeout was resolved by a second fetch. Retrieval failures are not exclusions.

Material findings:

- Butler National lists no Section 12(b) securities and has contradictory release years in its body versus cover/signature. Both issues need resolution; exchange eligibility is unproved.
- Tenet has a preliminary guidance announcement and a later results release for the same fiscal period. These need related-event treatment, not an automatic duplicate merge. Its senior-note ticker is not common stock.
- FNB and Regal Rexnord announce results before their filing/signature dates.
- Marzetti's cover date concerns an acquisition; its earnings announcement has a different date. Both catalyst components need recording.
- NCR Voyix uses common-stock ticker VYX despite an `ncr` filename. Its conference-call time does not establish release time.
- DMC stock purchase rights and Tyson's unlisted Class B shares must remain distinct from their public common-stock securities.
- Preliminary/final sequences also occur for PTC, Matson, PodcastOne, Life Time, Castle, Mirum and other issuers. ESAB's later filing explicitly says its results are consistent with the earlier preliminary figures. These require novelty and common-event review.
- FS KKR's January filing schedules a future call. NovaBay reports token holdings and staking rewards. Arcosa's February 24 filing concerns a divestiture. None is automatically equivalent to a complete quarterly earnings release.
- ENB's acquisition filing has Items 2.01 and 7.01 in its rendered body, despite the candidate's Item 2.02 metadata. Preserve the frozen record and reconcile the source mismatch.
- ACCESS Newswire's March 19 Item 2.02 states a December 31, 2026 period end. That apparent future-period inconsistency is retained and flagged for exhibit reconciliation, not silently corrected.
- Mercantile Bank's amendment corrects presentation metrics and says other original information is unchanged. It is not automatically a second earnings event.
- Alliance Resource and CrossAmerica list partnership units; National Healthcare Properties lists preferred stock only. Several issuers list no Section 12(b) securities, and Elite's table identifies OTCQB. Common-stock and exchange eligibility remain unresolved for these cases.
- Atlanta Braves and Gray Media list multiple common classes. Joint parent/subsidiary filings, ordinary shares, foreign incorporation and dual listings need explicit identity and scope review before selecting a security.
- Roivant's April 2 cash update and RenX's April 1 release fall outside the January 5–March 31 event window even though they are retained in the filing-buffer cohort.

Across the full metadata ledger, 56 candidates belong to issuers with multiple filings, and one filing is an amendment. These are review flags, not demonstrated duplicates or exclusions.

## Search exposure and outstanding work

A source-discovery search returned unrelated results, including unsolicited ARW post-event price/performance commentary. It was not used for selection, eligibility or labeling. No structured cohort price query was made. Preserve this exposure record: do not represent the entire review session as having seen no outcome information, and do not expand or alter membership based on it. Any later expansion requires explicit review of this exposure and the preregistered selection policy.

Next: retrieve the two inaccessible accessions; follow exhibits and issuer release archives; resolve the metadata and period-end conflicts, preliminary/final announcements, securities and timestamp intervals; preserve permitted source representations; and establish sufficient source-side eligibility before any outcome acquisition. All 241 screened cases still lack verified first-public time and pre-release identity availability. No event has been removed or accepted in this pass. The expanded pass used direct canonical SEC URLs and made no structured cohort price query.

Price-feed/adjustment/session-volume semantics, corporate-action coverage, permissions and independent timing checks remain separate acceptance requirements. The pilot still requires at least 100 complete eligible events across 25 issuers.
