# Four-candidate validation

The four uploaded issuers were reviewed on 2026-09-20. `reports/four-candidate-review.json` records the actual intake audit, provisional corporate-action windows and pipeline quarantine results. No candidate passed acceptance, and no predictive performance was measured.

| Issuer | Publication evidence | Pipeline reason |
| --- | --- | --- |
| Apple | Issuer date January 29; SEC acceptance is a distinct time | Ambiguous publication time |
| Microsoft | Issuer page metadata 21:08:16 UTC January 28, later than SEC acceptance 21:04:38 UTC | First-public time unverified |
| IBM | Issuer-distributed wire displays January 28, 16:08 ET, without seconds | Ambiguous publication time |
| NVIDIA | Issuer page date February 25; exact first-public time unresolved | Ambiguous publication time |

The Microsoft page's precise metadata is not proof of earliest publication. Its later modification time is also not substituted. The script preserves unknown timing instead of inventing seconds or assigning filing acceptance as the release time. Source records in the review bundle are explicitly analyst notes, not original archived articles or independently signed-off evidence.

Alpaca SIP returned 82 daily bars per symbol for January 2–April 30: 328 rows, with no missing expected sessions or zero-volume rows and valid OHLCV. This is date and numeric coverage, not certification of session semantics, adjustments, pagination or halt completeness. The queried historical symbol mapping date is January 28; identity availability at each event still needs review.

The corporate-actions response reported dividends with ex-dates February 9 (AAPL), February 10 (IBM), February 19 (MSFT), and March 11 (NVDA). Assuming after-close publication on the stated dates, dividends intersect the 10- and 20-session windows for Apple, IBM and NVIDIA, and the 20-session window for Microsoft. These are conditional windows, not accepted reaction dates. The returned IBM/CFLT acquisition identifies IBM as acquirer and is not blindly treated as an IBM share adjustment. No-action completeness is unverified.

Prices remain separate from the normalized label input because their raw-price and regular-session status has not been certified. `reports/four-candidate-quarantine-input.json` therefore contains real-event review records but no admitted prices. The builder stops at the first timing failure; the separate intake audit records the remaining gaps. A successful replay confirms reproducibility of quarantine, not successful event validation.

Reproduce the source-only quarantine with:

```sh
python -m nre build reports/four-candidate-quarantine-input.json --output data/review-snapshots
```

Reproduce the combined review using the privately retained decoded connector exports (`prices.json`, `actions.json`):

```sh
python scripts/review_four_candidates.py data/four-candidate-review ACTUAL_OBSERVATION_TIMESTAMP
```

Use the timestamp in the report for an exact replay of this review. Private raw price data and full copyrighted issuer pages are not published in this repository. Original upload files remain separate; their hashes are in the submission import reports.

Further collection alone will not resolve these four cases. They need earliest-publication evidence, historical identity availability, approved provider/session semantics, corporate-action review and independent spot checks. The frozen 100-event / 25-issuer pilot remains incomplete.

Sources:

- https://www.apple.com/newsroom/2026/01/apple-reports-first-quarter-results/
- https://news.microsoft.com/source/2026/01/28/microsoft-cloud-and-ai-strength-drives-second-quarter-results/
- https://www.prnewswire.com/news-releases/ibm-releases-fourth-quarter-results-302673165.html
- https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-2026
- https://docs.alpaca.markets/us/docs/market-data-faq
