"""Bounded real-data acquisition and label computation for the signed-off
CXT event (candidate 0000025445-26-000005, Crane NXT, Co.).

Same design as nre/slsn_acquire.py, kept as an independent, self-contained
script rather than sharing code: each event's evidence and identity are
explicit and independently auditable, and the pagination/fetch logic is
small enough that duplicating it costs less than risking a regression in
slsn_acquire.py (already proven in production) via a shared-module refactor.

provider["research_permitted"]:true was authorized 2026-09-23 for this
general pattern of use (redacted-anchor derived ratios/booleans/counts/
hashes only, never raw prices) -- see reports/m1-slsn-signoff-packet-
2026-09-22.json. Timing and identity for THIS candidate were separately
signed off 2026-09-23 ("sign off on cxt") -- see
reports/m1-cxt-signoff-packet-2026-09-23.json for the full record,
including a known, bounded caveat: a 2026-02-25 Investor Day disclosed
updated guidance, which should be read as a competing catalyst on the
session_10/session_20 labels specifically, not attributed solely to the
2026-02-11 earnings release. Day-1/session_2/session_5 are unaffected.
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
SYMBOL = "CXT"

# Anchor session 2026-02-11 through the 20th reaction session 2026-03-12,
# with a wider margin on both sides for corporate-action review.
BARS_PARAMS = dict(symbols=SYMBOL, timeframe="1Day", start="2026-02-01",
                    end="2026-03-31", feed="sip", adjustment="raw",
                    asof="2026-02-11", sort="asc", currency="USD", limit=50)
ACTIONS_PARAMS = dict(symbols=SYMBOL, start="2026-02-01", end="2026-03-31", limit=100, sort="asc")

# Computed via nre.calendar.Calendar (see reports/m1-cxt-signoff-packet-
# 2026-09-23.json "computed_required_sessions"), not hand-counted.
REQUIRED_SESSIONS = ["2026-02-11", "2026-02-12", "2026-02-13", "2026-02-17", "2026-02-18",
                      "2026-02-19", "2026-02-20", "2026-02-23", "2026-02-24", "2026-02-25",
                      "2026-02-26", "2026-02-27", "2026-03-02", "2026-03-03", "2026-03-04",
                      "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11",
                      "2026-03-12"]

SOURCE_TEXT = (
    "GlobeNewswire release, 'Crane NXT Announces Fourth Quarter and Full Year 2025 "
    "Results; Raises Annual Dividend by 6%', displayed dateline February 11, 2026 "
    "16:05 ET. https://www.globenewswire.com/news-release/2026/02/11/3236663/0/en/"
    "Crane-NXT-Announces-Fourth-Quarter-and-Full-Year-2025-Results-Raises-Annual-"
    "Dividend-by-6.html"
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
    """Return each action's type and ex_date, not just a count, so the caller
    can tell quality()'s CORPORATE_ACTION_IN_WINDOW check exactly which
    session that action actually affects -- confirmed via a real CXT dividend
    (ex_date field, "YYYY-MM-DD") in reports/m1-cxt-acquisition-result-2026-09-23.json's
    follow-up. Fails closed on any entry missing that field rather than
    guessing it doesn't matter."""
    merged, pages = _paginate(fetch, ACTIONS_PARAMS, "corporate_actions")
    entries = []
    for page in merged:
        ca = page.get("corporate_actions")
        if ca is None:
            continue
        if not isinstance(ca, dict):
            raise DataError("unexpected corporate_actions structure")
        for action_type, items in ca.items():
            if not isinstance(items, list):
                raise DataError("unexpected corporate_actions structure")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("ex_date"), str):
                    raise DataError("corporate action missing ex_date")
                entries.append({"type": action_type, "ex_date": item["ex_date"], "id": item.get("id")})
    return entries, pages


def build_bundle(bars_by_session, actions):
    retrieved_at = datetime.now(timezone.utc).isoformat()
    # corporate_actions_verified is genuinely earned here, not assumed: every
    # real action Alpaca reported is fed into bundle["corporate_actions"]
    # below with its actual ex_date, so nre.dataset's own
    # CORPORATE_ACTION_IN_WINDOW check -- not this blanket flag -- does the
    # real work of suppressing only the specific label windows an action's
    # ex_date actually falls inside (confirmed for CXT: only session_20
    # crosses the 2026-02-27 dividend; Day-1 through session_10 do not).
    prices = []
    for session, bar in sorted(bars_by_session.items()):
        prices.append({
            "price_id": "cxt-" + session, "security_id": "CXT-25445", "source_id": "alpaca-bars",
            "session": session, "provider_id": "alpaca", "feed": "sip", "price_basis": "raw",
            "open": bar["open"], "high": bar["high"], "low": bar["low"], "close": bar["close"],
            # 16:01 ET, not the 21:00 convention used for SLSN's premarket
            # event: this event is AFTER-HOURS, so the anchor is the SAME
            # day's close (2026-02-11) and must be available before the
            # 16:10 ET cutoff -- a closing price is realistically known
            # within a minute of the 16:00 bell, not hours later.
            "volume": bar["volume"], "available_at": session + "T16:01:00-05:00",
            "complete": True, "corporate_actions_verified": True,
            "halted": bar["volume"] == 0,
        })
    corporate_actions = [
        {"action_id": a["id"] or (a["type"] + "-" + a["ex_date"]), "security_id": "CXT-25445",
         "source_id": "alpaca-actions", "type": a["type"], "effective_date": a["ex_date"],
         # Conservative: known to be public no later than its own ex_date,
         # even though this specific dividend was actually announced earlier
         # (in the same 2026-02-11 16:05 ET release) -- not overclaiming
         # earlier knowledge than independently confirmed here.
         "available_at": a["ex_date"] + "T00:00:00-05:00"}
        for a in actions
    ]
    return {
        "schema_version": 1, "synthetic": False, "as_of": retrieved_at,
        "availability_mode": "historical_reconstruction",
        "sources": [
            {"source_id": "cxt-wire", "url": SOURCE_TEXT.split()[-1], "text": SOURCE_TEXT,
             "first_seen_at": "2026-02-11T16:06:00-05:00", "retrieved_at": retrieved_at},
            {"source_id": "alpaca-bars", "url": BARS_ENDPOINT, "text": "Alpaca SIP daily bars, CXT, "
             + BARS_PARAMS["start"] + " to " + BARS_PARAMS["end"] + ", asof " + BARS_PARAMS["asof"] + ".",
             "first_seen_at": retrieved_at, "retrieved_at": retrieved_at},
            {"source_id": "alpaca-actions", "url": ACTIONS_ENDPOINT,
             "text": "Alpaca corporate actions, CXT, " + ACTIONS_PARAMS["start"] + " to "
             + ACTIONS_PARAMS["end"] + ".", "first_seen_at": retrieved_at, "retrieved_at": retrieved_at},
        ],
        "securities": [
            # valid_from uses the prior confirmed quarterly 8-K date (2025-11-05,
            # same Item 2.02/9.01 pattern, no intervening ticker/exchange change
            # in the filing history checked 2026-09-23) as conservative evidence
            # identity was already established well before this event.
            {"security_id": "CXT-25445", "company_id": "0000025445", "cik": "0000025445",
             "ticker": "CXT", "exchange": "NYSE", "security_type": "common_stock",
             "source_id": "cxt-wire", "valid_from": "2025-11-05T00:00:00-05:00", "valid_to": None,
             "available_at": "2025-11-05T00:00:00-05:00"},
        ],
        "providers": [
            {"provider_id": "alpaca", "research_permitted": True,
             "terms_url": "https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf",
             "feeds": ["sip"], "session_scope": "regular"},
        ],
        "events": [
            {"event_id": "cxt-2026-02-11", "cluster_id": "cxt-q4fy25", "security_id": "CXT-25445",
             "source_id": "cxt-wire", "published_at": "2026-02-11T16:05:00-05:00",
             "cutoff": "2026-02-11T16:10:00-05:00", "precision": "minute",
             "first_public_verified": True, "timestamp_evidence": "16:05"},
        ],
        "prices": prices,
        "corporate_actions": corporate_actions,
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
        actions, action_pages = fetch_actions(lambda p: fetch(ACTIONS_ENDPOINT, p))
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
    # Dividend ex-dates/rates are already public (the release itself
    # announced the increase), so reporting the real entries -- not raw
    # price bars -- is safe and lets the actual suppressed-window reasoning
    # be checked against the source data, not just trusted blind.
    report["corporate_actions"] = actions
    report["missing_sessions"] = sorted(set(REQUIRED_SESSIONS) - set(bars_by_session))
    report["zero_volume_sessions"] = sorted(s for s, b in bars_by_session.items()
                                             if s in REQUIRED_SESSIONS and b["volume"] == 0)

    bundle = build_bundle(bars_by_session, actions)
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
    # mapped_day1, not complete_20_session: an event can reach MAPPED with
    # real, valid short-horizon labels while a real corporate action
    # correctly suppresses only its longest-horizon label (confirmed for
    # this candidate: the dividend crosses session_20's window but not
    # Day-1 through session_10). complete_20_session==0 in that case would
    # wrongly read as "nothing computed" when most labels are genuinely fine.
    report["labels_computed"] = build_report["mapped_day1"] > 0
    print(json.dumps(report, sort_keys=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
