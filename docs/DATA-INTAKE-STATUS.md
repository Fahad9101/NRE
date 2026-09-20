# Real-data acquisition status

On 2026-09-20, the acquisition search obtained the publicly documented Alpha Vantage IBM daily-history demo. This is an actual provider response, not a synthetic fixture. It contains 6,761 daily rows from 1999-11-01 through 2026-09-18. All 82 expected sessions from 2026-01-02 through 2026-04-30 are present, and numeric OHLCV consistency checks passed. Receipt time and response hash are in `reports/real-data-intake.json`.

The provider's documented demonstration endpoint is available without creating an account or buying credits. Its general full-history service is premium; a working IBM demo does not imply free arbitrary-symbol access. The terms support private individual research/testing; no public raw-data redistribution or commercial license is asserted. Accordingly the data was retained privately as `NRE-IBM-Historical-Prices.json`, not committed to this public repository. The report records the source URL, hash, coverage, terms URL and validation limitations.

Official Apple and Microsoft release HTML files were downloaded and hashed. Apple's source carries only a publication date and a later modification timestamp. Microsoft's visible call time is not a release timestamp. IBM's official release was readable through web retrieval, but direct HTML download timed out. All three remain date-level exploratory candidates with first-public verification false. Their fields and provenance are recorded in the intake report; no full issuer articles are redistributed here.

**This intake is not the frozen acceptance cohort.** Sources were assessed for access capability, and IBM was selected because it is the documented demonstration symbol. No market-wide census, independent timing checks, corporate-action audit, verified regular-session semantics, or historical identity review is complete. Zero events count toward the 100-event/25-issuer gate. The original empty-cohort audit remains a historical report of the gate run before this intake, not a claim that no real prices have subsequently been acquired.

Other tested routes: the existing Financial Datasets connector returned an insufficient-credit response (zero balance); nothing was purchased. Stooq's public download page returned a browser-verification challenge; no bypass was attempted. SEC's previously recorded 403 remains a separate source-access limitation. Official issuer releases offer a legitimate alternate source of news, subject to first-public timestamp review.

Update on 2026-09-20: the existing Alpaca connector is available and authenticated. Both historical IEX and SIP probes succeeded. An explicit SIP request for IBM returned all 82 sessions from January 2 through April 30, matching the provider calendar and passing OHLCV consistency checks. See [Alpaca access](ALPACA-ACCESS.md), `config/alpaca.json` and `reports/alpaca-access.json`. Credentials remain connector-managed; standalone CLI and GitHub Actions access are not configured. Session semantics, adjustment behavior, pagination, source rights and the event acceptance reviews remain pending. Successful access does not establish dataset acceptance or live SIP entitlement.

References:

- [Alpha Vantage documentation](https://www.alphavantage.co/documentation/)
- [Alpha Vantage terms](https://www.alphavantage.co/terms_of_service/)
- [Alpaca data plans and authentication](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [Apple release](https://www.apple.com/newsroom/2026/01/apple-reports-first-quarter-results/)
- [Microsoft release](https://www.microsoft.com/en-us/Investor/earnings/FY-2026-Q2/press-release-webcast)
- [IBM release](https://newsroom.ibm.com/2026-01-28-IBM-RELEASES-FOURTH-QUARTER-RESULTS)
