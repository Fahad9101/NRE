# Milestone 1 readiness assessment — September 21, 2026

**BLOCKED. Milestone 1 remains open. The historical reaction dataset and the audit of 100 complete events across 25 issuers are not complete.**

The frozen cohort contains 243 candidates across 215 issuers. Existing source notes cover 242 filing bodies; the remaining oversized FS KKR filing has a reviewed linked results exhibit. Displayed wire minutes exist for two candidates, but neither has verified first-public status. Partial SEC chronology checks do not establish the absence of earlier issuer or wire disclosures.

## New scope dispositions

The original frozen ledger is unchanged. `reports/m1-reviewed-candidate-ledger.json` adds dispositions while preserving every candidate ID and source hash. The first three exclusions under the existing pilot scope were:

| Candidate | Reason | Evidence |
| --- | --- | --- |
| 0000015847-26-000005 | Butler National identifies OTCQX: BUKS, outside eligible exchanges | [Release exhibit](https://www.sec.gov/Archives/edgar/data/15847/000001584726000005/buks-exx99x13126pressrelea.htm) |
| 0001174947-26-000123 | ENB identifies OTCQX: ENBP and announces acquisition completion | [Release exhibit](https://www.sec.gov/Archives/edgar/data/1437479/000117494726000123/ex99-1.htm) |
| 0001739445-26-000007 | Arcosa announces a divestiture; historical segment figures do not make it a company earnings-results release | [Release exhibit](https://www.sec.gov/Archives/edgar/data/1739445/000173944526000007/exh991pressrelease-bargesa.htm) |

These are source-based screening decisions by Codex, not independent human sign-off. After the security-scope follow-up below, six candidates are excluded and 237 remain quarantined. `reports/m1-event-staging.json` accounts for all 243 and carries observations, review flags and unresolved verification fields. It is candidate staging, not a completed news-reaction dataset. No remaining candidate has been assigned an invented publication timestamp, accepted security identity or price reaction.

## Alpaca validation

Sequential retries recovered from initial connector errors. The IBM diagnostic, outside the frozen cohort, returned all 82 expected daily sessions from January 2 through April 30, with consistent OHLCV structure, no missing sessions and no zero-volume sessions. Alpaca's calendar agreed with the expected dates.

The January 29 minute probe returned 391 ordered, unique timestamps with valid OHLCV: all 390 interval starts from 09:30 through 15:59 New York time, plus a 16:00 boundary bar. Daily volume differed from both the 390-bar sum and the sum including the boundary bar. This is a session-definition issue requiring reconciliation, not proof of bad data. A whole 16:00 minute cannot be assumed to isolate the closing auction.

`reports/m1-alpaca-coverage-review.json` records requests, canonical response hashes, counts and diagnostics. No raw market bars are published. Coverage of this one symbol does not establish cohort-wide coverage. Explicit adjustment semantics, regular-session volume, corporate-action review, historical security continuity, provider rights and pagination/completeness evidence remain unresolved. The connector does not expose adjustment or page-token controls. Accepted-for-labels remains false.

## Reproducible acceptance result

`reports/m1-readiness-audit.json` applies the existing acceptance engine to the complete reviewed candidate ledger and an explicitly empty accepted-input inventory. It reports **0 complete events, 0 complete-event issuers, 6 exclusions and 237 quarantined candidates**. This is a readiness audit, not the requested 100-event audit. Missing source text in the accepted inventory is not a claim that the separately preserved discovery archive is absent.

Recompute the engine result with:

```bash
python -m nre audit-cohort reports/m1-acceptance-input-inventory.json --protocol config/pilot.json --ledger reports/m1-reviewed-candidate-ledger.json --review reports/m1-acceptance-review.json --output /tmp/m1-audit.json
```

Exit status 2 is expected for BLOCKED. The published report adds `audit_scope` and `staging_counts`; all other fields must match the recomputation. The frozen membership hash remains `ae571171a7ba23c732d0230d9ed8c1dd21ac97f16bbda4ec087554a470ab2815`.

## Work required before acceptance

1. Obtain permitted, preserved release evidence and complete issuer/wire chronology, including preliminary announcements and version history. Current rendered-source access and incomplete issuer archives have not supported certification of first-public times.
2. Establish the relevant common-share identity and exchange eligibility at each event, resolving multi-class and related-issuer cases.
3. Resolve price adjustment, session volume, corporate-action, completeness and rights evidence; then acquire prices for source-eligible frozen candidates and build reaction labels.
4. Reach at least 100 complete events across 25 issuers and perform the required independent timing checks: two distinct events per represented timing class, each with two distinct reviewers. No independent reviews have been supplied or claimed.

Validation for this metadata update: 105 existing tests passed; acceptance output was recomputed and frozen membership reconciled. No investment rules or acceptance thresholds changed.

## Issuer-archive recovery follow-up

Browser navigation recovered Solesence's two-page 2026 archive and ACCESS's embedded historical feed. Solesence lists two 2026 announcements before its target release: a February executive appointment and a March call notice. ACCESS lists four: a conference notice, two product announcements and a call notice. The reviewed release bodies do not announce earlier quarterly results. ACCESS's January 28 conference presentation remains an explicit earlier-disclosure channel to inspect. Solesence's corporate news page also points to a January industry webinar whose content has not been reviewed.

The two December Solesence personnel exhibits and ACCESS's December buyback exhibit were screened. Historical ticker/exchange corroboration improved, but continuous security identity and first-public status remain unverified.

A timestamp-quality issue was found: ACCESS's March 5 notice says EDT, while New York was on EST. Its archive feed also displays unlabeled times three hours behind newsroom clock readings. No timezone conversion or earlier-publication conclusion has been inferred from these displays. Detailed observations and URLs are in `reports/m1-earlier-disclosure-review.json`. At the archive follow-up, counts were 0 complete events, 3 exclusions and 240 quarantined candidates; the security-scope follow-up below supersedes those disposition counts.

## Security-scope follow-up

`reports/m1-security-scope-review.json` records three additional exclusions confirmed directly against SEC filing registration tables: ARLP and CAPL are limited-partnership units; ELTP is OTCQB common stock. Current totals are **6 excluded, 237 quarantined, 0 complete events**. Frozen membership remains 243 candidates across 215 issuers.

Elite's Item 2.02 expressly places the quarterly 10-Q before its press release, so the release cannot simply be treated as the first disclosure. National Healthcare Properties lists only preferred classes in its registration table; these instruments are ineligible, but its candidate remains quarantined until common-share listing scope is settled.

The ACCESS conference presentation was not recovered by the focused follow-up searches. Searches are not negative evidence of disclosure. The remaining work is source evidence, historical identity, price semantics and independent review; software test success does not satisfy these gates. The acceptance report was recomputed after the disposition changes and frozen membership was checked unchanged.

## Single-event completion check — September 22

`reports/m1-slsn-completion-check.json` specifies the exact remaining evidence for Solesence and a conditional acquisition window. If its displayed March 31 08:02 ET wire minute is confirmed, the previous-close anchor is March 30 and the twentieth reaction session is April 28: 21 required daily sessions including the anchor. This calendar plan contains no observed returns and is not an accepted reaction record.

The January 8 webinar landing page is reachable, but its retrieved text contains no transcript or slides. Its product-development description cannot certify what was said. The Alpaca corporate-action query for SLSN from November 1 through April 30 returned no announcements; the empty response does not certify corporate-action or identity coverage.

Alpaca's official historical-bars documentation confirms a raw adjustment default, an explicit adjustment parameter, and the requirement to inspect the next-page token even when fewer rows than the requested limit are returned. The connected bars tool exposes neither adjustment nor page-token controls. No separate Alpaca credentials are configured in this runtime (only presence was checked; no secrets were printed). This does not establish whether GitHub secrets exist.

To remove the price-access limitation, the acquisition runtime needs securely configured Alpaca credentials or a permitted original API export retaining explicit raw/SIP/as-of parameters and every response page through a terminal token. Credentials must not be pasted into chat or committed. That access alone does not resolve session-volume methodology, research permissions, historical identity or first-public timing. Source-side evidence is still required before cohort outcomes are acquired. Milestone 1 remains open with zero complete events.

## GitHub Actions Alpaca access resolved — September 22

Repository Actions secrets are now correctly named and valid; `.github/workflows/alpaca-access.yml` exits 0 against live credentials (run `35758685542`, commit `76c3a9f`). All 82 expected IBM daily sessions were retrieved with zero missing and zero zero-volume rows, with SIP feed, raw adjustment, ascending order, explicit `asof` and complete pagination through an observed terminal page token all confirmed. See [docs/ALPACA-ACCESS.md](ALPACA-ACCESS.md) and `reports/alpaca-github-actions-diagnostic.json` for full evidence. This resolves the direct-REST access question; it remains an IBM-only diagnostic outside the frozen cohort (`accepted_for_labels: false`), and session-volume methodology, corporate-action coverage, historical identity, provider rights and durable raw-response archival remain open.

## Security-scope follow-up — September 22

The prior pass left National Healthcare Properties quarantined pending common-share listing scope, above. Resolved: its Class A common stock had no exchange listing at the February 20, 2026 event date. The company (formerly Healthcare Trust, Inc.) was a non-traded REIT at that time; only two preferred series (NHPAP, NHPBP) were listed, matching the candidate filing's own registration table. Its own 2026-04-13 investor-relations release describes the Nasdaq listing prospectively ("NHP has applied to list its Class A common stock"), and secondary sources place actual trading commencement at 2026-04-22 — both well after the event date. Current (2026-09-22) ticker status was deliberately not used as evidence.

The same pass then worked through every remaining candidate whose primary-source screening note carried an identity-related review flag (`LISTING_ELIGIBILITY_UNRESOLVED`, `NO_EXCHANGE_LISTING_IN_FILING`, `SECURITY_CLASS_REVIEW`, `NO_COMMON_STOCK_LISTING_IN_COVER`, `PARTNERSHIP_SECURITY_TYPE_REVIEW`, `MULTIPLE_SHARE_CLASSES`, `MULTIPLE_COMMON_CLASSES_REVIEW`, `MULTIPLE_LISTINGS_REVIEW`), other than ones already resolved (ARLP, CAPL, ELTP, NHP). Seven more candidates were excluded, each independently confirmed by direct SEC filing review plus a corroborating trading-venue check: Juniata Valley Financial Corp. (JUVF, OTCQX), ENB Financial Corp (ENBP, OTCQX — same issuer as the already-excluded 0001174947-26-000123), EBR Systems, Inc. (ASX-listed, US OTCPK only — an initial assumption that this was the Nasdaq-listed "EBR" ticker was wrong and caught by verification before it was acted on), Farmers and Merchants Bancshares, Inc. (FMFG, OTC), ParkerVision, Inc. (PRKR, OTCQB), MariMed Inc. (MRMD, OTCQX/CSE), and Federal Home Loan Bank of Des Moines (a member-owned cooperative with no public listing at all).

Five more candidates had their identity flag resolved as *eligible* rather than excluded, each requiring a specific-class decision rather than a fact check: Gray Media, Inc. (two NYSE common classes; used the plainly-titled "Common stock" GTN over "Class A common stock" GTN.A), Atlanta Braves Holdings, Inc. (two Nasdaq common classes, neither plainly titled; used Series C / BATRK, which has roughly 5x the public float of Series A / BATRA), White Mountains Insurance Group, Ltd. (one common-share class dual-listed on NYSE and the Bermuda Stock Exchange — not a class-selection question at all; used the NYSE listing, WTM), Fabrinet (Cayman Islands-incorporated ordinary shares listed directly on NYSE as FN, not via ADR), and Weatherford International plc (Ireland-incorporated ordinary shares listed directly on Nasdaq as WFRD, not via ADR). Two general, documented policies back these five: a class-selection policy (prefer a plainly-titled "Common stock" class when one exists among listed classes; otherwise prefer materially larger public float; otherwise leave quarantined rather than force a pick) and a foreign-ordinary-shares policy (directly exchange-listed foreign ordinary shares are in scope; ADRs are explicitly excluded from this policy and need separate review). Both policies were proposed and applied without independent human sign-off — they are flagged here for your review, not asserted as final authority. DMC Global (BOOM) and Tyson Foods (TSN) were checked against the same flags and found already unambiguous (each has exactly one listed common class) and needed no change.

Full citations, the exact policy text, and per-candidate reasoning are in `reports/m1-security-scope-review-2026-09-22.json`.

Separately, the SLSN January 8, 2026 webinar thread (the last open item on that candidate per the prior completion check) was pushed as far as open-web research allows: the event's own landing page, a targeted search, Solesence's own webinar archive (which does not list this session at all), and the one article that looked like related coverage (which turned out to be from 2020, unrelated) were all checked. No recording, transcript or financial content was found anywhere, and the topic is confirmed to be SPF product-development strategy, not earnings. `first_public_verified` stays `false` — this strengthens the evidence without and cannot substitute for either a recording turning up or independent human review. See `reports/m1-slsn-webinar-followup-2026-09-22.json`.

Current totals after this batch: **14 excluded, 229 quarantined, 0 complete events.** Frozen membership remains 243 candidates across 215 issuers; the membership SHA256 (`ae571171a7ba23c732d0230d9ed8c1dd21ac97f16bbda4ec087554a470ab2815`) was confirmed unchanged by recomputing `reports/m1-readiness-audit.json` through the existing `audit-cohort` engine after every change in this batch. Milestone 1 remains BLOCKED. This narrows the addressable candidate pool (229 quarantined, down from 237 at the start of today) and clears five more candidates for chronology work, but none of it is progress toward the 100-event/25-issuer target by itself — no candidate has cleared source chronology, and price acquisition has not been attempted for any cohort candidate. The independent-review requirement (two distinct human reviewers per timing class) also remains completely untouched by this or any other automated work; it cannot be satisfied without an actual second human reviewer.

## Foreign-incorporated common shares — September 22

The remaining `ISSUER_JURISDICTION_REVIEW`-flagged candidates were checked directly: Starz Entertainment Corp. (STRZ), Arbutus Biopharma (ABUS), Xenon Pharmaceuticals (XENE), Pangaea Logistics Solutions (PANL) and AbCellera Biologics (ABCL) are each British Columbia/Canada/Bermuda-incorporated but list exactly one Nasdaq class, explicitly titled "Common Shares" or "Common Stock" by the filer's own registration table — even more direct than Fabrinet/Weatherford's "ordinary shares" wording. This generalized the earlier foreign-ordinary-shares policy into `foreign_common_shares_policy`: foreign incorporation alone does not disqualify a directly NASDAQ/NYSE/NYSE American-listed common/ordinary share, regardless of which of those two words the filer uses, since the pilot's scope is "U.S.-listed," not "U.S.-incorporated"; ADRs remain excluded from this policy. All six are now identity-eligible and quarantined only for chronology, same as before. Roivant Sciences' second candidate (0001140361-26-012885) was left untouched — it's flagged for a release-date/event-window question, not identity, and stays out of scope for this pass. Dispositions unchanged (14 excluded, 229 quarantined) since these are reason-field updates, not exclusions.

## Review-standard amendment — September 22

The project owner (Fahad9101) was presented with two options for the independent-review gate: recruit a second reviewer, or explicitly revisit the requirement for a solo-operator project. Their exact words, verbatim, authorizing the latter: **"i take responsibility from here. no other reviewer. resume work."**

This is treated as a conscious, documented protocol amendment, not a silent weakening: `independent_timing_spot_checks` in `nre/acceptance.py` previously required two distinct reviewer names per spot-checked event; it now requires one. The "two distinct events per included timing class" dimension is unchanged. A real, non-blank named reviewer is still mandatory — this reduces independence, not accountability. `docs/MILESTONE-1-RUNBOOK.md` and the code comment at the gate were both updated to reference this section, and `tests/test_acceptance.py` was updated to test the new one-reviewer boundary (a single named reviewer now passes; blank or empty reviewer lists still fail).

What this does and does not change: it lowers the bar for the `independent_timing_spot_checks` gate specifically. It does not change any other acceptance gate, does not alter frozen candidate membership, and does not itself accept any event — `audit_cohort` still never sets `milestone_accepted: true` by design (see `nre/acceptance.py`); that remains a human declaration the project owner makes outside this codebase after reviewing the evidence, never something a script certifies. Concretely, going forward, the project owner is expected to personally review the evidence compiled for a candidate (e.g. an SLSN-style evidence package) and record their own name as the reviewer in `spot_checks` before any candidate can be treated as accepted — this document does not itself perform that review for any candidate.

## SLSN signed off; real pipeline run for the first time — September 23

The project owner reviewed `reports/m1-slsn-signoff-packet-2026-09-22.json` and signed off on timing and identity with the words "okay sign off" (2026-09-23), accepting the one residual gap search cannot close. `first_public_verified` and `historical_identity_verified` are now `true` for this candidate; the sign-off record is in that same packet.

That unlocked the first real, non-synthetic, non-out-of-cohort run of the full `nre.dataset.build()` pipeline. `nre/slsn_acquire.py` (new, `.github/workflows/slsn-acquire.yml`) fetches real SIP daily bars and corporate actions for SLSN and feeds them straight into the existing pipeline, printing only derived results — computed labels, counts, hashes — never raw OHLCV, including redacting the anchor close price that `build()` embeds as the return denominator. Result (run `35822680161`): all 21 required sessions present, zero missing, zero zero-volume; timezone/session classification correct (`premarket`, `2026-03-31`, matching every prior manual calculation); Alpaca's corporate-actions endpoint returned a genuinely empty, fully-paginated response. The event still quarantines, on exactly one gate: `PROVIDER_USE_UNVERIFIED`. `provider.research_permitted` was deliberately left `false` because Alpaca's terms (incorporating the NASDAQ OMX Global Subscriber Agreement and a Market Data Display Services agreement) have not actually been reviewed — checked today, still unresolved, not something a quick search settles. Full result in `reports/m1-slsn-real-acquisition-result-2026-09-23.json`.

Corporate-action completeness now has two independent clean signals (empty, paginated Alpaca response; no Item 3.03/5.03 SEC filings near the window) and is presented as its own explicit sign-off item in the packet, deliberately not folded into the timing sign-off. Provider rights is the one gate nothing has touched yet.
