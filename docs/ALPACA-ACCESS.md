# Alpaca access

Verified on 2026-09-20 using the existing authenticated Alpaca connector. No new credentials, subscriptions or account changes were required. Access through this session is working; the standalone Python CLI and GitHub Actions have not been connected to Alpaca.

## Acquisition settings

Use `config/alpaca.json` as the operator recipe. It is not yet loaded by the CLI. Explicitly pass `feed="sip"`: the connector defaulted to IEX during the first probe. Never silently fall back between feeds. Alpaca documents SIP as covering all US exchanges and IEX as a single exchange: https://docs.alpaca.markets/us/reference/stockbars.

A verified connector request:

```json
{
  "symbol": "IBM",
  "timeframe": "1Day",
  "start": "2026-01-02",
  "end": "2026-04-30",
  "feed": "sip",
  "limit": 1000,
  "asof": "2026-01-28"
}
```

Call `alpaca_get_stock_bars` with these arguments. Call `alpaca_get_calendar` with `start_date` and `end_date` (not `start` and `end`). Returned IBM coverage matched all 82 calendar sessions and passed numeric OHLCV consistency checks. This is an exploratory access probe, not acceptance evidence for a frozen event cohort. The access report publishes counts and settings, not raw market data.

## Remaining integration work

The CLI now audits saved connector responses without requiring local API keys:

```sh
python -m nre audit-alpaca data/alpaca/ibm.json --retrieved-at 2026-09-20T07:05:49.068Z --output data/alpaca/audit.json
```

Supply the decoded `get_stock_bars` payload containing `tool`, `request`, `counts` and `bars`. Use its actual receipt time, not the example above. The command checks explicit SIP selection, historical symbol mapping date, New York daily timestamps across DST, OHLCV validity, duplicates, order, counts and every requested calendar session. It records a canonical payload hash. Missing sessions remain visible; no forward filling occurs. Exit status 2 means the export remains staged for review, even when all calendar dates are present. This command does not retrieve data or construct accepted labels.

The real IBM run is recorded in `reports/alpaca-intake-validation.json`: 82 expected and received sessions, with no missing sessions or zero-volume rows. Alpaca's published [aggregation rules](https://docs.alpaca.markets/us/docs/market-data-faq) distinguish daily OHLC from daily volume: extended-hours trade conditions do **not** update daily open/high/low/close, but can update daily volume. This supports use of the documented daily OHLC construction while leaving core-session volume unverified. The historical-bars reference also documents `adjustment=raw` as the API default, `asof` symbol mapping, and total-record pagination through `next_page_token`. The ChatGPT connector, however, does not expose an adjustment argument/value or page token, so those transport semantics remain explicitly unverified rather than inferred.

The corporate-actions connector returned an IBM cash dividend with ex-date 2026-02-10, inside the January 29 reaction's 10- and 20-session windows. Under the existing raw-price policy those horizons cannot be treated as action-free. It also returned a March acquisition with IBM as acquirer and CFLT as acquiree: matching a symbol filter does not mean the action adjusts that symbol's shares. These findings require issuer-role review, not blind action import. This exploratory IBM case remains outside the frozen acceptance cohort.

Before admitting data into accepted NRE snapshots, verify core-session volume if volume is required, connector adjustment behavior, corporate actions, historical identity, source rights and first-public news timestamps. The four-symbol exploratory request returned exactly 328 expected symbol-session rows (82 for each symbol), so calendar coverage is reconciled for that bounded request; this is not a substitute for transport-level `next_page_token` visibility or trade-completeness evidence. Do not infer full arbitrary-symbol coverage or live SIP entitlement from this probe.

Credentials remain managed by the existing connection. Do not paste them into chat or commit them. If a standalone collector or GitHub workflow is added later, it will need a separately configured secret store; this setup does not transfer connector credentials to GitHub. Milestone 1 remains open with zero accepted real event outcomes.
