import json
import unittest
from unittest.mock import patch
from nre.slsn_acquire import fetch_bars, fetch_actions, build_bundle, main, REQUIRED_SESSIONS
from nre.core import DataError
from nre.dataset import build


def _bar(session, o=10.0, h=10.5, l=9.5, c=10.2, v=1000):
    return {"t": session + "T00:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}


class FetchBarsTests(unittest.TestCase):
    def test_single_page(self):
        def fetch(params):
            return json.dumps({"bars": {"SLSN": [_bar("2026-03-30"), _bar("2026-03-31")]},
                                "next_page_token": None}).encode()
        by_session, pages = fetch_bars(fetch)
        self.assertEqual(set(by_session), {"2026-03-30", "2026-03-31"})
        self.assertEqual(len(pages), 1)

    def test_duplicate_session_rejected(self):
        def fetch(params):
            return json.dumps({"bars": {"SLSN": [_bar("2026-03-30"), _bar("2026-03-30")]},
                                "next_page_token": None}).encode()
        with self.assertRaises(DataError):
            fetch_bars(fetch)

    def test_unexpected_symbol_rejected(self):
        def fetch(params):
            return json.dumps({"bars": {"OTHER": []}, "next_page_token": None}).encode()
        with self.assertRaises(DataError):
            fetch_bars(fetch)


class FetchActionsTests(unittest.TestCase):
    def test_empty_dict_shape(self):
        def fetch(params):
            return json.dumps({"corporate_actions": {}, "next_page_token": None}).encode()
        count, pages = fetch_actions(fetch)
        self.assertEqual(count, 0)

    def test_counts_entries_across_types(self):
        def fetch(params):
            return json.dumps({"corporate_actions": {"cash_dividends": [{"a": 1}], "splits": []},
                                "next_page_token": None}).encode()
        count, pages = fetch_actions(fetch)
        self.assertEqual(count, 1)

    def test_missing_pagination_metadata_rejected(self):
        def fetch(params):
            return json.dumps({"corporate_actions": {}}).encode()
        with self.assertRaises(DataError):
            fetch_actions(fetch)


class BuildBundleTests(unittest.TestCase):
    def test_full_window_quarantined_on_provider_rights_not_silently_completed(self):
        bars = {s: {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1000}
                for s in REQUIRED_SESSIONS}
        bundle = build_bundle(bars, actions_count=0)
        results, report = build(bundle)
        self.assertEqual(len(results), 1)
        outcome = results[0]
        # quality() on the base [anchor, reaction] window runs before any label
        # is computed; provider["research_permitted"]=False fails it there, so
        # the whole event quarantines with an empty labels dict -- it must not
        # silently reach MAPPED just because real, complete data was fetched.
        self.assertEqual(outcome["state"], "QUARANTINED")
        self.assertEqual(outcome["reasons"], ["PROVIDER_USE_UNVERIFIED"])
        self.assertEqual(outcome["labels"], {})
        self.assertEqual(report["complete_20_session"], 0)
        self.assertEqual(report["mapped_day1"], 0)

    def test_nonempty_corporate_actions_marks_bars_unverified(self):
        bars = {s: {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1000}
                for s in REQUIRED_SESSIONS}
        bundle = build_bundle(bars, actions_count=1)
        for p in bundle["prices"]:
            self.assertFalse(p["corporate_actions_verified"])

    def test_missing_session_quarantines_before_provider_check(self):
        bars = {s: {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1000}
                for s in REQUIRED_SESSIONS if s != "2026-03-31"}
        bundle = build_bundle(bars, actions_count=0)
        results, report = build(bundle)
        self.assertEqual(results[0]["state"], "QUARANTINED")
        self.assertEqual(results[0]["reasons"], ["MISSING_SESSION"])


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


class MainTests(unittest.TestCase):
    def test_no_credentials_no_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("builtins.print") as output:
            self.assertEqual(main(), 2)
            self.assertIn("MISSING_GITHUB_ACTIONS_SECRETS", output.call_args.args[0])

    def test_full_run_reports_provider_rights_blocker_not_fabricated_success(self):
        def responder(url):
            if "corporate-actions" in url:
                return json.dumps({"corporate_actions": {}, "next_page_token": None}).encode()
            bars = {"SLSN": [_bar(s) for s in REQUIRED_SESSIONS]}
            return json.dumps({"bars": bars, "next_page_token": None}).encode()

        env = {"APCA_API_KEY_ID": "id", "APCA_API_SECRET_KEY": "secret"}
        with patch.dict("os.environ", env, clear=True), \
             patch("nre.slsn_acquire.build_opener", return_value=_FakeOpener(responder)), \
             patch("builtins.print") as output:
            code = main()
            printed = json.loads(output.call_args.args[0])
            self.assertEqual(code, 0)
            self.assertTrue(printed["access_check_passed"])
            self.assertFalse(printed["labels_computed"])
            self.assertEqual(printed["corporate_actions_count"], 0)
            self.assertEqual(printed["missing_sessions"], [])
            # No raw OHLCV numbers anywhere in the printed report, including
            # the anchor's close price, which build() embeds as the return
            # denominator and main() must redact before printing.
            self.assertNotIn('"open": 10.0', output.call_args.args[0])
            self.assertNotIn("price", printed["computed_outcome"]["anchor"])


if __name__ == '__main__':
    unittest.main()
