import copy
import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from nre.core import DataError, timestamp
from nre import m6_guidance_compare as scorer

ROOT = Path(__file__).resolve().parents[1]


def protocol():
    return json.loads((ROOT / "config/m6-guidance-protocol-v2.json").read_text(encoding="utf-8"))


def fixture():
    """Entirely synthetic prices-derived labels, with no repository market data."""
    p, events, labels, quality = protocol(), [], {}, {}
    p["held_rows_before_label_screen"] = 60  # Synthetic universe, separate from the real58.
    starts = [(None, date(2025, 1, 2), 24), ("2025-H2", date(2025, 7, 1), 20),
              ("2026-H1", date(2026, 1, 2), 20), ("2026-Q3", date(2026, 7, 1), 20)]
    for block, first, count in starts:
        for i in range(count):
            day = (first + timedelta(days=i)).isoformat()
            sign = 1 if i % 2 == 0 else -1
            magnitude = 0.1 if i % 4 < 2 else 0.2
            h = (0.2, -0.2, -0.2, 0.2)[i % 4]
            gap = sign * magnitude
            target = 0.03 + 0.01 * ((magnitude - 0.15) / 0.05) + 0.02 * sign + 0.04 * h / 0.2
            eid = f"synthetic-{block or 'warmup'}-{i:02d}"
            event = {"event_id": eid, "cik": f"synthetic-issuer-{i % 20:02d}",
                     "reaction_session": day, "feature_cutoff_at": day + "T13:15:00+00:00",
                     "revision_fraction": math.sinh(-sign * h)}
            if block:
                event["held_block"] = block
            events.append(event)
            labels[eid] = {"gap": gap, "close_return": (1 + gap) * (1 - sign * target) - 1,
                           "mature_at": day + "T21:05:00+00:00"}
            quality[eid] = {"hard_exclusions": [], "soft_caveats": []}
    return p, events, labels, quality


class GuidanceComparisonTests(unittest.TestCase):
    def test_target_definition_and_paired_missingness(self):
        event = {"event_id": "synthetic", "cik": "issuer", "reaction_session": "2025-01-02", "revision_fraction": 0.1}
        q = {"hard_exclusions": [], "soft_caveats": []}
        for gap, close, target in [(0.25, 0.0, 0.2), (-0.2, 0.0, 0.25), (0.25, 0.5, -0.2)]:
            row, reason = scorer.private_row(event, {"gap": gap, "close_return": close, "mature_at": "2025-01-02T21:05:00Z"}, q, clean=True)
            self.assertIsNone(reason)
            self.assertAlmostEqual(row["target"], target)
            self.assertAlmostEqual(row["guidance"], -(1 if gap > 0 else -1) * math.asinh(0.1))
        for gap, close in [(0, 0.1), (float("nan"), 0.1), (-1, 0.1), (0.1, -1), (0.1, float("inf"))]:
            with self.subTest(gap=gap, close=close):
                row, reason = scorer.private_row(event, {"gap": gap, "close_return": close, "mature_at": "2025-01-02T21:05:00Z"}, q, clean=True)
                self.assertIsNone(row)
                self.assertIsNotNone(reason)

    def test_exact_four_parameter_ridge_and_training_only_population_scaling(self):
        rows = []
        for magnitude, sign, h in [(0.1, 1, 0.2), (0.1, -1, -0.2), (0.2, 1, -0.2), (0.2, -1, 0.2)]:
            x1, x2, x3 = (magnitude - 0.15) / 0.05, sign, h / 0.2
            rows.append({"baseline": (magnitude, sign), "guidance": h,
                         "target": 0.03 + 0.01 * x1 + 0.02 * x2 + 0.04 * x3})
        baseline, challenger, dropped = scorer.fit_models_private(rows)
        self.assertEqual(dropped, {"baseline": [], "challenger": []})
        # Orthogonal standardized columns have X'X=4, so lambda=1 shrinks slopes by4/5.
        future = {"baseline": (0.3, 1), "guidance": 0.4}
        self.assertAlmostEqual(baseline(future), 0.03 + 0.8 * (0.01 * 3 + 0.02))
        self.assertAlmostEqual(challenger(future), 0.03 + 0.8 * (0.01 * 3 + 0.02 + 0.04 * 2))

    def test_full_block_cutoff_includes_a_hard_masked_earliest_event(self):
        p, events, labels, quality = fixture()
        first = next(e for e in events if e.get("held_block") == "2025-H2")
        quality[first["event_id"]]["hard_exclusions"] = ["synthetic-hard-source"]
        labels.pop(first["event_id"])
        boundary = first["feature_cutoff_at"]
        labels[events[0]["event_id"]]["mature_at"] = boundary
        labels[events[1]["event_id"]]["mature_at"] = "2025-07-01T13:16:00+00:00"
        fold = scorer.evaluate_fold_private(p, events, labels, quality, p["folds"][0], clean=True)
        self.assertEqual(fold["first_full_block_feature_cutoff"], timestamp(boundary).isoformat())
        self.assertEqual(fold["fit_support"]["rows"], 22)
        self.assertEqual(fold["fit_exclusions"], {"fit_label_not_mature": 2})
        self.assertEqual(fold["test_exclusions"], {"hard_source_exclusion": 1})
        self.assertEqual(fold["status"], "scored")
        predictions = {r["event_id"]: (r["baseline"], r["challenger"]) for r in fold["paired_rows"]}
        labels[events[0]["event_id"]]["close_return"] = 0.9
        labels[events[1]["event_id"]]["close_return"] = -0.9
        for event in events:
            if event.get("held_block") == "2025-H2" and event["event_id"] in labels:
                labels[event["event_id"]]["close_return"] = 0.95
        changed = scorer.evaluate_fold_private(p, events, labels, quality, p["folds"][0], clean=True)
        self.assertEqual(predictions, {r["event_id"]: (r["baseline"], r["challenger"]) for r in changed["paired_rows"]})
        self.assertNotEqual([r["target"] for r in fold["paired_rows"]], [r["target"] for r in changed["paired_rows"]])

    def test_constant_guidance_cannot_be_dropped_and_called_a_comparison(self):
        p, events, labels, quality = fixture()
        for event in events:
            if "held_block" not in event:
                event["revision_fraction"] = 0
        result = scorer.compare(p, events, labels, quality)
        self.assertEqual(result["decision"], scorer.INSUFFICIENT)
        for report in result["reports"].values():
            self.assertEqual(report["folds"][0]["status"], "insufficient_support")
            self.assertEqual(report["folds"][0]["paired_rows"], 0)

    def test_sensitivity_cannot_replace_insufficient_clean_training(self):
        p, events, labels, quality = fixture()
        for event in events[:6]:
            quality[event["event_id"]]["soft_caveats"] = ["synthetic-soft-source"]
        result = scorer.compare(p, events, labels, quality)
        clean, sensitivity = (result["reports"][key] for key in ("clean_window", "all_defined"))
        self.assertEqual(clean["folds"][0]["fit_support"]["rows"], 18)
        self.assertEqual(sensitivity["folds"][0]["fit_support"]["rows"], 24)
        self.assertEqual(sensitivity["folds"][0]["status"], "scored")
        self.assertEqual(result["decision"], scorer.INSUFFICIENT)

    def test_public_result_contains_aggregates_and_membership_hashes_only(self):
        p, events, labels, quality = fixture()
        held = [e for e in events if e.get("held_block") == "2025-H2"]
        labels[held[0]["event_id"]]["gap"] = 0
        labels[held[1]["event_id"]]["close_return"] = None
        quality[held[2]["event_id"]]["hard_exclusions"] = ["synthetic-hard-source"]
        result = scorer.compare(p, events, labels, quality)
        self.assertEqual(result["decision"], scorer.PASS)
        for report in result["reports"].values():
            first = report["folds"][0]
            self.assertEqual(first["paired_rows"], 17)
            self.assertEqual(first["test_exclusions"], {"zero_opening_gap": 1, "close_unavailable": 1, "hard_source_exclusion": 1})
            self.assertEqual(report["summary"]["counts"]["paired_rows"], 57)
            self.assertRegex(first["pair_membership_sha256"], r"^[0-9a-f]{64}$")

        def check(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & {"event_id", "target", "gap", "close_return", "predictions", "coefficients", "price"})
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(result)
        self.assertTrue(all(e["event_id"] not in json.dumps(result) for e in events))

    def test_bootstrap_uses_fixed_forecasts_and_outer_endpoints(self):
        p = protocol()
        pairs = [{"event_id": f"synthetic-{i}", "issuer": f"issuer-{i % 2}",
                  "reaction_session": f"2025-07-0{i+1}", "gap_sign": 1 if i % 2 else -1,
                  "revision_sign": 1 if i % 2 else -1, "target": 0.1,
                  "baseline": 0, "challenger": 0.05} for i in range(4)]
        calls = []

        def bootstrap(differences, clusters, seed, replicates, levels):
            calls.append((list(differences), list(clusters), seed, replicates, levels))
            interval = [0.1, 0.9] if seed == 640001 else [-0.2, 0.1]
            return {"estimate": 0.0075, "intervals": {"0.99": interval}, "seed": seed}

        with patch.object(scorer.m4_metrics, "cluster_bootstrap", side_effect=bootstrap):
            summary = scorer.summarize_private([{"paired_rows": pairs}], p)
        self.assertEqual(summary["interval_99"], [-0.2, 0.9])
        self.assertEqual({c[2] for c in calls}, {640001, 640002})
        self.assertTrue(all(c[3:] == (5000, (0.99,)) for c in calls))
        self.assertTrue(all(all(abs(d - 0.0075) < 1e-15 for d in c[0]) for c in calls))

    def test_exact_decision_thresholds_and_every_support_floor(self):
        p = protocol()
        summary = {"counts": {"paired_rows": 40, "issuers": 15, "sessions": 20, "up_gaps": 10,
                               "down_gaps": 10, "folds_with_minimum_pairs": 2, "raises": 1, "cuts": 1},
                   "relative_mse_reduction": 0.05, "interval_99": [1e-12, 0.1], "mean_improvement": 0.0}
        report = {"folds": [{"status": "scored"}] * 3, "summary": summary}
        self.assertEqual(scorer.decide(report, report, p), scorer.PASS)
        for field in ["paired_rows", "issuers", "sessions", "up_gaps", "down_gaps", "folds_with_minimum_pairs", "raises", "cuts"]:
            changed = copy.deepcopy(report)
            changed["summary"]["counts"][field] -= 1
            with self.subTest(field=field):
                self.assertEqual(scorer.decide(changed, report, p), scorer.INSUFFICIENT)
        changed = copy.deepcopy(report)
        changed["summary"]["interval_99"][0] = 0
        self.assertEqual(scorer.decide(changed, report, p), scorer.NOT_MET)
        changed = copy.deepcopy(report)
        changed["summary"]["relative_mse_reduction"] = 0.05 - 1e-12
        self.assertEqual(scorer.decide(changed, report, p), scorer.NOT_MET)
        changed = copy.deepcopy(report)
        changed["summary"]["mean_improvement"] = -1e-15
        self.assertEqual(scorer.decide(report, changed, p), scorer.NOT_MET)
        changed = copy.deepcopy(report)
        changed["folds"][0] = {"status": "insufficient_support"}
        self.assertEqual(scorer.decide(report, changed, p), scorer.INSUFFICIENT)

    def test_membership_clusters_and_model_settings_fail_before_fit(self):
        p, events, labels, quality = fixture()
        with patch.object(scorer.m4_models, "fit_ridge", side_effect=AssertionError("model fitted")):
            changed = copy.deepcopy(p)
            changed["models"]["ridge_penalty"] = 0.5
            with self.assertRaisesRegex(DataError, "model settings"):
                scorer.compare(changed, events, labels, quality)
            missing = copy.deepcopy(quality)
            missing.pop(events[-1]["event_id"])
            with self.assertRaisesRegex(DataError, "membership"):
                scorer.compare(p, events, labels, missing)
            changed_events = copy.deepcopy(events)
            changed_events[-1]["cluster_id"] = changed_events[0]["event_id"]
            with self.assertRaisesRegex(DataError, "economic cluster"):
                scorer.compare(p, changed_events, labels, quality)
            missing_event = events[-1]
            with self.assertRaisesRegex(DataError, "complete frozen held membership"):
                scorer.compare(p, events[:-1], {k: v for k, v in labels.items() if k != missing_event["event_id"]},
                               {k: v for k, v in quality.items() if k != missing_event["event_id"]})
