"""Independent arithmetic and leakage checks on synthetic Phase 2 inputs."""
import random
import unittest
from datetime import date, timedelta
from pathlib import Path

from nre import m5_harness as harness, m5_models as models
from nre.m5_phase1b_audit import load
from nre.m5_phase1c import FEATURES

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = load(ROOT / "config/m5-protocol.json")


def fixtures(n=100):
    events, daily = [], {}
    for i in range(n):
        day = (date(2025, 1, 1) + timedelta(days=i * 2)).isoformat()
        key = f"fixture-{i}"
        events.append({"event_id": key, "cluster_id": key, "issuer": str(i % 11),
                       "reaction_session": day, "release_timing": "premarket",
                       "clock": day + "T13:00:00Z", "maturity": day + "T21:01:00Z",
                       "outcome_end": day + "T21:00:00Z", "outcome": i % 2})
        daily[key] = {feature: float(i % 2) for feature in FEATURES}
    return events, daily


class Models(unittest.TestCase):
    def test_tree_bootstrap_and_boosting_against_direct_arithmetic(self):
        rows = [{"x": i} for i in range(10)]
        y = [0] * 5 + [1] * 5
        grid = dict(PROTOCOL["models"]["grid"], boosting_rounds=1)
        stump = models.tree(rows, y, 1, 5, True)
        self.assertEqual(stump.threshold, 4.5)
        self.assertEqual([stump(row) for row in rows], y)
        model = models.boosting(rows, y, 1, grid, True)
        self.assertAlmostEqual(model(rows[0]), 0.4875026035157896)
        self.assertAlmostEqual(model(rows[-1]), 0.5124973964842103)
        rng = random.Random(77)
        expected = []
        for _ in range(32):
            sample = rng.choices(range(10), k=10)
            rng.sample(["x"], 1)
            ordered = sorted(sample)
            left = sum(y[i] for i in ordered[:5])
            right = sum(y[i] for i in ordered[5:])
            can_split = ordered[4] < ordered[5] and left != right
            expected.append(right / 5 if can_split else (left + right) / 10)
        self.assertAlmostEqual(models.forest(rows, y, 1, grid, 77)(rows[-1]), sum(expected) / 32)

    def test_calibration_constraint_and_residual_quantiles(self):
        model, state = models.platt([0.8] * 6 + [0.2] * 6, [0] * 6 + [1] * 6, 5)
        self.assertEqual(state, "CALIBRATED")
        self.assertEqual((model(0.1), model(0.9)), (0.5, 0.5))
        quantiles = models.quantiles(lambda _: 10, [None] * 3, [0, 10, 20])
        self.assertEqual(quantiles(None), (2, 10, 18))


class Harness(unittest.TestCase):
    def test_connected_clusters_are_whole_and_unmatured_rows_are_purged(self):
        events, _ = fixtures()
        events[0]["cluster_id"] = events[-1]["cluster_id"]
        events[1]["reaction_session"] = events[0]["reaction_session"]
        fit, select, calibration, test = harness.partitions(events[:80], events[80:])
        self.assertEqual(len(select), 12)
        self.assertEqual(len(calibration), 12)
        self.assertEqual({events[0]["event_id"], events[1]["event_id"]} &
                         {e["event_id"] for e in fit + select + calibration}, set())
        self.assertEqual(len(test), 22)
        self.assertFalse(harness.eligible_before([events[0]], harness.timestamp(events[0]["maturity"])))

    def test_future_labels_and_features_do_not_change_earlier_predictions(self):
        events, daily = fixtures()
        target = PROTOCOL["targets"][0]
        first = harness.run_fold(PROTOCOL, target, "fixture", events[:80], events[80:], daily)
        self.assertEqual(first["status"], "EVALUABLE")
        self.assertEqual(len(first["selection"]), 14)
        self.assertEqual(len(first["predictions"]), 20)
        self.assertEqual(set(first["predictions"][0]["ablations"]), set(harness.FAMILIES))
        events[-1]["outcome"] = 1 - events[-1]["outcome"]
        daily[events[-1]["event_id"]]["return_5"] = -500.0
        second = harness.run_fold(PROTOCOL, target, "fixture", events[:80], events[80:], daily)
        self.assertEqual(first["selection"], second["selection"])
        self.assertEqual(first["predictions"][:-1], second["predictions"][:-1])
        self.assertEqual(second, harness.run_fold(PROTOCOL, target, "fixture", events[:80], events[80:], daily))

    def test_immature_history_is_ignored(self):
        events, daily = fixtures()
        prior = dict(events[2], maturity=events[7]["clock"])
        first = harness.row_for(events[7], events[:2] + [prior], daily, "B")
        self.assertEqual(first, harness.row_for(events[7], events[:2] + [dict(prior, outcome=999)], daily, "B"))
        self.assertNotIn("open_gap", first[0])

    def test_regression_fold_and_reporting_on_fixture(self):
        events, daily = fixtures()
        target = next(t for t in PROTOCOL["targets"] if t["kind"] == "regression")
        for i, event in enumerate(events):
            event["outcome"] = i / 100
        fold = harness.run_fold(PROTOCOL, target, "fixture", events[:80], events[80:], daily)
        self.assertEqual(fold["status"], "EVALUABLE")
        replay = harness.run_fold(PROTOCOL, target, "fixture", events[:80], events[80:], daily, fold["choices"])
        self.assertEqual(replay["predictions"], fold["predictions"])
        summary = harness.summarize_development(PROTOCOL, target,
                                                {"clean_window": [fold], "all_event": [replay]})
        self.assertEqual(summary["clean_window"]["status"], "EVALUABLE")
        self.assertEqual(summary["clean_window"]["counts"]["events"], 20)
        self.assertFalse(summary["development_gate_passed"])
        self.assertEqual(set(fold["permutation_importance"]), {"after_hours", "issuer_history", "analogue", *FEATURES})

    def test_binary_report_and_nested_caps(self):
        events, daily = fixtures()
        target = PROTOCOL["targets"][0]
        fold = harness.run_fold(PROTOCOL, target, "fixture", events[:80], events[80:], daily)
        result = harness.summarize_development(PROTOCOL, target, {"clean_window": [fold], "all_event": [fold]})
        self.assertIn("pooled:10", result["clean_window"]["secondary"]["precision_at_k"])
        high = dict(fold["predictions"][0], candidate=0.9, baseline=0.8)
        low = dict(high, candidate=0.3, baseline=0.4)
        adjusted, caps = harness.monotonic_sensitivity([low], [high])
        self.assertEqual(caps, {"candidate": 1, "baseline": 1})
        self.assertEqual((adjusted[0]["candidate"], adjusted[0]["baseline"]), (0.3, 0.4))
        self.assertEqual(high["candidate"], 0.9)

    def test_artifact_verifier_rejects_a_mutated_archive(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as work:
            path = Path(work) / "artifact.zip"
            path.write_bytes(b"modified archive")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                harness.verify_artifact(path, ROOT)

    def test_c0_opening_gap_is_used_only_by_c0(self):
        events, daily = fixtures()
        event = dict(events[-1], open_gap=0.04)
        self.assertEqual(harness.row_for(event, events[:-1], daily, "C0")[0]["open_gap"], 0.04)
        self.assertNotIn("open_gap", harness.row_for(event, events[:-1], daily, "B")[0])
