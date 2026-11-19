# Milestone 6 guidance source audit

The registered annual-guidance comparison stops before price-label acquisition because its first chronological fold cannot meet the clean training minimum. The source audit verified 24 warmup pairs; two hard exclusions and four soft caveats leave 18 clean rows across 16 issuers. The registered minimum is 20 rows across 10 issuers in every fold. The all-defined sensitivity retains 22 rows, but cannot replace the clean primary. No closing outcomes were requested and no model was fitted. This is insufficient support, not a finding about predictive performance. [Protocol](../config/m6-guidance-protocol.json) · [Reproducible result](../reports/m6-guidance-preparation-result-2026-11-19.json)

| Source support before market-quality checks | Warmup | 2025 H2 held | 2026 H1 held | 2026 Q3 held | Held total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Reviewed candidate pairs | 24 | 27 | 18 | 13 | 58 |
| All-defined after hard source exclusions | 22 | 26 | 16 | 13 | 55 |
| Clean after hard and soft source masks | 18 | 26 | 15 | 12 | 53 |

These are upper bounds for the reviewed candidate rows. Raw warmup openings, common price basis, label maturity and other market-quality checks could reduce them. Later held blocks cannot supply training observations for the first fold. [Warmup evidence](../reports/m6-guidance-warmup-evidence-2026-11-19.json) · [Complete source masks](../reports/m6-guidance-source-masks-2026-11-19.json)

## Discovery and disposition

The warmup audit covers the fixed 20 held CIKs and January 2–June 30, 2025 reaction sessions. Its 43 original Item 2.02 filing dispositions comprise 24 reviewed guidance pairs, 16 fiscal-year initiations without a verified comparable active prior, two preliminary disclosures assigned to their final economic-release clusters, and one restructuring disclosure that does not create an extra quarterly earnings event. The manifest includes prior/current ranges and source timestamps, original SEC URLs, retrieved archive digests, dated listing covers, and submissions provenance. It also records 22 additional late-2024/early-2025 lookback archives. These checks found no extra qualifying pair in the reviewed sources; they do not establish exhaustive coverage of every public issuer communication. [Discovery ledger and features](../reports/m6-guidance-warmup-evidence-2026-11-19.json)

The two hard warmup exclusions are CSGP's changed consolidation scope after Matterport and DDOG's unresolved old/new guidance comparability after acquisitions. The four soft warmup masks are newly announced repurchase authorizations at DXCM, CRWD and MDB, and non-CEO appointments at ZS. Resolving DDOG favorably would raise the clean count to 19, still below 20. [Warmup source dispositions](../reports/m6-guidance-source-masks-2026-11-19.json)

EA's January preliminary update revised annual net bookings and quarterly GAAP revenue, without replacing the annual GAAP revenue bounds used for the February pair. Its February accelerated repurchase uses existing authority, so it does not meet the registered new-authorization caveat. SNPS's May 29 guidance suspension was published after that day's feature cutoff and cannot supply a retrospective exclusion. Both pairs remain source eligible. [Decision rationale and original references](../reports/m6-guidance-source-masks-2026-11-19.json)

The held-source audit identifies three hard exclusions: CRWD's Onum announcement, CTSH's material workforce restructuring, and MDB's unresolved Clarity acquisition provenance/comparability. SNPS's new repurchase authority and VRSK's interim CIO appointment supply two soft masks. Periodic filing metadata was checked, but a complete content audit of every periodic report and corporate-action/price-basis clearance remains outstanding. Consequently, the 53 clean held rows are provisional source support, not cleared market observations. [Held source dispositions and limitations](../reports/m6-guidance-source-masks-2026-11-19.json)

## Reproduction and boundary

Run:

```bash
python -m nre.m6_guidance_readiness
python -m unittest discover -s tests -p 'test_m6*.py' -v
```

The verifier checks the original registration and its pinned inputs, both complete preparation manifests, its own implementation digest, exact candidate membership, source windows and taxonomy, warmup ranges and clocks, listing metadata, and chronological source-support ceilings. It returns `STOP_INSUFFICIENT_SOURCE_SUPPORT`. Tests cover a source-mask checksum failure, a repinned but invalid observation window, the primary/sensitivity separation, and reproduction of the published result. [Preparation freeze](../reports/m6-guidance-preparation-freeze-2026-11-19.json) · [Verifier](../nre/m6_guidance_readiness.py) · [Tests](../tests/test_m6_guidance_readiness.py)

The frozen protocol remains unchanged. There is no scoring attempt, hash-only label acquisition, or new raw warmup market request to execute after this source gate fails. Continuing annual-guidance research requires a separately versioned design supported by a larger verified training sample, fixed before closing outcomes are requested. A source-only assessment of a longer historical warmup is the next research step and can use the same public disclosures without a subscription. The engine, prospective 2027 study and Milestones 7–9 remain deferred.
