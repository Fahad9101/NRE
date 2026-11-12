"""Acquire only the daily-bar features registered for Milestone 5 Phase 1c."""
import argparse
import bisect
import json
import math
import os
import statistics
import time as clock
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener

from nre import event_acquire as ea
from nre.calendar import Calendar
from nre.core import canonical, digest, timestamp
from nre.m5_phase1b_audit import load

PROTOCOL = "config/m5-protocol.json"
FREEZE = "reports/m5-protocol-freeze-2026-11-12.json"
PROBE = "config/m5-phase1a-probe-spec.json"
AUTHORIZATION = "reports/m5-phase1c-authorization-2026-11-12.json"
REGIME_SYMBOLS = ("SPY", "QQQ", "IWM", "RSP", "HYG", "LQD")
STRUCTURE = {
    "return_5": (6, ("close",)),
    "rv_20": (21, ("close",)),
    "atr_14_fraction": (15, ("high", "low", "close")),
    "adv_20": (20, ("close", "volume")),
    "rvol_20": (21, ("volume",)),
    "distance_252_high": (252, ("high", "close")),
}
REGIME = ("spy_return_20", "qqq_return_20", "iwm_return_20", "breadth_proxy", "credit_proxy")
FEATURES = tuple(STRUCTURE) + REGIME


def require(condition):
    if not condition:
        raise ValueError("Phase 1c input or coverage check failed")


def load_inputs(root):
    protocol, freeze, auth = (load(root / path) for path in (PROTOCOL, FREEZE, AUTHORIZATION))
    protocol_hash = digest(canonical(protocol))
    require(protocol_hash == freeze["canonical_sha256"] == auth["protocol_canonical_sha256"])
    inputs = protocol["inputs"]
    development, calendar_spec = (load(root / inputs[name]["path"])
                                  for name in ("development", "development_calendar"))
    for key, data in (("development", development), ("development_calendar", calendar_spec)):
        require(digest(canonical(data)) == inputs[key]["canonical_sha256"])
    holdout = inputs["holdout"]
    for pin in (holdout["events_spec"], holdout["registry"], holdout["owner_completion"]):
        require(digest((root / pin["path"]).read_bytes().replace(b"\r\n", b"\n")) == pin["sha256_git_lf"])
    sealed = load(root / holdout["events_spec"]["path"])
    registry = load(root / holdout["registry"]["path"])
    require(registry["seal"] == "hash_only")
    require({e["event_id"]: e["recorded_result"]["labels_sha256"] for e in sealed["events"]}
            == {e["event_id"]: e["labels_sha256"] for e in registry["events"]})
    probe = load(root / PROBE)
    require(digest(canonical(probe)) == auth["lookback_calendar_source"]["canonical_sha256"])
    # The Phase 1a SPY check verified this late-2023 session schedule. Earlier
    # sessions are outside the acquisition window.
    calendar = Calendar(dict(calendar_spec, start=probe["window"]["start"],
                             holidays=calendar_spec["holidays"] +
                             probe["calendar"]["full_day_holidays_for_other_years"]["2023"]))
    cohorts = {"development": development["events"], "holdout": sealed["events"]}
    require(len(cohorts["development"]) == 128 and len(cohorts["holdout"]) == 43)
    require(len({event["event_id"] for events in cohorts.values() for event in events}) == 171)
    require(tuple(protocol["feature_policy"]["market_regime"]["symbols"]) == REGIME_SYMBOLS)
    require(set(protocol["feature_policy"]["market_structure"]) == set(STRUCTURE))
    return protocol_hash, calendar, cohorts


def event_windows(event, calendar):
    cutoff = timestamp(event["cutoff"])
    day = cutoff.astimezone(calendar.zone).date().isoformat()
    require(calendar.spec["start"] <= day <= calendar.spec["end"])
    stop = bisect.bisect_left(calendar.days, day)
    issuer = event["security"]["ticker"]
    identity_start = timestamp(event["security"]["valid_from"])
    require("historical_identity" in event["attestations"] and identity_start <= cutoff)
    # Use the earliest session whose open falls within the attested identity.
    lower = max(0, stop - 252)
    issuer_days = tuple(session for session in calendar.days[lower:stop]
                        if calendar.bounds(session)[0] >= identity_start)
    supported_length = max((length for length, _ in STRUCTURE.values() if length <= len(issuer_days)),
                           default=0)
    issuer_days = issuer_days[-supported_length:] if supported_length else ()
    regime_days = tuple(calendar.days[max(0, stop - 21):stop])
    return issuer, issuer_days, regime_days


def request_windows(events, calendar):
    """Union only overlapping or consecutive authorized session windows per symbol."""
    indexes = {day: index for index, day in enumerate(calendar.days)}
    spans = defaultdict(list)
    for event in events:
        issuer, issuer_days, regime_days = event_windows(event, calendar)
        for symbol, days in [(issuer, issuer_days), *((symbol, regime_days) for symbol in REGIME_SYMBOLS)]:
            if days:
                spans[symbol].append((indexes[days[0]], indexes[days[-1]]))
    for symbol, intervals in sorted(spans.items()):
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1] + 1:
                first, last = merged[-1]
                merged[-1] = first, max(last, end)
            else:
                merged.append((start, end))
        for first, last in merged:
            yield symbol, calendar.days[first], calendar.days[last]


def fetch_window(fetch, symbol, start, end, zone):
    # The provider dates daily bars at local midnight, including across DST.
    first = datetime.combine(date.fromisoformat(start), time.min, zone)
    last = datetime.combine(date.fromisoformat(end), time(23, 59, 59), zone)
    bars, _ = ea.fetch_bars(lambda p: fetch(ea.BARS_ENDPOINT, p), symbol,
                            {"symbols": symbol, "timeframe": "1Day", "start": first.isoformat(),
                             "end": last.isoformat(), "feed": "sip", "adjustment": "raw",
                             "asof": "-", "sort": "asc", "currency": "USD", "limit": 1000})
    require(all(start <= day <= end for day in bars))
    return bars


def fetch_action_dates(fetch, symbol, start, end):
    params = {"symbols": symbol, "start": start, "end": end, "limit": 100, "sort": "asc"}

    def checked_fetch(query):
        raw = fetch(ea.ACTIONS_ENDPOINT, query)
        require("corporate_actions" in json.loads(raw))
        return raw

    try:
        actions, _ = ea.fetch_actions(checked_fetch, params)
    except HTTPError as error:
        if error.code != 400 or start[:4] == end[:4]:
            raise
        return set().union(*(fetch_action_dates(fetch, symbol, max(start, f"{year}-01-01"),
                                                min(end, f"{year}-12-31"))
                             for year in range(int(start[:4]), int(end[:4]) + 1)))
    # A payable or process date is not proof of the action's effective date.
    require(all(action.get("date_field") in (None, "effective_date") for action in actions))
    return {action["ex_date"] for action in actions if start <= action["ex_date"] <= end}


def acquire(events, calendar, fetch):
    bars, actions, unresolved = defaultdict(dict), defaultdict(set), defaultdict(set)
    for symbol, start, end in request_windows(events, calendar):
        bars[symbol].update(fetch_window(fetch, symbol, start, end, calendar.zone))
        try:
            actions[symbol].update(fetch_action_dates(fetch, symbol, start, end))
        except (ValueError, ea.DataError):
            unresolved[symbol].add((start, end))
    return bars, actions, unresolved


def validated_window(symbol, days, length, fields, data):
    bars, actions, unresolved = data
    if len(days) < length:
        return None, "insufficient_history"
    days = days[-length:]
    first, last = days[0], days[-1]
    if any(start <= last and end >= first for start, end in unresolved.get(symbol, ())):
        return None, "unverified_actions"
    if any(first <= action <= last for action in actions.get(symbol, ())):
        return None, "corporate_action"
    rows = [bars.get(symbol, {}).get(day) for day in days]
    if any(row is None for row in rows):
        return None, "missing_session"
    if any(type(row.get(field)) not in (int, float)
           or not math.isfinite(row[field]) or row[field] <= 0 for row in rows for field in fields):
        return None, "invalid_bar"
    return rows, None


def structure_value(name, rows):
    if name == "return_5":
        return rows[-1]["close"] / rows[0]["close"] - 1
    if name == "rv_20":
        return statistics.stdev(math.log(current["close"] / prior["close"])
                                for prior, current in zip(rows, rows[1:]))
    if name == "atr_14_fraction":
        return statistics.mean(max(current["high"] - current["low"],
                                   abs(current["high"] - prior["close"]),
                                   abs(current["low"] - prior["close"]))
                               for prior, current in zip(rows, rows[1:])) / rows[-1]["close"]
    if name == "adv_20":
        return statistics.mean(row["close"] * row["volume"] for row in rows)
    if name == "rvol_20":
        return rows[-1]["volume"] / statistics.mean(row["volume"] for row in rows[:-1])
    if name == "distance_252_high":
        return rows[-1]["close"] / max(row["high"] for row in rows) - 1
    raise ValueError("Unknown feature")


def event_features(event, calendar, data):
    symbol, issuer_days, regime_days = event_windows(event, calendar)
    values, missing = {}, {}
    for name, (length, fields) in STRUCTURE.items():
        rows, reason = validated_window(symbol, issuer_days, length, fields, data)
        values[name] = None if reason else structure_value(name, rows)
        if reason:
            missing[name] = reason
    returns = {}
    for etf in REGIME_SYMBOLS:
        rows, reason = validated_window(etf, regime_days, 21, ("close",), data)
        returns[etf] = (None, reason) if reason else (rows[-1]["close"] / rows[0]["close"] - 1, None)
    definitions = zip(REGIME, (("SPY",), ("QQQ",), ("IWM",), ("RSP", "SPY"), ("HYG", "LQD")))
    for name, legs in definitions:
        reason = next((returns[leg][1] for leg in legs if returns[leg][1]), None)
        values[name] = None if reason else returns[legs[0]][0] - (returns[legs[1]][0] if len(legs) == 2 else 0)
        if reason:
            missing[name] = reason
    return {"event_id": event["event_id"], "features": values, "unavailable": missing}


def summarize(rows):
    return {key: dict(sorted(Counter(row["unavailable"].get(key, "available") for row in rows).items()))
            for key in FEATURES}


def build_output(protocol_hash, calendar, cohorts, fetch):
    rows = {}
    for partition, events in cohorts.items():
        data = acquire(events, calendar, fetch)
        rows[partition] = [event_features(event, calendar, data)
                           for event in sorted(events, key=lambda event: event["event_id"])]
    coverage = {partition: summarize(features) for partition, features in rows.items()}
    require(all(any(report[key].get("available", 0) for key in family)
                for report in coverage.values() for family in (STRUCTURE, REGIME)))
    development = {"schema_version": 1, "protocol_sha256": protocol_hash, "partition": "development",
                   "events": rows["development"]}
    summary = {"schema_version": 1, "protocol_sha256": protocol_hash,
               "counts": {partition: len(features) for partition, features in rows.items()},
               "coverage": coverage, "development_sha256": digest(canonical(development)),
               "holdout_features_sha256": digest(canonical(rows["holdout"])),
               "holdout_seal": "hash_only"}
    return development, summary


def bounded_fetch(fetch):
    requests = 0
    last_started = None

    def get(endpoint, params):
        nonlocal requests, last_started
        require(endpoint in (ea.BARS_ENDPOINT, ea.ACTIONS_ENDPOINT) and requests < 650)
        if last_started is not None:
            clock.sleep(max(0, 0.35 - (clock.monotonic() - last_started)))
        last_started = clock.monotonic()
        requests += 1
        return fetch(endpoint, params)

    return get


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        protocol_hash, calendar, cohorts = load_inputs(Path("."))
        key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
        require(key and secret)
        fetch = ea.make_fetch(build_opener(ea.NoRedirect()), key, secret)
        development, summary = build_output(protocol_hash, calendar, cohorts, bounded_fetch(fetch))
        args.output.mkdir()
        (args.output / "development.json").write_bytes(canonical(development) + b"\n")
        (args.output / "summary.json").write_bytes(canonical(summary) + b"\n")
    except Exception:
        # Network payloads, exceptions, raw data and holdout features never reach logs.
        parser.exit(2, "Phase 1c acquisition failed. No artifact will be published.\n")


if __name__ == "__main__":
    main()
