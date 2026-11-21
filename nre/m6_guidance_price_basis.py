"""Audit raw prior anchors and corporate-action metadata without closing outcomes."""
import argparse
import json
import math
import os
import time as clock
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener

from . import event_acquire as ea
from .calendar import Calendar
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load
from .m6_guidance_revision import PROTOCOL, ROOT
from .m6_guidance_warmup_opening import locked_cohort as training_cohort, implementation_hashes

CA_START, CA_END = "2024-01-01", "2026-11-21"
REQUEST_BUDGET = 300
ANCHOR_DOMAIN = "nre-guidance-v2-raw-prior-anchor-v1"
ACTION_TYPES = frozenset((
    "reverse_splits", "forward_splits", "unit_splits", "cash_dividends", "stock_dividends",
    "spin_offs", "cash_mergers", "stock_mergers", "stock_and_cash_mergers", "redemptions",
    "name_changes", "worthless_removals", "rights_distributions", "partial_calls",
    "reorganizations", "capital_gains_distributions",
))


def locked_cohort(root=ROOT):
    warmup = training_cohort(root)
    protocol = load(root / PROTOCOL)
    calendar = Calendar(load(root / protocol["calendar"]))
    events = [dict(r, subset="warmup") for r in warmup["events"]]
    masks = {r["event_id"]: r for r in load(root / "reports/m6-guidance-source-masks-2026-11-19.json")["events"]}
    for source in load(root / protocol["held_evidence"])["guidance_candidates"]:
        mask = masks[source["event_id"]]
        if mask["hard_exclusions"]:
            continue
        events.append({"event_id": source["event_id"], "symbol": source["symbol"], "cik": source["cik"],
                       "reaction_session": source["reaction_session"], "subset": "held",
                       "clean_window": not bool(mask["soft_caveats"]),
                       "source_event_sha256": digest(canonical(source)),
                       "source_mask_sha256": digest(canonical(mask))})
    for event in events:
        event["anchor_session"] = calendar.offset(event["reaction_session"], -1)
    events.sort(key=lambda r: (r["reaction_session"], r["symbol"], r["event_id"]))
    if (len(events) != 107 or len({r["event_id"] for r in events}) != 107
            or len({(r["symbol"], r["reaction_session"]) for r in events}) != 107
            or sum(r["clean_window"] for r in events) != 97):
        raise DataError("Unexpected price-basis membership")
    pins = dict(warmup["source_canonical_sha256"])
    for path in (protocol["held_evidence"], protocol["calendar"]):
        pins[path] = protocol["input_canonical_sha256"][path]
    binding = {"protocol_sha256": warmup["protocol_sha256"], "source_canonical_sha256": pins, "events": events}
    return {**binding, "cohort_sha256": digest(canonical(binding))}


def action_params(cohort):
    return {"symbols": ",".join(sorted({r["symbol"] for r in cohort["events"]})),
            "start": CA_START, "end": CA_END, "limit": 1000, "sort": "asc",
            "data_quality": "all", "region": "all"}


def anchor_params(event, calendar):
    day = date.fromisoformat(event["anchor_session"])
    return {"symbols": event["symbol"], "timeframe": "1Day",
            "start": datetime.combine(day, time(), calendar.zone).isoformat(),
            "end": datetime.combine(day, time(23, 59, 59), calendar.zone).isoformat(),
            "feed": "sip", "adjustment": "raw", "asof": event["reaction_session"],
            "currency": "USD", "sort": "asc", "limit": 10}


def validate_request(endpoint, params, expected):
    if (set(params) - (set(expected) | {"page_token"})
            or any(params.get(k) != v for k, v in expected.items())
            or "page_token" in params and (not isinstance(params["page_token"], str)
                                             or not 0 < len(params["page_token"]) <= 4096)):
        raise DataError("Request outside registered preparation boundary")
    expected_endpoint = ea.BARS_ENDPOINT if "timeframe" in expected else ea.ACTIONS_ENDPOINT
    if endpoint != expected_endpoint:
        raise DataError("Unexpected preparation endpoint")


def inventory(pages, symbols):
    """Keep safe action metadata; amounts and ratios stay in private provider bytes."""
    actions, unresolved, seen = [], set(), {}
    for page in pages:
        groups = page.get("corporate_actions")
        if not isinstance(groups, dict):
            raise DataError("Malformed corporate-action inventory")
        for kind, rows in groups.items():
            if not isinstance(rows, list):
                raise DataError("Malformed corporate-action group")
            for row in rows:
                if not isinstance(row, dict):
                    raise DataError("Malformed corporate-action record")
                related = {v for k, v in row.items() if "symbol" in k and isinstance(v, str) and v in symbols}
                if not related:
                    unresolved.update(symbols)
                affected = related or symbols
                sha = digest(canonical(row))
                identity = row.get("id")
                if not isinstance(identity, str) or not identity:
                    unresolved.update(affected)
                elif identity in seen:
                    if seen[identity][0] != sha:
                        unresolved.update(affected | seen[identity][1])
                    continue
                else:
                    seen[identity] = sha, affected
                dates = {}
                invalid = False
                for field in ("ex_date", "effective_date", "process_date"):
                    value = row.get(field)
                    if value is not None:
                        try:
                            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                                raise ValueError()
                            dates[field] = value
                        except (ValueError, TypeError):
                            invalid = True
                if (invalid or kind not in ACTION_TYPES or not ("ex_date" in dates or "effective_date" in dates)
                        or "ex_date" in dates and "effective_date" in dates and dates["ex_date"] != dates["effective_date"]):
                    unresolved.update(affected)
                actions.append({"type": kind if kind in ACTION_TYPES else "unrecognized",
                                "symbols": sorted(related),
                                "id_sha256": digest(canonical(identity)) if isinstance(identity, str) else None,
                                **dates, "record_sha256": sha})
    return actions, unresolved


def bridge_status(event, actions, unresolved):
    if event["symbol"] in unresolved:
        return "unresolved_action_inventory", []
    hits = []
    for action in actions:
        if event["symbol"] not in action["symbols"]:
            continue
        if "ex_date" in action:
            intersects = event["anchor_session"] < action["ex_date"] <= event["reaction_session"]
        else:
            # Date-only effective actions on the anchor day could occur after its close.
            intersects = event["anchor_session"] <= action["effective_date"] <= event["reaction_session"]
        if intersects:
            hits.append(action["record_sha256"])
    return ("action_requires_reconciliation" if hits else "no_observed_action_in_bridge"), hits


def checked_anchor(pages, event, calendar):
    rows = []
    for page in pages:
        bars = page.get("bars")
        if not isinstance(bars, dict) or set(bars) - {event["symbol"]}:
            return None, "invalid_anchor_response"
        batch = bars.get(event["symbol"], [])
        if not isinstance(batch, list):
            return None, "invalid_anchor_response"
        rows.extend(batch)
    if not rows:
        return None, "missing_anchor"
    if len(rows) != 1 or not isinstance(rows[0], dict):
        return None, "ambiguous_anchor"
    row = rows[0]
    try:
        expected = datetime.combine(date.fromisoformat(event["anchor_session"]), time(), calendar.zone)
        if timestamp(row["t"]) != expected:
            raise ValueError()
        if any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) or row[k] <= 0 for k in ("o", "h", "l", "c", "v")):
            raise ValueError()
        if not row["l"] <= min(row["o"], row["c"]) <= max(row["o"], row["c"]) <= row["h"]:
            raise ValueError()
    except (KeyError, TypeError, ValueError, DataError):
        return None, "invalid_anchor"
    return row, "verified_raw_anchor"


def run(root, fetch):
    cohort = locked_cohort(root)
    calendar = Calendar(load(root / load(root / PROTOCOL)["calendar"]))
    requests, receipts = 0, []

    def checked(endpoint, params, expected):
        nonlocal requests
        validate_request(endpoint, params, expected)
        if requests >= REQUEST_BUDGET:
            raise DataError("Price-basis request budget exhausted")
        requests += 1
        raw = fetch(endpoint, params)
        if not isinstance(raw, bytes) or len(raw) > 4_000_000:
            raise DataError("Unexpected price-basis response representation")
        receipts.append({"request_sha256": digest(canonical({"endpoint": endpoint, "params": params})),
                         "response_sha256": digest(raw)})
        return raw

    symbols = {r["symbol"] for r in cohort["events"]}
    ca_params = action_params(cohort)
    ca_start = len(receipts)
    ca_http = None
    try:
        pages, _ = ea._paginate(lambda p: checked(ea.ACTIONS_ENDPOINT, p, ca_params), ca_params, "corporate_actions")
        actions, unresolved = inventory(pages, symbols)
        ca_status = "complete_paginated_inventory"
    except HTTPError as error:
        actions, unresolved, ca_http = [], symbols, error.code
        ca_status = "corporate_action_provider_error"
    ca_receipts = receipts[ca_start:]
    results, bar_access_error = [], None
    for event in cohort["events"]:
        params, receipt_start = anchor_params(event, calendar), len(receipts)
        row = None
        if bar_access_error is not None:
            anchor_status = "anchor_not_requested_after_provider_error"
        else:
            try:
                pages, _ = ea._paginate(lambda p: checked(ea.BARS_ENDPOINT, p, params), params, "bars")
                row, anchor_status = checked_anchor(pages, event, calendar)
            except HTTPError as error:
                anchor_status, bar_access_error = "anchor_provider_error", error.code
        action_status, hits = bridge_status(event, actions, unresolved)
        commitment = None
        if row is not None:
            commitment = digest(canonical({"domain": ANCHOR_DOMAIN, "protocol_sha256": cohort["protocol_sha256"],
                                            "cohort_sha256": cohort["cohort_sha256"], "event_id": event["event_id"],
                                            "symbol": event["symbol"], "anchor_session": event["anchor_session"],
                                            "query": params, "raw_anchor_bar": row}))
        results.append({k: event[k] for k in ("event_id", "symbol", "cik", "subset", "clean_window", "anchor_session", "reaction_session")}
                       | {"anchor_status": anchor_status, "anchor_commitment_sha256": commitment,
                          "corporate_action_status": action_status, "intersecting_action_sha256": hits,
                          "status": "provider_basis_checks_passed" if row is not None and action_status == "no_observed_action_in_bridge" else "basis_unverified",
                          "anchor_receipts": receipts[receipt_start:]})
    implementations = implementation_hashes(root)
    implementations["nre/m6_guidance_price_basis.py"] = digest((root / "nre/m6_guidance_price_basis.py").read_bytes().replace(b"\r\n", b"\n"))
    return {"schema_version": 1, "scope": "guidance_v2_prior_anchor_and_action_basis",
            "protocol_sha256": cohort["protocol_sha256"], "cohort_sha256": cohort["cohort_sha256"],
            "source_canonical_sha256": cohort["source_canonical_sha256"], "implementation_sha256_git_lf": implementations,
            "corporate_action_inventory": {"status": ca_status, "http_status": ca_http, "query": ca_params,
                                           "receipts": ca_receipts, "actions": actions, "unresolved_symbols": sorted(unresolved)},
            "anchor_provider_http_status": bar_access_error, "anchor_commitment_scheme": ANCHOR_DOMAIN,
            "screened": len(results), "dispositions": dict(Counter(r["status"] for r in results)),
            "requests": requests, "events": results, "reaction_session_bar_requests": 0,
            "closing_outcome_requests": 0, "model_runs": 0,
            "limitations": ["CA inventory is retrospective provider evidence, not a guarantee against late corrections or missing announcements.",
                            "Daily anchor close is the last eligible consolidated SIP price, not an exchange official closing-auction print.",
                            "These checks do not clear exhaustive periodic-report content, reaction closing labels, label maturity, or model feature variation."]}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        provider = ea.make_fetch(build_opener(ea.NoRedirect()), os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"])
        next_request = clock.monotonic()

        def fetch(endpoint, params):
            nonlocal next_request
            clock.sleep(max(0, next_request - clock.monotonic()))
            next_request = clock.monotonic() + 0.75
            return provider(endpoint, params)

        print(json.dumps(run(Path("."), fetch), sort_keys=True))
    except HTTPError as error:
        print(json.dumps({"status": "provider_error", "http_status": error.code}))
        return 2
    except Exception as error:
        print(json.dumps({"status": "price_basis_failed", "reason": type(error).__name__}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
