"""Milestone 5 Phase 1a: a bounded, read-only availability probe of the Alpaca market-data API.

    python -m nre.m5_phase1a_probe        (in GitHub Actions, with APCA_API_KEY_ID and APCA_API_SECRET_KEY)

It answers one question, fixed in config/m5-phase1a-probe-spec.json before it runs: which regime and market-structure fields can the provider supply point-in-time for
the pre-specified symbols. It keeps only availability metadata -- dates, counts, HTTP status codes and unit-free ratios -- and never a price or a volume value: each bar is
reduced to its date (and a zero-volume flag) the moment it is read, and a test checks the report for any such value. It computes no return, label or feature and adds nothing
to the dataset. Credentials come from the environment and are never printed. The report reaches the owner as the job log and as compressed check-run annotations, which the
public GitHub API serves without sign-in (decode_annotations reads them back).
"""
import base64
import gzip
import json
import os
import re
import sys
import time
from datetime import date, datetime, time as clock, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from .calendar import Calendar
from .core import DataError, canonical, digest

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "config" / "m5-phase1a-probe-spec.json"
BARS_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
ACTIONS_ENDPOINT = "https://data.alpaca.markets/v1/corporate-actions"
ALLOWED_ENDPOINTS = (BARS_ENDPOINT, ACTIONS_ENDPOINT)
NEW_YORK = ZoneInfo("America/New_York")
PAGE_LIMIT = 10000
MAX_PAGES = 10
NOTICE_CHARS = 3000
NOTICE_TITLE = "m5-phase1a-probe"
MESSAGE_CHARS = 160
VALUE_KEYS = frozenset(["o", "h", "l", "c", "v", "vw", "n", "open", "high", "low", "close", "volume", "price", "vwap"])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DataError("redirect rejected")


class Transport:
    """GET only, to the two allowed Alpaca endpoints, paced and counted. A non-200 answer is a result, not an error: (status, body), where the body of a failure holds at most a short message."""

    def __init__(self, key, secret, pacing=0.35, budget=260, sleep=time.sleep, opener=None):
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.pacing, self.budget, self.sleep = pacing, budget, sleep
        self.opener = opener or build_opener(NoRedirect())
        self.requests = 0

    def __call__(self, endpoint, params):
        if endpoint not in ALLOWED_ENDPOINTS:
            raise DataError("endpoint not allowed")
        for attempt in range(4):
            if self.requests >= self.budget:
                raise DataError("request budget exhausted")
            self.sleep(self.pacing)
            self.requests += 1
            request = Request(endpoint + "?" + urlencode(params), headers=self.headers, method="GET")
            try:
                with self.opener.open(request, timeout=30) as response:
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise DataError("response size limit exceeded")
                    return response.status, json.loads(raw)
            except HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    self.sleep(5)
                    continue
                return exc.code, {"message": _short_message(exc)}
        return 429, {"message": "rate limited after retries"}


def _short_message(exc):
    try:
        body = json.loads(exc.read(4000))
        message = body.get("message") if isinstance(body, dict) else None
        return message[:MESSAGE_CHARS] if isinstance(message, str) else None
    except (ValueError, OSError):
        return None


def load_spec(path=SPEC_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def spec_digest(spec):
    return digest(canonical(spec))


def spec_symbols(spec):
    symbols = spec["symbols"]
    out = symbols["regime_and_market_etfs"] + symbols["biotech_and_sector_etfs"] + symbols["issuers"]
    if len(set(out)) != len(out):
        raise DataError("duplicate symbol in the spec")
    return out


def _weekdays(start, end):
    day, out = date.fromisoformat(start), []
    while day <= date.fromisoformat(end):
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def expected_sessions(spec, project_calendars):
    """The sessions the window should hold: reviewed project calendars for the years that have one, weekdays less the spec's listed full-day holidays for the others."""
    window, calendar = spec["window"], spec["calendar"]
    holidays = {d for days in calendar["full_day_holidays_for_other_years"].values() for d in days}
    out = []
    for day in _weekdays(window["start"], window["end"]):
        year = day[:4]
        if year in project_calendars:
            if day in project_calendars[year]:
                out.append(day)
        elif year in calendar["full_day_holidays_for_other_years"]:
            if day not in holidays:
                out.append(day)
        else:
            raise DataError("no calendar for " + year)
    return out


def load_project_calendars(spec, root=ROOT):
    return {year: set(Calendar(json.loads((Path(root) / path).read_text(encoding="utf-8"))).days) for year, path in spec["calendar"]["reviewed_project_calendars"].items()}


def _bar_date(row):
    if not isinstance(row, dict) or not isinstance(row.get("t"), str):
        raise DataError("malformed bar record")
    try:
        return date.fromisoformat(row["t"][:10]).isoformat()
    except ValueError:
        raise DataError("malformed bar date") from None


def _rows(payload, key, symbol=None):
    body = (payload or {}).get(key)
    if symbol is not None:
        body = (body or {}).get(symbol)
    return body or []


def daily_bar_dates(fetch, symbol, start, end, feed="sip", adjustment="raw", asof=None):
    """Dates of the daily bars of one symbol and a count of zero-volume bars; each bar is reduced to those the moment it is read, so no price or volume value outlives the loop.
    asof='-' asks the provider to skip its symbol mapping (by default it stitches the history of an entity's earlier symbols into the queried one)."""
    dates, zero, pages, token, seen = [], 0, 0, None, set()
    while True:
        params = dict(symbols=symbol, timeframe="1Day", start=start, end=end, feed=feed, adjustment=adjustment, currency="USD", sort="asc", limit=PAGE_LIMIT)
        if asof is not None:
            params["asof"] = asof
        if token is not None:
            params["page_token"] = token
        status, payload = fetch(BARS_ENDPOINT, params)
        pages += 1
        if status != 200:
            return {"status": status, "dates": dates, "zero_volume": zero, "pages": pages, "message": (payload or {}).get("message")}
        if not isinstance(payload, dict) or "next_page_token" not in payload:
            raise DataError("missing pagination metadata")
        for row in _rows(payload, "bars", symbol):
            dates.append(_bar_date(row))
            zero += 1 if row.get("v") == 0 else 0
        token = payload["next_page_token"]
        if token is None:
            break
        if not isinstance(token, str) or not token or token in seen or pages >= MAX_PAGES:
            raise DataError("invalid, repeated or runaway pagination")
        seen.add(token)
    if dates != sorted(set(dates)):
        raise DataError("bar dates are duplicated or out of order")
    return {"status": 200, "dates": dates, "zero_volume": zero, "pages": pages, "message": None}


def _period_of(day, periods):
    for name, (first, last) in periods.items():
        if first <= day <= last:
            return name
    return "outside"


def summarize_bars(result, expected, spec):
    """Availability of one symbol's daily bars against the expected sessions."""
    if result["status"] != 200:
        return {"status": result["status"], "message": result["message"], "bars": 0}
    dates, window = result["dates"], spec["window"]
    periods = window["periods"]
    got, first = set(dates), (dates[0] if dates else None)
    after_first = [d for d in expected if first is not None and d >= first]
    missing = [d for d in after_first if d not in got]
    unexpected = sorted(got - set(expected))
    before = sum(1 for d in dates if d < window["first_reaction_session"])
    return {"status": 200, "bars": len(dates), "first_bar_date": first, "last_bar_date": dates[-1] if dates else None, "pages": result["pages"],
            "bars_by_period": {name: sum(1 for d in dates if _period_of(d, periods) == name) for name in periods},
            "expected_sessions_from_first_bar": len(after_first), "missing_sessions": len(missing),
            "missing_by_period": {name: sum(1 for d in missing if _period_of(d, periods) == name) for name in periods},
            "missing_dates_first_20": missing[:20], "bars_on_unexpected_dates": len(unexpected), "unexpected_dates_first_20": unexpected[:20],
            "zero_volume_bars": result["zero_volume"], "bars_before_first_reaction_session": before,
            "has_required_lookback": before >= window["lookback_sessions_needed"]}


def reference_check(result, expected):
    """Does the reference symbol's series equal the expected sessions? Differences are listed, not hidden."""
    if result["status"] != 200:
        return {"status": result["status"], "matches_expected_sessions": False}
    got = set(result["dates"])
    return {"status": 200, "bars": len(result["dates"]), "expected_sessions": len(expected), "matches_expected_sessions": got == set(expected),
            "expected_but_absent": sorted(set(expected) - got)[:30], "present_but_unexpected": sorted(got - set(expected))[:30]}


def accepted_values(fetch, symbol, start, end, parameter, values, fixed):
    """For each value of one request parameter: the HTTP status and the number of bars returned."""
    out = {}
    for value in values:
        params = dict(symbols=symbol, timeframe="1Day", start=start, end=end, sort="asc", limit=100, currency="USD")
        params.update(fixed)
        params[parameter] = value
        status, payload = fetch(BARS_ENDPOINT, params)
        out[value] = {"status": status, "bars": len(_rows(payload, "bars", symbol)) if status == 200 else 0, "message": None if status == 200 else (payload or {}).get("message")}
    return out


def _year_windows(start, end):
    out, first = [], date.fromisoformat(start)
    while first <= date.fromisoformat(end):
        last = min(date(first.year, 12, 31), date.fromisoformat(end))
        out.append((first.isoformat(), last.isoformat()))
        first = last + timedelta(days=1)
    return out


def corporate_action_counts(fetch, symbol, start, end):
    """Counts of the corporate actions the provider lists for one symbol, by action type; no dates and no amounts are kept. A 400 for the whole window (the documentation states no limit on
    its length, but the pipeline has only used about two months) is retried by calendar year."""
    whole = _corporate_action_window(fetch, symbol, start, end)
    if whole["status"] != 400:
        return whole
    counts, pages = {}, 0
    for first, last in _year_windows(start, end):
        part = _corporate_action_window(fetch, symbol, first, last)
        pages += part["pages"]
        if part["status"] != 200:
            return dict(part, pages=pages, chunked_by_year_after_400=True, first_400_message=whole.get("message"))
        for kind, count in part["by_type"].items():
            counts[kind] = counts.get(kind, 0) + count
    return {"status": 200, "by_type": dict(sorted(counts.items())), "pages": pages, "chunked_by_year_after_400": True, "first_400_message": whole.get("message")}


def _corporate_action_window(fetch, symbol, start, end):
    counts, pages, token, seen = {}, 0, None, set()
    while True:
        params = dict(symbols=symbol, start=start, end=end, limit=100, sort="asc")
        if token is not None:
            params["page_token"] = token
        status, payload = fetch(ACTIONS_ENDPOINT, params)
        pages += 1
        if status != 200:
            return {"status": status, "message": (payload or {}).get("message"), "by_type": counts, "pages": pages}
        if not isinstance(payload, dict) or "next_page_token" not in payload:
            raise DataError("missing pagination metadata")
        actions = payload.get("corporate_actions") or {}
        if not isinstance(actions, dict):
            raise DataError("unexpected corporate_actions structure")
        for kind, items in actions.items():
            if not isinstance(items, list):
                raise DataError("unexpected corporate_actions structure")
            counts[kind] = counts.get(kind, 0) + len(items)
        token = payload["next_page_token"]
        if token is None:
            break
        if not isinstance(token, str) or not token or token in seen or pages >= MAX_PAGES:
            raise DataError("invalid, repeated or runaway pagination")
        seen.add(token)
    return {"status": 200, "by_type": dict(sorted(counts.items())), "pages": pages}


def candidate_dates(spec, root=ROOT):
    """ticker -> filing dates of the frozen candidate ledgers (earnings 8-K candidates; the ledgers hold no outcomes)."""
    guard, root = spec["event_day_guard"], Path(root)
    cohort = json.loads((root / guard["cohort"]).read_text(encoding="utf-8"))
    ticker_of = {issuer["cik"]: issuer["ticker"] for issuer in cohort["issuers"]}
    out = {}
    for ledger in guard["ledgers"]:
        for candidate in json.loads((root / ledger).read_text(encoding="utf-8"))["candidates"]:
            out.setdefault(ticker_of[candidate["cik"]], []).append(candidate["filing_date"])
    return out


def sample_pairs(spec, candidates):
    """The (symbol, session) pairs of the minute sample that stay away from candidate dates, and those skipped."""
    sample, guard = spec["checks"]["minute_sample"], spec["event_day_guard"]
    kept, skipped = [], []
    for symbol in sample["symbols"]:
        for session in sample["sessions"]:
            if session > guard["latest_allowed_sample_session"]:
                raise DataError("sample session after the latest allowed")
            near = [d for d in candidates.get(symbol, []) if abs((date.fromisoformat(d) - date.fromisoformat(session)).days) <= guard["exclude_within_calendar_days"]]
            (skipped if near else kept).append({"symbol": symbol, "session": session})
    return kept, skipped


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def minute_semantics(fetch, symbol, session, hours):
    """Minute-bar counts by part of the day, and unit-free ratios between the minute volume and the daily bar's volume. Per-bar values are summed into local totals and dropped."""
    day = date.fromisoformat(session)
    opened, closed = [datetime.combine(day, clock.fromisoformat(h), NEW_YORK) for h in hours]
    daily_status, daily_payload = fetch(BARS_ENDPOINT, dict(symbols=symbol, timeframe="1Day", start=session, end=(day + timedelta(days=1)).isoformat(), feed="sip", adjustment="raw",
                                                           currency="USD", sort="asc", limit=10))
    if daily_status != 200:
        return {"status": daily_status, "stage": "daily", "message": (daily_payload or {}).get("message")}
    daily = [row.get("v") for row in _rows(daily_payload, "bars", symbol) if _bar_date(row) == session]
    daily_volume = daily[0] if daily else None
    counts, volumes, pages, token, seen = {"premarket": 0, "regular": 0, "after_hours": 0}, {"premarket": 0, "regular": 0, "after_hours": 0}, 0, None, set()
    while True:
        params = dict(symbols=symbol, timeframe="1Min", start=opened.isoformat(), end=closed.isoformat(), feed="sip", adjustment="raw", currency="USD", sort="asc", limit=PAGE_LIMIT)
        if token is not None:
            params["page_token"] = token
        status, payload = fetch(BARS_ENDPOINT, params)
        pages += 1
        if status != 200:
            return {"status": status, "stage": "minute", "message": (payload or {}).get("message")}
        if not isinstance(payload, dict) or "next_page_token" not in payload:
            raise DataError("missing pagination metadata")
        for row in _rows(payload, "bars", symbol):
            if not isinstance(row, dict) or not isinstance(row.get("t"), str):
                raise DataError("malformed bar record")
            moment = datetime.fromisoformat(row["t"].replace("Z", "+00:00")).astimezone(NEW_YORK)
            part = "premarket" if moment.time() < clock(9, 30) else "regular" if moment.time() < clock(16, 0) else "after_hours"
            counts[part] += 1
            volumes[part] += row.get("v") or 0
        token = payload["next_page_token"]
        if token is None:
            break
        if not isinstance(token, str) or not token or token in seen or pages >= MAX_PAGES:
            raise DataError("invalid, repeated or runaway pagination")
        seen.add(token)
    everything = sum(volumes.values())
    return {"status": 200, "daily_bar_present": daily_volume is not None, "minute_bars": counts, "pages": pages,
            "daily_volume_over_regular_minute_volume": _ratio(daily_volume, volumes["regular"]) if daily_volume is not None else None,
            "daily_volume_over_all_hours_minute_volume": _ratio(daily_volume, everything) if daily_volume is not None else None,
            "premarket_share_of_all_hours_minute_volume": _ratio(volumes["premarket"], everything),
            "after_hours_share_of_all_hours_minute_volume": _ratio(volumes["after_hours"], everything)}


def mapping_effect(fetch, symbol, window, mapped):
    """The same daily-bar query with the provider's symbol mapping skipped, beside the default one: how many bars, and from when, come only from the mapping."""
    plain = daily_bar_dates(fetch, symbol, window["start"], window["end"], asof="-")
    if plain["status"] != 200 or mapped.get("status") != 200:
        return {"status_without_mapping": plain["status"], "status_with_default_mapping": mapped.get("status"), "message": plain["message"] or mapped.get("message")}
    first_mapped, first_plain = (mapped["dates"][0] if mapped["dates"] else None), (plain["dates"][0] if plain["dates"] else None)
    return {"status_without_mapping": 200, "bars_with_default_mapping": len(mapped["dates"]), "bars_without_mapping": len(plain["dates"]), "first_bar_date_with_default_mapping": first_mapped,
            "first_bar_date_without_mapping": first_plain, "bars_that_only_the_mapping_supplies": len(set(mapped["dates"]) - set(plain["dates"])),
            "mapping_changes_the_history": mapped["dates"] != plain["dates"]}


def _guarded(name, function, *args):
    """One check's failure is recorded and does not stop the others."""
    try:
        return function(*args)
    except DataError as exc:
        return {"error": "DATA_ERROR", "detail": str(exc), "check": name}
    except Exception as exc:  # the class name is code metadata, never response content or a credential
        return {"error": "UNCATEGORIZED_" + type(exc).__name__.upper(), "check": name}


def run(spec, fetch, retrieved_at, project_calendars=None, candidates=None, environ=None):
    environ = os.environ if environ is None else environ
    project_calendars = load_project_calendars(spec) if project_calendars is None else project_calendars
    candidates = candidate_dates(spec) if candidates is None else candidates
    window, checks = spec["window"], spec["checks"]
    expected = expected_sessions(spec, project_calendars)
    report = {"schema_version": 1, "kind": "m5_phase1a_probe_result", "complete": False, "spec_id": spec["id"], "spec_revision": spec["revision"], "spec_sha256": spec_digest(spec),
              "retrieved_at": retrieved_at, "github": {name: environ.get(name) for name in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW")},
              "window": {"start": window["start"], "end": window["end"], "expected_sessions": len(expected)}}
    series = {}
    for symbol in spec_symbols(spec):
        series[symbol] = _guarded("daily_bars " + symbol, daily_bar_dates, fetch, symbol, window["start"], window["end"])
    reference = spec["symbols"]["reference_calendar_symbol"]
    report["reference_calendar"] = _guarded("reference_calendar", reference_check, series[reference], expected) if "dates" in series[reference] else {"error": "reference series unavailable"}
    report["daily_bars"] = {symbol: (summarize_bars(result, expected, spec) if "status" in result else result) for symbol, result in series.items()}
    report["symbol_mapping"] = {symbol: _guarded("symbol_mapping " + symbol, mapping_effect, fetch, symbol, window, series[symbol]) for symbol in spec["symbols"]["issuers"]}
    adjustment, feeds = checks["adjustment_modes"], checks["feeds"]
    report["adjustment_modes"] = _guarded("adjustment_modes", accepted_values, fetch, adjustment["symbol"], adjustment["start"], adjustment["end"], "adjustment", adjustment["values"],
                                          {"feed": spec["transport"]["feed"]})
    report["feeds"] = _guarded("feeds", accepted_values, fetch, feeds["symbol"], feeds["start"], feeds["end"], "feed", feeds["values"], {"adjustment": spec["transport"]["adjustment"]})
    report["corporate_actions"] = {symbol: _guarded("corporate_actions " + symbol, corporate_action_counts, fetch, symbol, window["start"], window["end"]) for symbol in spec["symbols"]["issuers"]}
    kept, skipped = sample_pairs(spec, candidates)
    sample = checks["minute_sample"]
    report["minute_sample"] = {"hours_new_york": sample["hours_new_york"], "skipped_for_nearness_to_a_candidate_date": skipped,
                               "pairs": [dict(pair, **_guarded("minute_sample " + pair["symbol"] + " " + pair["session"], minute_semantics, fetch, pair["symbol"], pair["session"],
                                                                sample["hours_new_york"])) for pair in kept]}
    report["requests_made"] = getattr(fetch, "requests", None)
    report["checks_that_errored"] = count_errors(report)
    report["complete"] = True
    return report


def count_errors(node):
    """How many entries of the report are check failures (a dict with an 'error' key) rather than results."""
    if isinstance(node, dict):
        return (1 if "error" in node else 0) + sum(count_errors(value) for value in node.values())
    if isinstance(node, list):
        return sum(count_errors(item) for item in node)
    return 0


def contains_value_keys(node):
    """True if any key of the nested report is one that would carry a price or volume value."""
    if isinstance(node, dict):
        return any(key in VALUE_KEYS or contains_value_keys(value) for key, value in node.items())
    if isinstance(node, list):
        return any(contains_value_keys(item) for item in node)
    return False


def pack(report):
    """Canonical JSON, gzip with a fixed mtime, base64: (the canonical bytes, the base64 text)."""
    raw = canonical(report)
    return raw, base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode("ascii")


def annotation_lines(report, notice_chars=NOTICE_CHARS, max_parts=9):
    """Workflow-command notices carrying the packed report, then one digest notice. If the report is too large for max_parts, the long date samples are dropped first."""
    raw, packed = pack(report)
    if -(-len(packed) // notice_chars) > max_parts:
        slim = json.loads(raw)
        for node in list(slim.get("daily_bars", {}).values()):
            for key in ("missing_dates_first_20", "unexpected_dates_first_20"):
                node.pop(key, None)
        slim["trimmed_for_annotations"] = True
        raw, packed = pack(slim)
    parts = [packed[i:i + notice_chars] for i in range(0, len(packed), notice_chars)]
    if len(parts) > max_parts:
        raise DataError("report too large for annotations")
    lines = ["::notice title=%s part %d of %d::%s" % (NOTICE_TITLE, i + 1, len(parts), part) for i, part in enumerate(parts)]
    lines.append("::notice title=%s digest::sha256=%s bytes=%d parts=%d" % (NOTICE_TITLE, digest(raw), len(raw), len(parts)))
    return lines


def decode_annotations(items):
    """items: (title, message) pairs from the check-run annotations API, in any order. Returns the report dict, after checking the digest notice."""
    parts, digest_message = {}, None
    for title, message in items:
        match = re.fullmatch(NOTICE_TITLE + r" part (\d+) of (\d+)", title or "")
        if match:
            parts[int(match.group(1))] = (int(match.group(2)), message)
        elif title == NOTICE_TITLE + " digest":
            digest_message = message
    if not parts or digest_message is None:
        raise DataError("annotations are incomplete")
    total = {count for count, _ in parts.values()}
    if len(total) != 1 or sorted(parts) != list(range(1, total.pop() + 1)):
        raise DataError("annotation parts are missing")
    raw = gzip.decompress(base64.b64decode("".join(parts[i][1] for i in sorted(parts))))
    wanted = re.search(r"sha256=([0-9a-f]{64}) bytes=(\d+)", digest_message)
    if not wanted or wanted.group(1) != digest(raw) or int(wanted.group(2)) != len(raw):
        raise DataError("annotation digest mismatch")
    return json.loads(raw)


def main():
    key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    report = {"complete": False, "kind": "m5_phase1a_probe_result"}
    if not key or not secret:
        report["error"] = "MISSING_GITHUB_ACTIONS_SECRETS"
    else:
        try:
            spec = load_spec()
            fetch = Transport(key, secret, pacing=spec["transport"]["pacing_seconds"], budget=spec["transport"]["request_budget"])
            report = run(spec, fetch, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        except DataError as exc:
            report["error"] = "DATA_VALIDATION_FAILED: " + str(exc)
        except URLError:
            report["error"] = "NETWORK_ERROR"
        except Exception as exc:  # class name only: never response content or credentials
            report["error"] = "UNCATEGORIZED_" + type(exc).__name__.upper()
    print(json.dumps(report, sort_keys=True, indent=2))
    for line in annotation_lines(report):
        print(line)
    return 0 if report.get("complete") else 2


if __name__ == "__main__":
    sys.exit(main())
