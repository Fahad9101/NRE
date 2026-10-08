"""The Milestone 5 Phase 1a availability probe (nre/m5_phase1a_probe.py), its spec (config/m5-phase1a-probe-spec.json) and its workflow. Offline, against a deterministic stand-in for the provider
whose bars carry distinctive price and volume values, so the tests can show that none of them reaches the report."""
import ast
import base64
import contextlib
import copy
import io
import json
import os
import re
import unittest
from datetime import date, datetime, time as clock, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from nre import m5_phase1a_probe as probe
from nre.core import DataError, canonical, digest

ROOT = Path(__file__).resolve().parent.parent
SPEC = probe.load_spec()
CALENDARS = probe.load_project_calendars(SPEC)
NEW_YORK = ZoneInfo("America/New_York")
LEAK_PRICE, LEAK_VOLUME = 123.456789, 987654321      # carried by every fake bar; the report must never contain them
RATIO_KEYS = {"daily_volume_over_regular_minute_volume", "daily_volume_over_all_hours_minute_volume", "premarket_share_of_all_hours_minute_volume", "after_hours_share_of_all_hours_minute_volume"}
STAMP = "2026-10-08T17:00:00Z"


class FakeAlpaca:
    """A deterministic stand-in for the market-data API: the calls it receives are recorded, and its bars hold values on purpose."""

    def __init__(self, first_bar=None, missing=None, zero_volume=None, extra_dates=None, page_size=None, statuses=None, raises=None, actions=None, session_daily_volume=390000, pre_market=True,
                 pre_market_bar_volume=100, after_hours_bar_volume=50, no_mapping_first_bar=None, dated_actions=None, max_actions_span_days=None):
        self.pre_market_bar_volume, self.after_hours_bar_volume = pre_market_bar_volume, after_hours_bar_volume
        self.no_mapping_first_bar, self.dated_actions, self.max_actions_span_days = no_mapping_first_bar or {}, dated_actions or {}, max_actions_span_days
        self.expected = probe.expected_sessions(SPEC, CALENDARS)
        self.first_bar, self.missing, self.zero_volume, self.extra_dates = first_bar or {}, missing or {}, zero_volume or {}, extra_dates or {}
        self.page_size, self.statuses, self.raises, self.actions = page_size, statuses or {}, raises or set(), actions or {}
        self.session_daily_volume, self.pre_market = session_daily_volume, pre_market
        self.calls, self.requests = [], 0

    def __call__(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        self.requests += 1
        symbol = params["symbols"]
        if symbol in self.raises:
            raise RuntimeError("provider exploded for " + symbol)
        for key in ("feed", "adjustment", "timeframe"):
            if (key, params.get(key)) in self.statuses:
                return self.statuses[(key, params.get(key))], {"message": "not permitted on this plan"}
        if endpoint == probe.ACTIONS_ENDPOINT:
            return self._actions(symbol, params)
        return self._daily(symbol, params) if params["timeframe"] == "1Day" else self._minute(symbol, params)

    def _daily(self, symbol, params):
        start, end = params["start"][:10], params["end"][:10]
        single = (date.fromisoformat(end) - date.fromisoformat(start)).days <= 1
        days = sorted((set(self.expected) | set(self.extra_dates.get(symbol, ()))) - set(self.missing.get(symbol, ())))
        rows = []
        earliest = max(self.first_bar.get(symbol, "0000-00-00"), self.no_mapping_first_bar.get(symbol, "0000-00-00") if params.get("asof") == "-" else "0000-00-00")
        for day in days:
            if not start <= day <= end or day < earliest:
                continue
            volume = 0 if day in self.zero_volume.get(symbol, ()) else (self.session_daily_volume if single else LEAK_VOLUME)
            rows.append({"t": day + "T04:00:00Z", "o": LEAK_PRICE, "h": LEAK_PRICE + 1, "l": LEAK_PRICE - 1, "c": LEAK_PRICE, "v": volume, "n": 777, "vw": LEAK_PRICE})
        if not rows:
            return 200, {"bars": {}, "next_page_token": None}
        offset = int(params.get("page_token") or 0)
        size = self.page_size or len(rows)
        return 200, {"bars": {symbol: rows[offset:offset + size]}, "next_page_token": str(offset + size) if offset + size < len(rows) else None}

    def _minute(self, symbol, params):
        day = datetime.fromisoformat(params["start"]).date()
        plan = ([(4, m, self.pre_market_bar_volume) for m in range(10)] if self.pre_market else []) + [(9, 30 + m, 1000) for m in range(30)] + [(h, m, 1000) for h in range(10, 16) for m in range(60)] \
            + [(16, m, self.after_hours_bar_volume) for m in range(5)]
        rows = [{"t": datetime.combine(day, clock(h, m), NEW_YORK).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": LEAK_PRICE, "h": LEAK_PRICE, "l": LEAK_PRICE,
                 "c": LEAK_PRICE, "v": volume, "n": 777} for h, m, volume in plan]
        return 200, {"bars": {symbol: rows}, "next_page_token": None}

    def _actions(self, symbol, params):
        if self.max_actions_span_days is not None and (date.fromisoformat(params["end"]) - date.fromisoformat(params["start"])).days > self.max_actions_span_days:
            return 400, {"message": "the requested range is too long"}
        if symbol in self.dated_actions:                                                                  # actions on dates: only those inside the requested window are returned
            page = {}
            for day, kind in sorted(self.dated_actions[symbol].items()):
                if params["start"] <= day <= params["end"]:
                    page.setdefault(kind, []).append({"id": kind + "-" + day, "ex_date": day, "rate": LEAK_PRICE})
            return 200, {"corporate_actions": page, "next_page_token": None}
        pages = self.actions.get(symbol, [{}])
        index = int(params.get("page_token") or 0)
        page = {kind: [{"id": "%s-%d" % (kind, i), "ex_date": "2024-02-01", "rate": LEAK_PRICE} for i in range(count)] for kind, count in pages[index].items()}
        return 200, {"corporate_actions": page, "next_page_token": str(index + 1) if index + 1 < len(pages) else None}


def run_fake(**kwargs):
    fake = FakeAlpaca(**kwargs)
    return probe.run(SPEC, fake, STAMP, project_calendars=CALENDARS, candidates=probe.candidate_dates(SPEC), environ={"GITHUB_RUN_ID": "42", "GITHUB_SHA": "abc123"}), fake


def leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from leaves(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from leaves(value, path + (index,))
    else:
        yield path, node


class SpecTests(unittest.TestCase):
    def test_the_symbols_are_unique_and_the_issuers_are_the_cohorts(self):
        symbols = probe.spec_symbols(SPEC)
        self.assertEqual(len(symbols), 13 + 15 + 23)
        self.assertEqual(len(set(symbols)), len(symbols))
        cohort = json.loads((ROOT / SPEC["symbols"]["issuers_from"]).read_text(encoding="utf-8"))
        self.assertEqual(sorted(SPEC["symbols"]["issuers"]), sorted(issuer["ticker"] for issuer in cohort["issuers"]))
        self.assertEqual(SPEC["symbols"]["reference_calendar_symbol"], "SPY")
        self.assertIn("SPY", symbols)
        self.assertEqual(SPEC["symbols"]["issuers"], sorted(SPEC["symbols"]["issuers"]))

    def test_the_window_covers_the_milestone_4_span_with_contiguous_periods_and_enough_lookback(self):
        window = SPEC["window"]
        blocks = json.loads((ROOT / "config" / "m4-protocol.json").read_text(encoding="utf-8"))["blocks_and_folds"]["expected_blocks"]["first_and_last_reaction_session"]
        self.assertEqual(window["first_reaction_session"], blocks[0][0])
        self.assertEqual(window["periods"]["study_span"], [blocks[0][0], blocks[-1][1]])
        lookback, study, fresh = (window["periods"][name] for name in ("lookback", "study_span", "fresh"))
        self.assertEqual((lookback[0], fresh[1]), (window["start"], window["end"]))
        self.assertEqual(date.fromisoformat(lookback[1]) + timedelta(days=1), date.fromisoformat(study[0]))
        self.assertEqual(date.fromisoformat(study[1]) + timedelta(days=1), date.fromisoformat(fresh[0]))
        expected = probe.expected_sessions(SPEC, CALENDARS)
        self.assertGreaterEqual(sum(1 for day in expected if day < window["first_reaction_session"]), window["lookback_sessions_needed"])
        self.assertEqual(window["lookback_sessions_needed"], 252)

    def test_the_minute_sample_stays_in_2025_on_ordinary_sessions_and_the_budget_covers_the_plan(self):
        sample, guard = SPEC["checks"]["minute_sample"], SPEC["event_day_guard"]
        expected = set(probe.expected_sessions(SPEC, CALENDARS))
        for session in sample["sessions"]:
            self.assertIn(session, expected)
            self.assertLessEqual(session, guard["latest_allowed_sample_session"])
            self.assertEqual(date.fromisoformat(session).weekday(), 2)                               # a Wednesday, mid-week
        self.assertLess(guard["latest_allowed_sample_session"], "2026-01-22")                         # before Milestone 1's first reaction session, which the ledgers do not list
        self.assertTrue(set(sample["symbols"]) <= set(probe.spec_symbols(SPEC)))
        planned = len(probe.spec_symbols(SPEC)) + len(SPEC["checks"]["adjustment_modes"]["values"]) + len(SPEC["checks"]["feeds"]["values"]) + 2 * len(SPEC["symbols"]["issuers"]) \
            + 2 * len(sample["symbols"]) * len(sample["sessions"])                                       # daily bars, the two comparisons, the symbol-mapping query and the actions, and the minute sample
        self.assertGreaterEqual(SPEC["transport"]["request_budget"], int(planned * 1.5))
        self.assertEqual(SPEC["transport"]["bars_endpoint"], probe.BARS_ENDPOINT)
        self.assertEqual(SPEC["transport"]["corporate_actions_endpoint"], probe.ACTIONS_ENDPOINT)
        self.assertEqual((SPEC["transport"]["feed"], SPEC["transport"]["adjustment"]), ("sip", "raw"))

    def test_the_spec_says_what_it_keeps_and_what_it_does_not(self):
        self.assertIn("keeps no price and no volume value", SPEC["purpose"])
        self.assertIn("adds nothing to the dataset", SPEC["purpose"])
        self.assertIn("VIXY and VXX are listed as futures-based proxies", SPEC["symbols"]["not_requested"])
        self.assertEqual(SPEC["authority"]["authorization"], "reports/m5-phase1a-authorization-2026-10-08.json")
        self.assertTrue((ROOT / SPEC["authority"]["authorization"]).is_file())


class CalendarTests(unittest.TestCase):
    def test_expected_sessions_follow_the_reviewed_calendars_and_the_listed_holidays(self):
        expected = probe.expected_sessions(SPEC, CALENDARS)
        by_year = {year: [d for d in expected if d.startswith(year)] for year in ("2023", "2024", "2025", "2026")}
        self.assertEqual(len(by_year["2024"]), 252)                                                  # 262 weekdays less 10 holidays
        self.assertEqual(len(by_year["2025"]), 250)                                                  # the reviewed 2025 calendar, with the January 9 closure
        self.assertEqual(by_year["2025"], sorted(CALENDARS["2025"]))
        self.assertEqual(by_year["2026"], sorted(d for d in CALENDARS["2026"] if d <= "2026-10-02"))
        self.assertEqual((expected[0], expected[-1]), ("2023-10-02", "2026-10-02"))
        for closed in ("2023-11-23", "2023-12-25", "2024-03-29", "2024-12-25", "2025-01-09", "2025-04-18", "2026-04-03", "2024-06-01"):
            self.assertNotIn(closed, expected)
        for open_day in ("2024-11-29", "2024-12-24", "2025-07-03"):                                   # early closes are sessions
            self.assertIn(open_day, expected)
        self.assertEqual(len(expected), len(set(expected)))
        self.assertEqual(expected, sorted(expected))

    def test_a_year_without_a_calendar_is_refused(self):
        spec = copy.deepcopy(SPEC)
        spec["window"]["end"] = "2027-01-04"
        with self.assertRaises(DataError):
            probe.expected_sessions(spec, CALENDARS)


class DailyBarTests(unittest.TestCase):
    def test_only_dates_and_a_zero_volume_count_come_out_of_the_bars(self):
        fake = FakeAlpaca(zero_volume={"NBIX": {"2025-02-03", "2025-02-04"}})
        result = probe.daily_bar_dates(fake, "NBIX", "2023-10-02", "2026-10-02")
        self.assertEqual((result["status"], result["zero_volume"], result["pages"]), (200, 2, 1))
        self.assertEqual(result["dates"], probe.expected_sessions(SPEC, CALENDARS))
        self.assertEqual(set(result), {"status", "dates", "zero_volume", "pages", "message"})
        self.assertNotIn(str(LEAK_VOLUME), json.dumps(result))
        self.assertNotIn("123.456789", json.dumps(result))

    def test_the_request_is_the_pipelines_own_with_no_asof_and_a_page_limit(self):
        fake = FakeAlpaca()
        probe.daily_bar_dates(fake, "CACI", "2023-10-02", "2026-10-02")
        endpoint, params = fake.calls[0]
        self.assertEqual(endpoint, probe.BARS_ENDPOINT)
        self.assertEqual(params, dict(symbols="CACI", timeframe="1Day", start="2023-10-02", end="2026-10-02", feed="sip", adjustment="raw", currency="USD", sort="asc", limit=10000))

    def test_pages_are_followed_and_a_runaway_or_repeated_token_is_refused(self):
        paged = FakeAlpaca(page_size=100)
        result = probe.daily_bar_dates(paged, "CACI", "2023-10-02", "2026-10-02")
        self.assertEqual((result["pages"], len(result["dates"])), (8, len(probe.expected_sessions(SPEC, CALENDARS))))
        self.assertEqual([call[1].get("page_token") for call in paged.calls], [None] + [str(100 * i) for i in range(1, 8)])
        with self.assertRaises(DataError):                                                           # more pages than the cap
            probe.daily_bar_dates(FakeAlpaca(page_size=60), "CACI", "2023-10-02", "2026-10-02")

        asked = []

        def repeating(endpoint, params):
            asked.append(params.get("page_token"))
            return 200, {"bars": {"X": [{"t": "2024-01-02T05:00:00Z", "v": 1}]}, "next_page_token": "same"}
        with self.assertRaises(DataError):
            probe.daily_bar_dates(repeating, "X", "2024-01-01", "2024-01-31")
        self.assertEqual(asked, [None, "same"])                                                      # stopped at the first repeat, not at the page cap

    def test_malformed_answers_are_refused_and_a_failure_status_is_a_result(self):
        with self.assertRaises(DataError):
            probe.daily_bar_dates(lambda e, p: (200, {"bars": {"X": []}}), "X", "2024-01-01", "2024-01-31")                          # no pagination metadata
        with self.assertRaises(DataError):
            probe.daily_bar_dates(lambda e, p: (200, {"bars": {"X": [{"o": 1}]}, "next_page_token": None}), "X", "2024-01-01", "2024-01-31")
        with self.assertRaises(DataError):
            probe.daily_bar_dates(lambda e, p: (200, {"bars": {"X": [{"t": "garbage"}]}, "next_page_token": None}), "X", "2024-01-01", "2024-01-31")
        with self.assertRaises(DataError):                                                           # not strictly ascending
            rows = [{"t": "2024-01-03T05:00:00Z", "v": 1}, {"t": "2024-01-02T05:00:00Z", "v": 1}]
            probe.daily_bar_dates(lambda e, p: (200, {"bars": {"X": rows}, "next_page_token": None}), "X", "2024-01-01", "2024-01-31")
        failed = probe.daily_bar_dates(lambda e, p: (403, {"message": "denied"}), "X", "2024-01-01", "2024-01-31")
        self.assertEqual((failed["status"], failed["dates"], failed["message"]), (403, [], "denied"))
        empty = probe.daily_bar_dates(lambda e, p: (200, {"bars": {}, "next_page_token": None}), "X", "2024-01-01", "2024-01-31")
        self.assertEqual((empty["status"], empty["dates"]), (200, []))

    def test_the_summary_is_computed_by_hand_for_a_small_case(self):
        spec = {"window": {"periods": {"a": ["2024-01-01", "2024-01-31"], "b": ["2024-02-01", "2024-02-29"]}, "first_reaction_session": "2024-02-01", "lookback_sessions_needed": 3}}
        expected = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-02-01", "2024-02-02"]
        result = {"status": 200, "dates": ["2024-01-03", "2024-01-04", "2024-02-02", "2024-03-01"], "zero_volume": 1, "pages": 1, "message": None}
        summary = probe.summarize_bars(result, expected, spec)
        self.assertEqual((summary["bars"], summary["first_bar_date"], summary["last_bar_date"]), (4, "2024-01-03", "2024-03-01"))
        self.assertEqual(summary["expected_sessions_from_first_bar"], 4)                              # 01-02 precedes the first bar and is not counted
        self.assertEqual((summary["missing_sessions"], summary["missing_dates_first_20"]), (1, ["2024-02-01"]))
        self.assertEqual(summary["missing_by_period"], {"a": 0, "b": 1})
        self.assertEqual(summary["bars_by_period"], {"a": 2, "b": 1})                                 # 03-01 is in no period
        self.assertEqual((summary["bars_on_unexpected_dates"], summary["unexpected_dates_first_20"]), (1, ["2024-03-01"]))
        self.assertEqual((summary["zero_volume_bars"], summary["bars_before_first_reaction_session"], summary["has_required_lookback"]), (1, 2, False))
        on_boundary = dict(result, dates=["2024-01-03", "2024-02-01"])
        self.assertEqual(probe.summarize_bars(on_boundary, expected, spec)["bars_before_first_reaction_session"], 1)           # a bar on the first reaction session is not lookback
        exactly_enough = dict(result, dates=["2024-01-02", "2024-01-03", "2024-01-04", "2024-02-01"])
        self.assertEqual(probe.summarize_bars(exactly_enough, expected, spec)["bars_before_first_reaction_session"], 3)
        self.assertTrue(probe.summarize_bars(exactly_enough, expected, spec)["has_required_lookback"])                         # three needed, three present
        self.assertEqual(probe.summarize_bars(dict(result, status=403, message="denied"), expected, spec), {"status": 403, "message": "denied", "bars": 0})
        self.assertEqual(probe.summarize_bars({"status": 200, "dates": [], "zero_volume": 0, "pages": 1, "message": None}, expected, spec)["first_bar_date"], None)

    def test_the_reference_series_is_compared_with_the_expected_sessions_and_differences_are_listed(self):
        expected = probe.expected_sessions(SPEC, CALENDARS)
        same = probe.reference_check({"status": 200, "dates": list(expected)}, expected)
        self.assertEqual((same["matches_expected_sessions"], same["expected_but_absent"], same["present_but_unexpected"]), (True, [], []))
        changed = [d for d in expected if d != "2024-06-03"] + ["2024-12-25"]
        different = probe.reference_check({"status": 200, "dates": sorted(changed)}, expected)
        self.assertEqual((different["matches_expected_sessions"], different["expected_but_absent"], different["present_but_unexpected"]), (False, ["2024-06-03"], ["2024-12-25"]))
        self.assertEqual(probe.reference_check({"status": 403}, expected), {"status": 403, "matches_expected_sessions": False})


class OtherCheckTests(unittest.TestCase):
    def test_accepted_values_record_status_and_bar_count_for_each_value(self):
        fake = FakeAlpaca(statuses={("feed", "iex"): 403})
        feeds = probe.accepted_values(fake, "SPY", "2025-06-02", "2025-06-06", "feed", ["sip", "iex"], {"adjustment": "raw"})
        self.assertEqual(feeds["sip"], {"status": 200, "bars": 5, "message": None})
        self.assertEqual(feeds["iex"], {"status": 403, "bars": 0, "message": "not permitted on this plan"})
        modes = probe.accepted_values(fake, "SPY", "2025-06-02", "2025-06-06", "adjustment", ["raw", "split", "dividend", "all"], {"feed": "sip"})
        self.assertEqual({value: result["status"] for value, result in modes.items()}, {"raw": 200, "split": 200, "dividend": 200, "all": 200})
        self.assertEqual([call[1]["adjustment"] for call in fake.calls[2:]], ["raw", "split", "dividend", "all"])

    def test_corporate_actions_are_counted_by_type_across_pages_without_dates_or_amounts(self):
        fake = FakeAlpaca(actions={"TECX": [{"cash_dividends": 2, "name_changes": 1}, {"cash_dividends": 1, "forward_splits": 1}]})
        result = probe.corporate_action_counts(fake, "TECX", "2023-10-02", "2026-10-02")
        self.assertEqual(result, {"status": 200, "by_type": {"cash_dividends": 3, "forward_splits": 1, "name_changes": 1}, "pages": 2})
        self.assertNotIn("2024-02-01", json.dumps(result))
        self.assertEqual(fake.calls[0][1], dict(symbols="TECX", start="2023-10-02", end="2026-10-02", limit=100, sort="asc"))
        self.assertEqual(probe.corporate_action_counts(FakeAlpaca(), "NBIX", "2023-10-02", "2026-10-02"), {"status": 200, "by_type": {}, "pages": 1})
        denied = probe.corporate_action_counts(FakeAlpaca(statuses={("feed", None): 403}), "NBIX", "2023-10-02", "2026-10-02")
        self.assertEqual(denied["status"], 403)
        with self.assertRaises(DataError):
            probe.corporate_action_counts(lambda e, p: (200, {"corporate_actions": []}), "NBIX", "2023-10-02", "2026-10-02")

    def test_the_minute_semantics_are_ratios_checked_by_hand(self):
        result = probe.minute_semantics(FakeAlpaca(), "SPY", "2025-03-12", ["04:00", "20:00"])
        regular, pre, after = 390 * 1000, 10 * 100, 5 * 50
        self.assertEqual(result["minute_bars"], {"premarket": 10, "regular": 390, "after_hours": 5})
        self.assertEqual(result["daily_volume_over_regular_minute_volume"], 1.0)                      # the fake's daily volume is the regular-session total
        self.assertEqual(result["daily_volume_over_all_hours_minute_volume"], round(regular / (regular + pre + after), 4))
        self.assertEqual(result["premarket_share_of_all_hours_minute_volume"], round(pre / (regular + pre + after), 4))
        self.assertEqual(result["after_hours_share_of_all_hours_minute_volume"], round(after / (regular + pre + after), 4))
        self.assertEqual((result["status"], result["daily_bar_present"]), (200, True))
        heavy = probe.minute_semantics(FakeAlpaca(pre_market_bar_volume=40000, after_hours_bar_volume=20000), "SPY", "2025-03-12", ["04:00", "20:00"])      # shares large enough to tell the denominators apart
        pre, after = 10 * 40000, 5 * 20000
        everything = regular + pre + after
        self.assertEqual(heavy["premarket_share_of_all_hours_minute_volume"], round(pre / everything, 4))
        self.assertEqual(heavy["after_hours_share_of_all_hours_minute_volume"], round(after / everything, 4))
        self.assertEqual(heavy["daily_volume_over_all_hours_minute_volume"], round(regular / everything, 4))
        self.assertNotEqual(heavy["premarket_share_of_all_hours_minute_volume"], round(pre / regular, 4))
        none = probe.minute_semantics(FakeAlpaca(pre_market=False), "SPY", "2025-03-12", ["04:00", "20:00"])
        self.assertEqual((none["minute_bars"]["premarket"], none["premarket_share_of_all_hours_minute_volume"]), (0, 0.0))
        failed = probe.minute_semantics(FakeAlpaca(statuses={("timeframe", "1Min"): 403}), "SPY", "2025-03-12", ["04:00", "20:00"])
        self.assertEqual((failed["status"], failed["stage"]), (403, "minute"))
        no_bar = probe.minute_semantics(FakeAlpaca(missing={"SPY": {"2025-03-12"}}), "SPY", "2025-03-12", ["04:00", "20:00"])
        self.assertEqual((no_bar["daily_bar_present"], no_bar["daily_volume_over_regular_minute_volume"]), (False, None))

    def test_the_minute_request_spans_the_hours_in_new_york_time_with_the_offset_in_force(self):
        fake = FakeAlpaca()
        probe.minute_semantics(fake, "SPY", "2025-03-12", ["04:00", "20:00"])                        # after the March 9 change to daylight time
        probe.minute_semantics(fake, "SPY", "2025-12-10", ["04:00", "20:00"])
        minute = [params for _, params in fake.calls if params["timeframe"] == "1Min"]
        self.assertEqual([(p["start"], p["end"]) for p in minute], [("2025-03-12T04:00:00-04:00", "2025-03-12T20:00:00-04:00"), ("2025-12-10T04:00:00-05:00", "2025-12-10T20:00:00-05:00")])
        self.assertTrue(all(p["feed"] == "sip" and p["adjustment"] == "raw" for p in minute))


class GuardTests(unittest.TestCase):
    def test_candidate_dates_come_from_the_ledgers_and_the_guard_skips_pairs_near_them(self):
        candidates = probe.candidate_dates(SPEC)
        ledger_rows = [c for name in SPEC["event_day_guard"]["ledgers"] for c in json.loads((ROOT / name).read_text(encoding="utf-8"))["candidates"]]
        self.assertEqual(sum(len(v) for v in candidates.values()), len(ledger_rows))
        self.assertEqual(sorted(candidates), sorted(SPEC["symbols"]["issuers"]))
        kept, skipped = probe.sample_pairs(SPEC, candidates)
        self.assertEqual(len(kept) + len(skipped), len(SPEC["checks"]["minute_sample"]["symbols"]) * len(SPEC["checks"]["minute_sample"]["sessions"]))
        def near(symbol, session):
            return any(abs((date.fromisoformat(d) - date.fromisoformat(session)).days) <= 5 for d in candidates.get(symbol, []))
        for pair in kept:
            self.assertFalse(near(pair["symbol"], pair["session"]), pair)
        for pair in skipped:
            self.assertTrue(near(pair["symbol"], pair["session"]), pair)
        self.assertEqual([p for p in skipped if p["symbol"] in ("SPY", "XBI")], [])                   # ETFs have no earnings

    def test_a_candidate_inside_the_distance_skips_the_pair_and_one_outside_does_not(self):
        spec = copy.deepcopy(SPEC)
        spec["checks"]["minute_sample"].update(symbols=["AAA"], sessions=["2025-03-12", "2025-06-11"])
        kept, skipped = probe.sample_pairs(spec, {"AAA": ["2025-03-17"]})                              # 5 days after the first session, 98 days before the second
        self.assertEqual((kept, skipped), ([{"symbol": "AAA", "session": "2025-06-11"}], [{"symbol": "AAA", "session": "2025-03-12"}]))
        kept, skipped = probe.sample_pairs(spec, {"AAA": ["2025-03-18"]})                              # 6 days: outside
        self.assertEqual(skipped, [])

    def test_a_sample_session_after_the_latest_allowed_is_refused(self):
        spec = copy.deepcopy(SPEC)
        spec["checks"]["minute_sample"]["sessions"] = ["2026-02-11"]
        with self.assertRaises(DataError):
            probe.sample_pairs(spec, {})


class TransportTests(unittest.TestCase):
    class Response:
        def __init__(self, body, status=200):
            self.body, self.status = body, status

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, limit=None):
            return self.body if limit is None else self.body[:limit]

    class Opener:
        def __init__(self, answers):
            self.answers, self.requests = list(answers), []

        def open(self, request, timeout=None):
            self.requests.append((request, timeout))
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

    def failure(self, code, body=b'{"message": "denied"}'):
        return HTTPError("https://data.alpaca.markets/v2/stocks/bars", code, "x", {}, io.BytesIO(body))

    def test_a_request_is_a_get_with_the_credentials_in_headers_only(self):
        opener = self.Opener([self.Response(b'{"bars": {}, "next_page_token": null}')])
        slept = []
        transport = probe.Transport("KEYKEY123", "SECRETSECRET456", pacing=0.35, budget=5, sleep=slept.append, opener=opener)
        status, body = transport(probe.BARS_ENDPOINT, {"symbols": "SPY", "limit": 10})
        self.assertEqual((status, body, slept, transport.requests), (200, {"bars": {}, "next_page_token": None}, [0.35], 1))
        request, timeout = opener.requests[0]
        self.assertEqual((request.get_method(), timeout), ("GET", 30))
        self.assertEqual(request.full_url, probe.BARS_ENDPOINT + "?symbols=SPY&limit=10")
        self.assertNotIn("KEYKEY123", request.full_url)
        self.assertEqual({k.lower(): v for k, v in request.header_items()}, {"apca-api-key-id": "KEYKEY123", "apca-api-secret-key": "SECRETSECRET456"})
        self.assertNotIn("KEYKEY123", repr(body))

    def test_a_failure_is_a_result_with_a_short_message_and_a_429_is_retried_with_a_pause(self):
        opener = self.Opener([self.failure(429), self.Response(b'{"ok": 1}')])
        slept = []
        transport = probe.Transport("k", "s", pacing=0.1, budget=9, sleep=slept.append, opener=opener)
        self.assertEqual(transport(probe.BARS_ENDPOINT, {}), (200, {"ok": 1}))
        self.assertEqual(slept, [0.1, 5, 0.1])
        long_message = b'{"message": "' + b"x" * 500 + b'"}'
        opener = self.Opener([self.failure(403, long_message)])
        status, body = probe.Transport("k", "s", sleep=lambda s: None, opener=opener)(probe.BARS_ENDPOINT, {})
        self.assertEqual((status, len(body["message"])), (403, probe.MESSAGE_CHARS))
        opener = self.Opener([self.failure(500, b"not json")])
        self.assertEqual(probe.Transport("k", "s", sleep=lambda s: None, opener=opener)(probe.BARS_ENDPOINT, {}), (500, {"message": None}))

    def test_four_rate_limited_answers_in_a_row_end_as_a_429_result(self):
        opener = self.Opener([self.failure(429)] * 4)
        status, body = probe.Transport("k", "s", budget=9, sleep=lambda s: None, opener=opener)(probe.BARS_ENDPOINT, {})
        self.assertEqual((status, len(opener.requests)), (429, 4))

    def test_the_budget_and_the_endpoint_allowlist_are_enforced(self):
        transport = probe.Transport("k", "s", budget=2, sleep=lambda s: None, opener=self.Opener([self.Response(b"{}")] * 5))
        transport(probe.BARS_ENDPOINT, {})
        transport(probe.ACTIONS_ENDPOINT, {})
        with self.assertRaises(DataError):
            transport(probe.BARS_ENDPOINT, {})
        with self.assertRaises(DataError):
            probe.Transport("k", "s", sleep=lambda s: None, opener=self.Opener([]))("https://data.alpaca.markets/v2/account", {})
        with self.assertRaises(DataError):
            probe.Transport("k", "s", sleep=lambda s: None, opener=self.Opener([]))("https://evil.example/v2/stocks/bars", {})

    def test_a_redirect_is_rejected_and_an_oversized_answer_is_refused(self):
        with self.assertRaises(DataError):
            probe.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example/")
        transport = probe.Transport("k", "s", sleep=lambda s: None, opener=self.Opener([self.Response(b"x" * 2_000_001)]))
        with self.assertRaises(DataError):
            transport(probe.BARS_ENDPOINT, {})


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.fake = run_fake()

    def test_the_report_covers_every_symbol_and_check_and_names_its_spec(self):
        report = self.report
        self.assertTrue(report["complete"])
        self.assertEqual((report["spec_id"], report["spec_revision"], report["spec_sha256"]), (SPEC["id"], 1, digest(canonical(SPEC))))
        self.assertEqual(report["github"], {"GITHUB_SHA": "abc123", "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": None, "GITHUB_WORKFLOW": None})
        self.assertEqual(sorted(report["daily_bars"]), sorted(probe.spec_symbols(SPEC)))
        self.assertEqual(sorted(report["corporate_actions"]), sorted(SPEC["symbols"]["issuers"]))
        self.assertTrue(report["reference_calendar"]["matches_expected_sessions"])
        self.assertEqual(report["checks_that_errored"], 0)
        self.assertEqual(report["window"]["expected_sessions"], len(probe.expected_sessions(SPEC, CALENDARS)))
        for symbol, summary in report["daily_bars"].items():
            self.assertEqual((summary["missing_sessions"], summary["has_required_lookback"], summary["first_bar_date"]), (0, True, "2023-10-02"), symbol)
        self.assertEqual(sorted(report["adjustment_modes"]), sorted(SPEC["checks"]["adjustment_modes"]["values"]))
        self.assertEqual(sorted(report["feeds"]), sorted(SPEC["checks"]["feeds"]["values"]))
        self.assertTrue(all(result["status"] == 200 for result in list(report["adjustment_modes"].values()) + list(report["feeds"].values())))
        self.assertEqual(sorted(report["symbol_mapping"]), sorted(SPEC["symbols"]["issuers"]))
        for issuer, mapping in report["symbol_mapping"].items():
            self.assertEqual((mapping["mapping_changes_the_history"], mapping["bars_that_only_the_mapping_supplies"]), (False, 0), issuer)

    def test_it_makes_only_get_requests_to_the_two_endpoints_within_budget_with_the_specs_parameters(self):
        window, transport = SPEC["window"], SPEC["transport"]
        self.assertLessEqual(self.fake.requests, transport["request_budget"])
        self.assertEqual(self.report["requests_made"], self.fake.requests)
        for endpoint, params in self.fake.calls:
            self.assertIn(endpoint, probe.ALLOWED_ENDPOINTS)
            self.assertIn(params.get("asof"), (None, "-"))                                                # the default mapping, or the mapping skipped; never a date
            if endpoint == probe.BARS_ENDPOINT and params["timeframe"] == "1Day" and params["limit"] == probe.PAGE_LIMIT and params["end"] == window["end"]:
                self.assertEqual((params["start"], params["feed"], params["adjustment"]), (window["start"], transport["feed"], transport["adjustment"]))
        daily = [p for e, p in self.fake.calls if e == probe.BARS_ENDPOINT and p["start"] == window["start"] and p["end"] == window["end"]]
        self.assertEqual(sorted(p["symbols"] for p in daily if "asof" not in p), sorted(probe.spec_symbols(SPEC)))
        self.assertEqual(sorted(p["symbols"] for p in daily if p.get("asof") == "-"), sorted(SPEC["symbols"]["issuers"]))        # the second query, for the issuers only
        actions = [p for e, p in self.fake.calls if e == probe.ACTIONS_ENDPOINT]
        self.assertEqual(sorted(p["symbols"] for p in actions), sorted(SPEC["symbols"]["issuers"]))
        week = SPEC["checks"]["feeds"]
        self.assertEqual((week["start"], week["end"]), (SPEC["checks"]["adjustment_modes"]["start"], SPEC["checks"]["adjustment_modes"]["end"]))
        compared = [p for e, p in self.fake.calls if p.get("start") == week["start"] and p.get("end") == week["end"]]
        self.assertEqual([(p["feed"], p["adjustment"]) for p in compared],                                # the adjustment comparison holds the feed at sip; the feed comparison holds the adjustment at raw
                         [("sip", "raw"), ("sip", "split"), ("sip", "dividend"), ("sip", "spin-off"), ("sip", "all"), ("sip", "raw"), ("iex", "raw"), ("boats", "raw"), ("otc", "raw")])

    def test_the_minute_sample_uses_only_the_pairs_the_guard_keeps(self):
        kept, skipped = probe.sample_pairs(SPEC, probe.candidate_dates(SPEC))
        self.assertEqual([(p["symbol"], p["session"]) for p in self.report["minute_sample"]["pairs"]], [(p["symbol"], p["session"]) for p in kept])
        self.assertEqual(self.report["minute_sample"]["skipped_for_nearness_to_a_candidate_date"], skipped)
        requested = {(p["symbols"], p["start"][:10]) for e, p in self.fake.calls if p.get("timeframe") == "1Min"}
        self.assertEqual(requested, {(p["symbol"], p["session"]) for p in kept})
        self.assertEqual(self.report["minute_sample"]["hours_new_york"], ["04:00", "20:00"])
        for _, params in [call for call in self.fake.calls if call[1].get("timeframe") == "1Min"]:
            self.assertEqual((params["start"][11:16], params["end"][11:16]), ("04:00", "20:00"))
        self.assertGreater(len(skipped), 0)
        for pair in self.report["minute_sample"]["pairs"]:
            self.assertEqual(pair["minute_bars"], {"premarket": 10, "regular": 390, "after_hours": 5})

    def test_no_price_or_volume_value_reaches_the_report(self):
        text = canonical(self.report).decode("utf-8")
        for leaked in (str(LEAK_VOLUME), "123.456789", "124.456789", "122.456789", "390000"):
            self.assertNotIn(leaked, text)
        self.assertFalse(probe.contains_value_keys(self.report))
        for path, value in leaves(self.report):
            if isinstance(value, float):
                self.assertIn(path[-1], RATIO_KEYS, path)
        ratios = [value for path, value in leaves(self.report) if path[-1] in RATIO_KEYS and value is not None]
        self.assertTrue(ratios and all(0 <= r <= 1.5 for r in ratios))

    def test_the_probe_notices_what_is_unusual_zero_volume_gaps_a_late_first_bar_extra_dates_and_actions(self):
        report, _ = run_fake(first_bar={"TECX": "2024-06-03"}, missing={"CACI": {"2025-03-03", "2026-05-04"}}, zero_volume={"NBIX": {"2025-02-03"}}, extra_dates={"XLC": ["2024-12-25"]},
                             actions={"TECX": [{"name_changes": 1, "cash_dividends": 2}]}, statuses={("feed", "iex"): 403})
        bars = report["daily_bars"]
        self.assertEqual((bars["TECX"]["first_bar_date"], bars["TECX"]["has_required_lookback"], bars["TECX"]["missing_sessions"]), ("2024-06-03", False, 0))
        self.assertLess(bars["TECX"]["bars_before_first_reaction_session"], 252)
        self.assertEqual((bars["CACI"]["missing_sessions"], bars["CACI"]["missing_by_period"]), (2, {"lookback": 0, "study_span": 1, "fresh": 1}))
        self.assertEqual(bars["CACI"]["missing_dates_first_20"], ["2025-03-03", "2026-05-04"])
        self.assertEqual(bars["NBIX"]["zero_volume_bars"], 1)
        self.assertEqual((bars["XLC"]["bars_on_unexpected_dates"], bars["XLC"]["unexpected_dates_first_20"]), (1, ["2024-12-25"]))
        self.assertEqual(report["corporate_actions"]["TECX"]["by_type"], {"cash_dividends": 2, "name_changes": 1})
        self.assertEqual(report["feeds"]["iex"], {"status": 403, "bars": 0, "message": "not permitted on this plan"})
        self.assertEqual(report["checks_that_errored"], 0)

    def test_a_reverse_merger_shows_up_as_history_that_only_the_symbol_mapping_supplies(self):
        report, fake = run_fake(no_mapping_first_bar={"TECX": "2024-06-26"})
        mapping = report["symbol_mapping"]["TECX"]
        earlier = [d for d in probe.expected_sessions(SPEC, CALENDARS) if d < "2024-06-26"]
        self.assertEqual(mapping["first_bar_date_with_default_mapping"], "2023-10-02")
        self.assertEqual(mapping["first_bar_date_without_mapping"], "2024-06-26")
        self.assertEqual((mapping["bars_that_only_the_mapping_supplies"], mapping["mapping_changes_the_history"]), (len(earlier), True))
        self.assertEqual(mapping["bars_with_default_mapping"] - mapping["bars_without_mapping"], len(earlier))
        self.assertEqual(report["symbol_mapping"]["CACI"]["mapping_changes_the_history"], False)
        skipped = [p for e, p in fake.calls if p.get("asof") == "-"]
        self.assertEqual(len(skipped), 23)
        def refused(endpoint, params):
            return 403, {"message": "forbidden"}
        self.assertEqual(probe.mapping_effect(refused, "TECX", SPEC["window"], {"status": 200, "dates": ["2024-01-02"]}),
                         {"status_without_mapping": 403, "status_with_default_mapping": 200, "message": "forbidden"})
        self.assertEqual(probe.mapping_effect(FakeAlpaca(), "TECX", SPEC["window"], {"status": 403, "message": "x"}),
                         {"status_without_mapping": 200, "status_with_default_mapping": 403, "message": "x"})

    def test_a_refused_corporate_action_window_is_retried_by_calendar_year(self):
        dated = {"TECX": {"2023-12-15": "cash_dividends", "2024-06-26": "name_changes", "2025-02-03": "cash_dividends", "2026-09-01": "forward_splits"}}
        whole = probe.corporate_action_counts(FakeAlpaca(dated_actions=dated), "TECX", "2023-10-02", "2026-10-02")
        self.assertEqual(whole, {"status": 200, "by_type": {"cash_dividends": 2, "forward_splits": 1, "name_changes": 1}, "pages": 1})
        fake = FakeAlpaca(dated_actions=dated, max_actions_span_days=400)
        chunked = probe.corporate_action_counts(fake, "TECX", "2023-10-02", "2026-10-02")
        self.assertEqual(chunked["by_type"], {"cash_dividends": 2, "forward_splits": 1, "name_changes": 1})
        self.assertEqual((chunked["status"], chunked["chunked_by_year_after_400"], chunked["first_400_message"], chunked["pages"]), (200, True, "the requested range is too long", 4))
        windows = [(p["start"], p["end"]) for _, p in fake.calls[1:]]
        self.assertEqual(windows, [("2023-10-02", "2023-12-31"), ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-10-02")])
        hopeless = probe.corporate_action_counts(FakeAlpaca(dated_actions=dated, max_actions_span_days=1), "TECX", "2023-10-02", "2026-10-02")
        self.assertEqual((hopeless["status"], hopeless["chunked_by_year_after_400"]), (400, True))
        self.assertEqual(probe._year_windows("2024-03-01", "2024-03-01"), [("2024-03-01", "2024-03-01")])
        self.assertEqual(probe._year_windows("2024-12-31", "2025-01-01"), [("2024-12-31", "2024-12-31"), ("2025-01-01", "2025-01-01")])

    def test_pages_do_not_change_what_is_reported_except_the_page_counts(self):
        paged, _ = run_fake(page_size=100)
        strip = lambda node: {k: strip(v) for k, v in node.items() if k not in ("pages", "requests_made")} if isinstance(node, dict) else node       # noqa: E731
        self.assertEqual(canonical(strip(paged)), canonical(strip(self.report)))
        self.assertEqual(paged["daily_bars"]["CACI"]["pages"], 8)

    def test_one_failing_check_is_recorded_and_does_not_stop_the_others(self):
        report, _ = run_fake(raises={"ACHV"})
        self.assertTrue(report["complete"])
        self.assertEqual(report["daily_bars"]["ACHV"]["error"], "UNCATEGORIZED_RUNTIMEERROR")
        self.assertEqual(report["corporate_actions"]["ACHV"]["error"], "UNCATEGORIZED_RUNTIMEERROR")
        self.assertEqual(report["daily_bars"]["CACI"]["status"], 200)
        self.assertGreaterEqual(report["checks_that_errored"], 3)                                      # the daily bars, the actions and each minute-sample pair of ACHV
        self.assertNotIn("provider exploded", canonical(report).decode("utf-8"))                       # the exception text is never kept
        self.assertEqual(probe.count_errors({"a": [{"error": "x"}, {"b": {"error": "y"}}]}), 2)
        self.assertTrue(probe.contains_value_keys({"a": [{"b": {"v": 1}}]}))                          # the detector the leak test relies on finds a volume key at any depth
        self.assertTrue(probe.contains_value_keys({"close": 1}))
        self.assertFalse(probe.contains_value_keys({"bars": 3, "first_bar_date": "2024-01-02", "zero_volume_bars": 0}))

    def test_a_provider_that_refuses_everything_is_reported_as_statuses_not_as_a_crash(self):
        refuse = lambda endpoint, params: (403, {"message": "forbidden"})                                  # noqa: E731
        report = probe.run(SPEC, refuse, STAMP, project_calendars=CALENDARS, candidates=probe.candidate_dates(SPEC), environ={})
        self.assertTrue(report["complete"])
        self.assertEqual(report["daily_bars"]["SPY"], {"status": 403, "message": "forbidden", "bars": 0})
        self.assertEqual(report["reference_calendar"], {"status": 403, "matches_expected_sessions": False})
        self.assertEqual(report["corporate_actions"]["NBIX"]["status"], 403)


class AnnotationTests(unittest.TestCase):
    @staticmethod
    def items_of(lines):
        out = []
        for line in lines:
            match = re.fullmatch(r"::notice title=([^:]+)::(.*)", line)
            out.append((match.group(1), match.group(2)))
        return out

    @classmethod
    def setUpClass(cls):
        cls.report, _ = run_fake()

    def test_the_report_round_trips_through_the_notices_in_any_order(self):
        lines = probe.annotation_lines(self.report)
        self.assertTrue(all(line.startswith("::notice title=m5-phase1a-probe ") for line in lines))
        self.assertLessEqual(len(lines), 10)
        for line in lines:
            self.assertNotRegex(line, r"[\r\n%]")
            self.assertLessEqual(len(line.split("::", 2)[2]), probe.NOTICE_CHARS + 200)
        self.assertLessEqual(probe.NOTICE_CHARS, 3500)                                                  # well under the runner's cap of 4096 characters a message
        raw, packed = probe.pack(self.report)
        self.assertEqual(base64.b64decode(packed)[4:8], b"\x00\x00\x00\x00")                           # the gzip header's modification time is fixed at 0
        self.assertEqual(raw, canonical(self.report))
        items = self.items_of(lines)
        self.assertEqual(canonical(probe.decode_annotations(items)), canonical(self.report))
        self.assertEqual(canonical(probe.decode_annotations(list(reversed(items)))), canonical(self.report))
        self.assertEqual(probe.annotation_lines(self.report), lines)                                   # deterministic: gzip with a fixed mtime

    def test_a_damaged_or_incomplete_set_of_notices_is_refused(self):
        items = self.items_of(probe.annotation_lines(self.report))
        with self.assertRaises(DataError):
            probe.decode_annotations(items[1:])                                                         # a part missing
        with self.assertRaises(DataError):
            probe.decode_annotations(items[:-1])                                                        # no digest
        altered = list(items)
        title, message = altered[0]
        middle = len(message) // 2                                                                      # a character inside the compressed stream (the last characters can be padding that gzip tolerates)
        altered[0] = (title, message[:middle] + ("A" if message[middle] != "A" else "B") + message[middle + 1:])
        with self.assertRaises(Exception):
            probe.decode_annotations(altered)
        digest_title, digest_message = items[-1]
        wrong = items[:-1] + [(digest_title, digest_message.replace("sha256=", "sha256=0"))]
        with self.assertRaises(DataError):
            probe.decode_annotations(wrong)
        sha = re.search(r"sha256=([0-9a-f]{64})", digest_message).group(1)
        other_sha = ("0" if sha[0] != "0" else "1") + sha[1:]                                           # a well-formed digest that is not this report's
        with self.assertRaises(DataError):
            probe.decode_annotations(items[:-1] + [(digest_title, digest_message.replace(sha, other_sha))])
        size = int(re.search(r"bytes=(\d+)", digest_message).group(1))
        with self.assertRaises(DataError):                                                              # the right digest with the wrong length
            probe.decode_annotations(items[:-1] + [(digest_title, digest_message.replace("bytes=%d" % size, "bytes=%d" % (size + 1)))])
        self.assertEqual(canonical(probe.decode_annotations(items)), canonical(self.report))            # and the untouched set still decodes

    def test_a_report_too_large_for_the_notices_is_trimmed_of_its_date_samples_first(self):
        big = copy.deepcopy(self.report)
        for index, summary in enumerate(big["daily_bars"].values()):
            summary["missing_dates_first_20"] = [digest(("%d-%d" % (index, i)).encode()) for i in range(20)]
        lines = probe.annotation_lines(big)
        decoded = probe.decode_annotations(self.items_of(lines))
        self.assertTrue(decoded["trimmed_for_annotations"])
        self.assertNotIn("missing_dates_first_20", decoded["daily_bars"]["SPY"])
        self.assertEqual(decoded["daily_bars"]["SPY"]["bars"], big["daily_bars"]["SPY"]["bars"])
        self.assertLessEqual(len(lines), 10)
        hopeless = copy.deepcopy(big)
        hopeless["padding"] = [digest(str(i).encode()) for i in range(3000)]
        with self.assertRaises(DataError):
            probe.annotation_lines(hopeless)


class MainTests(unittest.TestCase):
    def run_main(self, environ, transport=None):
        out = io.StringIO()
        patches = [mock.patch.dict(os.environ, environ)]
        if transport is not None:
            patches.append(mock.patch.object(probe, "Transport", transport))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with contextlib.redirect_stdout(out):
                code = probe.main()
        return code, out.getvalue()

    def test_without_the_secrets_it_reports_that_and_exits_with_2(self):
        code, output = self.run_main({"APCA_API_KEY_ID": "", "APCA_API_SECRET_KEY": ""})
        self.assertEqual(code, 2)
        self.assertIn("MISSING_GITHUB_ACTIONS_SECRETS", output)
        self.assertIn("::notice title=m5-phase1a-probe digest::", output)

    def test_with_the_secrets_it_prints_the_report_and_the_notices_and_never_the_secrets(self):
        fake = FakeAlpaca()
        code, output = self.run_main({"APCA_API_KEY_ID": "KEYKEY123", "APCA_API_SECRET_KEY": "SECRETSECRET456"}, transport=lambda key, secret, **kwargs: fake)
        self.assertEqual(code, 0)
        self.assertNotIn("KEYKEY123", output)
        self.assertNotIn("SECRETSECRET456", output)
        printed = json.loads(output[:output.index("\n::notice")])
        self.assertTrue(printed["complete"])
        lines = [line for line in output.splitlines() if line.startswith("::notice")]
        items = [re.fullmatch(r"::notice title=([^:]+)::(.*)", line).groups() for line in lines]
        self.assertEqual(canonical(probe.decode_annotations(items)), canonical(printed))

    def test_an_unexpected_failure_is_reported_by_class_name_only(self):
        def broken(key, secret, **kwargs):
            raise ValueError("the message holds KEYKEY123")
        code, output = self.run_main({"APCA_API_KEY_ID": "KEYKEY123", "APCA_API_SECRET_KEY": "SECRETSECRET456"}, transport=broken)
        self.assertEqual(code, 2)
        self.assertIn("UNCATEGORIZED_VALUEERROR", output)
        self.assertNotIn("KEYKEY123", output)


class StaticTests(unittest.TestCase):
    def test_the_module_imports_only_the_standard_library_and_the_projects_own_modules(self):
        tree = ast.parse((ROOT / "nre" / "m5_phase1a_probe.py").read_text(encoding="utf-8"))
        allowed = {"base64", "gzip", "json", "os", "re", "sys", "time", "datetime", "pathlib", "urllib.error", "urllib.parse", "urllib.request", "zoneinfo"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(("." * node.level) + (node.module or ""))
        self.assertEqual({name for name in imported if not name.startswith(".")}, allowed)
        self.assertEqual({name for name in imported if name.startswith(".")}, {".calendar", ".core"})

    def test_the_workflow_runs_the_module_with_only_the_two_secrets_and_publishes_nothing(self):
        text = (ROOT / ".github" / "workflows" / "m5-phase1a-probe.yml").read_text(encoding="utf-8")
        for needed in ("name: M5 Phase 1a availability probe", "workflow_dispatch:", "branches: [main]", "- '.github/workflows/m5-phase1a-probe.yml'", "- 'config/m5-phase1a-probe-spec.json'",
                       "permissions:\n  contents: read", "timeout-minutes: 15", "python-version: '3.12'", "run: python -m nre.m5_phase1a_probe",
                       "APCA_API_KEY_ID: ${{ secrets.APCA_API_KEY_ID }}", "APCA_API_SECRET_KEY: ${{ secrets.APCA_API_SECRET_KEY }}"):
            self.assertIn(needed, text)
        self.assertEqual(sorted(re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", text)), ["secrets.APCA_API_KEY_ID", "secrets.APCA_API_SECRET_KEY"])
        for forbidden in ("upload-artifact", "contents: write", "git push", "pull_request_target", "curl"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(len(re.findall(r"^\s+- '", text, re.M)), 2)                                    # only the workflow and the spec trigger a push run

    def test_the_authorization_record_is_the_one_the_spec_cites(self):
        record = json.loads((ROOT / SPEC["authority"]["authorization"]).read_text(encoding="utf-8"))
        self.assertEqual([m["text"] for m in record["owner_messages"]], ["authorize phase 1a"])
        self.assertIn("line 35069", record["owner_messages"][0]["source"])
        self.assertEqual(record["owner_messages"][0]["at"], "2026-10-08T16:25:07.994Z")


if __name__ == "__main__":
    unittest.main()
