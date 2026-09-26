"""Real-data acquisition and label computation for the attested M1 events in config/m1-events.json.

Fetches SIP daily bars and corporate actions from Alpaca for each event's session window, builds the reviewed
bundle and runs nre.dataset.build(). Prints only derived results -- labels, counts, hashes, reasons -- never raw
OHLCV or credentials; raw bars exist only in this process's memory.
"""
import argparse
import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .calendar import Calendar
from .core import DataError, canonical, digest, iso, timestamp
from .dataset import build

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = ROOT / "config" / "m1-events.json"
BARS_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
ACTIONS_ENDPOINT = "https://data.alpaca.markets/v1/corporate-actions"
REACTION_SESSIONS = 20
TIMINGS = {"premarket", "after_hours"}
ATTESTATIONS = {"first_public_time", "historical_identity", "corporate_actions"}
RESERVED_SOURCE_IDS = {"alpaca-bars", "alpaca-actions"}
TICKER = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
SECURITY_KEYS = ("security_id", "company_id", "cik", "ticker", "exchange", "security_type", "valid_from", "available_at")
SOURCE_KEYS = ("source_id", "url", "text", "first_seen_at")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DataError("redirect rejected")


def _require(mapping, keys, label):
    if not isinstance(mapping, dict):
        raise DataError(label + " must be an object")
    for key in keys:
        if not isinstance(mapping.get(key), str) or not mapping[key].strip():
            raise DataError(label + "." + key + " must be a nonempty string")


def _aware(value, label):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise DataError(label + " is not an ISO timestamp") from None
    if parsed.tzinfo is None:
        raise DataError(label + " needs a UTC offset")
    return parsed


def _attested(attestation, label, root):
    _require(attestation, ("reviewer", "record"), label + " attestation")
    try:
        date.fromisoformat(attestation.get("date"))
    except (TypeError, ValueError):
        raise DataError(label + " attestation needs an ISO date") from None
    if not (root / attestation["record"]).is_file():
        raise DataError(label + " attestation record not found: " + attestation["record"])


def event_window(event, calendar):
    session, timing = calendar.classify(event["published_at"])
    anchor = calendar.offset(session, -1)
    sessions = [anchor] + [calendar.offset(session, i) for i in range(REACTION_SESSIONS)]
    last = date.fromisoformat(sessions[-1])
    month_end = (last.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    asof = datetime.fromisoformat(event["published_at"]).astimezone(calendar.zone).date()
    return {"anchor_session": anchor, "reaction_session": session, "release_timing": timing,
            "required_sessions": sessions, "start": date.fromisoformat(anchor).replace(day=1).isoformat(),
            "end": month_end.isoformat(), "asof": asof.isoformat()}


def _validate_event(event, calendar, root):
    _require(event, ("event_id", "cluster_id", "candidate_id", "published_at", "cutoff", "timestamp_evidence"), "event")
    name = event["event_id"]
    security, source = event.get("security"), event.get("source")
    _require(security, SECURITY_KEYS, name + ".security")
    _require(source, SOURCE_KEYS, name + ".source")
    if not TICKER.match(security["ticker"]):
        raise DataError(name + ": ticker is not a plain symbol")
    if source["source_id"] in RESERVED_SOURCE_IDS or not source["url"].startswith("https://"):
        raise DataError(name + ": source needs an unreserved id and an https URL")
    if event.get("precision") != "minute":
        raise DataError(name + ": only minute precision is supported")
    published = _aware(event["published_at"], name + ".published_at")
    if published.utcoffset() != published.astimezone(calendar.zone).utcoffset():
        raise DataError(name + ": published_at must carry the New York UTC offset in force at that instant")
    if published.second or published.microsecond:
        raise DataError(name + ": published_at must be minute-aligned")
    if published.astimezone(calendar.zone).strftime("%H:%M") != event["timestamp_evidence"]:
        raise DataError(name + ": timestamp_evidence must equal the New York wall-clock minute of published_at")
    if event["timestamp_evidence"] not in source["text"]:
        raise DataError(name + ": timestamp_evidence not found in source text")
    if timestamp(source["first_seen_at"]) < timestamp(event["published_at"]):
        raise DataError(name + ": source first_seen_at precedes publication")
    window = event_window(event, calendar)
    if event.get("expected_release_timing") not in TIMINGS or window["release_timing"] != event["expected_release_timing"]:
        raise DataError(name + ": release timing computed from published_at disagrees with expected_release_timing")
    if window["reaction_session"] != event.get("expected_reaction_session"):
        raise DataError(name + ": reaction session computed from published_at disagrees with expected_reaction_session")
    attestations = event.get("attestations", {})
    if not isinstance(attestations, dict) or set(attestations) - ATTESTATIONS:
        raise DataError(name + ": attestations may only use " + ", ".join(sorted(ATTESTATIONS)))
    for key, attestation in attestations.items():
        _attested(attestation, name + "." + key, root)
    recorded = event.get("recorded_result")
    if recorded is not None:
        if not isinstance(recorded, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(recorded.get("labels_sha256"))):
            raise DataError(name + ": recorded_result needs a 64-hex labels_sha256")
        _require(recorded, ("recorded_in",), name + ".recorded_result")
        if not (root / recorded["recorded_in"]).is_file():
            raise DataError(name + ": recorded_result record not found: " + recorded["recorded_in"])
    for caveat in event.get("caveats", []):
        if not isinstance(caveat, dict) or not isinstance(caveat.get("labels"), list) or not isinstance(caveat.get("note"), str):
            raise DataError(name + ": each caveat needs a labels list and a note")


def validate_spec(spec, calendar, root=ROOT):
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise DataError("event spec schema_version 1 required")
    provider = spec.get("provider")
    _require(provider, ("provider_id", "terms_url", "session_scope"), "provider")
    if not provider["terms_url"].startswith("https://") or not isinstance(provider.get("feeds"), list):
        raise DataError("provider needs an https terms_url and a feeds list")
    if provider.get("research_permitted") is True:
        _attested(provider.get("attestation"), "provider", root)
    elif provider.get("research_permitted") is not False:
        raise DataError("provider.research_permitted must be boolean")
    events = spec.get("events")
    if not isinstance(events, list) or not events:
        raise DataError("events list required")
    for event in events:
        _validate_event(event, calendar, root)
    for key in ("event_id", "cluster_id", "candidate_id"):
        values = [event[key] for event in events]
        if len(set(values)) != len(values):
            raise DataError("duplicate " + key)


def _paginate(fetch, base_params, payload_key):
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


def bars_params(ticker, window):
    return dict(symbols=ticker, timeframe="1Day", start=window["start"], end=window["end"], feed="sip",
                adjustment="raw", asof=window["asof"], sort="asc", currency="USD", limit=50)


def actions_params(ticker, window):
    return dict(symbols=ticker, start=window["start"], end=window["end"], limit=100, sort="asc")


def fetch_bars(fetch, ticker, params):
    merged, pages = _paginate(fetch, params, "bars")
    by_session = {}
    for page in merged:
        bars = page.get("bars")
        if not isinstance(bars, dict) or set(bars) - {ticker}:
            raise DataError("unexpected bars structure")
        batch = bars.get(ticker, [])
        if not isinstance(batch, list):
            raise DataError("invalid bar list")
        for row in batch:
            try:
                session = row["t"][:10]
                bar = {"open": row["o"], "high": row["h"], "low": row["l"], "close": row["c"], "volume": row["v"]}
            except (KeyError, TypeError):
                raise DataError("malformed bar record") from None
            if session in by_session:
                raise DataError("duplicate session in bars response")
            by_session[session] = bar
    return by_session, pages


def fetch_actions(fetch, params):
    """Each action's type and ex_date, so the pipeline can suppress exactly the labels an action crosses."""
    merged, pages = _paginate(fetch, params, "corporate_actions")
    entries = []
    for page in merged:
        actions = page.get("corporate_actions")
        if actions in (None, {}, []):
            continue
        if not isinstance(actions, dict):
            raise DataError("unexpected corporate_actions structure")
        for action_type, items in actions.items():
            if not isinstance(items, list):
                raise DataError("unexpected corporate_actions structure")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("ex_date"), str):
                    raise DataError("corporate action missing ex_date")
                try:
                    date.fromisoformat(item["ex_date"])
                except ValueError:
                    raise DataError("corporate action ex_date is not a date") from None
                entries.append({"type": action_type, "ex_date": item["ex_date"], "id": item.get("id")})
    return entries, pages


def build_bundle(event, provider, window, bars_by_session, actions, retrieved_at, calendar):
    security, source, ticker = event["security"], event["source"], event["security"]["ticker"]
    attested = event.get("attestations", {})
    first_public = "first_public_time" in attested and "historical_identity" in attested
    actions_verified = "corporate_actions" in attested
    stamp = iso(retrieved_at)
    prices = []
    for session in window["required_sessions"]:
        bar = bars_by_session.get(session)
        if bar is None:
            continue
        prices.append({
            "price_id": ticker.lower() + "-" + session, "security_id": security["security_id"],
            "source_id": "alpaca-bars", "session": session, "provider_id": provider["provider_id"],
            "feed": "sip", "price_basis": "raw", "open": bar["open"], "high": bar["high"],
            "low": bar["low"], "close": bar["close"], "volume": bar["volume"],
            # A regular close is known within a minute of the bell; a later stamp would wrongly block the
            # same-day anchor of an after-hours release at its cutoff.
            "available_at": iso(calendar.bounds(session)[1] + timedelta(minutes=1)),
            "complete": True, "halted": bar["volume"] == 0,
            # Unattested events stay quarantined while still reporting the actions found.
            "corporate_actions_verified": actions_verified,
        })
    return {
        "schema_version": 1, "synthetic": False, "as_of": stamp,
        "availability_mode": "historical_reconstruction",
        "sources": [
            {"source_id": source["source_id"], "url": source["url"], "text": source["text"],
             "first_seen_at": source["first_seen_at"], "retrieved_at": stamp},
            {"source_id": "alpaca-bars", "url": BARS_ENDPOINT, "first_seen_at": stamp, "retrieved_at": stamp,
             "text": "Alpaca SIP daily bars, " + ticker + ", " + window["start"] + " to " + window["end"]
             + ", asof " + window["asof"] + "."},
            {"source_id": "alpaca-actions", "url": ACTIONS_ENDPOINT, "first_seen_at": stamp, "retrieved_at": stamp,
             "text": "Alpaca corporate actions, " + ticker + ", " + window["start"] + " to " + window["end"] + "."},
        ],
        "securities": [
            {"security_id": security["security_id"], "company_id": security["company_id"], "cik": security["cik"],
             "ticker": ticker, "exchange": security["exchange"], "security_type": security["security_type"],
             "source_id": source["source_id"], "valid_from": security["valid_from"], "valid_to": None,
             "available_at": security["available_at"]},
        ],
        "providers": [
            {"provider_id": provider["provider_id"], "research_permitted": provider["research_permitted"] is True,
             "terms_url": provider["terms_url"], "feeds": provider["feeds"], "session_scope": provider["session_scope"]},
        ],
        "events": [
            {"event_id": event["event_id"], "cluster_id": event["cluster_id"], "security_id": security["security_id"],
             "source_id": source["source_id"], "published_at": event["published_at"], "cutoff": event["cutoff"],
             "precision": "minute", "first_public_verified": first_public,
             "timestamp_evidence": event["timestamp_evidence"]},
        ],
        "prices": prices,
        "corporate_actions": [
            {"action_id": a["id"] or (a["type"] + "-" + a["ex_date"]), "security_id": security["security_id"],
             "source_id": "alpaca-actions", "type": a["type"], "effective_date": a["ex_date"],
             # Conservatively public no later than its own ex-date.
             "available_at": iso(datetime.combine(date.fromisoformat(a["ex_date"]), time(0), calendar.zone))}
            for a in actions],
        "features": [],
    }


def labels_digest(outcome):
    return digest(canonical({name: {"value": label["value"], "reason": label["reason"]}
                             for name, label in outcome["labels"].items()}))


def _error_category(exc):
    if isinstance(exc, HTTPError):
        return "ALPACA_HTTP_" + str(exc.code)
    if isinstance(exc, DataError):
        return "DATA_VALIDATION_FAILED: " + str(exc)
    if isinstance(exc, json.JSONDecodeError):
        return "INVALID_JSON_RESPONSE"
    if isinstance(exc, URLError):
        return "NETWORK_ERROR"
    return "UNCATEGORIZED_" + type(exc).__name__.upper()


def run_event(event, provider, fetch, calendar, retrieved_at=None):
    ticker = event["security"]["ticker"]
    report = {"event_id": event["event_id"], "ticker": ticker, "access_check_passed": False, "labels_computed": False}
    if event.get("caveats"):
        report["caveats"] = event["caveats"]
    try:
        window = event_window(event, calendar)
        report["window"] = {key: window[key] for key in ("anchor_session", "reaction_session", "release_timing",
                                                          "start", "end", "asof")}
        report["window"]["required_sessions"] = len(window["required_sessions"])
        bars, bar_pages = fetch_bars(lambda p: fetch(BARS_ENDPOINT, p), ticker, bars_params(ticker, window))
        actions, action_pages = fetch_actions(lambda p: fetch(ACTIONS_ENDPOINT, p), actions_params(ticker, window))
        report.update(access_check_passed=True, bar_pages=bar_pages, action_pages=action_pages,
                      corporate_actions=actions)
        required = window["required_sessions"]
        report["missing_sessions"] = [s for s in required if s not in bars]
        report["zero_volume_sessions"] = [s for s in required if s in bars and bars[s]["volume"] == 0]
        bundle = build_bundle(event, provider, window, bars, actions, retrieved_at or datetime.now(timezone.utc),
                              calendar)
        report["bundle_sha256"] = digest(canonical(bundle))
        results, build_report = build(bundle)
        outcome = results[0]
        if outcome.get("anchor"):
            # event_outcome() embeds the anchor close as the return denominator; keep only its identifier.
            outcome["anchor"] = {k: v for k, v in outcome["anchor"].items() if k != "price"}
        report.update(build_report=build_report, computed_outcome=outcome,
                      labels_computed=build_report["mapped_day1"] > 0)
        if outcome["state"] == "MAPPED":
            report["labels_sha256"] = labels_digest(outcome)
        pinned = (event.get("recorded_result") or {}).get("labels_sha256")
        if pinned is not None:
            report["labels_match_recorded"] = report.get("labels_sha256") == pinned
            if not report["labels_match_recorded"]:
                report["error"] = "LABELS_DIFFER_FROM_RECORDED"
    except Exception as exc:
        report["error"] = _error_category(exc)
    return report


def _compact(report):
    outcome = report.get("computed_outcome") or {}
    labels = {} if report.get("labels_match_recorded") else outcome.get("labels", {})
    return {"state": outcome.get("state"), "reasons": outcome.get("reasons"), "error": report.get("error"),
            "release_timing": outcome.get("release_timing"), "reaction_session": outcome.get("reaction_session"),
            "missing_sessions": report.get("missing_sessions"), "zero_volume_sessions": report.get("zero_volume_sessions"),
            "corporate_actions": report.get("corporate_actions"), "labels_sha256": report.get("labels_sha256"),
            "labels_match_recorded": report.get("labels_match_recorded"),
            "labels": {k: v["value"] for k, v in sorted(labels.items())},
            "label_reasons": {k: v["reason"] for k, v in sorted(labels.items()) if v["reason"]}}


def _annotations(level, all_ok, events, budget=3300):
    """GitHub truncates an annotation message near 4,096 characters, so split the summary into parts."""
    parts, current, size = [], {}, 0
    for key, value in events.items():
        piece = len(json.dumps({key: value}, separators=(",", ":")))
        if current and size + piece > budget:
            parts.append(current)
            current, size = {}, 0
        current[key] = value
        size += piece
    if current or not parts:
        parts.append(current)
    lines = []
    for number, part in enumerate(parts, 1):
        message = json.dumps({"all_ok": all_ok, "part": "%d/%d" % (number, len(parts)), "events": part},
                             sort_keys=True, separators=(",", ":"))
        message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        lines.append("::" + level + " title=NRE event acquisition::" + message)
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Acquire real prices and compute labels for attested M1 events.")
    parser.add_argument("--spec", default=str(DEFAULT_SPEC))
    parser.add_argument("--event", default="all", help="event_id from the spec, or 'all'")
    args = parser.parse_args(argv)
    out = {"all_ok": False, "events": {}}

    def finish(code):
        print(json.dumps(out, sort_keys=True, indent=2))
        return code

    try:
        calendar = Calendar()
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        validate_spec(spec, calendar)
        events = [e for e in spec["events"] if args.event in ("all", e["event_id"])]
        if not events:
            raise DataError("unknown event: " + args.event)
    except Exception as exc:
        detail = "not valid JSON" if isinstance(exc, json.JSONDecodeError) else _error_category(exc)
        out["error"] = "SPEC_INVALID: " + detail
        return finish(2)

    key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        out["error"] = "MISSING_GITHUB_ACTIONS_SECRETS"
        return finish(2)

    opener = build_opener(NoRedirect())

    def fetch(endpoint, params):
        request = Request(endpoint + "?" + urlencode(params),
                          headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        with opener.open(request, timeout=30) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise DataError("response size limit exceeded")
            return raw

    for event in events:
        out["events"][event["event_id"]] = run_event(event, spec["provider"], fetch, calendar)
    out["all_ok"] = all("error" not in report for report in out["events"].values())
    code = finish(0 if out["all_ok"] else 2)
    if os.getenv("GITHUB_ACTIONS") == "true":
        for line in _annotations("notice" if out["all_ok"] else "error", out["all_ok"],
                                 {k: _compact(v) for k, v in out["events"].items()}):
            print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
