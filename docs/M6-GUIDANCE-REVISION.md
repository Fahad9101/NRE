# Milestone 6 annual-guidance comparison, version 2

The longer source-reviewed training window supplies 44 clean rows across 20 issuers and clears the registered support floor of 20 rows across 10 issuers. Version 2 fixes training sessions at July 1, 2024 through June 30, 2025 and retains the same 20 issuer CIKs, 58 held events, inherited source masks, model settings and decision thresholds. The original half-year study remains frozen with its insufficient-support result. No closing outcomes were requested and no model was fitted for either version. [Version 2 protocol](../config/m6-guidance-protocol-v2.json) · [Readiness result](../reports/m6-guidance-v2-readiness-2026-11-19.json) · [Original source gate](M6-GUIDANCE-READINESS.md)

| Source support before market-quality checks | Added July–December 2024 | Inherited January–June 2025 | Combined training |
| --- | ---: | ---: | ---: |
| Candidate pairs | 37 | 24 | 61 |
| Hard source exclusions | 7 | 2 | 9 |
| Additional soft-only masks | 4 | 4 | 8 |
| Clean rows | 26 | 18 | 44 |
| All-defined sensitivity rows | 30 | 22 | 52 |

## Added source evidence

The added half-year has 40 original earnings filings. Thirty-seven supply comparable annual guidance pairs and three initiate a new fiscal-year outlook without a comparable active prior. The audit inventory contains 190 original or amended 2024 current reports across the same 20 CIKs. It preserves original SEC URLs and retrieved submission digests, including one early SNPS packet that exceeded the bounded decompression limit. No candidate uses that packet as its numeric prior; later original outlooks establish the reviewed pair. Dated filing covers verify each added candidate's historical Nasdaq symbol. [Earlier-window evidence and complete disposition ledger](../reports/m6-guidance-earlier-evidence-2026-11-19.json)

The audit reconciles intervening disclosures rather than assuming the preceding earnings release is the latest outlook. Cognizant's August 27 acquisition-completion release updates annual revenue guidance to include Belcan. Intuit's September 26 investor-day release explicitly reaffirms numeric annual bounds. Their original issuer pages provide precise publication times; the source objects record those publisher timestamps with a conservative one-minute availability buffer. They do not fabricate SEC acceptance timestamps. Date-only original priors, when used, require availability by the next New York midnight. SEC inputs retain the existing acceptance-plus-two-minute rule, filing-date floor and exclusion at or after 17:30 New York. [Prior sources and clock representations](../reports/m6-guidance-earlier-evidence-2026-11-19.json)

New source masks use the original taxonomy. Acquisitions with unresolved guidance comparability are hard failures; newly announced repurchase authority and non-CEO appointments are soft caveats. A departure or retirement alone does not become an appointment. An unchanged dividend, an existing authorization or a recap of earlier public news does not become a newly announced catalyst. The complete event-level rationale is fixed before market outcomes. [Additional source masks](../reports/m6-guidance-earlier-source-masks-2026-11-19.json)

The final review also withholds Amgen's August pair because the first-public timing and materiality of its AMG 193 regulatory-designation update remain unresolved. This conservative disposition does not assert that every early-stage designation is automatically material. Its October regulatory-date recap has an independently dated October 18 original reporter account quoting Amgen directly, before the October observation window, and remains source eligible. [Amgen source dispositions](../reports/m6-guidance-earlier-source-masks-2026-11-19.json)

## What is preserved

Both versions use the opening-gap ridge baseline, one transformed annual-revenue revision column, the same three chronological folds and training-only standardization. The minimum remains 20 common fit rows across 10 issuers in every fold. Held scoring still requires 40 paired observations, 15 issuers, 20 sessions, sufficient up/down gap support and at least two folds with 10 pairs. The same MSE improvement, clustered bootstrap and sensitivity gates apply, with one logged scoring attempt. The revision verifier rejects changes to those settings even if the revised file is rehashed. [Protocol](../config/m6-guidance-protocol-v2.json) · [Verifier](../nre/m6_guidance_revision.py)

The inherited source masks leave 53 clean held rows across 19 issuers and 42 sessions; the sensitivity retains 55. The clean source subset contains 38 raises, 12 unchanged revisions and three cuts across two issuers. These source counts remain upper bounds before market-quality and maturity checks, and the small cut subgroup cannot support a directional claim. [Inherited source masks](../reports/m6-guidance-source-masks-2026-11-19.json) · [Recomputed support](../reports/m6-guidance-v2-readiness-2026-11-19.json)

## Interpretation and next step

The added training overlaps calendar-2024 issuer qualification and partly predates the September 30 roster's November 27 publication. Version 2 explicitly overrides only the original frame's training dates and preserves the frame itself. It is retrospective development using a selected historical roster, not evidence of a contemporaneously available July 2024 universe or independent validation. The change was motivated by source insufficiency before closing outcomes, not by model performance. [Revision lineage and disclosure](../config/m6-guidance-protocol-v2.json)

Run `python -m nre.m6_guidance_revision` to verify the original chain, additive source pins, unchanged settings, new numeric guidance and clock evidence, economic-event deduplication, observation windows and source-support ceilings. It returns `READY_FOR_RAW_WARMUP_OPENINGS`. The next preparation step is to verify official openings for the complete source-eligible training universe using the existing historical connection. Scoring requires the remaining checks for a common price basis, label maturity and feature variation, plus a frozen acquisition manifest with hash-only commitments. Exhaustive periodic-report content review and corporate-action clearance remain outstanding. [Freeze](../reports/m6-guidance-v2-freeze-2026-11-19.json) · [Tests](../tests/test_m6_guidance_revision.py)

The public-disclosure work needs no additional subscription. The engine, proposed 2027 study, trading and Milestones 7–9 remain deferred.
