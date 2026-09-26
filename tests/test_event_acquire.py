import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from nre import event_acquire as ea
from nre.calendar import Calendar
from nre.core import DataError, canonical, digest

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads(ea.DEFAULT_SPEC.read_text(encoding="utf-8"))
CAL = Calendar()
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
SLSN, CXT = "slsn-2026-03-31", "cxt-2026-02-11"
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}
RAW_PRICES = ("123.45", "130.5", "120.25", "125.75")

# Windows of the two original per-event scripts (hand-listed for SLSN, calendar-computed for CXT), kept as golden data.
SLSN_SESSIONS = ["2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02", "2026-04-06", "2026-04-07", "2026-04-08",
                 "2026-04-09", "2026-04-10", "2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17",
                 "2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28"]
CXT_SESSIONS = ["2026-02-11", "2026-02-12", "2026-02-13", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
                "2026-02-23", "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27", "2026-03-02", "2026-03-03",
                "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12"]
SESSIONS = {SLSN: SLSN_SESSIONS, CXT: CXT_SESSIONS}


def spec_copy():
    return copy.deepcopy(SPEC)


def event_copy(event_id):
    return copy.deepcopy(next(e for e in SPEC["events"] if e["event_id"] == event_id))


def bar(session, o=123.45, h=130.5, l=120.25, c=125.75, v=1000):
    return {"t": session + "T00:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}


def fetcher(ticker, rows, actions=None):
    def fetch(endpoint, params):
        if endpoint == ea.ACTIONS_ENDPOINT:
            return json.dumps({"corporate_actions": actions or {}, "next_page_token": None}).encode()
        return json.dumps({"bars": {ticker: rows}, "next_page_token": None}).encode()
    return fetch


def run(event_id, rows=None, actions=None, event=None, provider=None):
    event = event or event_copy(event_id)
    rows = [bar(s) for s in SESSIONS[event_id]] if rows is None else rows
    return ea.run_event(event, provider or SPEC["provider"], fetcher(event["security"]["ticker"], rows, actions),
                        CAL, NOW)


def ramp(sessions, reaction_open=None):
    """Session i closes at 101+i (anchor 101), so every label has an independently checkable value."""
    rows = []
    for i, session in enumerate(sessions):
        o, h, l, c = 100 + i, 102 + i, 98 + i, 101 + i
        if i == 1 and reaction_open is not None:
            o, h, l, c = reaction_open, reaction_open + 2, reaction_open - 1, reaction_open + 1
        rows.append(bar(session, o, h, l, c))
    return rows


class SpecTests(unittest.TestCase):
    def rejects(self, mutate, fragment):
        spec = spec_copy()
        mutate(spec)
        with self.assertRaises(DataError) as caught:
            ea.validate_spec(spec, CAL)
        self.assertIn(fragment, str(caught.exception))

    def test_shipped_spec_is_valid(self):
        ea.validate_spec(SPEC, CAL)

    def test_shipped_events(self):
        got = {e["event_id"]: (e["expected_release_timing"], e["expected_reaction_session"]) for e in SPEC["events"]}
        self.assertEqual(got[SLSN], ("premarket", "2026-03-31"))
        self.assertEqual(got[CXT], ("after_hours", "2026-02-12"))

    def test_recorded_events_agree_with_ledger_and_review(self):
        ledger = json.loads((ROOT / "reports/m1-reviewed-candidate-ledger.json").read_text(encoding="utf-8"))
        included = {c["event_id"]: c["candidate_id"] for c in ledger["candidates"] if c["disposition"] == "included"}
        recorded = {e["event_id"]: e["candidate_id"] for e in SPEC["events"] if "recorded_result" in e}
        self.assertEqual(included, recorded)
        for event in SPEC["events"]:
            if "recorded_result" in event:
                self.assertEqual(set(event["attestations"]), ea.ATTESTATIONS, event["event_id"])
        review = json.loads((ROOT / "reports/m1-acceptance-review.json").read_text(encoding="utf-8"))
        self.assertLessEqual({s["event_id"] for s in review["spot_checks"]}, set(included))

    def test_recorded_pins_match_the_committed_records(self):
        legacy_reasons = {SLSN: {}, CXT: {"session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"}}
        for event in SPEC["events"]:
            if "recorded_result" not in event:
                continue
            record = json.loads((ROOT / event["recorded_result"]["recorded_in"]).read_text(encoding="utf-8"))
            reasons = record.get("label_reasons", legacy_reasons.get(event["event_id"], {}))
            labels = {name: {"value": value, "reason": reasons.get(name)}
                      for name, value in record["computed_labels"].items()}
            self.assertEqual(digest(canonical(labels)), event["recorded_result"]["labels_sha256"], event["event_id"])

    def test_pending_events_never_produce_labels(self):
        for event in SPEC["events"]:
            if set(event.get("attestations", {})) == ea.ATTESTATIONS:
                continue
            rows = [bar(s) for s in ea.event_window(event, CAL)["required_sessions"]]
            report = ea.run_event(copy.deepcopy(event), SPEC["provider"],
                                  fetcher(event["security"]["ticker"], rows), CAL, NOW)
            outcome = report["computed_outcome"]
            self.assertEqual((outcome["state"], outcome["labels"]), ("QUARANTINED", {}), event["event_id"])
            self.assertNotIn("labels_sha256", report)

    def test_offset_must_match_new_york(self):
        self.rejects(lambda s: s["events"][0].update(published_at="2026-03-31T08:02:00-05:00"),
                     "New York UTC offset")

    def test_evidence_must_equal_wall_clock_minute(self):
        self.rejects(lambda s: s["events"][0].update(timestamp_evidence="08:03"), "wall-clock minute")

    def test_evidence_must_appear_in_source_text(self):
        self.rejects(lambda s: s["events"][0]["source"].update(text="no time shown https://example.com"),
                     "not found in source text")

    def test_expected_timing_and_session_must_agree_with_calendar(self):
        self.rejects(lambda s: s["events"][0].update(expected_release_timing="after_hours"), "release timing")
        self.rejects(lambda s: s["events"][0].update(expected_reaction_session="2026-04-01"), "reaction session")

    def test_regular_session_release_rejected(self):
        def mutate(spec):
            event = spec["events"][0]
            event.update(published_at="2026-03-31T10:02:00-04:00", timestamp_evidence="10:02")
            event["source"].update(text=event["source"]["text"] + " 10:02", first_seen_at="2026-03-31T10:03:00-04:00")
        self.rejects(mutate, "release timing")

    def test_only_minute_precision(self):
        self.rejects(lambda s: s["events"][0].update(precision="second"), "minute precision")

    def test_source_cannot_be_seen_before_publication(self):
        self.rejects(lambda s: s["events"][0]["source"].update(first_seen_at="2026-03-31T08:01:00-04:00"),
                     "first_seen_at precedes")

    def test_ticker_must_be_plain_symbol(self):
        self.rejects(lambda s: s["events"][0]["security"].update(ticker="slsn&x=1"), "plain symbol")

    def test_source_must_be_https(self):
        self.rejects(lambda s: s["events"][0]["source"].update(url="http://example.com/x"), "https URL")

    def test_attestation_needs_reviewer_date_and_existing_record(self):
        self.rejects(lambda s: s["events"][0]["attestations"]["first_public_time"].update(reviewer=" "), "reviewer")
        self.rejects(lambda s: s["events"][0]["attestations"]["first_public_time"].update(date="soon"), "ISO date")
        self.rejects(lambda s: s["events"][0]["attestations"]["corporate_actions"].update(
            record="reports/does-not-exist.json"), "record not found")

    def test_unknown_attestation_rejected(self):
        self.rejects(lambda s: s["events"][0]["attestations"].update(timing={}), "attestations may only use")

    def test_provider_permission_requires_attestation(self):
        self.rejects(lambda s: s["provider"].pop("attestation"), "provider attestation")
        self.rejects(lambda s: s["provider"].update(research_permitted="yes"), "boolean")

    def test_unattested_provider_is_a_valid_dry_run_spec(self):
        spec = spec_copy()
        spec["provider"].update(research_permitted=False)
        spec["provider"].pop("attestation")
        ea.validate_spec(spec, CAL)

    def test_duplicates_rejected(self):
        self.rejects(lambda s: s["events"].append(copy.deepcopy(s["events"][0])), "duplicate event_id")

    def test_recorded_result_shape(self):
        self.rejects(lambda s: s["events"][0]["recorded_result"].update(labels_sha256="abc"), "64-hex")
        self.rejects(lambda s: s["events"][0]["recorded_result"].update(recorded_in="reports/none.json"),
                     "record not found")


class WindowTests(unittest.TestCase):
    def test_windows_match_the_original_per_event_scripts(self):
        expected = {SLSN: ("2026-03-01", "2026-04-30", "2026-03-31"), CXT: ("2026-02-01", "2026-03-31", "2026-02-11")}
        for event_id, span in expected.items():
            window = ea.event_window(event_copy(event_id), CAL)
            self.assertEqual(window["required_sessions"], SESSIONS[event_id])
            self.assertEqual((window["start"], window["end"], window["asof"]), span)

    def test_request_parameters_match_the_original_per_event_scripts(self):
        window = ea.event_window(event_copy(CXT), CAL)
        self.assertEqual(ea.bars_params("CXT", window), dict(
            symbols="CXT", timeframe="1Day", start="2026-02-01", end="2026-03-31", feed="sip", adjustment="raw",
            asof="2026-02-11", sort="asc", currency="USD", limit=50))
        self.assertEqual(ea.actions_params("CXT", window), dict(
            symbols="CXT", start="2026-02-01", end="2026-03-31", limit=100, sort="asc"))

    def test_window_spans_the_month_of_the_twentieth_session(self):
        event = event_copy(SLSN)
        event["published_at"] = "2026-01-06T08:02:00-05:00"
        window = ea.event_window(event, CAL)
        self.assertEqual((window["start"], window["end"]), ("2026-01-01", "2026-02-28"))
        self.assertEqual(len(window["required_sessions"]), 21)


class FetchTests(unittest.TestCase):
    def bars(self, pages, ticker="SLSN"):
        it = iter(pages)
        return ea.fetch_bars(lambda p: json.dumps(next(it)).encode(), ticker, {})

    def test_single_page(self):
        by_session, pages = self.bars([{"bars": {"SLSN": [bar("2026-03-30"), bar("2026-03-31")]},
                                        "next_page_token": None}])
        self.assertEqual(set(by_session), {"2026-03-30", "2026-03-31"})
        self.assertEqual(len(pages), 1)

    def test_pages_are_merged_through_the_terminal_token(self):
        by_session, pages = self.bars([{"bars": {"SLSN": [bar("2026-03-30")]}, "next_page_token": "t1"},
                                       {"bars": {"SLSN": [bar("2026-03-31")]}, "next_page_token": None}])
        self.assertEqual(set(by_session), {"2026-03-30", "2026-03-31"})
        self.assertEqual(len(pages), 2)

    def test_duplicate_session_rejected(self):
        with self.assertRaises(DataError):
            self.bars([{"bars": {"SLSN": [bar("2026-03-30"), bar("2026-03-30")]}, "next_page_token": None}])

    def test_unexpected_symbol_rejected(self):
        with self.assertRaises(DataError):
            self.bars([{"bars": {"OTHER": []}, "next_page_token": None}])

    def test_malformed_record_rejected(self):
        with self.assertRaises(DataError):
            self.bars([{"bars": {"SLSN": [{"t": "2026-03-30T00:00:00Z"}]}, "next_page_token": None}])

    def test_missing_pagination_metadata_rejected(self):
        with self.assertRaises(DataError):
            self.bars([{"bars": {"SLSN": []}}])

    def test_repeated_token_rejected(self):
        with self.assertRaises(DataError):
            self.bars([{"bars": {}, "next_page_token": "t1"}, {"bars": {}, "next_page_token": "t1"}])

    def actions(self, payload):
        return ea.fetch_actions(lambda p: json.dumps({"corporate_actions": payload, "next_page_token": None}).encode(),
                                {})

    def test_empty_shapes_mean_no_actions(self):
        for empty in ({}, [], None):
            self.assertEqual(self.actions(empty)[0], [])

    def test_extracts_type_ex_date_and_id(self):
        entries, _ = self.actions({"cash_dividends": [{"ex_date": "2026-02-27", "id": "abc", "rate": 0.18}]})
        self.assertEqual(entries, [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}])

    def test_unusable_actions_fail_closed(self):
        for payload in ({"cash_dividends": [{"rate": 0.18}]}, {"cash_dividends": [{"ex_date": "soon"}]},
                        {"cash_dividends": "x"}, [{"ex_date": "2026-02-27"}]):
            with self.assertRaises(DataError):
                self.actions(payload)

    def test_redirects_rejected(self):
        with self.assertRaises(DataError):
            ea.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example")


class BundleTests(unittest.TestCase):
    def bundle(self, event_id, actions=()):
        event = event_copy(event_id)
        window = ea.event_window(event, CAL)
        bars = {s: {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10} for s in SESSIONS[event_id]}
        return ea.build_bundle(event, SPEC["provider"], window, bars, list(actions), NOW, CAL)

    def test_close_availability_follows_new_york_daylight_time(self):
        slsn = {p["session"]: p["available_at"] for p in self.bundle(SLSN)["prices"]}
        cxt = {p["session"]: p["available_at"] for p in self.bundle(CXT)["prices"]}
        self.assertEqual(slsn["2026-03-30"], "2026-03-30T20:01:00Z")
        self.assertEqual(cxt["2026-02-11"], "2026-02-11T21:01:00Z")

    def test_only_required_sessions_enter_the_bundle(self):
        event = event_copy(SLSN)
        window = ea.event_window(event, CAL)
        bars = {s: {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10}
                for s in SLSN_SESSIONS + ["2026-03-02", "2026-04-30"]}
        bundle = ea.build_bundle(event, SPEC["provider"], window, bars, [], NOW, CAL)
        self.assertEqual([p["session"] for p in bundle["prices"]], SLSN_SESSIONS)

    def test_action_id_falls_back_and_available_at_is_new_york_midnight(self):
        action = self.bundle(CXT, [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": None}])["corporate_actions"][0]
        self.assertEqual(action["action_id"], "cash_dividends-2026-02-27")
        self.assertEqual(action["available_at"], "2026-02-27T05:00:00Z")

    def test_attestations_drive_the_verification_flags(self):
        event = event_copy(SLSN)
        window = ea.event_window(event, CAL)
        bars = {s: {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10} for s in SLSN_SESSIONS}
        full = ea.build_bundle(event, SPEC["provider"], window, bars, [], NOW, CAL)
        self.assertTrue(full["events"][0]["first_public_verified"])
        self.assertTrue(all(p["corporate_actions_verified"] for p in full["prices"]))
        del event["attestations"]["corporate_actions"]
        no_actions = ea.build_bundle(event, SPEC["provider"], window, bars, [], NOW, CAL)
        self.assertFalse(any(p["corporate_actions_verified"] for p in no_actions["prices"]))
        del event["attestations"]["historical_identity"]
        no_identity = ea.build_bundle(event, SPEC["provider"], window, bars, [], NOW, CAL)
        self.assertFalse(no_identity["events"][0]["first_public_verified"])


class RunEventTests(unittest.TestCase):
    def test_premarket_event_maps_with_a_negative_gap(self):
        report = run(SLSN)
        outcome = report["computed_outcome"]
        self.assertEqual((outcome["state"], outcome["reasons"]), ("MAPPED", []))
        self.assertEqual((outcome["release_timing"], outcome["reaction_session"]), ("premarket", "2026-03-31"))
        self.assertEqual(outcome["anchor"]["session"], "2026-03-30")
        self.assertAlmostEqual(outcome["labels"]["day1_close_return"]["value"], 0.0)
        self.assertFalse(outcome["labels"]["gap_ge_3pct"]["value"])
        self.assertEqual(outcome["labels"]["positive_gap_retained_half"]["reason"], "NOT_POSITIVE_GAP_GE_0_5PCT")
        self.assertEqual(report["build_report"]["complete_20_session"], 1)
        self.assertTrue(report["labels_computed"])
        self.assertEqual(report["missing_sessions"], [])
        self.assertEqual(len(report["labels_sha256"]), 64)

    def test_after_hours_event_maps_and_anchors_on_the_same_day(self):
        outcome = run(CXT)["computed_outcome"]
        self.assertEqual(outcome["state"], "MAPPED")
        self.assertEqual((outcome["release_timing"], outcome["reaction_session"]), ("after_hours", "2026-02-12"))
        self.assertEqual(outcome["anchor"]["session"], "2026-02-11")

    def test_labels_follow_their_windows(self):
        labels = run(SLSN, rows=ramp(SLSN_SESSIONS))["computed_outcome"]["labels"]
        value = {name: label["value"] for name, label in labels.items()}
        self.assertAlmostEqual(value["day1_open_return"], 0.0)
        self.assertAlmostEqual(value["day1_high_return"], 103 / 101 - 1)
        self.assertAlmostEqual(value["day1_low_return"], 99 / 101 - 1)
        self.assertAlmostEqual(value["day1_close_return"], 102 / 101 - 1)
        for n in (2, 5, 10, 20):
            self.assertAlmostEqual(value["session_%d_close_return" % n], (101 + n) / 101 - 1)
        self.assertEqual(labels["session_20_close_return"]["window"], SLSN_SESSIONS)

    def test_positive_gap_labels(self):
        value = {name: label["value"] for name, label in
                 run(SLSN, rows=ramp(SLSN_SESSIONS, reaction_open=108))["computed_outcome"]["labels"].items()}
        self.assertTrue(value["gap_ge_3pct"] and value["gap_ge_5pct"])
        self.assertFalse(value["gap_ge_10pct"])
        self.assertFalse(value["positive_gap_filled"])
        self.assertTrue(value["positive_gap_retained_half"])

    def test_dividend_suppresses_only_the_label_it_crosses(self):
        actions = {"cash_dividends": [{"ex_date": "2026-02-27", "id": "abc", "rate": 0.18}]}
        report = run(CXT, actions=actions)
        labels = report["computed_outcome"]["labels"]
        self.assertEqual(report["computed_outcome"]["state"], "MAPPED")
        for name in ("day1_close_return", "session_2_close_return", "session_5_close_return", "session_10_close_return"):
            self.assertIsNone(labels[name]["reason"], name)
        self.assertEqual(labels["session_20_close_return"]["reason"], "CORPORATE_ACTION_IN_WINDOW")
        self.assertIsNone(labels["session_20_close_return"]["value"])
        self.assertTrue(report["labels_computed"])
        self.assertEqual(report["corporate_actions"], [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}])

    def test_dividend_inside_the_day_one_window_quarantines_the_event(self):
        report = run(CXT, actions={"cash_dividends": [{"ex_date": "2026-02-12", "id": "early"}]})
        self.assertEqual(report["computed_outcome"]["state"], "QUARANTINED")
        self.assertEqual(report["computed_outcome"]["reasons"], ["CORPORATE_ACTION_IN_WINDOW"])
        self.assertFalse(report["labels_computed"])

    def test_dividend_on_the_anchor_date_does_not_touch_any_window(self):
        report = run(CXT, actions={"cash_dividends": [{"ex_date": "2026-02-11", "id": "same-day"}]})
        self.assertEqual(report["computed_outcome"]["state"], "MAPPED")
        self.assertIsNone(report["computed_outcome"]["labels"]["session_20_close_return"]["reason"])

    def test_missing_session_quarantines_and_is_reported(self):
        rows = [bar(s) for s in SLSN_SESSIONS if s != "2026-03-31"]
        report = run(SLSN, rows=rows)
        self.assertEqual(report["computed_outcome"]["reasons"], ["MISSING_SESSION"])
        self.assertEqual(report["missing_sessions"], ["2026-03-31"])

    def test_zero_volume_session_quarantines_and_is_reported(self):
        rows = [bar(s, v=0 if s == "2026-03-31" else 1000) for s in SLSN_SESSIONS]
        report = run(SLSN, rows=rows)
        self.assertEqual(report["computed_outcome"]["reasons"], ["INCOMPLETE_OR_HALTED_SESSION"])
        self.assertEqual(report["zero_volume_sessions"], ["2026-03-31"])

    def test_unattested_timing_or_identity_quarantines_without_labels(self):
        for key in ("first_public_time", "historical_identity"):
            event = event_copy(SLSN)
            del event["attestations"][key]
            outcome = run(SLSN, event=event)["computed_outcome"]
            self.assertEqual(outcome["reasons"], ["FIRST_PUBLIC_TIME_UNVERIFIED"], key)
            self.assertEqual(outcome["labels"], {})

    def test_unattested_corporate_actions_quarantines_but_reports_the_actions(self):
        event = event_copy(CXT)
        del event["attestations"]["corporate_actions"]
        actions = {"cash_dividends": [{"ex_date": "2026-02-27", "id": "abc"}]}
        report = run(CXT, actions=actions, event=event)
        self.assertEqual(report["computed_outcome"]["reasons"], ["CORPORATE_ACTION_AUDIT_MISSING"])
        self.assertEqual(report["computed_outcome"]["labels"], {})
        self.assertEqual(len(report["corporate_actions"]), 1)

    def test_provider_permission_false_still_quarantines(self):
        provider = copy.deepcopy(SPEC["provider"])
        provider["research_permitted"] = False
        outcome = run(SLSN, provider=provider)["computed_outcome"]
        self.assertEqual((outcome["state"], outcome["reasons"], outcome["labels"]),
                         ("QUARANTINED", ["PROVIDER_USE_UNVERIFIED"], {}))

    def test_report_holds_no_raw_prices(self):
        report = run(SLSN)
        text = json.dumps(report)
        for raw in RAW_PRICES:
            self.assertNotIn(raw, text)
        self.assertNotIn("price", report["computed_outcome"]["anchor"])

    def test_caveats_travel_with_the_report(self):
        caveat = run(CXT)["caveats"][0]
        self.assertEqual(caveat["labels"], ["session_10_close_return", "session_20_close_return"])

    def test_recorded_labels_pin(self):
        event = event_copy(SLSN)
        event.pop("recorded_result")
        first = run(SLSN, event=copy.deepcopy(event))
        self.assertNotIn("labels_match_recorded", first)
        event["recorded_result"] = {"labels_sha256": first["labels_sha256"], "recorded_in": "x"}
        matched = run(SLSN, event=copy.deepcopy(event))
        self.assertTrue(matched["labels_match_recorded"])
        self.assertNotIn("error", matched)
        event["recorded_result"]["labels_sha256"] = "0" * 64
        drifted = run(SLSN, event=event)
        self.assertFalse(drifted["labels_match_recorded"])
        self.assertEqual(drifted["error"], "LABELS_DIFFER_FROM_RECORDED")

    def test_a_pinned_event_that_no_longer_maps_is_an_error(self):
        event = event_copy(SLSN)
        report = run(SLSN, event=event, rows=[bar(s) for s in SLSN_SESSIONS[:-1]])
        self.assertEqual(report["computed_outcome"]["state"], "MAPPED")
        self.assertEqual(report["computed_outcome"]["labels"]["session_20_close_return"]["reason"], "MISSING_SESSION")
        self.assertEqual(report["error"], "LABELS_DIFFER_FROM_RECORDED")


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size=-1):
        return self._data


class _FakeOpener:
    def __init__(self, responder):
        self._responder = responder

    def open(self, req, timeout=None):
        return _FakeResponse(self._responder(req.full_url))


def both_events(url):
    cxt = "symbols=CXT" in url
    if "corporate-actions" in url:
        actions = {"cash_dividends": [{"ex_date": "2026-02-27", "id": "abc"}]} if cxt else {}
        return json.dumps({"corporate_actions": actions, "next_page_token": None}).encode()
    ticker, sessions = ("CXT", CXT_SESSIONS) if cxt else ("SLSN", SLSN_SESSIONS)
    return json.dumps({"bars": {ticker: [bar(s) for s in sessions]}, "next_page_token": None}).encode()


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def unpinned_spec(self):
        spec = spec_copy()
        spec["events"] = [e for e in spec["events"] if e["event_id"] in (SLSN, CXT)]
        for event in spec["events"]:
            event.pop("recorded_result")
        path = Path(self.tmp.name) / "spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return str(path)

    def run_main(self, argv, responder=both_events, env=ENV):
        with patch.dict("os.environ", env, clear=True), \
             patch("nre.event_acquire.build_opener", return_value=_FakeOpener(responder)), \
             patch("builtins.print") as output:
            code = ea.main(argv)
        return code, [call.args[0] for call in output.call_args_list]

    def test_no_credentials_no_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("nre.event_acquire.build_opener") as opener, \
             patch("builtins.print") as output:
            self.assertEqual(ea.main([]), 2)
        self.assertIn("MISSING_GITHUB_ACTIONS_SECRETS", output.call_args.args[0])
        opener.assert_not_called()

    def test_unknown_event_rejected_before_any_network(self):
        with patch.dict("os.environ", ENV, clear=True), patch("nre.event_acquire.build_opener") as opener, \
             patch("builtins.print") as output:
            self.assertEqual(ea.main(["--event", "nope"]), 2)
        self.assertIn("unknown event", output.call_args.args[0])
        opener.assert_not_called()

    def test_invalid_spec_rejected(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        code, printed = self.run_main(["--spec", str(bad)])
        self.assertEqual(code, 2)
        self.assertIn("SPEC_INVALID: not valid JSON", printed[0])

    def test_all_events_run_and_report(self):
        code, printed = self.run_main(["--spec", self.unpinned_spec()])
        report = json.loads(printed[0])
        self.assertEqual(code, 0)
        self.assertTrue(report["all_ok"])
        self.assertEqual({k: v["computed_outcome"]["state"] for k, v in report["events"].items()},
                         {SLSN: "MAPPED", CXT: "MAPPED"})
        self.assertEqual(report["events"][CXT]["computed_outcome"]["labels"]["session_20_close_return"]["reason"],
                         "CORPORATE_ACTION_IN_WINDOW")

    def test_single_event_selected(self):
        code, printed = self.run_main(["--spec", self.unpinned_spec(), "--event", CXT])
        self.assertEqual(list(json.loads(printed[0])["events"]), [CXT])

    def test_shipped_pins_are_enforced(self):
        code, printed = self.run_main(["--event", SLSN])
        report = json.loads(printed[0])
        self.assertEqual(code, 2)
        self.assertFalse(report["all_ok"])
        self.assertEqual(report["events"][SLSN]["error"], "LABELS_DIFFER_FROM_RECORDED")

    def test_nothing_sensitive_is_printed(self):
        _, printed = self.run_main(["--spec", self.unpinned_spec()])
        text = "\n".join(printed)
        for secret in ("AKTESTKEY123", "SECRETVALUE456") + RAW_PRICES:
            self.assertNotIn(secret, text)

    def test_error_categories(self):
        def raising(exc):
            def responder(url):
                raise exc
            return responder
        cases = [(HTTPError("u", 401, "Unauthorized", {}, None), "ALPACA_HTTP_401"),
                 (URLError("down"), "NETWORK_ERROR"),
                 (json.JSONDecodeError("bad", "x", 0), "INVALID_JSON_RESPONSE"),
                 (RuntimeError("SECRETVALUE456"), "UNCATEGORIZED_RUNTIMEERROR")]
        for exc, category in cases:
            code, printed = self.run_main(["--spec", self.unpinned_spec(), "--event", SLSN], raising(exc))
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(printed[0])["events"][SLSN]["error"], category)
            self.assertNotIn("SECRETVALUE456", printed[0])

    def test_one_failing_event_does_not_stop_the_others(self):
        def responder(url):
            if "symbols=SLSN" in url:
                raise URLError("down")
            return both_events(url)
        code, printed = self.run_main(["--spec", self.unpinned_spec()], responder)
        events = json.loads(printed[0])["events"]
        self.assertEqual(code, 2)
        self.assertEqual(events[SLSN]["error"], "NETWORK_ERROR")
        self.assertEqual(events[CXT]["computed_outcome"]["state"], "MAPPED")

    def test_github_annotation_only_inside_actions(self):
        _, printed = self.run_main(["--spec", self.unpinned_spec()])
        self.assertEqual(len(printed), 1)
        _, printed = self.run_main(["--spec", self.unpinned_spec()], env=dict(ENV, GITHUB_ACTIONS="true"))
        line = printed[-1]
        prefix = "::notice title=NRE event acquisition::"
        self.assertTrue(line.startswith(prefix))
        self.assertNotIn("\n", line)
        summary = json.loads(line[len(prefix):])
        self.assertTrue(summary["all_ok"])
        self.assertEqual(summary["events"][CXT]["state"], "MAPPED")
        self.assertIn("day1_close_return", summary["events"][SLSN]["labels"])
        for raw in RAW_PRICES:
            self.assertNotIn(raw, line)

    def test_annotations_split_under_the_github_limit(self):
        events = {"e%02d" % i: {"labels": {"day1_close_return": 0.123456789012345 + i}, "note": "y" * 300}
                  for i in range(40)}
        lines = ea._annotations("notice", True, events)
        prefix = "::notice title=NRE event acquisition::"
        self.assertGreater(len(lines), 1)
        merged = {}
        for number, line in enumerate(lines, 1):
            self.assertTrue(line.startswith(prefix))
            self.assertLess(len(line), 4000)
            self.assertNotIn("\n", line)
            body = json.loads(line[len(prefix):])
            self.assertEqual(body["part"], "%d/%d" % (number, len(lines)))
            merged.update(body["events"])
        self.assertEqual(merged, events)

    def test_annotation_escapes_percent_signs(self):
        line = ea._annotations("notice", True, {"a": {"note": "100%"}})[0]
        self.assertIn("100%25", line)

    def test_matched_pins_drop_label_values_from_the_annotation(self):
        report = {"labels_match_recorded": True, "labels_sha256": "abc",
                  "computed_outcome": {"state": "MAPPED", "labels": {"a": {"value": 1.5, "reason": None}}}}
        compact = ea._compact(report)
        self.assertEqual((compact["labels"], compact["labels_sha256"]), ({}, "abc"))
        report["labels_match_recorded"] = None
        self.assertEqual(ea._compact(report)["labels"], {"a": 1.5})

    def test_failed_run_annotates_an_error(self):
        _, printed = self.run_main(["--event", SLSN], env=dict(ENV, GITHUB_ACTIONS="true"))
        self.assertTrue(printed[-1].startswith("::error title=NRE event acquisition::"))


if __name__ == "__main__":
    unittest.main()
