"""Bounded, read-only REST access diagnostic. Never emits raw bars or secrets."""
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .alpaca import audit_daily
from .core import DataError, digest

PARAMS = dict(symbols="IBM", timeframe="1Day", start="2026-01-02",
              end="2026-04-30", feed="sip", adjustment="raw",
              asof="2026-01-28", sort="asc", currency="USD", limit=50)
ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DataError("redirect rejected")


def collect(fetch):
    """Follow even short pages, fail closed on missing/repeated tokens."""
    rows, pages, seen = [], [], set()
    token = None
    for _ in range(20):
        params = dict(PARAMS)
        if token is not None:
            params["page_token"] = token
        raw = fetch(params)
        page = json.loads(raw)
        if not isinstance(page, dict) or "next_page_token" not in page:
            raise DataError("missing pagination metadata")
        bars = page.get("bars")
        if not isinstance(bars, dict) or set(bars) - {"IBM"}:
            raise DataError("unexpected bars structure")
        batch = bars.get("IBM", [])
        if not isinstance(batch, list):
            raise DataError("invalid bar list")
        rows.extend(batch)
        pages.append({"sha256": digest(raw), "records": len(batch)})
        token = page["next_page_token"]
        if token is None:
            break
        if not isinstance(token, str) or not token or token in seen:
            raise DataError("invalid or repeated pagination token")
        seen.add(token)
    else:
        raise DataError("pagination limit exceeded")
    normalized = [{"symbol": "IBM", "timestamp": r["t"],
                   **{out: r[key] for out, key in
                      [("open", "o"), ("high", "h"), ("low", "l"),
                       ("close", "c"), ("volume", "v")]}} for r in rows]
    payload = {"tool": "get_stock_bars", "request": {
        **PARAMS, "symbols": ["IBM"], "tz": "America/New_York"},
        "bars": {"IBM": normalized}, "counts": {
            "records": len(rows), "symbols": 1, "per_symbol": {"IBM": len(rows)}}}
    report = audit_daily(payload, datetime.now(timezone.utc).isoformat())
    report["transport"] = "direct_alpaca_rest"
    report["scope"] = "IBM access diagnostic outside frozen acceptance cohort"
    report["request"] = dict(PARAMS)
    report["pages"] = pages
    report["terminal_page_observed"] = True
    report["adjustment_requested"] = "raw"
    report["blockers"] = [x for x in report["blockers"] if x not in
                           {"ADJUSTMENT_UNVERIFIED", "PAGINATION_METADATA_UNAVAILABLE"}]
    report["blockers"].append("RAW_RESPONSE_ARCHIVE_REQUIRED_FOR_ACCEPTANCE")
    report["hash_basis"] = "canonical normalized REST bars; pages hash original response bytes"
    report["access_check_passed"] = bool(rows) and not any(
        x in report["blockers"] for x in ("MISSING_SESSIONS", "ZERO_VOLUME_SESSIONS"))
    return report


def main():
    key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    report = {"access_check_passed": False, "accepted_for_labels": False}
    if not key or not secret:
        report["error"] = "MISSING_GITHUB_ACTIONS_SECRETS"
    else:
        opener = build_opener(NoRedirect())

        def fetch(params):
            req = Request(ENDPOINT + "?" + urlencode(params), headers={
                "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
            with opener.open(req, timeout=30) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise DataError("response size limit exceeded")
                return raw

        try:
            report = collect(fetch)
        except HTTPError as exc:
            # Never print request headers, response bodies, or exception text.
            report["error"] = "ALPACA_HTTP_" + str(exc.code)
        except Exception:
            report["error"] = "NETWORK_OR_RESPONSE_VALIDATION_FAILED"
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["access_check_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
