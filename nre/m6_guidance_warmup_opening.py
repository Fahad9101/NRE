"""Verify frozen guidance-v2 training openings; publish hashes and dispositions only."""
import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener

from . import event_acquire as ea
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load
from .m6_guidance_revision import (
    EARLIER, MASKS, PARENT_MASKS, PARENT_WARMUP, PROTOCOL, ROOT, check_revision,
)
from .m6_historical_opening import VENUES, first_minute_open

PROTOCOL_SHA256 = "d5152e432065fc830bc5078133bfdf15dde651f14f5a8505857c4d14b2353598"
COMMITMENT_DOMAIN = "nre-guidance-v2-official-opening-v1"
SOURCE_PATHS = (PARENT_WARMUP, PARENT_MASKS, EARLIER, MASKS)
IMPLEMENTATION_PATHS = (
    "nre/m6_guidance_warmup_opening.py", "nre/m6_historical_opening.py",
    "nre/event_acquire.py", "nre/core.py", "nre/calendar.py",
)
REQUEST_BUDGET = 450


def locked_cohort(root=ROOT):
    """Return the exact source-eligible union; soft masks annotate the clean subset."""
    registration = check_revision(root)
    if (registration["protocol_sha256"] != PROTOCOL_SHA256
            or registration["decision"] != "READY_FOR_RAW_WARMUP_OPENINGS"):
        raise DataError("Unexpected guidance opening registration")
    protocol = load(root / PROTOCOL)
    source_pins = {path: protocol["input_canonical_sha256"][path] for path in SOURCE_PATHS}
    candidates = load(root / PARENT_WARMUP)["candidate_events"] + load(root / EARLIER)["candidate_events"]
    masks = {r["event_id"]: r for path in (PARENT_MASKS, MASKS) for r in load(root / path)["events"]}
    events = []
    for source in candidates:
        mask = masks[source["event_id"]]
        if mask["hard_exclusions"]:
            continue
        if (not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", source["symbol"])
                or not any(r["symbol"] == source["symbol"] and "NASDAQ" in r["exchange"].upper()
                           for r in source["listing_evidence"]["listed_securities"])):
            raise DataError("Unexpected historical opening identity")
        events.append({
            "event_id": source["event_id"], "symbol": source["symbol"], "cik": source["cik"],
            "reaction_session": source["reaction_session"], "scheduled_open_at": source["scheduled_open_at"],
            "feature_cutoff_at": source["feature_cutoff_at"], "venue": "NASDAQ",
            "clean_window": not bool(mask["soft_caveats"]),
            "source_event_sha256": digest(canonical(source)), "source_mask_sha256": digest(canonical(mask)),
        })
    events.sort(key=lambda row: (timestamp(row["scheduled_open_at"]), row["symbol"], row["event_id"]))
    if (len(events) != 52 or sum(r["clean_window"] for r in events) != 44
            or len({(r["symbol"], r["reaction_session"]) for r in events}) != len(events)
            or len({r["event_id"] for r in events}) != len(events)):
        raise DataError("Unexpected guidance opening cohort")
    binding = {"protocol_sha256": PROTOCOL_SHA256, "source_canonical_sha256": source_pins, "events": events}
    return {**binding, "cohort_sha256": digest(canonical(binding))}


def trade_params(event):
    start = timestamp(event["scheduled_open_at"])
    return {"start": start.isoformat(), "end": (start + timedelta(seconds=60)).isoformat(),
            "feed": "sip", "sort": "asc", "limit": 5000, "asof": event["reaction_session"]}


def validate_trade_request(event, endpoint, params):
    expected = trade_params(event)
    if (endpoint != f"https://data.alpaca.markets/v2/stocks/{event['symbol']}/trades"
            or set(params) - {**expected, "page_token": None}.keys()
            or any(params.get(key) != value for key, value in expected.items())
            or ("page_token" in params and (not isinstance(params["page_token"], str)
                                            or not 0 < len(params["page_token"]) <= 4096))):
        raise DataError("Request outside frozen first-minute opening boundary")


def opening_commitment(event, selected, protocol_sha256, cohort_sha256):
    """Reproduce from the selected raw Q trade, without persisting this preimage.

    Retain the original provider timestamp and integer trade id. The positive price
    is represented as a normalized, fixed-point decimal string so 100 and 100.0
    produce the same commitment. A later acquirer must use this same domain,
    event/cohort binding and selector, then compare the resulting digest.
    """
    preimage = {"domain": COMMITMENT_DOMAIN, "protocol_sha256": protocol_sha256,
                "cohort_sha256": cohort_sha256, "event_id": event["event_id"],
                "symbol": event["symbol"], "cik": event["cik"],
                "reaction_session": event["reaction_session"], "venue": "Q", "tape": "C",
                "selected_official_open": {"id": selected["i"], "timestamp": selected["t"],
                                           "price_decimal": format(Decimal(str(selected["p"])).normalize(), "f")}}
    return digest(canonical(preimage))


def implementation_hashes(root):
    protocol = load(root / PROTOCOL)
    paths = set(IMPLEMENTATION_PATHS) | set(protocol["implementation_sha256_git_lf"])
    return {path: digest((root / path).read_bytes().replace(b"\r\n", b"\n")) for path in sorted(paths)}


def run(root, fetch, *, consume_opening=None):
    """Run only opening checks; the optional callback receives verified values privately."""
    cohort = locked_cohort(root)
    results, request_count = [], 0
    for event in cohort["events"]:
        pages, request_hashes, response_hashes = [], [], []

        def checked_fetch(endpoint, params):
            nonlocal request_count
            validate_trade_request(event, endpoint, params)
            if request_count >= REQUEST_BUDGET:
                raise DataError("Opening request budget exhausted")
            request_count += 1
            raw = fetch(endpoint, params)
            if not isinstance(raw, bytes) or len(raw) > 4_000_000:
                raise DataError("Unexpected opening response representation")
            request_hashes.append(digest(canonical({"endpoint": endpoint, "params": params})))
            response_hashes.append(digest(raw))
            pages.append(json.loads(raw))
            return raw

        start = timestamp(event["scheduled_open_at"])
        price, reason = first_minute_open(event["symbol"], VENUES[event["venue"]], start, checked_fetch,
                                          asof=event["reaction_session"], page_limit=5000)
        commitment = None
        if reason is None:
            # Selection and ambiguity checks are performed by the unchanged selector.
            # Extract its unique selected tuple only to construct the private preimage.
            selected = {}
            for page in pages:
                for trade in page.get("trades") or ():
                    if ((trade.get("x"), trade.get("z")) == VENUES[event["venue"]]
                            and "Q" in (trade.get("c") or ()) and trade.get("u") is None
                            and trade.get("p") == price and type(trade.get("i")) is int
                            and start <= timestamp(trade["t"]) < start + timedelta(seconds=60)):
                        selected[trade["i"], trade["t"], trade["p"]] = trade
            if len(selected) != 1:
                raise DataError("Verified opening commitment selection differs")
            commitment = opening_commitment(event, next(iter(selected.values())),
                                            cohort["protocol_sha256"], cohort["cohort_sha256"])
            if consume_opening is not None:
                consume_opening(event, price, commitment)
        results.append({key: event[key] for key in ("event_id", "symbol", "cik", "reaction_session", "clean_window")}
                       | {"status": reason or "verified_open", "opening_commitment_sha256": commitment,
                          "provider_request_sha256": request_hashes, "provider_response_sha256": response_hashes})
    dispositions = Counter(row["status"] for row in results)
    clean = [row for row in results if row["clean_window"]]
    return {"schema_version": 1, "scope": "guidance_v2_training_official_open_coverage",
            "protocol_sha256": cohort["protocol_sha256"], "cohort_sha256": cohort["cohort_sha256"],
            "source_canonical_sha256": cohort["source_canonical_sha256"],
            "implementation_sha256_git_lf": implementation_hashes(root),
            "opening_commitment_scheme": COMMITMENT_DOMAIN,
            "screened": len(results), "matched": dispositions["verified_open"],
            "clean_screened": len(clean), "clean_matched": sum(r["status"] == "verified_open" for r in clean),
            "dispositions": dict(dispositions), "requests": request_count, "events": results,
            "closing_outcome_requests": 0, "model_runs": 0}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        provider = ea.make_fetch(build_opener(ea.NoRedirect()), os.environ["APCA_API_KEY_ID"],
                                 os.environ["APCA_API_SECRET_KEY"])
        next_request = time.monotonic()

        def fetch(endpoint, params):
            nonlocal next_request
            time.sleep(max(0, next_request - time.monotonic()))
            next_request = time.monotonic() + 0.75
            return provider(endpoint, params)

        print(json.dumps(run(Path("."), fetch), sort_keys=True))
    except HTTPError as error:
        print(json.dumps({"status": "provider_error", "http_status": error.code}))
        return 2
    except Exception as error:
        # Never print provider payloads, request headers or exception messages.
        print(json.dumps({"status": "warmup_opening_failed", "reason": type(error).__name__}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
