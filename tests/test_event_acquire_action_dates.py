"""Option (A) of the Milestone 5 Phase 1b batch 1 signoff (reports/m5-phase1b-batch1-signoff-2026-10-09.json): an action Alpaca gives no ex_date (a merger carries effective, payable and process dates instead) is dated by the first of those it has,
the label engine suppresses the labels it crosses exactly as for any action, the entry says which field the date came from, and an action with none of the dates still fails closed. The sealed view names the field, and only one of the three known
names, when the date is not an ex-date; nothing else of the item (a rate, a symbol, a ratio) passes through. Everything here is simulated: no Alpaca answer for any real issuer is used or assumed."""
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

from nre import event_acquire as ea
from nre.calendar import Calendar
from nre.core import DataError

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads(ea.DEFAULT_SPEC.read_text(encoding="utf-8"))
BATCH_1 = json.loads((ROOT / "config" / "m5-phase1b-events.json").read_text(encoding="utf-8"))
CAL = Calendar()
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
CXT, NBIX = "cxt-2026-02-11", "nbix-m5b-2026-05-05"
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}
RATE = 5127.3319                                                                       # stands for any rate, price or ratio a merger item carries
SESSIONS = ["2026-02-11", "2026-02-12", "2026-02-13", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
            "2026-02-23", "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27", "2026-03-02", "2026-03-03",
            "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12"]
MISSING, NOT_A_DATE = "corporate action missing ex_date", "corporate action ex_date is not a date"
SUPPRESSED = "CORPORATE_ACTION_IN_WINDOW"


def price_path(sessions, anchor=7183.2941, gap=0.07, day1=0.0173, drift=0.0013):
    """Distinctive prices with four decimals. Session 0 is the anchor; session 1 the reaction day; later sessions drift."""
    rows, previous = [], anchor
    for i, session in enumerate(sessions):
        if i == 0:
            o, c = anchor * 0.9961, anchor
        elif i == 1:
            o = anchor * (1 + gap)
            c = o * (1 + day1)
        else:
            o, c = previous, previous * (1 + drift)
        rows.append({"t": session + "T00:00:00Z", "o": round(o, 4), "h": round(max(o, c) * 1.0111, 4), "l": round(min(o, c) * 0.9877, 4), "c": round(c, 4), "v": 1000003 + 7919 * i})
        previous = c
    return rows


def fetcher(ticker, rows, actions):
    def fetch(endpoint, params):
        if endpoint == ea.ACTIONS_ENDPOINT:
            return json.dumps({"corporate_actions": actions, "next_page_token": None}).encode()
        return json.dumps({"bars": {ticker: rows}, "next_page_token": None}).encode()
    return fetch


def cxt_event(sealed=False):
    event = copy.deepcopy(next(e for e in SPEC["events"] if e["event_id"] == CXT))
    event.pop("recorded_result", None)
    if sealed:
        event["seal"] = ea.SEAL
    return event


def run_cxt(actions, sealed=False):
    return ea.run_event(cxt_event(sealed), SPEC["provider"], fetcher("CXT", price_path(SESSIONS), actions), CAL, NOW, sealed=sealed)


def reasons(report):
    """Each session-return label's reason, from an unsealed report (labels) or a sealed one (session_labels); empty when the event itself was stopped (a date on the reaction day stops the day-1 label and so the event)."""
    outcome = report["computed_outcome"]
    labels = outcome["labels"] if "labels" in outcome else outcome["session_labels"]
    return {name: labels[name]["reason"] for name in ea.SESSION_LABEL_NAMES if name in (labels or {})}


def outcome_of(report):
    return {"state": report["computed_outcome"]["state"], "reasons": report["computed_outcome"]["reasons"], "labels": reasons(report)}


class FetchActionsTests(unittest.TestCase):
    def actions(self, payload):
        return ea.fetch_actions(lambda p: json.dumps({"corporate_actions": payload, "next_page_token": None}).encode(), {})[0]

    def test_an_ex_date_is_used_exactly_as_before_whatever_other_dates_the_item_carries(self):
        item = {"ex_date": "2026-02-27", "id": "abc", "effective_date": "2026-03-05", "payable_date": "2026-03-06", "process_date": "2026-03-04", "rate": 0.18}
        self.assertEqual(self.actions({"cash_dividends": [item]}), [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}])

    def test_the_dates_an_item_does_not_use_are_never_examined(self):
        for others in ({"effective_date": "soon", "payable_date": 5, "process_date": ["2026-05-18"]}, {"effective_date": "", "payable_date": None}, {"process_date": "2026-13-45"}):
            with self.subTest(others=others):
                self.assertEqual(self.actions({"cash_dividends": [dict(others, ex_date="2026-02-27", id="abc")]}), [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}])
        self.assertEqual(self.actions({"cash_mergers": [{"effective_date": "2026-05-18", "payable_date": "soon", "process_date": 5, "id": "m-1"}]}),
                         [{"type": "cash_mergers", "ex_date": "2026-05-18", "id": "m-1", "date_field": "effective_date"}])

    def test_an_action_without_an_ex_date_takes_the_first_of_its_effective_payable_and_process_dates_and_names_it(self):
        dates = {"effective_date": "2026-05-18", "payable_date": "2026-05-19", "process_date": "2026-05-20"}
        for absent, expected in (((), ("2026-05-18", "effective_date")), (("effective_date",), ("2026-05-19", "payable_date")), (("effective_date", "payable_date"), ("2026-05-20", "process_date"))):
            with self.subTest(absent=absent):
                item = dict({k: v for k, v in dates.items() if k not in absent}, id="m-1", cash_rate=RATE)
                self.assertEqual(self.actions({"cash_mergers": [item]}), [{"type": "cash_mergers", "ex_date": expected[0], "id": "m-1", "date_field": expected[1]}])

    def test_a_null_date_counts_as_absent_so_the_next_field_dates_the_action(self):
        for item, field in (({"ex_date": None, "effective_date": "2026-05-18"}, "effective_date"), ({"ex_date": None, "effective_date": None, "payable_date": "2026-05-18"}, "payable_date"),
                            ({"ex_date": None, "effective_date": None, "payable_date": None, "process_date": "2026-05-18"}, "process_date")):
            with self.subTest(field=field):
                self.assertEqual(self.actions({"cash_mergers": [item]}), [{"type": "cash_mergers", "ex_date": "2026-05-18", "id": None, "date_field": field}])

    def test_an_action_with_none_of_the_dates_still_fails_closed_with_the_same_message(self):
        nulls = {"ex_date": None, "effective_date": None, "payable_date": None, "process_date": None}
        other_dates = {"record_date": "2026-05-18", "declaration_date": "2026-05-01", "expiration_date": "2026-05-20", "due_bill_on_date": "2026-05-17"}          # only the four named fields date an action
        for item in ({"id": "m-1", "cash_rate": RATE}, {}, nulls, other_dates, dict(nulls, **other_dates), "x", 5, None, ["2026-05-18"]):
            with self.subTest(item=item), self.assertRaises(DataError) as caught:
                self.actions({"cash_mergers": [item]})
            self.assertEqual(str(caught.exception), MISSING)

    def test_a_date_that_is_present_but_unusable_is_an_error_and_never_a_reason_to_try_the_next_one(self):
        cases = (({"effective_date": "soon", "payable_date": "2026-05-19"}, NOT_A_DATE), ({"effective_date": "", "payable_date": "2026-05-19"}, NOT_A_DATE),
                 ({"payable_date": "2026-13-45", "process_date": "2026-05-19"}, NOT_A_DATE), ({"ex_date": "soon", "effective_date": "2026-05-18"}, NOT_A_DATE),
                 ({"effective_date": 20260518, "payable_date": "2026-05-19"}, MISSING), ({"effective_date": ["2026-05-18"], "process_date": "2026-05-19"}, MISSING),
                 ({"ex_date": 20260227, "effective_date": "2026-05-18"}, MISSING))
        for item, message in cases:
            with self.subTest(item=item), self.assertRaises(DataError) as caught:
                self.actions({"cash_mergers": [item]})
            self.assertEqual(str(caught.exception), message)

    def test_several_actions_each_keep_their_own_date_and_field(self):
        payload = {"cash_dividends": [{"ex_date": "2026-02-27", "id": "d-1"}, {"ex_date": "2026-03-13", "id": "d-2"}], "reverse_splits": [{"ex_date": "2026-04-01", "id": "s-1"}],
                   "cash_mergers": [{"effective_date": "2026-05-18", "id": "m-1"}, {"process_date": "2026-05-20", "id": "m-2"}]}
        self.assertEqual(self.actions(payload), [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "d-1"}, {"type": "cash_dividends", "ex_date": "2026-03-13", "id": "d-2"},
                                                 {"type": "reverse_splits", "ex_date": "2026-04-01", "id": "s-1"},
                                                 {"type": "cash_mergers", "ex_date": "2026-05-18", "id": "m-1", "date_field": "effective_date"},
                                                 {"type": "cash_mergers", "ex_date": "2026-05-20", "id": "m-2", "date_field": "process_date"}])

    def test_an_action_on_a_later_page_is_read_the_same_way(self):
        pages = iter([{"corporate_actions": {"cash_dividends": [{"ex_date": "2026-02-27", "id": "d-1"}]}, "next_page_token": "t1"},
                      {"corporate_actions": {"cash_mergers": [{"effective_date": "2026-05-18", "id": "m-1"}]}, "next_page_token": None}])
        entries, recorded = ea.fetch_actions(lambda p: json.dumps(next(pages)).encode(), {})
        self.assertEqual(entries, [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "d-1"}, {"type": "cash_mergers", "ex_date": "2026-05-18", "id": "m-1", "date_field": "effective_date"}])
        self.assertEqual(len(recorded), 2)


class SuppressionTests(unittest.TestCase):
    def test_a_merger_dated_by_its_effective_date_suppresses_the_labels_it_crosses_and_the_run_lists_it(self):
        report = run_cxt({"cash_mergers": [{"effective_date": "2026-02-27", "id": "m-1", "cash_rate": RATE}]})
        self.assertNotIn("error", report)
        self.assertEqual(report["corporate_actions"], [{"type": "cash_mergers", "ex_date": "2026-02-27", "id": "m-1", "date_field": "effective_date"}])
        self.assertEqual(report["computed_outcome"]["state"], "MAPPED")
        self.assertEqual(reasons(report), {"session_2_close_return": None, "session_5_close_return": None, "session_10_close_return": None, "session_20_close_return": SUPPRESSED})

    def test_it_gives_the_labels_a_dividend_with_that_date_would_give_whichever_session_of_the_window_the_date_is(self):
        patterns = set()
        for day in SESSIONS:
            with self.subTest(day=day):
                merger = run_cxt({"cash_mergers": [{"effective_date": day, "id": "x"}]})
                dividend = run_cxt({"cash_dividends": [{"ex_date": day, "id": "x"}]})
                self.assertEqual(outcome_of(merger), outcome_of(dividend))
                self.assertEqual(merger["computed_outcome"]["labels"], dividend["computed_outcome"]["labels"])
                self.assertEqual(merger.get("labels_sha256"), dividend.get("labels_sha256"))
                patterns.add(json.dumps(outcome_of(merger), sort_keys=True))
        self.assertGreaterEqual(len(patterns), 4)                              # the windows differ from date to date, so this compares something

    def test_a_payable_or_process_date_dates_an_action_with_no_effective_date_the_same_way(self):
        for field in ("payable_date", "process_date"):
            with self.subTest(field=field):
                report = run_cxt({"cash_mergers": [{field: "2026-02-27", "id": "m-1"}]})
                self.assertEqual(report["corporate_actions"], [{"type": "cash_mergers", "ex_date": "2026-02-27", "id": "m-1", "date_field": field}])
                self.assertEqual(reasons(report), {"session_2_close_return": None, "session_5_close_return": None, "session_10_close_return": None, "session_20_close_return": SUPPRESSED})

    def test_an_action_with_no_usable_date_stops_the_run_before_any_label_exists_and_the_sealed_run_says_so_in_the_same_words(self):
        for payload, message in (({"cash_mergers": [{"id": "m-1", "cash_rate": RATE}]}, MISSING), ({"cash_mergers": [{"effective_date": "soon"}]}, NOT_A_DATE)):
            for sealed in (False, True):
                with self.subTest(message=message, sealed=sealed):
                    report = run_cxt(payload, sealed=sealed)
                    self.assertEqual((report["error"], report["access_check_passed"], report["labels_computed"]), ("DATA_VALIDATION_FAILED: " + message, False, False))
                    self.assertNotIn("computed_outcome", report)
                    self.assertNotIn("5127.3319", json.dumps(report))


class SealedViewTests(unittest.TestCase):
    def test_the_sealed_view_names_the_date_field_only_when_the_date_is_not_an_ex_date(self):
        payload = {"cash_dividends": [{"ex_date": "2026-03-02", "id": "d-1"}], "cash_mergers": [{"effective_date": "2026-02-27", "id": "m-1"}]}
        view = ea.sealed_report(run_cxt(payload, sealed=True))
        self.assertEqual(view["corporate_actions"], [{"type": "cash_dividends", "ex_date": "2026-03-02", "id": "d-1"}, {"type": "cash_mergers", "ex_date": "2026-02-27", "id": "m-1", "date_field": "effective_date"}])
        self.assertEqual(ea.sealed_report(run_cxt(payload)), view)           # the unsealed run reduces to the same view

    def test_a_field_name_the_pipeline_does_not_know_never_reaches_the_view(self):
        base = {"event_id": "x", "ticker": "T"}
        shown = ("effective_date", "payable_date", "process_date")
        for name in shown + ("ex_date", "7183.2941", "", None, "Effective_date", "effective_date ", ["effective_date"], {"effective_date": 1}, 5, "cash_rate"):
            with self.subTest(name=name):
                action = {"type": "cash_mergers", "ex_date": "2026-05-18", "id": "m-1", "date_field": name, "cash_rate": RATE, "acquirer_symbol": "ZZZZ"}
                entry = ea.sealed_report(dict(base, corporate_actions=[action]))["corporate_actions"][0]
                self.assertEqual(set(entry), {"type", "ex_date", "id"} | ({"date_field"} if name in shown else set()))
                if name in shown:
                    self.assertEqual(entry["date_field"], name)
                self.assertNotIn("5127.3319", json.dumps(entry))

    def test_nothing_else_of_the_item_reaches_a_report_a_sealed_report_or_a_view(self):
        item = {"effective_date": "2026-02-27", "id": "m-1", "cash_rate": RATE, "rate": 1.2345, "acquirer_symbol": "ZZZZ", "acquiree_symbol": "YYYY"}
        sealed = run_cxt({"cash_mergers": [item]}, sealed=True)
        for text in (json.dumps(sealed), json.dumps(ea.sealed_report(sealed)), json.dumps(ea.sealed_report(run_cxt({"cash_mergers": [item]})))):
            for leaked in ("5127.3319", "1.2345", "ZZZZ", "YYYY", "cash_rate", "acquirer", "acquiree"):
                self.assertNotIn(leaked, text)
            self.assertIsNone(re.search(r"\d\.\d", text))


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


class SealedMainTests(unittest.TestCase):
    def test_a_sealed_run_over_a_merger_item_full_of_decimals_prints_the_view_and_the_tripwire_stays_quiet(self):
        item = {"effective_date": "2026-02-27", "id": "m-1", "cash_rate": RATE, "rate": 1.2345, "acquirer_symbol": "ZZZZ"}

        def responder(url):
            if "corporate-actions" in url:
                return json.dumps({"corporate_actions": {"cash_mergers": [item]}, "next_page_token": None}).encode()
            return json.dumps({"bars": {"CXT": price_path(SESSIONS)}, "next_page_token": None}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            spec = copy.deepcopy(SPEC)
            spec["events"] = [cxt_event(sealed=True)]
            path = Path(tmp) / "spec.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            stderr = io.StringIO()
            with patch.dict("os.environ", ENV, clear=True), patch("nre.event_acquire.build_opener", return_value=_Opener(responder)), patch("builtins.print") as output, contextlib.redirect_stderr(stderr):
                code = ea.main(["--sealed", "--spec", str(path)])
        printed = [call.args[0] for call in output.call_args_list]
        self.assertEqual((code, len(printed), stderr.getvalue()), (0, 1, ""))
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"MAPPED": 1}))
        self.assertEqual(out["events"][CXT]["corporate_actions"], [{"type": "cash_mergers", "ex_date": "2026-02-27", "id": "m-1", "date_field": "effective_date"}])
        self.assertEqual(out["events"][CXT]["session_labels"]["session_20_close_return"], {"exists": False, "reason": SUPPRESSED})
        for leaked in ("5127.3319", "1.2345", "ZZZZ", "AKTESTKEY123", "SECRETVALUE456", "7183.2941"):
            self.assertNotIn(leaked, printed[0])


class MergerShapedItemOnTheBatch1Nbix(unittest.TestCase):
    """The shipped batch 1 file's NBIX event with a made-up, merger-shaped item. What Alpaca really returned for NBIX is not known to this test (the sealed view could not show it); the item stands for any merger that has no ex_date."""

    ITEM = {"effective_date": "2026-05-18", "payable_date": "2026-05-19", "id": "m-1", "cash_rate": RATE}

    def run_nbix(self, attested):
        event = copy.deepcopy(next(e for e in BATCH_1["events"] if e["event_id"] == NBIX))
        event.pop("recorded_result", None)                                          # a made-up history cannot match a pinned commitment
        if attested:
            event["attestations"] = {name: {"reviewer": "test", "date": "2026-10-09", "record": "none"} for name in sorted(ea.ATTESTATIONS)}
        else:
            event.pop("attestations", None)
        window = ea.event_window(event, CAL)
        report = ea.run_event(event, BATCH_1["provider"], fetcher("NBIX", price_path(window["required_sessions"]), {"cash_mergers": [self.ITEM]}), CAL, NOW, sealed=True)
        return window, ea.sealed_report(report)

    def test_unattested_it_runs_lists_the_item_and_quarantines_on_the_attestation_alone(self):
        _, view = self.run_nbix(attested=False)
        self.assertEqual((view["state"], view["reasons"], view["access_check_passed"], view["missing_sessions"], view["zero_volume_sessions"], "error" in view), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], True, [], [], False))
        self.assertEqual(view["corporate_actions"], [{"type": "cash_mergers", "ex_date": "2026-05-18", "id": "m-1", "date_field": "effective_date"}])
        self.assertIsNone(view["labels_sha256"])

    def test_attested_in_memory_it_suppresses_exactly_the_labels_the_item_crosses(self):
        window, view = self.run_nbix(attested=True)
        self.assertEqual((view["state"], view["reasons"]), ("MAPPED", []))
        reaction = window["reaction_session"]
        expected = {"session_%d_close_return" % n: (SUPPRESSED if window["anchor_session"] < "2026-05-18" <= CAL.offset(reaction, n - 1) else None) for n in (2, 5, 10, 20)}
        self.assertEqual({name: label["reason"] for name, label in view["session_labels"].items()}, expected)
        self.assertEqual(expected, {"session_2_close_return": None, "session_5_close_return": None, "session_10_close_return": SUPPRESSED, "session_20_close_return": SUPPRESSED})   # the test compares something


if __name__ == "__main__":
    unittest.main()
