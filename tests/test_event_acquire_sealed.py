"""The hash-only seal of nre.event_acquire (config/m5-phase1b-protocol.json, "seal"): a sealed run prints an event's state, window facts, missing and zero-volume sessions, corporate actions, the SHA-256
commitment of its labels and whether each session-return label exists -- and nothing a price, a return or a day-1 or gap label could be read from. The tests inject distinctive four-decimal prices through a fake
provider and look for them, and for every label computed from them, in everything a run prints, reports or annotates; and they run price histories that differ in exactly the things the seal hides (the sign and size of
the gap, the day-1 move, the later drift) and require identical sealed reports except the commitment."""
import contextlib
import copy
import io
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from nre import event_acquire as ea
from nre.calendar import Calendar
from nre.core import DataError

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads(ea.DEFAULT_SPEC.read_text(encoding="utf-8"))
PROTOCOL = json.loads((ROOT / "config" / "m5-phase1b-protocol.json").read_text(encoding="utf-8"))
WORKFLOW = ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml"
CAL = Calendar()
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
SLSN, CXT = "slsn-2026-03-31", "cxt-2026-02-11"
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}
PIN_RECORD = "reports/m5-phase1b-authorization-2026-10-09.json"                      # any file that exists: the pin needs a record to point at
SLSN_SESSIONS = ["2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02", "2026-04-06", "2026-04-07", "2026-04-08",
                 "2026-04-09", "2026-04-10", "2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17",
                 "2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28"]
CXT_SESSIONS = ["2026-02-11", "2026-02-12", "2026-02-13", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
                "2026-02-23", "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27", "2026-03-02", "2026-03-03",
                "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12"]
SESSIONS = {SLSN: SLSN_SESSIONS, CXT: CXT_SESSIONS}
DIVIDEND = {"cash_dividends": [{"ex_date": "2026-02-27", "id": "abc"}]}


def bar(session, o, h, l, c, v):
    return {"t": session + "T00:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}


def price_path(sessions, anchor=7183.2941, gap=0.0, day1=0.0173, drift=0.0013):
    """Distinctive prices with four decimals. Session 0 is the anchor; session 1 the reaction day (open = anchor * (1 + gap), close = open * (1 + day1)); later sessions drift."""
    rows, previous = [], anchor
    for i, session in enumerate(sessions):
        if i == 0:
            o, c = anchor * 0.9961, anchor
        elif i == 1:
            o = anchor * (1 + gap)
            c = o * (1 + day1)
        else:
            o, c = previous, previous * (1 + drift)
        rows.append(bar(session, round(o, 4), round(max(o, c) * 1.0111, 4), round(min(o, c) * 0.9877, 4), round(c, 4), 1000003 + 7919 * i))
        previous = c
    return rows


def fetcher(ticker, rows, actions=None):
    calls = []

    def fetch(endpoint, params):
        calls.append(endpoint)
        if endpoint == ea.ACTIONS_ENDPOINT:
            return json.dumps({"corporate_actions": actions or {}, "next_page_token": None}).encode()
        return json.dumps({"bars": {ticker: rows}, "next_page_token": None}).encode()
    fetch.calls = calls
    return fetch


def event_copy(event_id, sealed=True, pinned=False, attested=True):
    event = copy.deepcopy(next(e for e in SPEC["events"] if e["event_id"] == event_id))
    if not pinned:
        event.pop("recorded_result", None)
    if not attested:
        event.pop("attestations", None)
    if sealed:
        event["seal"] = ea.SEAL
    return event


def full_run(event_id, rows, actions=None, **kwargs):
    """The unsealed run: what a sealed run must not print."""
    event = event_copy(event_id, sealed=False, **kwargs)
    return ea.run_event(event, SPEC["provider"], fetcher(event["security"]["ticker"], rows, actions), CAL, NOW)


def sealed_run(event_id, rows, actions=None, **kwargs):
    event = event_copy(event_id, **kwargs)
    return ea.run_event(event, SPEC["provider"], fetcher(event["security"]["ticker"], rows, actions), CAL, NOW, sealed=True)


def fragments(rows, report):
    """Every number a price or a label could be read from: the injected prices and volumes, and the value of every label the engine computed from them."""
    found = set()
    for row in rows:
        found.update(json.dumps(row[key]) for key in ("o", "h", "l", "c"))
        found.add(str(row["v"]))
    for label in (report["computed_outcome"].get("labels") or {}).values():
        if isinstance(label["value"], float):
            found.update((repr(label["value"]), "%.6f" % label["value"], "%.5f" % label["value"]))
    return {f for f in found if len(f) >= 6}


class SealedViewTests(unittest.TestCase):
    def test_the_sealed_report_is_rebuilt_from_an_allowlist(self):
        rows = price_path(SLSN_SESSIONS, gap=0.07)
        report = sealed_run(SLSN, rows)
        self.assertEqual(set(report), {"event_id", "ticker", "access_check_passed", "labels_computed", "window", "missing_sessions", "zero_volume_sessions", "corporate_actions",
                                       "computed_outcome", "labels_sha256"})
        view = ea.sealed_report(report)
        self.assertEqual(set(view), ea.SEALED_REPORT_KEYS - {"error"})
        self.assertEqual((view["event_id"], view["ticker"], view["sealed"], view["access_check_passed"], view["state"], view["reasons"]), (SLSN, "SLSN", True, True, "MAPPED", []))
        self.assertEqual(view["window"], {"anchor_session": "2026-03-30", "reaction_session": "2026-03-31", "release_timing": "premarket", "start": "2026-03-01", "end": "2026-04-30",
                                          "asof": "2026-03-31", "required_sessions": 21})
        self.assertEqual((view["missing_sessions"], view["zero_volume_sessions"], view["corporate_actions"]), ([], [], []))
        self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
        self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")
        self.assertIsNone(view["labels_match_recorded"])

    def test_nothing_else_in_a_report_can_pass_through_it(self):
        report = sealed_run(SLSN, price_path(SLSN_SESSIONS))
        report.update(bundle_sha256="a" * 64, bar_pages=[{"sha256": "b" * 64, "records": 21}], caveats=[{"labels": ["all"], "note": "x"}], labels={"day1_close_return": 0.0173},
                      build_report={"mapped_day1": 1}, extra="7183.2941")
        report["computed_outcome"].update(labels={"day1_close_return": {"value": 0.0173, "reason": None}}, anchor={"price": 7183.2941})
        view = ea.sealed_report(report)
        self.assertEqual(set(view), ea.SEALED_REPORT_KEYS - {"error"})
        text = json.dumps(view)
        for leaked in ("7183.2941", "0.0173", "bundle_sha256", "bar_pages", "caveats", "build_report", "day1_", '"price"', '"labels"'):
            self.assertNotIn(leaked, text)

    def test_a_full_unsealed_report_is_reduced_to_the_same_view_as_the_sealed_run_of_it(self):
        rows = price_path(SLSN_SESSIONS, gap=0.07)
        self.assertEqual(ea.sealed_report(full_run(SLSN, rows)), ea.sealed_report(sealed_run(SLSN, rows)))

    def test_the_sealed_run_never_holds_a_label_an_anchor_or_the_bars_digests(self):
        report = sealed_run(SLSN, price_path(SLSN_SESSIONS, gap=0.07))
        self.assertEqual(set(report["computed_outcome"]), {"state", "reasons", "release_timing", "reaction_session", "session_labels"})
        self.assertEqual(set(report["computed_outcome"]["session_labels"]), set(ea.SESSION_LABEL_NAMES))
        self.assertNotIn("bundle_sha256", report)
        self.assertNotIn("bar_pages", report)
        self.assertNotIn("build_report", report)
        for fragment in fragments(price_path(SLSN_SESSIONS, gap=0.07), full_run(SLSN, price_path(SLSN_SESSIONS, gap=0.07))):
            self.assertNotIn(fragment, json.dumps(report))

    def test_no_decimal_number_no_price_and_no_label_value_appears_in_the_view(self):
        for gap in (-0.4, -0.003, 0.0, 0.004, 0.006, 0.07, 0.4):
            rows = price_path(SLSN_SESSIONS, gap=gap)
            text = json.dumps(ea.sealed_report(sealed_run(SLSN, rows)))
            self.assertIsNone(re.search(r"\d\.\d", text), (gap, text))
            for fragment in fragments(rows, full_run(SLSN, rows)):
                self.assertNotIn(fragment, text, gap)

    def test_histories_that_differ_in_everything_the_seal_hides_give_identical_views_except_the_commitment(self):
        histories = {"gap up 40%": dict(gap=0.4), "gap down 40%": dict(gap=-0.4), "gap just above the 0.5% line": dict(gap=0.006, day1=-0.02), "gap just below it": dict(gap=0.004, day1=0.03),
                     "gap down, day one up": dict(gap=-0.01, day1=0.05), "flat": dict(gap=0.0, day1=0.0, drift=0.0), "later sessions fall": dict(gap=0.02, drift=-0.004),
                     "another level": dict(anchor=3.2917, gap=0.03)}
        views, commitments = {}, {}
        for name, changes in histories.items():
            view = ea.sealed_report(sealed_run(SLSN, price_path(SLSN_SESSIONS, **changes)))
            commitments[name] = view.pop("labels_sha256")
            views[name] = view
        first = next(iter(views.values()))
        for name, view in views.items():
            self.assertEqual(view, first, name)
        self.assertEqual(len(set(commitments.values())), len(histories))                             # the commitment does depend on the labels

    def test_the_gap_reason_would_have_told_the_gap_s_sign_and_the_sealed_view_hides_it(self):
        above = full_run(SLSN, price_path(SLSN_SESSIONS, gap=0.006))["computed_outcome"]["labels"]["positive_gap_filled"]["reason"]
        below = full_run(SLSN, price_path(SLSN_SESSIONS, gap=0.004))["computed_outcome"]["labels"]["positive_gap_filled"]["reason"]
        self.assertEqual((above, below), (None, "NOT_POSITIVE_GAP_GE_0_5PCT"))
        self.assertNotIn("NOT_POSITIVE_GAP_GE_0_5PCT", ea.EVENT_REASONS | ea.SESSION_LABEL_REASONS)
        for gap in (0.006, 0.004):
            self.assertNotIn("POSITIVE_GAP", json.dumps(ea.sealed_report(sealed_run(SLSN, price_path(SLSN_SESSIONS, gap=gap)))))

    def test_the_commitment_is_the_one_the_earlier_steps_pin(self):
        rows = price_path(SLSN_SESSIONS, gap=0.07)
        self.assertEqual(sealed_run(SLSN, rows)["labels_sha256"], full_run(SLSN, rows)["labels_sha256"])
        self.assertEqual(sealed_run(SLSN, rows)["labels_sha256"], sealed_run(SLSN, rows)["labels_sha256"])

    def test_missing_and_zero_volume_sessions_and_corporate_actions_are_reported(self):
        rows = price_path(SLSN_SESSIONS)
        view = ea.sealed_report(sealed_run(SLSN, rows[:-1]))
        self.assertEqual((view["state"], view["missing_sessions"]), ("MAPPED", [SLSN_SESSIONS[-1]]))
        self.assertEqual(view["session_labels"]["session_20_close_return"], {"exists": False, "reason": "MISSING_SESSION"})
        self.assertTrue(all(view["session_labels"][name]["exists"] for name in ("session_2_close_return", "session_5_close_return", "session_10_close_return")))
        rows[5]["v"] = 0
        view = ea.sealed_report(sealed_run(SLSN, rows))
        self.assertEqual((view["state"], view["zero_volume_sessions"]), ("MAPPED", [SLSN_SESSIONS[5]]))
        self.assertEqual({name: label["reason"] for name, label in view["session_labels"].items()},
                         {"session_2_close_return": None, "session_5_close_return": "INCOMPLETE_OR_HALTED_SESSION", "session_10_close_return": "INCOMPLETE_OR_HALTED_SESSION",
                          "session_20_close_return": "INCOMPLETE_OR_HALTED_SESSION"})
        view = ea.sealed_report(sealed_run(CXT, price_path(CXT_SESSIONS), actions=DIVIDEND))
        self.assertEqual(view["corporate_actions"], [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}])
        self.assertEqual({name: label["reason"] for name, label in view["session_labels"].items()},
                         {"session_2_close_return": None, "session_5_close_return": None, "session_10_close_return": None, "session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"})

    def test_an_unattested_event_is_quarantined_with_its_facts_and_no_labels_exist(self):
        report = sealed_run(CXT, price_path(CXT_SESSIONS), actions=DIVIDEND, attested=False)
        view = ea.sealed_report(report)
        self.assertEqual((view["state"], view["reasons"], view["session_labels"], view["labels_sha256"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], None, None))
        self.assertEqual((view["corporate_actions"], view["missing_sessions"], view["zero_volume_sessions"]), ([{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}], [], []))
        self.assertNotIn("labels_sha256", report)

    def test_a_pinned_commitment_is_checked_without_showing_anything_else(self):
        rows = price_path(SLSN_SESSIONS, gap=0.07)
        event = event_copy(SLSN)
        pinned = sealed_run(SLSN, rows)["labels_sha256"]
        event["recorded_result"] = {"labels_sha256": pinned, "recorded_in": PIN_RECORD}
        fetch = fetcher("SLSN", rows)
        matched = ea.sealed_report(ea.run_event(copy.deepcopy(event), SPEC["provider"], fetch, CAL, NOW, sealed=True))
        self.assertEqual((matched["labels_match_recorded"], matched["labels_sha256"], "error" in matched), (True, pinned, False))
        drifted = ea.sealed_report(ea.run_event(copy.deepcopy(event), SPEC["provider"], fetcher("SLSN", price_path(SLSN_SESSIONS, gap=0.08)), CAL, NOW, sealed=True))
        self.assertEqual((drifted["labels_match_recorded"], drifted["error"]), (False, "LABELS_DIFFER_FROM_RECORDED"))

    def test_unknown_reasons_errors_and_values_become_other_or_nothing(self):
        report = {"event_id": "e1", "ticker": "AAA", "access_check_passed": True,
                  "computed_outcome": {"state": "MAPPED", "reasons": ["NOT_POSITIVE_GAP_GE_0_5PCT", "FIRST_PUBLIC_TIME_UNVERIFIED", "7183.2941"],
                                       "session_labels": {"session_2_close_return": {"exists": False, "reason": "NOT_POSITIVE_GAP_GE_0_5PCT"},
                                                          "session_5_close_return": {"exists": False, "reason": "MISSING_SESSION"},
                                                          "session_10_close_return": {"exists": True, "reason": None}, "day1_close_return": {"exists": True, "reason": None}}},
                  "window": {"anchor_session": "2026-03-30", "reaction_session": "7183.2941", "release_timing": "7183.2941", "start": "2026-03-01", "end": "x", "asof": None, "required_sessions": "21"},
                  "missing_sessions": ["2026-03-30", "7183.2941"], "zero_volume_sessions": "2026-03-30",
                  "corporate_actions": [{"type": "cash 7183.2941", "ex_date": "7183.2941", "id": "a b"}, {"type": "forward_splits", "ex_date": "2026-03-30", "id": "x-1"}, {"type": "cash_dividends", "ex_date": "2026-03-31", "id": "1.5"}],
                  "labels_sha256": "7183.2941", "labels_match_recorded": "yes", "error": "DATA_VALIDATION_FAILED: invalid OHLCV 7183.2941"}
        view = ea.sealed_report(report)
        self.assertEqual(view["reasons"], ["OTHER", "FIRST_PUBLIC_TIME_UNVERIFIED", "OTHER"])
        self.assertEqual(view["session_labels"], {"session_2_close_return": {"exists": False, "reason": "OTHER"}, "session_5_close_return": {"exists": False, "reason": "MISSING_SESSION"},
                                                  "session_10_close_return": {"exists": True, "reason": None}})
        self.assertEqual(view["window"], {"anchor_session": "2026-03-30", "reaction_session": None, "release_timing": None, "start": "2026-03-01", "end": None, "asof": None, "required_sessions": None})
        self.assertEqual((view["missing_sessions"], view["zero_volume_sessions"]), (["2026-03-30"], []))
        self.assertEqual(view["corporate_actions"], [{"type": "OTHER", "ex_date": None, "id": None}, {"type": "forward_splits", "ex_date": "2026-03-30", "id": "x-1"},
                                                     {"type": "cash_dividends", "ex_date": "2026-03-31", "id": None}])
        self.assertEqual((view["labels_sha256"], view["labels_match_recorded"], view["error"]), (None, None, "DATA_VALIDATION_FAILED: OTHER"))
        self.assertNotIn("7183.2941", json.dumps(view))
        report["computed_outcome"]["state"] = "7183.2941"
        self.assertIsNone(ea.sealed_report(report)["state"])

    def test_a_sealed_run_sanitizes_its_error_where_it_arises(self):
        price = "7183.2941"

        def raising(exc):
            def fetch(endpoint, params):
                raise exc
            return fetch
        for exc, category in ((DataError("invalid OHLCV " + price), "DATA_VALIDATION_FAILED: OTHER"), (RuntimeError(price), "UNCATEGORIZED_RUNTIMEERROR"), (URLError(price), "NETWORK_ERROR")):
            report = ea.run_event(event_copy(SLSN), SPEC["provider"], raising(exc), CAL, NOW, sealed=True)
            self.assertEqual(report["error"], category)
            self.assertNotIn(price, json.dumps(report))
        report = ea.run_event(event_copy(SLSN, sealed=False), SPEC["provider"], raising(DataError("invalid OHLCV " + price)), CAL, NOW)       # the unsealed run keeps its message, as it always did
        self.assertEqual(report["error"], "DATA_VALIDATION_FAILED: invalid OHLCV " + price)

    def test_the_commitment_is_computed_the_way_the_recorded_pins_of_the_earlier_steps_were(self):
        checked = 0
        for event in SPEC["events"]:
            if "recorded_result" not in event:
                continue
            record = json.loads((ROOT / event["recorded_result"]["recorded_in"]).read_text(encoding="utf-8"))
            reasons = record.get("label_reasons", {"cxt-2026-02-11": {"session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"}}.get(event["event_id"], {}))
            labels = {name: {"value": value, "reason": reasons.get(name)} for name, value in record["computed_labels"].items()}
            self.assertEqual(ea.labels_digest({"labels": labels}), event["recorded_result"]["labels_sha256"], event["event_id"])
            checked += 1
        self.assertGreaterEqual(checked, 20)

    def test_error_categories_keep_only_what_no_price_can_be(self):
        for text, expected in (("ALPACA_HTTP_403", "ALPACA_HTTP_403"), ("ALPACA_HTTP_4031", "ERROR_OTHER"), ("NETWORK_ERROR", "NETWORK_ERROR"), ("INVALID_JSON_RESPONSE", "INVALID_JSON_RESPONSE"),
                               ("LABELS_DIFFER_FROM_RECORDED", "LABELS_DIFFER_FROM_RECORDED"), ("UNCATEGORIZED_RUNTIMEERROR", "UNCATEGORIZED_RUNTIMEERROR"),
                               ("UNCATEGORIZED_7183.2941", "ERROR_OTHER"), ("DATA_VALIDATION_FAILED: malformed bar record", "DATA_VALIDATION_FAILED: malformed bar record"),
                               ("DATA_VALIDATION_FAILED: not a supported session: 2026-04-03", "DATA_VALIDATION_FAILED: not a supported session: 2026-04-03"),
                               ("DATA_VALIDATION_FAILED: invalid OHLCV", "DATA_VALIDATION_FAILED: OTHER"), ("DATA_VALIDATION_FAILED: close 7183.2941", "DATA_VALIDATION_FAILED: OTHER"),
                               ("a bar closed at 7183.2941", "ERROR_OTHER"), ("", "ERROR_OTHER")):
            self.assertEqual(ea.sealed_error(text), expected, text)

    def test_the_reason_lists_cover_every_reason_the_label_engine_gives_except_the_gap_one(self):
        source = (ROOT / "nre" / "dataset.py").read_text(encoding="utf-8")
        given = (set(re.findall(r'stop\("([A-Z_0-9]+)"\)', source)) | set(re.findall(r'return "([A-Z_0-9]+)"', source)) | set(re.findall(r'label\(None, window, "([A-Z_0-9]+)"\)', source))
                 | set(re.findall(r'reason, window = "([A-Z_0-9]+)", \[\]', source)))
        self.assertIn("NOT_POSITIVE_GAP_GE_0_5PCT", given)
        self.assertEqual(given - {"NOT_POSITIVE_GAP_GE_0_5PCT"}, set(ea.EVENT_REASONS))
        self.assertLessEqual(ea.SESSION_LABEL_REASONS, ea.EVENT_REASONS)
        self.assertEqual(ea.SESSION_LABEL_REASONS, ea.QUALITY_REASONS | {"CALENDAR_OUT_OF_RANGE"})

    def test_the_view_realizes_the_protocol_s_lists(self):
        seal = PROTOCOL["seal"]
        may, never = seal["a_sealed_run_may_report"], seal["a_sealed_run_never_reports"]
        realized_by = [("event_id, ticker, release timing", {"event_id", "ticker", "window"}), ("the event's state and its event-level quarantine reasons", {"state", "reasons"}),
                       ("missing sessions and zero-volume sessions", {"missing_sessions", "zero_volume_sessions"}), ("corporate actions (type, ex-date, id)", {"corporate_actions"}),
                       ("the SHA-256 commitment of the event's labels, and whether it matches the pinned one", {"labels_sha256", "labels_match_recorded"}),
                       ("for each of session_2_close_return, session_5_close_return, session_10_close_return and session_20_close_return, only whether the label exists", {"session_labels"}),
                       ("counts of events by state", set())]
        self.assertEqual(len(may), len(realized_by))
        for item, (start, _) in zip(may, realized_by):
            self.assertTrue(item.startswith(start), item)
        keys = set().union(*(keys for _, keys in realized_by))
        self.assertEqual(keys | {"sealed", "access_check_passed", "error"}, set(ea.SEALED_REPORT_KEYS))                     # the three extras: that the view is sealed, that the provider answered, an error category
        self.assertEqual(seal["method"], ea.SEAL)
        self.assertEqual(len(never), 5)
        for item, start in zip(never, ("a label value, a price, a return", "whether any day-1 label", "the reason NOT_POSITIVE_GAP_GE_0_5PCT", "the times at which labels became available", "anything computed from a bar's open, high, low, close or volume")):
            self.assertTrue(item.startswith(start), item)
        names = [name for name in ea.LABEL_NAMES if name not in ea.SESSION_LABEL_NAMES]
        for gap in (-0.4, 0.4):
            text = json.dumps(ea.sealed_report(sealed_run(SLSN, price_path(SLSN_SESSIONS, gap=gap))))
            for name in names + ["available_at", "label_available", "NOT_POSITIVE_GAP"]:
                self.assertNotIn(name, text)


class _Response:
    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size=-1):
        return self._data


class _Opener:
    def __init__(self, responder):
        self._responder = responder

    def open(self, req, timeout=None):
        return _Response(self._responder(req.full_url))


def both_events(gap=0.07):
    def responder(url):
        cxt = "symbols=CXT" in url
        if "corporate-actions" in url:
            return json.dumps({"corporate_actions": DIVIDEND if cxt else {}, "next_page_token": None}).encode()
        ticker, sessions = ("CXT", CXT_SESSIONS) if cxt else ("SLSN", SLSN_SESSIONS)
        return json.dumps({"bars": {ticker: price_path(sessions, gap=gap)}, "next_page_token": None}).encode()
    return responder


class SealedMainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def spec_path(self, sealed=True, mark=True, attested=True, marked=(SLSN, CXT)):
        spec = copy.deepcopy(SPEC)
        spec["events"] = [event_copy(e, sealed=sealed and mark and e in marked, attested=attested) for e in (SLSN, CXT)]
        path = Path(self.tmp.name) / "spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return str(path)

    def run_main(self, argv, responder=None, env=ENV):
        stderr = io.StringIO()
        with patch.dict("os.environ", env, clear=True), patch("nre.event_acquire.build_opener", return_value=_Opener(responder or both_events())), \
             patch("builtins.print") as output, contextlib.redirect_stderr(stderr):
            code = ea.main(argv)
        return code, [call.args[0] for call in output.call_args_list], stderr.getvalue()

    def test_an_event_marked_sealed_refuses_to_run_without_the_flag_and_nothing_is_fetched(self):
        with patch.dict("os.environ", ENV, clear=True), patch("nre.event_acquire.build_opener") as opener, patch("builtins.print") as output:
            code = ea.main(["--spec", self.spec_path()])
        self.assertEqual(code, 2)
        opener.assert_not_called()
        printed = json.loads(output.call_args.args[0])
        self.assertIn("run it with --sealed", printed["error"])
        self.assertTrue(printed["error"].startswith("SPEC_INVALID: "))
        self.assertEqual(printed["events"], {})
        fetch = fetcher("SLSN", price_path(SLSN_SESSIONS))
        report = ea.run_event(event_copy(SLSN), SPEC["provider"], fetch, CAL, NOW)
        self.assertEqual((report["error"], fetch.calls), ("SEALED_EVENT_REQUIRES_SEALED_RUN", []))
        self.assertNotIn("computed_outcome", report)

    def test_one_marked_event_among_unmarked_ones_is_enough_to_refuse_an_unsealed_run(self):
        for marked in ((SLSN,), (CXT,)):
            with patch.dict("os.environ", ENV, clear=True), patch("nre.event_acquire.build_opener") as opener, patch("builtins.print") as output:
                code = ea.main(["--spec", self.spec_path(marked=marked)])
            self.assertEqual(code, 2, marked)
            opener.assert_not_called()
            self.assertIn("run it with --sealed", json.loads(output.call_args.args[0])["error"])
        code, printed, _ = self.run_main(["--spec", self.spec_path(marked=(CXT,)), "--event", SLSN])   # only the selected events count: the unmarked one may run unsealed
        self.assertEqual((code, list(json.loads(printed[0])["events"])), (0, [SLSN]))

    def test_the_flag_runs_a_marked_event_and_prints_only_the_sealed_view(self):
        code, printed, stderr = self.run_main(["--sealed", "--spec", self.spec_path()])
        self.assertEqual((code, len(printed), stderr), (0, 1, ""))
        out = json.loads(printed[0])
        self.assertEqual(set(out), {"all_ok", "sealed", "seal", "events", "counts_by_state"})
        self.assertEqual((out["all_ok"], out["sealed"], out["seal"], out["counts_by_state"]), (True, True, "hash_only", {"MAPPED": 2}))
        self.assertEqual(set(out["events"]), {SLSN, CXT})
        for view in out["events"].values():
            self.assertEqual(set(view), ea.SEALED_REPORT_KEYS - {"error"})
        self.assertEqual(out["events"][CXT]["session_labels"]["session_20_close_return"], {"exists": False, "reason": "CORPORATE_ACTION_IN_WINDOW"})

    def test_the_flag_also_works_on_a_spec_that_marks_nothing(self):
        code, printed, _ = self.run_main(["--sealed", "--spec", self.spec_path(mark=False)])
        self.assertEqual(code, 0)
        self.assertNotIn("computed_outcome", printed[0])

    def test_a_sealed_output_that_holds_a_decimal_or_the_gap_reason_is_refused_whole(self):
        base = {"event_id": SLSN, "ticker": "SLSN", "sealed": True, "state": "MAPPED"}
        for leak in ({"x": 0.0173}, {"reasons": ["NOT_POSITIVE_GAP_GE_0_5PCT"]}, {"session_labels": {"session_2_close_return": {"exists": "1.5"}}}):
            with patch("nre.event_acquire.sealed_report", return_value=dict(base, **leak)):
                code, printed, stderr = self.run_main(["--sealed", "--spec", self.spec_path()], env=dict(ENV, GITHUB_ACTIONS="true"))
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(printed[0]), {"all_ok": False, "sealed": True, "seal": "hash_only", "error": "SEALED_OUTPUT_REFUSED", "events": {}})
            self.assertEqual(len(printed), 2)
            self.assertTrue(printed[1].startswith("::error title=NRE sealed event acquisition::"))
            for text in printed + [stderr]:
                for leaked in ("0.0173", "NOT_POSITIVE", "1.5", "MAPPED"):
                    self.assertNotIn(leaked, text)

    def test_nothing_sensitive_reaches_stdout_or_a_github_annotation(self):
        rows = {"SLSN": price_path(SLSN_SESSIONS, gap=0.07), "CXT": price_path(CXT_SESSIONS, gap=0.07)}
        forbidden = set(ENV.values())
        for event_id, ticker in ((SLSN, "SLSN"), (CXT, "CXT")):
            forbidden |= fragments(rows[ticker], full_run(event_id, rows[ticker], actions=DIVIDEND if ticker == "CXT" else None))
        code, printed, stderr = self.run_main(["--sealed", "--spec", self.spec_path()], env=dict(ENV, GITHUB_ACTIONS="true"))
        self.assertEqual(code, 0)
        self.assertEqual(len(printed), 2)
        prefix = "::notice title=NRE sealed event acquisition::"
        self.assertTrue(printed[1].startswith(prefix))
        summary = json.loads(printed[1][len(prefix):])
        self.assertEqual((summary["all_ok"], summary["part"], set(summary["events"])), (True, "1/1", {SLSN, CXT}))
        self.assertEqual(summary["events"], json.loads(printed[0])["events"])
        text = "\n".join(printed) + stderr
        self.assertIsNone(re.search(r"\d\.\d", text))
        for fragment in forbidden:
            self.assertNotIn(fragment, text)
        for hidden in ("day1_", "gap_ge_", "positive_gap", "NOT_POSITIVE_GAP", "bundle_sha256", "bar_pages", "computed_outcome", "anchor_price"):
            self.assertNotIn(hidden, text)

    def test_a_failed_sealed_run_annotates_an_error_with_the_sealed_title(self):
        _, printed, _ = self.run_main(["--sealed", "--spec", self.spec_path()], env=dict(ENV, GITHUB_ACTIONS="true"), responder=lambda url: (_ for _ in ()).throw(URLError("down")))
        self.assertTrue(printed[-1].startswith("::error title=NRE sealed event acquisition::"))
        out = json.loads(printed[0])
        self.assertEqual({v["error"] for v in out["events"].values()}, {"NETWORK_ERROR"})
        self.assertEqual(out["counts_by_state"], {"NOT_RUN": 2})

    def test_errors_whose_text_could_hold_a_price_are_reported_by_category_only(self):
        price = "7183.2941"

        def raising(exc):
            def responder(url):
                raise exc
            return responder
        for exc, category in ((HTTPError("u", 422, "Unprocessable " + price, {}, None), "ALPACA_HTTP_422"), (URLError(price), "NETWORK_ERROR"),
                              (json.JSONDecodeError(price, price, 0), "INVALID_JSON_RESPONSE"), (RuntimeError(price), "UNCATEGORIZED_RUNTIMEERROR"),
                              (DataError("invalid OHLCV " + price), "DATA_VALIDATION_FAILED: OTHER"), (DataError("redirect rejected"), "DATA_VALIDATION_FAILED: redirect rejected")):
            code, printed, stderr = self.run_main(["--sealed", "--spec", self.spec_path()], raising(exc), env=dict(ENV, GITHUB_ACTIONS="true"))
            self.assertEqual(code, 2)
            out = json.loads(printed[0])
            self.assertEqual({v["error"] for v in out["events"].values()}, {category}, category)
            self.assertNotIn(price, "\n".join(printed) + stderr)

    def test_a_bar_that_fails_the_engine_s_own_validation_is_reported_without_saying_why(self):
        def responder(url):
            if "corporate-actions" in url:
                return json.dumps({"corporate_actions": {}, "next_page_token": None}).encode()
            rows = price_path(SLSN_SESSIONS)
            rows[3]["h"], rows[3]["l"] = 1.2345, 9999.8765                                 # high below low: the label engine refuses the bundle
            return json.dumps({"bars": {"SLSN": rows}, "next_page_token": None}).encode()
        code, printed, stderr = self.run_main(["--sealed", "--spec", self.spec_path(), "--event", SLSN], responder)
        self.assertEqual(code, 2)
        out = json.loads(printed[0])
        self.assertEqual(out["events"][SLSN]["error"], "DATA_VALIDATION_FAILED: OTHER")
        for number in ("1.2345", "9999.8765"):
            self.assertNotIn(number, printed[0] + stderr)

    def test_an_unexpected_exception_prints_neither_a_traceback_nor_its_message(self):
        price = "7183.2941"
        with patch("nre.event_acquire.sealed_report", side_effect=ValueError(price)):
            code, printed, stderr = self.run_main(["--sealed", "--spec", self.spec_path()])
        out = json.loads(printed[0])
        self.assertEqual(code, 2)
        self.assertEqual({v["error"] for v in out["events"].values()}, {"SEALED_REPORT_FAILED"})
        self.assertEqual(set(next(iter(out["events"].values()))), {"event_id", "ticker", "sealed", "error"})
        with patch("nre.event_acquire.run_event", side_effect=ValueError(price)):
            code, printed, stderr = self.run_main(["--sealed", "--spec", self.spec_path()])
        self.assertEqual((code, json.loads(printed[0])), (2, {"all_ok": False, "sealed": True, "seal": "hash_only", "error": "SEALED_RUN_FAILED"}))
        for text in (printed[0], stderr):
            self.assertNotIn(price, text)
            self.assertNotIn("Traceback", text)

    def test_an_invalid_spec_is_reported_before_anything_is_fetched(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with patch.dict("os.environ", ENV, clear=True), patch("nre.event_acquire.build_opener") as opener, patch("builtins.print") as output:
            code = ea.main(["--sealed", "--spec", str(bad)])
        self.assertEqual(code, 2)
        opener.assert_not_called()
        self.assertEqual(json.loads(output.call_args.args[0])["error"], "SPEC_INVALID: not valid JSON")
        spec = json.loads(Path(self.spec_path()).read_text(encoding="utf-8"))
        spec["events"][0]["seal"] = "open"
        path = Path(self.tmp.name) / "unsealed-word.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        with self.assertRaises(DataError):
            ea.validate_spec(spec, CAL)

    def test_an_unsealed_run_of_an_unmarked_spec_still_prints_the_full_report(self):
        code, printed, _ = self.run_main(["--spec", self.spec_path(sealed=False)])
        out = json.loads(printed[0])
        self.assertEqual((code, "sealed" in out), (0, False))
        self.assertIn("day1_close_return", out["events"][SLSN]["computed_outcome"]["labels"])


class SealedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_it_runs_only_the_sealed_command_on_the_phase_1b_events_with_the_two_provider_secrets(self):
        text = self.text
        self.assertIn('run: python -m nre.event_acquire --sealed --spec config/m5-phase1b-events.json --event "$EVENT_ID"', text)
        self.assertEqual(re.findall(r"^\s*run:", text, re.M).__len__(), 1)
        self.assertEqual(sorted(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text))), ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"])
        self.assertEqual(sorted(re.findall(r"^\s{10}([A-Z_]+):", text, re.M)), ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "EVENT_ID"])
        self.assertIn("EVENT_ID: ${{ inputs.event_id || 'all' }}", text)
        self.assertEqual(text.count("${{ inputs."), 1)                                         # the input reaches the command only as an environment variable, never inside the script text

    def test_it_runs_on_dispatch_and_on_a_push_of_the_events_file_only(self):
        header = self.text.split("permissions:")[0]
        self.assertIn("workflow_dispatch:", header)
        self.assertIn("event_id:", header)
        self.assertIn("push:\n    branches: [main]\n    paths:\n      - 'config/m5-phase1b-events.json'\n", header)
        self.assertEqual(re.findall(r"^      - '([^']+)'", header, re.M), ["config/m5-phase1b-events.json"])
        for absent in ("schedule:", "pull_request", "workflow_run", "nre/event_acquire.py", "m5-phase1b-event-acquire.yml'"):
            self.assertNotIn(absent, header)

    def test_it_can_leave_nothing_behind_that_holds_a_value(self):
        text = self.text
        self.assertRegex(text, r"permissions:\n  contents: read\njobs:")
        for absent in ("upload-artifact", "actions/cache", "download-artifact", " tee ", "| ", ">>", " > ", "set -x", "ACTIONS_STEP_DEBUG", "ACTIONS_RUNNER_DEBUG", "curl ", "wget ", "contents: write",
                       "git commit", "git push", "--calendar", "echo ", "cat "):
            self.assertNotIn(absent, text.replace("||", ""), absent)
        self.assertIn("timeout-minutes:", text)
        self.assertIn("python-version: '3.12'", text)

    def test_its_header_says_what_it_does_and_does_not_print(self):
        header = " ".join(line.lstrip("# ").strip() for line in self.text.split("\non:\n")[0].splitlines())
        for phrase in ("hash-only seal", "never a label value, a price, a return or a day-1 or gap label", "the SHA-256 commitment of its labels", "It uploads nothing and writes nothing."):
            self.assertIn(phrase, header)


if __name__ == "__main__":
    unittest.main()
