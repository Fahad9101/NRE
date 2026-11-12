"""Phase 1c must use complete pre-cutoff windows and keep holdout values sealed."""
import json
import unittest
from datetime import date, datetime
from pathlib import Path

from nre import event_acquire as ea
from nre import m5_phase1c as features
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


class Phase1cTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_hash, cls.calendar, cls.cohorts = features.load_inputs(ROOT)

    def test_frozen_cohorts_and_identity_windows(self):
        self.assertEqual({key: len(events) for key, events in self.cohorts.items()},
                         {"development": 128, "holdout": 43})
        for events in self.cohorts.values():
            for event in events:
                _, issuer, regime = features.event_windows(event, self.calendar)
                cutoff = datetime.fromisoformat(event["cutoff"]).astimezone(self.calendar.zone)
                self.assertTrue(all(date.fromisoformat(day) < cutoff.date() for day in issuer + regime))
                self.assertEqual(len(regime), 21)
                self.assertTrue(all(self.calendar.bounds(day)[0] >= datetime.fromisoformat(
                    event["security"]["valid_from"]) for day in issuer))

    def test_bar_validation_requires_exact_sessions_and_resolved_actions(self):
        days = ("2026-04-20", "2026-04-21")
        bars = {"X": {day: {"close": 100, "volume": 10} for day in days}}
        self.assertIsNone(features.validated_window("X", days, 2, ("close",), (bars, {}, {}))[1])
        self.assertEqual(features.validated_window("X", days, 3, ("close",), (bars, {}, {}))[1],
                         "insufficient_history")
        self.assertEqual(features.validated_window("X", days, 2, ("close",), (bars, {"X": {days[0]}}, {}))[1],
                         "corporate_action")
        self.assertEqual(features.validated_window("X", days, 2, ("close",),
                                                  (bars, {}, {"X": [days]}))[1], "unverified_actions")
        bars["X"][days[-1]]["volume"] = 0
        self.assertEqual(features.validated_window("X", days, 2, ("volume",), (bars, {}, {}))[1],
                         "invalid_bar")
        del bars["X"][days[-1]]
        self.assertEqual(features.validated_window("X", days, 2, ("close",), (bars, {}, {}))[1],
                         "missing_session")

    def test_feature_formulas(self):
        rows = [{"close": 100, "high": 105, "low": 95, "volume": 10}] * 252
        self.assertEqual(features.structure_value("return_5", rows[-6:]), 0)
        self.assertEqual(features.structure_value("rv_20", rows[-21:]), 0)
        self.assertAlmostEqual(features.structure_value("atr_14_fraction", rows[-15:]), 0.1)
        self.assertEqual(features.structure_value("adv_20", rows[-20:]), 1000)
        self.assertEqual(features.structure_value("rvol_20", rows[-21:]), 1)
        self.assertAlmostEqual(features.structure_value("distance_252_high", rows), 100 / 105 - 1)
        changed = rows[-21:-1] + [dict(rows[-1], close=110, volume=20)]
        self.assertAlmostEqual(features.structure_value("return_5", changed[-6:]), 0.1)
        self.assertEqual(features.structure_value("rvol_20", changed), 2)

    def test_full_acquisition_outputs_only_development_and_holdout_commitment(self):
        def fetch(endpoint, params):
            symbol = params["symbols"]
            if endpoint == ea.ACTIONS_ENDPOINT:
                return canonical({"corporate_actions": {}, "next_page_token": None})
            self.assertEqual(endpoint, ea.BARS_ENDPOINT)
            self.assertEqual((params["feed"], params["adjustment"], params["asof"]), ("sip", "raw", "-"))
            start, end = params["start"][:10], params["end"][:10]
            return canonical({"bars": {symbol: [
                {"t": day + "T05:00:00Z", "o": 41.23456789, "h": 111.25, "l": 88.25, "c": 100, "v": 10}
                for day in self.calendar.days if start <= day <= end]}, "next_page_token": None})

        development, summary = features.build_output(self.protocol_hash, self.calendar, self.cohorts, fetch)
        self.assertEqual(summary["counts"], {"development": 128, "holdout": 43})
        self.assertEqual(summary["development_sha256"], digest(canonical(development)))
        self.assertRegex(summary["holdout_features_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(all(set(row["features"]) == set(features.FEATURES) for row in development["events"]))
        text = json.dumps([development, summary])
        self.assertNotIn("41.23456789", text)
        for event in self.cohorts["holdout"]:
            self.assertNotIn(event["event_id"], text)
        self.assertEqual(summary["coverage"]["holdout"]["spy_return_20"], {"available": 43})
