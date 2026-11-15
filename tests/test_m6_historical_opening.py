import json
import unittest
from pathlib import Path

from nre import m6_historical_opening as probe


class HistoricalOpeningTests(unittest.TestCase):
    def test_only_prior_anchor_and_bounded_listing_venue_open_are_used(self):
        pin = probe.load(probe.V1)["development"]["events"]
        event = probe.load(pin["path"])["events"][0]
        calendar = probe.Calendar(probe.load("config/m2-merged-calendar-2024-2026.json"))
        requests = []

        def fetch(endpoint, params):
            requests.append((endpoint, params))
            symbol = event["security"]["ticker"]
            if endpoint == probe.ea.BARS_ENDPOINT:
                self.assertEqual(params["start"][:10], "2026-03-30")
                self.assertEqual(params["end"][:10], "2026-03-30")
                return probe.canonical({"bars": {symbol: [{"t": "2026-03-30T04:00:00Z",
                                    "o": 90, "h": 110, "l": 90, "c": 100, "v": 10}]},
                                   "next_page_token": None})
            self.assertEqual(endpoint, probe.TRADES.format(symbol))
            self.assertEqual(params["start"], "2026-03-31T13:30:00+00:00")
            self.assertEqual(params["end"], "2026-03-31T13:31:00+00:00")
            official = {"x": "Q", "z": "C", "c": ["Q"], "i": 1, "p": 115,
                        "t": "2026-03-31T13:30:00.123456789Z"}
            if "page_token" not in params:
                return probe.canonical({"symbol": symbol, "trades": [dict(official, c=["O"])],
                                   "next_page_token": "next"})
            return probe.canonical({"symbol": symbol, "trades": [official, dict(official, x="N"),
                              dict(official, t=params["end"])], "next_page_token": None})

        gap, reason = probe.sample(event, calendar, fetch)
        self.assertIsNone(reason)
        self.assertAlmostEqual(gap, .15)
        self.assertEqual(len(requests), 3)

    def test_full_cohort_summary_uses_fixed_selectors_and_contains_counts_only(self):
        from unittest.mock import patch

        with patch.object(probe, "sample", return_value=(.15, None)):
            report = probe.run(Path("."), None)
        self.assertEqual(sum(report["dispositions"].values()), 128)
        self.assertEqual(report["discordant"], report["dispositions"]["verified_open"])
        self.assertEqual(report["allocations"][0]["tail"], -1)
        self.assertEqual(report["allocations"][0]["magnitude"], 0)
        self.assertFalse(report["receipt_latency_verified"])
        self.assertNotIn(".15", json.dumps(report))

    def test_threshold_equality_and_signed_disagreement(self):
        reference = probe.load(probe.V1)["planning_evidence"]
        threshold = probe.load(probe.V2)["comparator"]["threshold"]
        self.assertEqual(probe.selections(.15, reference, threshold), (-1, 0))
        self.assertEqual(probe.selections(-.17, reference, threshold), (0, 1))
        self.assertEqual(probe.selections(-threshold, reference, threshold), (0, 0))
