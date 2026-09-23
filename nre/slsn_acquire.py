"""Bounded real-data acquisition and label computation for the signed-off
SLSN event (candidate 0001171843-26-002061).

Fetches real SIP daily bars and corporate actions from Alpaca for a fixed,
narrow window, constructs the reviewed bundle using evidence already gathered
and signed off (see reports/m1-slsn-signoff-packet-2026-09-22.json), and runs
the existing nre.dataset.build() pipeline. Prints only derived results --
computed labels, counts, hashes, quality reasons -- never raw OHLCV numbers,
never credentials. Raw bars exist only transiently in this process's memory.

provider["research_permitted"] was False until the terms were actually
reviewed in full (reports/m1-alpaca-provider-rights-review-2026-09-23.json)
and the project owner explicitly signed off on 2026-09-23 ("yes, sign off on
both"), authorizing this specific, narrow use: redacted-anchor derived
ratios/booleans/counts/hashes only, never raw prices. See
reports/m1-slsn-signoff-packet-2026-09-22.json for the full record. The
"substitute for Information at scale" question from that review is
explicitly not resolved by this sign-off and should be revisited as the
cohort grows -- this authorization is not a blanket one for bulk publication.
"""
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .core import DataError, digest, canonical
from .dataset import build

BARS_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
ACTIONS_ENDPOINT = "https://data.alpaca.markets/v1/corporate-actions"
SYMBOL = "SLSN"

# Anchor session 2026-03-30 through the 20th reaction session 2026-04-28,
# with a wider margin on both sides for corporate-action review.
BARS_PARAMS = dict(symbols=SYMBOL, timeframe="1Day", start="2026-03-01",
                    end="2026-04-30", feed="sip", adjustment="raw",
                    asof="2026-03-31", sort="asc", currency="USD", limit=50)
ACTIONS_PARAMS = dict(symbols=SYMBOL, start="2026-03-01", end="2026-04-30", limit=100, sort="asc")

REQUIRED_SESSIONS = ["2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02", "2026-04-06",
                      "2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10", "2026-04-13",
                      "2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17", "2026-04-20",
                      "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27",
                      "2026-04-28"]

SOURCE_TEXT = (
    "GlobeNewswire release, 'Solésence Reports Fourth Quarter and Full Year 2025 "
    "Financial Results', displayed dateline March 31, 2026 08:02 ET. "
    "https://www.globenewswire.com/news-release/2026/03/31/3265441/12101/en/"
    "sol%C3%A9sence-reports-fourth-quarter-and-full-year-2025-financial-results.html"
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DataError("redirect rejected")


def _paginate(fetch, base_params, payload_key):
    """Shared pagination for any Alpaca endpoint shaped {..., "next_page_token": ...}."""
    pages, seen, token, merged = [], set(), None, []
    for _ in range(20):
        params = dict(base_params)
        if token is not None:
            params["page_token"] = token
        raw = fetch(params)
        page = json.loads(raw)
        if not isinstance(page, dict) or "next_page_token" not in page:
            raise DataError("missing pagination metadata")
        pages.append({"sha256": digest(raw), "records": len(page.get(payload_key) or [])
                       if isinstance(page.get(payload_key), list) else None})
        merged.append(page)
        token = page["next_page_token"]
        if token is None:
            break
        if not isinstance(token, str) or not token or token in seen:
            raise DataError("invalid or repeated pagination token")
        seen.add(token)
    else:
        raise DataError("pagination limit exceeded")
    return merged, pages


def fetch_bars(fetch):
    merged, pages = _paginate(fetch, BARS_PARAMS, "bars")
    rows = []
    for page in merged:
        bars = page.get("bars")
        if not isinstance(bars, dict) or set(bars) - {SYMBOL}:
            raise DataError("unexpected bars structure")
        batch = bars.get(SYMBOL, [])
        if not isinstance(batch, list):
            raise DataError("invalid bar list")
        rows.extend(batch)
    by_session = {}
    for r in rows:
        session = r["t"][:10]
        if session in by_session:
            raise DataError("duplicate session in bars response")
        by_session[session] = {"open": r["o"], "high": r["h"], "low": r["l"],
                                "close": r["c"], "volume": r["v"]}
    return by_session, pages


def fetch_actions(fetch):
    merged, pages = _paginate(fetch, ACTIONS_PARAMS, "corporate_actions")
    total = 0
    for page in merged:
        ca = page.get("corporate_actions")
        if ca is None:
            continue
        if isinstance(ca, dict):
            total += sum(len(v) for v in ca.values() if isinstance(v, list))
        elif isinstance(ca, list):
            total += len(ca)
        else:
            raise DataError("unexpected corporate_actions structure")
    return total, pages


def build_bundle(bars_by_session, actions_count):
    retrieved_at = datetime.now(timezone.utc).isoformat()
    corporate_actions_verified = actions_count == 0
    prices = []
    for session, bar in sorted(bars_by_session.items()):
        prices.append({
            "price_id": "slsn-" + session, "security_id": "SLSN-883107", "source_id": "alpaca-bars",
            "session": session, "provider_id": "alpaca", "feed": "sip", "price_basis": "raw",
            "open": bar["open"], "high": bar["high"], "low": bar["low"], "close": bar["close"],
            "volume": bar["volume"], "available_at": session + "T21:00:00-04:00",
            "complete": True, "corporate_actions_verified": corporate_actions_verified,
            "halted": bar["volume"] == 0,
        })
    return {
        "schema_version": 1, "synthetic": False, "as_of": retrieved_at,
        "availability_mode": "historical_reconstruction",
        "sources": [
            {"source_id": "slsn-wire", "url": SOURCE_TEXT.split()[-1], "text": SOURCE_TEXT,
             "first_seen_at": "2026-03-31T08:03:00-04:00", "retrieved_at": retrieved_at},
            {"source_id": "alpaca-bars", "url": BARS_ENDPOINT, "text": "Alpaca SIP daily bars, SLSN, "
             + BARS_PARAMS["start"] + " to " + BARS_PARAMS["end"] + ", asof " + BARS_PARAMS["asof"] + ".",
             "first_seen_at": retrieved_at, "retrieved_at": retrieved_at},
        ],
        "securities": [
            {"security_id": "SLSN-883107", "company_id": "0000883107", "cik": "0000883107",
             "ticker": "SLSN", "exchange": "NASDAQ", "security_type": "common_stock",
             "source_id": "slsn-wire", "valid_from": "2025-12-01T00:00:00-05:00", "valid_to": None,
             "available_at": "2025-12-01T17:23:33Z"},
        ],
        "providers": [
            {"provider_id": "alpaca", "research_permitted": True,
             "terms_url": "https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf",
             "feeds": ["sip"], "session_scope": "regular"},
        ],
        "events": [
            {"event_id": "slsn-2026-03-31", "cluster_id": "slsn-q4fy25", "security_id": "SLSN-883107",
             "source_id": "slsn-wire", "published_at": "2026-03-31T08:02:00-04:00",
             "cutoff": "2026-03-31T08:05:00-04:00", "precision": "minute",
             "first_public_verified": True, "timestamp_evidence": "08:02"},
        ],
        "prices": prices,
        "corporate_actions": [],
        "features": [],
    }


def main():
    key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    report = {"access_check_passed": False, "labels_computed": False}
    if not key or not secret:
        report["error"] = "MISSING_GITHUB_ACTIONS_SECRETS"
        print(json.dumps(report, sort_keys=True, indent=2))
        return 2

    opener = build_opener(NoRedirect())

    def fetch(endpoint, params):
        req = Request(endpoint + "?" + urlencode(params), headers={
            "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        with opener.open(req, timeout=30) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise DataError("response size limit exceeded")
            return raw

    try:
        bars_by_session, bar_pages = fetch_bars(lambda p: fetch(BARS_ENDPOINT, p))
        actions_count, action_pages = fetch_actions(lambda p: fetch(ACTIONS_ENDPOINT, p))
    except HTTPError as exc:
        report["error"] = "ALPACA_HTTP_" + str(exc.code)
        print(json.dumps(report, sort_keys=True, indent=2))
        return 2
    except DataError as exc:
        report["error"] = "DATA_VALIDATION_FAILED: " + str(exc)
        print(json.dumps(report, sort_keys=True, indent=2))
        return 2
    except json.JSONDecodeError:
        report["error"] = "INVALID_JSON_RESPONSE"
        print(json.dumps(report, sort_keys=True, indent=2))
        return 2
    except URLError:
        report["error"] = "NETWORK_ERROR"
        print(json.dumps(report, sort_keys=True, indent=2))
        return 2
    except Exception as exc:
        report["error"] = "UNCATEGORIZED_" + type(exc).__name__.upper()
        print(json.dumps(report, sort_keys=True, indent=2))
        return 2

    report["access_check_passed"] = True
    report["bar_pages"] = bar_pages
    report["action_pages"] = action_pages
    report["corporate_actions_count"] = actions_count
    report["missing_sessions"] = sorted(set(REQUIRED_SESSIONS) - set(bars_by_session))
    report["zero_volume_sessions"] = sorted(s for s, b in bars_by_session.items()
                                             if s in REQUIRED_SESSIONS and b["volume"] == 0)

    bundle = build_bundle(bars_by_session, actions_count)
    report["bundle_sha256"] = digest(canonical(bundle))
    results, build_report = build(bundle)
    report["build_report"] = build_report
    # Derived only: computed labels (percentages/booleans/reasons), never raw
    # OHLCV. event_outcome() embeds the anchor's raw close price as the return
    # denominator; redact it here and keep only its identifier/session.
    outcome = results[0] if results else None
    if outcome and outcome.get("anchor"):
        outcome["anchor"] = {k: v for k, v in outcome["anchor"].items() if k != "price"}
    report["computed_outcome"] = outcome
    report["labels_computed"] = build_report["complete_20_session"] > 0
    print(json.dumps(report, sort_keys=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
