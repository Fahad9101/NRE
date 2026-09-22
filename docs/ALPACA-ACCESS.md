# Alpaca access

Verified on 2026-09-20 using the existing authenticated Alpaca connector. No new credentials, subscriptions or account changes were required. The connector access described below is separate from the direct REST diagnostic added on September 22.

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

## GitHub Actions direct REST diagnostic

The user reports saving `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` as repository Actions secrets. `.github/workflows/alpaca-access.yml` supplies them only to `python -m nre.alpaca_probe`. The workflow runs on relevant main-branch pushes or manual dispatch. Live success must be verified in its run log; saving secrets alone does not establish access.

The bounded IBM diagnostic explicitly requests SIP, raw adjustment, USD, ascending order and historical symbol as-of. It follows every next-page token, including short pages, rejects absent/repeated tokens and unexpected symbols, and checks all 82 expected daily sessions. IBM remains outside the frozen acceptance cohort. Only settings, response hashes, counts and quality metadata are printed. No raw bars, credentials, account details or trades are published. Redirects are rejected; HTTP errors are reported by status only. There is no feed fallback or paid subscription action.

Exit 0 means this bounded historical access/coverage check passed, not Milestone 1 acceptance or live SIP entitlement. Raw response preservation, session-volume methodology, corporate-action coverage, identity, rights and publication-time reviews still gate accepted labels. This diagnostic deliberately does not retain raw responses or construct a dataset. `config/alpaca.json` remains the separate connector operator recipe, not this fixed diagnostic's configuration.
