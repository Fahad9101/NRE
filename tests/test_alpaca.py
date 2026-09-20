import copy
import unittest
from nre.alpaca import audit_daily
from nre.core import DataError


def payload():
    return {"tool": "get_stock_bars", "request": {
        "symbols": ["TEST"], "timeframe": "1Day", "feed": "sip",
        "start": "2026-03-06", "end": "2026-03-09", "asof": "2026-03-06",
        "tz": "America/New_York", "sort": "asc", "currency": None},
        "counts": {"symbols": 1, "records": 2, "per_symbol": {"TEST": 2}},
        "bars": {"TEST": [{"symbol": "TEST", "timestamp": t, "open": 10,
            "high": 11, "low": 9, "close": 10, "volume": 100}
            for t in ["2026-03-06T05:00:00Z", "2026-03-09T04:00:00Z"]]}}


class AlpacaAuditTests(unittest.TestCase):
    def audit(self, p):
        return audit_daily(p, "2026-09-20T06:00:00Z")

    def test_dst_complete_but_not_accepted(self):
        result = self.audit(payload())
        self.assertEqual(result["coverage"]["TEST"]["missing_sessions"], [])
        self.assertFalse(result["accepted_for_labels"])
        self.assertIn("REGULAR_SESSION_VOLUME_UNVERIFIED", result["blockers"])

    def test_missing_first_session_not_hidden(self):
        p = payload()
        p["bars"]["TEST"].pop(0)
        p["counts"]["records"] = p["counts"]["per_symbol"]["TEST"] = 1
        r = self.audit(p)
        self.assertEqual(r["coverage"]["TEST"]["missing_sessions"], ["2026-03-06"])

    def test_missing_symbol_not_hidden(self):
        p = payload()
        p["request"]["symbols"].append("MISSING")
        self.assertEqual(self.audit(p)["coverage"]["MISSING"]["received"], 0)

    def test_zero_volume_requires_review(self):
        p = payload()
        p["bars"]["TEST"][0]["volume"] = 0
        self.assertIn("ZERO_VOLUME_SESSIONS", self.audit(p)["blockers"])

    def test_bad_request_rejected(self):
        for key, value in [("feed", "iex"), ("asof", None), ("asof", "2027-01-01"),
                           ("timeframe", "1Min"), ("currency", "EUR"),
                           ("start", "2025-12-31"), ("end", "2026-03-01"),
                           ("sort", "desc"), ("symbols", ["TEST", "TEST"])]:
            with self.subTest(key=key, value=value), self.assertRaises(DataError):
                p = payload()
                p["request"][key] = value
                self.audit(p)

    def test_bad_bars_rejected(self):
        for key, value in [("timestamp", "2026-03-09T05:00:00Z"),
                           ("timestamp", "2026-03-09T00:00:00"),
                           ("timestamp", "2026-03-10T04:00:00Z"),
                           ("symbol", "OTHER"), ("volume", -1), ("open", True),
                           ("close", float("nan")), ("high", 8)]:
            with self.subTest(key=key, value=value), self.assertRaises(DataError):
                p = payload()
                p["bars"]["TEST"][1][key] = value
                self.audit(p)

    def test_duplicate_and_reordered_bars_rejected(self):
        for duplicate in (True, False):
            p = payload()
            if duplicate:
                p["bars"]["TEST"][1] = copy.deepcopy(p["bars"]["TEST"][0])
            else:
                p["bars"]["TEST"].reverse()
            with self.assertRaises(DataError):
                self.audit(p)

    def test_count_disagreement_rejected(self):
        p = payload()
        p["counts"]["records"] = 3
        with self.assertRaises(DataError):
            self.audit(p)

    def test_unclosed_window_rejected(self):
        with self.assertRaises(DataError):
            audit_daily(payload(), "2026-03-09T19:59:00Z")


if __name__ == "__main__":
    unittest.main()
