import json
import unittest
from unittest.mock import patch
from nre.cxt_acquire import fetch_bars, fetch_actions, build_bundle, main, REQUIRED_SESSIONS
from nre.core import DataError
from nre.dataset import build


def _bar(session, o=10.0, h=10.5, l=9.5, c=10.2, v=1000):
    return {"t": session + "T00:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}


class FetchBarsTests(unittest.TestCase):
    def test_single_page(self):
        def fetch(params):
            return json.dumps({"bars": {"CXT": [_bar("2026-02-11"), _bar("2026-02-12")]},
                                "next_page_token": None}).encode()
        by_session, pages = fetch_bars(fetch)
        self.assertEqual(set(by_session), {"2026-02-11", "2026-02-12"})

    def test_unexpected_symbol_rejected(self):
        def fetch(params):
            return json.dumps({"bars": {"OTHER": []}, "next_page_token": None}).encode()
        with self.assertRaises(DataError):
            fetch_bars(fetch)


class FetchActionsTests(unittest.TestCase):
    def test_empty_dict_shape(self):
        def fetch(params):
            return json.dumps({"corporate_actions": {}, "next_page_token": None}).encode()
        entries, pages = fetch_actions(fetch)
        self.assertEqual(entries, [])

    def test_extracts_type_and_ex_date(self):
        # Shape confirmed against CXT's real corporate-actions response
        # (reports/m1-cxt-acquisition-result-2026-09-23.json follow-up):
        # {"corporate_actions": {"cash_dividends": [{"ex_date": "...", ...}]}}
        def fetch(params):
            return json.dumps({"corporate_actions": {"cash_dividends": [
                {"ex_date": "2026-02-27", "id": "abc", "rate": 0.18}]},
                "next_page_token": None}).encode()
        entries, pages = fetch_actions(fetch)
        self.assertEqual(entries, [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}])

    def test_missing_ex_date_fails_closed(self):
        def fetch(params):
            return json.dumps({"corporate_actions": {"cash_dividends": [{"rate": 0.18}]},
                                "next_page_token": None}).encode()
        with self.assertRaises(DataError):
            fetch_actions(fetch)


class BuildBundleTests(unittest.TestCase):
    def test_no_actions_maps_everything(self):
        bars = {s: {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1000}
                for s in REQUIRED_SESSIONS}
        bundle = build_bundle(bars, actions=[])
        results, report = build(bundle)
        outcome = results[0]
        self.assertEqual(outcome["state"], "MAPPED")
        self.assertEqual(outcome["release_timing"], "after_hours")
        self.assertEqual(outcome["reaction_session"], "2026-02-12")
        self.assertEqual(report["complete_20_session"], 1)

    def test_real_dividend_suppresses_only_session_20(self):
        # The real CXT dividend (ex_date 2026-02-27) falls after session_10's
        # window (ends 2026-02-26) but inside session_20's (ends 2026-03-12) --
        # confirmed by direct calendar computation before writing this test,
        # not assumed. Day-1 through session_10 must still compute; only
        # session_20 should be suppressed.
        bars = {s: {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1000}
                for s in REQUIRED_SESSIONS}
        actions = [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": "abc"}]
        bundle = build_bundle(bars, actions)
        results, report = build(bundle)
        outcome = results[0]
        self.assertEqual(outcome["state"], "MAPPED")
        self.assertIsNone(outcome["labels"]["day1_close_return"]["reason"])
        self.assertIsNone(outcome["labels"]["session_2_close_return"]["reason"])
        self.assertIsNone(outcome["labels"]["session_5_close_return"]["reason"])
        self.assertIsNone(outcome["labels"]["session_10_close_return"]["reason"])
        self.assertEqual(outcome["labels"]["session_20_close_return"]["reason"], "CORPORATE_ACTION_IN_WINDOW")
        self.assertIsNone(outcome["labels"]["session_20_close_return"]["value"])

    def test_action_id_falls_back_when_missing(self):
        bars = {s: {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1000}
                for s in REQUIRED_SESSIONS}
        actions = [{"type": "cash_dividends", "ex_date": "2026-02-27", "id": None}]
        bundle = build_bundle(bars, actions)
        self.assertEqual(bundle["corporate_actions"][0]["action_id"], "cash_dividends-2026-02-27")

    def test_missing_session_quarantines(self):
        bars = {s: {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1000}
                for s in REQUIRED_SESSIONS if s != "2026-02-12"}
        bundle = build_bundle(bars, actions=[])
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

    def test_full_run_with_real_dividend_still_computes_short_horizon_labels(self):
        def responder(url):
            if "corporate-actions" in url:
                return json.dumps({"corporate_actions": {"cash_dividends": [
                    {"ex_date": "2026-02-27", "id": "abc", "rate": 0.18}]},
                    "next_page_token": None}).encode()
            bars = {"CXT": [_bar(s) for s in REQUIRED_SESSIONS]}
            return json.dumps({"bars": bars, "next_page_token": None}).encode()

        env = {"APCA_API_KEY_ID": "id", "APCA_API_SECRET_KEY": "secret"}
        with patch.dict("os.environ", env, clear=True), \
             patch("nre.cxt_acquire.build_opener", return_value=_FakeOpener(responder)), \
             patch("builtins.print") as output:
            code = main()
            printed = json.loads(output.call_args.args[0])
            self.assertEqual(code, 0)
            self.assertTrue(printed["labels_computed"])
            outcome = printed["computed_outcome"]
            self.assertEqual(outcome["state"], "MAPPED")
            self.assertIsNone(outcome["labels"]["day1_close_return"]["reason"])
            self.assertEqual(outcome["labels"]["session_20_close_return"]["reason"], "CORPORATE_ACTION_IN_WINDOW")
            self.assertNotIn("price", outcome["anchor"])


if __name__ == '__main__':
    unittest.main()
