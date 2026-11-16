import math
import unittest
from datetime import datetime, timedelta, timezone

from nre.m6_revenue import evaluate_fold, revenue_feature


def at(day, hour, minute=0):
    return datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc)


def event(event_id, day, gap, close, *, maturity=None):
    return {
        "event_id": event_id,
        "cluster_id": event_id,
        "cik": f"issuer-{event_id}",
        "reaction_session": at(day, 0).date().isoformat(),
        "cutoff": at(day, 12),
        "available_at": {"day1_close_return": maturity or at(day, 21)},
        "labels": {
            "day1_open_return": {"value": gap},
            "day1_close_return": {"value": close},
        },
    }


class RevenueComparisonTests(unittest.TestCase):
    def test_revenue_must_be_available_strictly_before_the_feature_cutoff(self):
        cutoff = at(7, 14, 15)
        release = {"status": "usable", "growth_fraction": -0.25, "current_usd": 75, "prior_usd": 100}
        for seconds, expected in [(-1, (math.asinh(-0.25), None)),
                                  (0, (None, "revenue_at_or_after_cutoff")),
                                  (1, (None, "revenue_at_or_after_cutoff"))]:
            with self.subTest(seconds=seconds):
                available = (cutoff + timedelta(seconds=seconds)).isoformat()
                row = {"scheduled_open": dict(release, availability_proxy=available)}
                self.assertEqual(revenue_feature(row, cutoff), expected)
        self.assertEqual(revenue_feature({"scheduled_open": {"status": "no_eligible_filing"}}, cutoff),
                         (None, "revenue_unavailable"))

    def test_fold_uses_mature_matched_rows_and_ignores_held_out_closes_when_predicting(self):
        rows = [event("fit-up", 1, 0.10, 0.20),
                event("fit-down", 2, -0.12, -0.05),
                event("fit-up-again", 3, 0.21, 0.25),
                event("fit-missing-revenue", 4, -0.05, -0.30),
                event("fit-at-boundary", 5, -0.17, -0.06, maturity=at(7, 14, 15)),
                event("fit-after-boundary", 6, 0.08, 0.18, maturity=at(7, 14, 16)),
                event("test-up", 7, 0.15, 0.05),
                event("test-down", 8, -0.08, -0.03),
                event("test-missing-revenue", 9, 0.15, 0.05)]
        blocks, features = {}, {}
        for i, row in enumerate(rows, start=1):
            event_id = row["event_id"]
            missing = event_id.endswith("missing-revenue")
            blocks[event_id] = 1 if i < 7 else 3
            features[event_id] = {
                "cutoff": at(i, 14, 15),
                "context": None if missing else math.asinh((i - 2) / 10),
                "revenue_exclusion": "revenue_unavailable" if missing else None,
                "source": None if missing else "original_wire",
            }

        result = evaluate_fold(rows, blocks, features, 3, 3)
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["fit_rows"], 3)
        self.assertEqual(result["fit_exclusions"], {"revenue_unavailable": 1, "fit_label_not_mature": 2})
        self.assertEqual(result["test_exclusions"], {"revenue_unavailable": 1})
        pairs = {row["event_id"]: row for row in result["paired_rows"]}
        self.assertEqual(set(pairs), {"test-up", "test-down"})
        for row in pairs.values():
            self.assertFalse(row["baseline_fallback"])
            self.assertTrue(math.isfinite(row["baseline"]))
            self.assertTrue(math.isfinite(row["challenger"]))

        # Changing an excluded training target must affect neither model's fit.
        rows[3]["labels"]["day1_close_return"]["value"] = 0.50
        rows[4]["labels"]["day1_close_return"]["value"] = 0.50
        rows[5]["labels"]["day1_close_return"]["value"] = 0.50
        rows[6]["labels"]["day1_close_return"]["value"] = 0.50
        revised = evaluate_fold(rows, blocks, features, 3, 3)["paired_rows"]
        for row in revised:
            original = pairs[row["event_id"]]
            self.assertEqual(row["baseline"], original["baseline"])
            self.assertEqual(row["challenger"], original["challenger"])
            if row["event_id"] == "test-up":
                self.assertNotEqual(row["target"], original["target"])
            else:
                self.assertEqual(row["target"], original["target"])

        insufficient = evaluate_fold(rows, blocks, features, 3, 4)
        self.assertEqual(insufficient["fit_rows"], 3)
        self.assertNotEqual(insufficient["status"], "scored")
        self.assertFalse(insufficient["paired_rows"])
