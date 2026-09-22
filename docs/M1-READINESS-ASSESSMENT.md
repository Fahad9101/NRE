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

The prior pass left National Healthcare Properties quarantined pending common-share listing scope, above. Resolved: its Class A common stock had no exchange listing at the February 20, 2026 event date. The company (formerly Healthcare Trust, Inc.) was a non-traded REIT at that time; only two preferred series (NHPAP, NHPBP) were listed, matching the candidate filing's own registration table. Its own 2026-04-13 investor-relations release describes the Nasdaq listing prospectively ("NHP has applied to list its Class A common stock"), and secondary sources place actual trading commencement at 2026-04-22 — both well after the event date. Current (2026-09-22) ticker status was deliberately not used as evidence. See `reports/m1-security-scope-review-2026-09-22.json` for full citations.

Current totals after this exclusion: **7 excluded, 236 quarantined, 0 complete events.** Frozen membership remains 243 candidates across 215 issuers; the membership SHA256 (`ae571171a7ba23c732d0230d9ed8c1dd21ac97f16bbda4ec087554a470ab2815`) was confirmed unchanged by recomputing `reports/m1-readiness-audit.json` through the existing `audit-cohort` engine. Milestone 1 remains BLOCKED — this is one disposition on one already-flagged candidate, not progress toward the 100-event/25-issuer target, which requires source chronology and price acquisition work still not started for any candidate.
