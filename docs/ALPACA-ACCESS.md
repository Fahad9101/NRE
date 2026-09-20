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

Before admitting data into NRE snapshots, verify regular-session construction, adjustment behavior, corporate actions, historical identity, source rights and first-public news timestamps. The connector response did not expose adjustment or pagination metadata. Do not infer full arbitrary-symbol coverage or live SIP entitlement from this small probe. The API documentation requires pagination checks even when a page contains fewer than the requested limit.

Credentials remain managed by the existing connection. Do not paste them into chat or commit them. If a standalone collector or GitHub workflow is added later, it will need a separately configured secret store; this setup does not transfer connector credentials to GitHub. Milestone 1 remains open with zero accepted real event outcomes.
