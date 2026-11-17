"""Check the historical official open for each frozen M6 guidance pilot event."""
import json
import os
import re
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener

from . import event_acquire as ea
from .calendar import Calendar
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load
from .m6_guidance_frame import FRAME
from .m6_historical_opening import VENUES, first_minute_open

PILOT = "reports/m6-guidance-pilot-evidence-2026-11-17.json"
PILOT_SHA256 = "c8d7e2eea92f2e50cf0aa0c961f88514bb8a0221d3da39eeae1b8940fea28c22"


def locked_events(root):
    pilot = load(root / PILOT)
    if digest(canonical(pilot)) != PILOT_SHA256 or pilot["frame_path"] != FRAME:
        raise DataError("Guidance evidence changed")
    frame = load(root / FRAME)
    if digest(canonical(frame)) != pilot["frame_canonical_sha256"]:
        raise DataError("Guidance roster changed")
    calendar_pin = frame["calendar"]
    calendar_spec = load(root / calendar_pin["path"])
    if digest(canonical(calendar_spec)) != calendar_pin["canonical_sha256"]:
        raise DataError("Guidance calendar changed")
    calendar = Calendar(calendar_spec)
    events = pilot["guidance_candidates"]
    for event in events:
        session, timing = calendar.classify(event["current"]["source_time"])
        start, _ = calendar.bounds(session)
        if (event["venue"] != "NASDAQ" or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", event["symbol"])
                or (session, timing) != (event["reaction_session"], event["release_timing"])
                or timestamp(event["scheduled_open_at"]) != start
                or timestamp(event["feature_cutoff_at"]) != start - timedelta(minutes=15)
                or timestamp(event["current"]["availability_proxy"]) >= start - timedelta(minutes=15)):
            raise DataError("Unexpected historical identity or clock")
    return events


def run(root, fetch):
    results = []
    for event in locked_events(root):
        symbol, session = (event[key] for key in ("symbol", "reaction_session"))
        start = timestamp(event["scheduled_open_at"])
        _, reason = first_minute_open(symbol, VENUES[event["venue"]], start, fetch, asof=session, page_limit=5000)
        results.append({"symbol": symbol, "reaction_session": session, "status": reason or "verified_open"})
    dispositions = Counter(row["status"] for row in results)
    return {"scope": "guidance_pilot_official_open_coverage", "schema_version": 1,
            "guidance_evidence_sha256": PILOT_SHA256, "screened": len(results),
            "matched": dispositions["verified_open"], "dispositions": dict(dispositions), "events": results}


def main():
    try:
        provider = ea.make_fetch(build_opener(ea.NoRedirect()), os.environ["APCA_API_KEY_ID"],
                                 os.environ["APCA_API_SECRET_KEY"])
        requests = 0
        next_request = time.monotonic()

        def fetch(endpoint, params):
            nonlocal requests, next_request
            if (requests >= 120 or params.get("feed") != "sip"
                    or not re.fullmatch(r"https://data\.alpaca\.markets/v2/stocks/[A-Z][A-Z0-9.]{0,9}/trades", endpoint)
                    or timestamp(params["end"]) - timestamp(params["start"]) != timedelta(seconds=60)):
                raise DataError("Request outside opening pilot boundary")
            time.sleep(max(0, next_request - time.monotonic()))
            next_request = time.monotonic() + 0.35
            requests += 1
            return provider(endpoint, params)

        result = run(Path("."), fetch)
        print(json.dumps(dict(result, requests=requests), sort_keys=True))
    except HTTPError as error:
        print(json.dumps({"status": "provider_error", "http_status": error.code}))
        return 2
    except (DataError, KeyError, TypeError, ValueError, OSError) as error:
        print(json.dumps({"status": "opening_pilot_failed", "reason": type(error).__name__}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
