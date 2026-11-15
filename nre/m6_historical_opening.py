"""Historical SIP opening-only diagnostic for M6. Outputs counts, never trade data."""
import json
import math
import os
import re
import time as clock
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener

from . import caveat_sensitivity, event_acquire as ea
from .calendar import Calendar
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load

V1 = "config/m6-protocol.json"
V2 = "config/m6-protocol-v2.json"
AUTH = "reports/m6-historical-opening-authorization-2026-11-15.json"
VENUES = {"NYSE": ("N", "A"), "NASDAQ": ("Q", "C")}
TRADES = "https://data.alpaca.markets/v2/stocks/{}/trades"


def selections(gap, reference, threshold):
    if not gap:
        return 0, 0
    direction = -1 if gap > 0 else 1
    outside = gap < reference["candidate_reference_q10"] or gap > reference["candidate_reference_q90"]
    meets_floor = abs(reference["candidate_reference_mean"] - gap) >= 0.02
    return direction if outside and meets_floor else 0, direction if abs(gap) > threshold else 0


def sample(event, calendar, fetch):
    symbol = event["security"]["ticker"]
    venue = VENUES.get(event["security"]["exchange"])
    if venue is None or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol):
        return None, "unsupported_listing"
    window = ea.event_window(event, calendar)
    start, _ = calendar.bounds(window["reaction_session"])
    end = start + timedelta(seconds=60)
    if timestamp(event["cutoff"]) >= start or window["release_timing"] not in ea.TIMINGS:
        return None, "unsupported_clock"
    anchor = date.fromisoformat(window["anchor_session"])
    midnight = datetime.combine(anchor, time.min, calendar.zone)
    if timestamp(event["security"]["valid_from"]) > calendar.bounds(anchor.isoformat())[1]:
        return None, "anchor_identity_unverified"
    bars, _ = ea.fetch_bars(lambda p: fetch(ea.BARS_ENDPOINT, p), symbol, {
        "symbols": symbol, "timeframe": "1Day", "start": midnight.isoformat(),
        "end": datetime.combine(anchor, time(23, 59, 59), calendar.zone).isoformat(),
        "feed": "sip", "adjustment": "raw", "asof": "-", "limit": 10,
    })
    if set(bars) - {anchor.isoformat()}:
        raise DataError("Unexpected date in anchor response")
    close = bars.get(anchor.isoformat(), {}).get("close")
    if type(close) not in (float, int) or not math.isfinite(close) or close <= 0:
        return None, "missing_anchor"
    pages, _ = ea._paginate(lambda p: fetch(TRADES.format(symbol), p), {
        "start": start.isoformat(), "end": end.isoformat(), "feed": "sip",
        "sort": "asc", "limit": 1000,
    }, "trades")
    official = set()
    suspect = False
    for page in pages:
        if page.get("symbol") != symbol or not isinstance(page.get("trades"), list):
            raise DataError("Malformed trade response")
        for trade in page["trades"]:
            if (trade.get("x"), trade.get("z")) != venue or "Q" not in (trade.get("c") or ()):
                continue
            at = timestamp(trade["t"])
            if not start <= at < end:
                continue
            price, trade_id = trade.get("p"), trade.get("i")
            if (trade.get("u") is not None or type(trade_id) is not int or type(price) not in (int, float)
                    or not math.isfinite(price) or price <= 0):
                suspect = True
                continue
            official.add((trade_id, trade["t"], price))
    if suspect or len(official) > 1:
        return None, "ambiguous_official_open"
    if not official:
        return None, "no_official_open"
    return next(iter(official))[2] / close - 1, None


def run(root, fetch):
    v1, v2, auth = (load(root / path) for path in (V1, V2, AUTH))
    for key, protocol in (("v1", v1), ("v2", v2)):
        if digest(canonical(protocol)) != auth[key + "_canonical_sha256"]:
            raise DataError("Protocol checksum mismatch")
    pin = v1["development"]["events"]
    spec_path = root / pin["path"]
    if digest(spec_path.read_bytes().replace(b"\r\n", b"\n")) != pin["sha256_git_lf"]:
        raise DataError("Cohort checksum mismatch")
    cal_pin = auth["calendar"]
    cal_spec = load(root / cal_pin["path"])
    if digest(canonical(cal_spec)) != cal_pin["canonical_sha256"]:
        raise DataError("Calendar checksum mismatch")
    calendar = Calendar(cal_spec)
    spec = load(spec_path)
    events = spec["events"]
    if len(events) != 128 or len({e["event_id"] for e in events}) != 128:
        raise DataError("Unexpected cohort membership")
    caveats = caveat_sensitivity.caveated_pairs(spec, with_derived=True)
    statuses, pairs = Counter(), Counter()
    seen, discordant_issuers, discordant_sessions = set(), set(), set()
    for event in sorted(events, key=lambda e: (timestamp(e["cutoff"]), e["event_id"])):
        if event["cluster_id"] in seen:
            statuses["duplicate_cluster"] += 1
            continue
        seen.add(event["cluster_id"])
        if "day1_open_return" in caveats.get(event["event_id"], ()):
            statuses["opening_caveat"] += 1
            continue
        gap, reason = sample(event, calendar, fetch)
        if reason:
            statuses[reason] += 1
            continue
        statuses["verified_open"] += 1
        a, b = selections(gap, v1["planning_evidence"], v2["comparator"]["threshold"])
        pairs[a, b] += 1
        if a != b:
            discordant_issuers.add(event["security"]["cik"])
            discordant_sessions.add(event["expected_reaction_session"])
    return {"status": "complete", "scope": "historical_opening_only", "screened": len(events),
            "dispositions": dict(statuses),
            "allocations": [{"tail": a, "magnitude": b, "count": n} for (a, b), n in sorted(pairs.items())],
            "discordant": sum(n for (a, b), n in pairs.items() if a != b),
            "discordant_issuers": len(discordant_issuers), "discordant_sessions": len(discordant_sessions),
            "receipt_latency_verified": False}


def main():
    try:
        provider = ea.make_fetch(build_opener(ea.NoRedirect()), os.environ["APCA_API_KEY_ID"],
                                 os.environ["APCA_API_SECRET_KEY"])

        requests = 0
        next_request = clock.monotonic()

        def fetch(endpoint, params):
            nonlocal requests, next_request
            if requests >= 650:
                raise DataError("Request budget exhausted")
            if endpoint != ea.BARS_ENDPOINT and not re.fullmatch(
                    r"https://data\.alpaca\.markets/v2/stocks/[A-Z][A-Z0-9.]{0,9}/trades", endpoint):
                raise DataError("Unexpected endpoint")
            clock.sleep(max(0, next_request - clock.monotonic()))
            next_request = clock.monotonic() + 0.35
            requests += 1
            return provider(endpoint, params)

        print(json.dumps(run(Path("."), fetch), sort_keys=True))
    except HTTPError as error:
        print(json.dumps({"status": "provider_error", "http_status": error.code}))
        return 2
    except Exception:
        print('{"status":"diagnostic_failed"}')
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
