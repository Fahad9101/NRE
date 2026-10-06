"""The Milestone 4 metrics, intervals and decision rule on small cases computed by hand. Pure functions: no events, no folds, no data."""
import math
import re
import unittest
from pathlib import Path

from nre import fingerprints as fp
from nre import m4_metrics as m
from nre import m4_protocol as pr

ROOT = Path(__file__).resolve().parent.parent


class ScoreTests(unittest.TestCase):
    def test_brier_is_the_mean_squared_probability_error(self):
        self.assertAlmostEqual(m.brier([0.8, 0.2, 0.5], [True, False, True]), (0.04 + 0.04 + 0.25) / 3)
        self.assertEqual(m.brier([1.0, 0.0], [True, False]), 0.0)
        self.assertEqual(m.brier([0.0, 1.0], [True, False]), 1.0)

    def test_log_loss_is_clipped_at_the_protocols_bounds(self):
        self.assertAlmostEqual(m.log_loss([0.8, 0.2], [True, False]), -math.log(0.8))
        self.assertAlmostEqual(m.log_loss([0.0], [True]), -math.log(1e-6))
        self.assertAlmostEqual(m.log_loss([1.0], [False]), -math.log(1e-6))
        self.assertTrue(math.isfinite(m.log_loss([0.0, 1.0], [True, False])))

    def test_average_precision_known_values(self):
        self.assertAlmostEqual(m.average_precision([0.9, 0.8, 0.7, 0.6], [True, False, True, False]), 0.5 + 0.5 * 2 / 3)
        self.assertEqual(m.average_precision([0.9, 0.8, 0.1], [True, True, False]), 1.0)
        self.assertAlmostEqual(m.average_precision([0.1, 0.2, 0.9], [True, True, False]), 0.5 * 0.5 + 0.5 * 2 / 3)  # recall 0.5 at precision 1/2, then 1 at 2/3

    def test_average_precision_of_tied_scores_is_the_base_rate_whatever_the_order(self):
        for outcomes in ([True, False, False, True], [False, True, True, False], [True, True, False, False]):
            self.assertAlmostEqual(m.average_precision([0.3] * 4, outcomes), 0.5)

    def test_average_precision_needs_a_positive(self):
        with self.assertRaises(ValueError):
            m.average_precision([0.1, 0.2], [False, False])

    def test_precision_at_k_takes_the_highest_scores_and_breaks_ties_by_key(self):
        scores, outcomes, keys = [0.9, 0.8, 0.7, 0.6, 0.5], [True, False, True, False, True], list("abcde")
        self.assertAlmostEqual(m.precision_at_k(scores, outcomes, keys, 3), 2 / 3)
        self.assertEqual(m.precision_at_k([0.5, 0.5, 0.5], [False, True, False], ["c", "a", "b"], 1), 1.0)  # key 'a' comes first
        self.assertEqual(m.precision_at_k([0.5, 0.5, 0.5], [False, True, False], ["c", "z", "b"], 1), 0.0)  # key 'b' comes first
        self.assertEqual(m.ranked([0.2, 0.9, 0.2], ["x", "y", "a"]), [1, 2, 0])


class RandomRankingTests(unittest.TestCase):
    def test_a_random_ranking_is_seeded_and_centred_on_the_base_rate(self):
        outcomes = [i < 6 for i in range(30)]  # 20% positive
        keys = ["e%02d" % i for i in range(30)]
        first = m.random_precision_at_k(outcomes, keys, 10, 410003)
        again = m.random_precision_at_k(outcomes, keys, 10, 410003)
        other = m.random_precision_at_k(outcomes, keys, 10, 410004)
        self.assertEqual(first, again)
        self.assertNotEqual(first["mean"], other["mean"])
        self.assertEqual(first["rankings"], pr.RANDOM_RANKINGS)
        self.assertAlmostEqual(first["mean"], 0.2, delta=0.02)
        self.assertLess(first["low"], first["mean"])
        self.assertGreater(first["high"], first["mean"])

    def test_the_ranking_does_not_depend_on_the_order_the_events_are_given_in(self):
        outcomes = [True, False, True, False, False, True, False, False, True, False]
        keys = list("abcdefghij")
        forward = m.random_precision_at_k(outcomes, keys, 4, 1, rankings=200)
        order = list(range(9, -1, -1))
        backward = m.random_precision_at_k([outcomes[i] for i in order], [keys[i] for i in order], 4, 1, rankings=200)
        self.assertEqual(forward, backward)

    def test_only_random_dot_random_is_used_because_its_stream_is_stable_across_python_versions(self):
        source = (ROOT / "nre" / "m4_metrics.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\.(randrange|randint|shuffle|sample|choice|choices|gauss|uniform)\(", source))
        self.assertIn("rng.random()", source)


class BinSummaryTests(unittest.TestCase):
    def test_reliability_bins_are_equal_frequency_and_at_most_four(self):
        for n, sizes in ((45, [12, 11, 11, 11]), (30, [10, 10, 10]), (25, [13, 12]), (10, [10]), (80, [20, 20, 20, 20])):
            scores = [i / n for i in range(n)]
            result = m.reliability(scores, [i % 3 == 0 for i in range(n)], ["k%03d" % i for i in range(n)])
            self.assertEqual([b["n"] for b in result["bins"]], sizes, n)
            self.assertGreaterEqual(min(sizes), pr.MIN_PER_BIN)

    def test_reliability_needs_ten_predictions_for_one_bin(self):
        result = m.reliability([0.1] * 9, [True] * 9, list("abcdefghi"))
        self.assertEqual(result["state"], m.INSUFFICIENT_DATA)
        self.assertNotIn("bins", result)

    def test_each_bin_reports_its_rate_and_the_wilson_interval(self):
        scores = [0.1] * 10 + [0.9] * 10
        outcomes = [True] * 2 + [False] * 8 + [True] * 7 + [False] * 3
        keys = ["k%02d" % i for i in range(20)]
        low, high = m.reliability(scores, outcomes, keys)["bins"]
        self.assertEqual((low["n"], low["observed_rate"], low["mean_prediction"]), (10, 0.2, 0.1))
        self.assertEqual((high["n"], high["observed_rate"], high["mean_prediction"]), (10, 0.7, 0.9))
        self.assertEqual((low["wilson_low"], low["wilson_high"]), fp.wilson(2, 10, 0.95))
        self.assertEqual((high["wilson_low"], high["wilson_high"]), fp.wilson(7, 10, 0.95))

    def test_confusion_at_each_events_own_threshold(self):
        result = m.confusion([0.5, 0.2, 0.7, 0.1], [True, False, False, True], [0.4] * 4)
        self.assertEqual((result["true_positives"], result["false_negatives"], result["false_positives"], result["true_negatives"]), (1, 1, 1, 1))
        self.assertEqual((result["false_positive_rate"], result["false_negative_rate"]), (0.5, 0.5))
        self.assertEqual(m.confusion([0.3, 0.9], [True, False], [0.3, 0.5])["true_positives"], 1)  # "at least": equal counts as positive
        self.assertIsNone(m.confusion([0.5], [True], [0.4])["false_positive_rate"])
        self.assertIsNone(m.confusion([0.5], [False], [0.4])["false_negative_rate"])

    def test_confusion_of_a_constant_prediction_at_its_own_base_rate_calls_everything_positive(self):
        result = m.confusion([0.3] * 6, [True, False, True, False, False, False], [0.3] * 6)
        self.assertEqual((result["false_positive_rate"], result["false_negative_rate"]), (1.0, 0.0))

    def test_terciles_of_the_predicted_probability_with_the_mean_return_in_each(self):
        scores = [0.1, 0.9, 0.5, 0.3, 0.7, 0.2, 0.8]
        returns = [0.01, 0.30, 0.10, None, 0.20, 0.02, 0.40]
        result = m.tercile_means(scores, returns, list("abcdefg"))
        self.assertEqual([t["events"] for t in result["terciles"]], [3, 2, 2])  # 7 = 3 + 2 + 2, the remainder to the lowest
        self.assertEqual([t["events_with_a_return"] for t in result["terciles"]], [2, 2, 2])
        lowest = result["terciles"][0]  # scores 0.1, 0.2, 0.3 -> returns 0.01, 0.02, None
        self.assertAlmostEqual(lowest["mean_return"], 0.015)
        self.assertAlmostEqual(result["terciles"][2]["mean_return"], 0.35)
        self.assertEqual(m.tercile_means([0.1, 0.2], [0.0, 0.0], ["a", "b"])["state"], m.INSUFFICIENT_DATA)


class RegressionMetricTests(unittest.TestCase):
    def test_pinball_loss_known_values(self):
        self.assertAlmostEqual(m.pinball(1.0, 0.4, 0.9), 0.54)
        self.assertAlmostEqual(m.pinball(1.0, 0.4, 0.1), 0.06)
        self.assertAlmostEqual(m.pinball(0.0, 0.4, 0.9), 0.04)
        self.assertEqual(m.pinball(0.5, 0.5, 0.9), 0.0)

    def test_one_event_all_three_levels(self):
        metrics = m.regression_metrics([1.0], [(0.0, 0.5, 2.0)])
        self.assertAlmostEqual(metrics["mean_pinball_loss"], (0.1 + 0.25 + 0.1) / 3)
        self.assertEqual(metrics["pinball_loss_by_level"].keys(), {"0.1", "0.5", "0.9"})
        self.assertEqual(metrics["interval_coverage"], 1.0)
        self.assertAlmostEqual(metrics["mae_of_the_median"], 0.5)
        self.assertAlmostEqual(m.event_pinball(1.0, (0.0, 0.5, 2.0)), (0.1 + 0.25 + 0.1) / 3)

    def test_coverage_counts_outcomes_inside_the_interval_inclusive_of_its_ends(self):
        metrics = m.regression_metrics([0.0, 1.0, 2.0, 3.0], [(0.0, 1.0, 2.0)] * 4)
        self.assertEqual(metrics["interval_coverage"], 0.75)


class BootstrapTests(unittest.TestCase):
    def test_the_interval_is_seeded_and_deterministic(self):
        differences = [0.1, -0.2, 0.05, 0.0, -0.1, 0.3, -0.05, 0.02, -0.01, 0.07]
        clusters = ["a", "a", "b", "b", "c", "c", "d", "d", "e", "e"]
        first = m.cluster_bootstrap(differences, clusters, 410001)
        self.assertEqual(first, m.cluster_bootstrap(differences, clusters, 410001))
        self.assertNotEqual(first["intervals"], m.cluster_bootstrap(differences, clusters, 410002)["intervals"])
        self.assertEqual((first["events"], first["clusters"], first["replicates"], first["seed"]), (10, 5, 5000, 410001))
        self.assertAlmostEqual(first["estimate"], sum(differences) / 10)

    def test_the_99_percent_interval_contains_the_95_percent_interval(self):
        differences = [((i * 37) % 11 - 5) / 50 for i in range(40)]
        result = m.cluster_bootstrap(differences, ["c%d" % (i // 2) for i in range(40)], 5)
        (low95, high95), (low99, high99) = result["intervals"]["0.95"], result["intervals"]["0.99"]
        self.assertLessEqual(low99, low95)
        self.assertGreaterEqual(high99, high95)

    def test_whole_clusters_are_resampled_not_single_events(self):
        # two clusters of five: one all +1, one all -1. Resampling clusters gives means of +1, 0 or -1 only, so the 95% interval is [-1, 1];
        # resampling the ten events themselves would give a far narrower interval.
        differences, clusters = [1.0] * 5 + [-1.0] * 5, ["a"] * 5 + ["b"] * 5
        result = m.cluster_bootstrap(differences, clusters, 3, replicates=2000)
        self.assertEqual(result["intervals"]["0.95"], [-1.0, 1.0])

    def test_a_constant_difference_has_a_degenerate_interval(self):
        result = m.cluster_bootstrap([0.25] * 12, ["c%d" % (i % 4) for i in range(12)], 1, replicates=500)
        self.assertEqual(result["intervals"]["0.95"], [0.25, 0.25])
        self.assertEqual(result["estimate"], 0.25)

    def test_replicates_are_drawn_with_the_seeded_generators_random_only(self):
        # one cluster: every replicate is that cluster, so every interval is its mean whatever the seed
        for seed in (1, 2, 3):
            self.assertEqual(m.cluster_bootstrap([0.5, 1.5], ["only", "only"], seed, replicates=50)["intervals"]["0.99"], [1.0, 1.0])

    def test_the_headline_is_the_wider_interval_and_the_first_clustering_on_a_tie(self):
        by = {"reaction_session": {"intervals": {"0.95": [-0.2, 0.2], "0.99": [-0.3, 0.3]}},
              "issuer": {"intervals": {"0.95": [-0.1, 0.4], "0.99": [-0.25, 0.25]}}}
        result = m.headline(by)
        self.assertEqual(result["0.95"], {"clustering": "issuer", "low": -0.1, "high": 0.4})  # width 0.5 against 0.4
        self.assertEqual(result["0.99"], {"clustering": "reaction_session", "low": -0.3, "high": 0.3})
        tie = {"reaction_session": {"intervals": {"0.95": [0.0, 1.0]}}, "issuer": {"intervals": {"0.95": [1.0, 2.0]}}}
        self.assertEqual(m.headline(tie)["0.95"]["clustering"], "reaction_session")

    def test_contrast_runs_both_clusterings_with_their_own_seeds(self):
        differences = [0.1, -0.1, 0.2, -0.2, 0.05, 0.0]
        clusters = {"reaction_session": ["s1", "s1", "s2", "s2", "s3", "s3"], "issuer": ["i1", "i2", "i3", "i1", "i2", "i3"]}
        result = m.contrast(differences, clusters, {"reaction_session": 410001, "issuer": 410002})
        self.assertEqual(set(result["by_clustering"]), {"reaction_session", "issuer"})
        self.assertEqual(result["by_clustering"]["issuer"]["seed"], 410002)
        self.assertAlmostEqual(result["estimate"], sum(differences) / 6)
        self.assertEqual(set(result["headline"]), {"0.95", "0.99"})


class DecisionRuleTests(unittest.TestCase):
    CLAIM = {"state": m.EVALUABLE}

    def decide(self, interval, estimate, state=m.EVALUABLE):
        return m.decide({"state": state, "claim_interval": interval}, {"estimate": estimate})

    def test_better_needs_the_clean_interval_below_zero_and_the_all_event_estimate_below_zero(self):
        self.assertEqual(self.decide([-0.05, -0.01], -0.02), m.DISTINGUISHABLE_BETTER)
        self.assertEqual(self.decide([-0.05, 0.0], -0.02), m.NOT_DISTINGUISHABLE)  # an interval touching zero is not below it
        self.assertEqual(self.decide([-0.05, -0.01], 0.01), m.NOT_DISTINGUISHABLE)  # the all-event result can only disagree with a claim
        self.assertEqual(self.decide([-0.05, -0.01], 0.0), m.NOT_DISTINGUISHABLE)
        self.assertEqual(self.decide([-0.05, -0.01], None), m.NOT_DISTINGUISHABLE)

    def test_worse_is_the_mirror_image(self):
        self.assertEqual(self.decide([0.01, 0.05], 0.02), m.DISTINGUISHABLE_WORSE)
        self.assertEqual(self.decide([0.0, 0.05], 0.02), m.NOT_DISTINGUISHABLE)
        self.assertEqual(self.decide([0.01, 0.05], -0.02), m.NOT_DISTINGUISHABLE)

    def test_an_interval_that_straddles_zero_is_not_distinguishable(self):
        self.assertEqual(self.decide([-0.01, 0.01], -0.5), m.NOT_DISTINGUISHABLE)

    def test_thresholds_not_met_in_the_clean_window_version_is_insufficient_data_whatever_else_holds(self):
        self.assertEqual(self.decide(None, -0.5, state="INSUFFICIENT_DATA"), m.INSUFFICIENT_DATA)
        self.assertEqual(self.decide([-0.05, -0.01], -0.02, state="INSUFFICIENT_DATA"), m.INSUFFICIENT_DATA)

    def test_no_status_is_a_claim_of_an_edge_and_the_protocol_says_so(self):
        text = pr.load_json(pr.PROTOCOL_PATH)["decision_rule"]["no_edge_claim"]
        self.assertTrue(text.startswith("no status in this protocol, including DISTINGUISHABLE_BETTER, is a claim of"))
        self.assertIn("tradable or production-ready edge", text)


if __name__ == "__main__":
    unittest.main()
