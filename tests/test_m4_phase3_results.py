"""The committed Phase 3 results: consistent with the experiment log and the predictions file, recomputed independently from the predictions and the development labels,
reproduced by running the evaluation again, and the holdout still sealed. Nothing here writes anything."""
import json
import math
import random
import unittest
from collections import Counter
from pathlib import Path

from nre import m4_data as d
from nre import m4_harness as h
from nre import m4_metrics as m
from nre import m4_phase2 as p2
from nre import m4_phase3 as p3
from nre import m4_protocol as pr
from nre import m4_registry as reg
from nre.core import canonical, digest, iso

ROOT = Path(__file__).resolve().parent.parent
DATE = "2026-10-07"
RESULTS = ROOT / "reports" / ("m4-phase3-results-%s.json" % DATE)
PREDICTIONS = ROOT / "reports" / ("m4-phase3-predictions-%s.jsonl" % DATE)
PHASE_2_EXPERIMENTS = 2 * (18 + 18 + 15)  # the records Phase 2 left after the genesis
EXPERIMENTS = 2 * 2 * 18  # two targets x two versions x six predictors x (two development folds and the pooled set)
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
TARGETS = d.targets(PROTOCOL)
EXTENSION, HALF = p3.TARGETS
EVALUATED_COMBINATIONS = ((EXTENSION, "all_event"), (EXTENSION, "clean_window"), (HALF, "all_event"))  # loses_half_of_gap's clean-window version is INSUFFICIENT_DATA


def close(a, b, tolerance=1e-9):
    """Equal in structure, and equal to `tolerance` in every number (the C libraries behind exp and log can differ in the last bit between platforms)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], tolerance) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tolerance * max(1.0, abs(a), abs(b))
    return a == b


def quantile(ordered, p):
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


class ResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(RESULTS.read_text(encoding="utf-8"))
        cls.by_key = {}
        for line in PREDICTIONS.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            cls.by_key.setdefault((record["target_id"], record["version"], record["predictor_id"]), []).append(record)
        cls.inputs = d.load_inputs(PROTOCOL)  # the holdout events stay sealed; only the development labels are read below
        cls.versions = d.versions(cls.inputs)

    # ---- the logs and the predictions file ----------------------------------------------------------------------------------------------------

    def test_the_experiment_log_holds_phase_3s_records_after_phase_2s_and_all_name_the_evaluating_commit(self):
        records = [r for r, _ in reg.read(reg.EXPERIMENT_LOG)]
        self.assertEqual(reg.verify_chain(reg.EXPERIMENT_LOG, "experiments", PROTOCOL)["records"], len(records))
        earlier = records[1:1 + PHASE_2_EXPERIMENTS]
        experiments = records[1 + PHASE_2_EXPERIMENTS:1 + PHASE_2_EXPERIMENTS + EXPERIMENTS]
        self.assertEqual(len(experiments), EXPERIMENTS)
        self.assertEqual({r["target_id"] for r in earlier}, set(p2.TARGETS))  # Phase 2's records are where Phase 2 left them
        self.assertEqual([r["experiment_id"] for r in experiments], ["m4-experiment-%05d" % n for n in range(1 + PHASE_2_EXPERIMENTS, 1 + PHASE_2_EXPERIMENTS + EXPERIMENTS)])
        commits = {r["harness_commit"] for r in experiments}
        self.assertEqual(len(commits), 1)  # one clean tree produced them all
        self.assertRegex(commits.pop(), r"^[0-9a-f]{40}$")
        self.assertNotIn(experiments[0]["harness_commit"], {r["harness_commit"] for r in earlier})
        self.assertEqual({r["protocol_sha256"] for r in experiments}, {pr.protocol_sha256(PROTOCOL)})
        self.assertEqual({r["target_id"] for r in experiments}, set(p3.TARGETS))
        self.assertEqual({r["clock"] for r in experiments}, {"C0"})
        self.assertEqual(Counter((r["target_id"], r["version"], r["state"]) for r in experiments),
                         {(EXTENSION, "all_event", "EVALUATED"): 18, (EXTENSION, "clean_window", "EVALUATED"): 18, (HALF, "all_event", "EVALUATED"): 18,
                          (HALF, "clean_window", "INSUFFICIENT_DATA"): 18})

    def test_every_experiment_names_the_hash_of_the_predictions_in_the_predictions_file(self):
        by_fold = {}
        for (target, version, predictor), records in self.by_key.items():
            for record in records:
                by_fold.setdefault((target, version, predictor, record["fold"]), []).append([record["event_id"], record["prediction"]])
        checked = 0
        for record, _ in reg.read(reg.EXPERIMENT_LOG)[1 + PHASE_2_EXPERIMENTS:1 + PHASE_2_EXPERIMENTS + EXPERIMENTS]:
            if record["fold"] == "pooled_development":
                continue
            key = (record["target_id"], record["version"], record["predictor_id"], record["fold"])
            if record["state"] != "EVALUATED":
                self.assertNotIn(key, by_fold)  # an INSUFFICIENT_DATA experiment made no predictions...
                self.assertEqual(record["predictions_sha256"], digest(canonical([])))  # ...and its record says so
                self.assertEqual(record["test_event_ids_sha256"], reg.hash_list([]))
                continue
            rows = by_fold[key]
            self.assertEqual(record["predictions_sha256"], digest(canonical(rows)))
            self.assertEqual(record["test_event_ids_sha256"], reg.hash_list(sorted(e for e, _ in rows)))
            checked += 1
        self.assertEqual(checked, 3 * 6 * 2)

    def test_every_prediction_is_a_protocol_prediction_record_timed_at_the_regular_open_with_no_other_state(self):
        by_id = {e["event_id"]: e for e in self.versions["all_event"]}
        calendar = self.inputs["calendar"]
        for records in self.by_key.values():
            for record in records:
                self.assertEqual({k: record[k] for k in ("response_state", "opportunity_state", "confidence_tier")},
                                 {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"})
                for field in PROTOCOL["experiment_log"]["prediction_record_fields"]:
                    self.assertIn(field, record)
                event = by_id[record["event_id"]]
                self.assertEqual(record["prediction_time"], iso(calendar.bounds(event["reaction_session"])[0]))  # the C0 clock: the regular open, not the cutoff
                self.assertNotEqual(record["prediction_time"], iso(event["cutoff"]))
        expected = sum(run["metrics"]["counts"]["events"] for target in self.report["evaluations"].values() for ev in target.values() for run in ev["predictors"].values()
                       if run["state"] == "EVALUATED")
        self.assertEqual(sum(len(v) for v in self.by_key.values()), expected)  # one record for every predictor and test event the report counts
        self.assertEqual({(t, v) for t, v, _ in self.by_key}, set(EVALUATED_COMBINATIONS))

    # ---- recomputed independently --------------------------------------------------------------------------------------------------------------

    def test_the_scores_and_contrasts_recompute_from_the_predictions_and_the_development_labels(self):
        losses = {}
        for (target_id, version, predictor), records in self.by_key.items():
            target = TARGETS[target_id]
            by_id = {e["event_id"]: e for e in self.versions[version]}
            per_event = {}
            for record in records:
                y = target.function(by_id[record["event_id"]]["labels"])
                self.assertIsNotNone(y)
                per_event[record["event_id"]] = (record["prediction"] - (1.0 if y else 0.0)) ** 2
            losses[(target_id, version, predictor)] = per_event
            metrics = self.report["evaluations"][target_id][version]["predictors"][predictor]["metrics"]
            self.assertAlmostEqual(math.fsum(per_event.values()) / len(per_event), metrics["brier"], places=9)
            self.assertEqual(len(per_event), metrics["counts"]["events"])
        for target_id, version in EVALUATED_COMBINATIONS:
            for predictor, contrast in self.report["evaluations"][target_id][version]["contrasts"].items():
                a, b = losses[(target_id, version, predictor)], losses[(target_id, version, "C1_pooled_rate")]
                self.assertEqual(list(a), list(b))
                self.assertAlmostEqual(math.fsum(a[e] - b[e] for e in a) / len(a), contrast["estimate"], places=9)

    def test_the_m2_bootstrap_intervals_recompute_from_the_seeds(self):
        for target_id, version in EVALUATED_COMBINATIONS:
            records = {pid: {r["event_id"]: r for r in self.by_key[(target_id, version, pid)]} for pid in ("M2_logistic", "C1_pooled_rate")}
            by_id = {e["event_id"]: e for e in self.versions[version]}
            target = TARGETS[target_id]
            differences = {}
            for event_id in records["M2_logistic"]:
                y = 1.0 if target.function(by_id[event_id]["labels"]) else 0.0
                differences[event_id] = (records["M2_logistic"][event_id]["prediction"] - y) ** 2 - (records["C1_pooled_rate"][event_id]["prediction"] - y) ** 2
            contrast = self.report["evaluations"][target_id][version]["contrasts"]["M2_logistic"]
            for name, field, seed_key in (("reaction_session", "reaction_session", "bootstrap_reaction_session"), ("issuer", "cik", "bootstrap_issuer")):
                clusters = sorted({by_id[e][field] for e in differences})
                sums = {c: math.fsum(v for e, v in differences.items() if by_id[e][field] == c) for c in clusters}
                sizes = {c: sum(1 for e in differences if by_id[e][field] == c) for c in clusters}
                rng = random.Random(PROTOCOL["seeds"][seed_key])
                replicates = []
                for _ in range(pr.BOOTSTRAP_REPLICATES):
                    picks = [clusters[int(rng.random() * len(clusters))] for _ in clusters]
                    replicates.append(math.fsum(sums[c] for c in picks) / sum(sizes[c] for c in picks))
                replicates.sort()
                for level in (0.95, 0.99):
                    tail = (1 - level) / 2
                    got = contrast["by_clustering"][name]["intervals"]["%g" % level]
                    self.assertAlmostEqual(quantile(replicates, tail), got[0], places=9, msg=(target_id, version, name, level))
                    self.assertAlmostEqual(quantile(replicates, 1 - tail), got[1], places=9, msg=(target_id, version, name, level))

    # ---- the decision rule and the roles --------------------------------------------------------------------------------------------------------

    def test_the_statuses_follow_the_decision_rule_from_the_stored_intervals(self):
        self.assertEqual(self.report["statuses"], {EXTENSION: {"M2_logistic": m.NOT_DISTINGUISHABLE}, HALF: {"M2_logistic": m.INSUFFICIENT_DATA}})
        clean, every = (self.report["evaluations"][EXTENSION][v] for v in ("clean_window", "all_event"))
        interval = clean["contrasts"]["M2_logistic"]["headline"]["0.99"]
        self.assertEqual(self.report["statuses"][EXTENSION]["M2_logistic"],
                         m.decide({"state": m.EVALUABLE, "claim_interval": [interval["low"], interval["high"]]}, {"estimate": every["contrasts"]["M2_logistic"]["estimate"]}))
        self.assertTrue(interval["low"] < 0 < interval["high"])  # the 99% interval straddles zero, so neither better nor worse
        half_clean = self.report["evaluations"][HALF]["clean_window"]
        self.assertEqual(half_clean["pooled_development_test"]["state"], m.INSUFFICIENT_DATA)
        self.assertEqual(self.report["statuses"][HALF]["M2_logistic"],
                         m.decide({"state": half_clean["pooled_development_test"]["state"]}, {"estimate": self.report["evaluations"][HALF]["all_event"]["contrasts"]["M2_logistic"]["estimate"]}))

    def test_exactly_one_contrast_is_confirmatory_and_loses_half_of_gap_has_none(self):
        roles = [(t, v, pid, c["role"]) for t in p3.TARGETS for v in d.VERSIONS for pid, c in self.report["evaluations"][t][v]["contrasts"].items() if c["role"] == "confirmatory"]
        self.assertEqual(roles, [(EXTENSION, "clean_window", "M2_logistic", "confirmatory")])
        self.assertEqual(self.report["evaluations"][EXTENSION]["all_event"]["contrasts"]["M2_logistic"]["role"], "companion_of_the_confirmatory_contrast")
        half = self.report["evaluations"][HALF]["all_event"]["contrasts"]
        self.assertEqual({c["role"] for c in half.values()}, {"exploratory"})
        self.assertIn("INSUFFICIENT_DATA", half["M2_logistic"]["role_note"])
        for target_id, version in EVALUATED_COMBINATIONS:
            ev = self.report["evaluations"][target_id][version]
            for c in list(ev["other_contrasts"].values()) + list(ev["fold_contrasts"].values()):
                self.assertEqual(c["role"], "exploratory")

    def test_loses_half_of_gap_cannot_be_evaluated_in_the_clean_window_version_and_says_why(self):
        ev = self.report["evaluations"][HALF]["clean_window"]
        self.assertEqual(ev["folds"]["dev_test_block_3"]["state"], d.INSUFFICIENT_DATA)  # 9 training positives in fold 3
        self.assertEqual(ev["folds"]["dev_test_block_3"]["train"]["positives"], 9)
        self.assertEqual(ev["folds"]["dev_test_block_4"]["state"], d.EVALUABLE)
        self.assertEqual(ev["pooled_development_test"]["test"], {"defined": 10, "positives": 5, "negatives": 5})
        self.assertIn("5 positives among 10 defined events (at least 10 needed)", ev["pooled_development_test"]["reason"])
        self.assertEqual({run["state"] for run in ev["predictors"].values()}, {d.INSUFFICIENT_DATA})
        self.assertEqual((ev["contrasts"], ev["other_contrasts"], ev["fold_contrasts"]), ({}, {}, {}))

    def test_no_contrast_excludes_zero_and_nothing_is_a_claim(self):
        pooled = [c for t in p3.TARGETS for v in d.VERSIONS for section in ("contrasts", "other_contrasts") for c in self.report["evaluations"][t][v][section].values()]
        self.assertEqual(len(pooled), 3 * (5 + 4))
        for c in pooled:
            for level in ("0.95", "0.99"):
                self.assertTrue(c["headline"][level]["low"] <= 0 <= c["headline"][level]["high"])
        folds = [c for t in p3.TARGETS for v in d.VERSIONS for c in self.report["evaluations"][t][v]["fold_contrasts"].values()]
        self.assertEqual(len(folds), 3 * 2)
        self.assertTrue(all(c["headline"]["0.95"]["low"] <= 0 <= c["headline"]["0.95"]["high"] for c in folds))
        self.assertTrue(any("not a claim" in line.lower() or "never a claim" in line.lower() or "edge" in line.lower() for line in self.report["not_a_claim"]))

    def test_the_opening_gap_is_the_last_feature_of_every_m2_fit_and_no_other_predictor_uses_it(self):
        for target_id, version in EVALUATED_COMBINATIONS:
            predictors = self.report["evaluations"][target_id][version]["predictors"]
            for pid, run in predictors.items():
                for fold in run["folds"].values():
                    if pid.startswith("M2"):
                        self.assertEqual(fold["model"]["features"][-1], "open_gap")
                        self.assertEqual(fold["model"]["kept"][-1], "open_gap")
                        self.assertTrue(fold["diagnostics"]["converged"])
                        self.assertEqual(fold["diagnostics"]["repairs_of_the_nested_threshold"], 0)
                    else:
                        self.assertNotIn("open_gap", json.dumps(fold["model"]))

    # ---- reproduced, and the holdout ------------------------------------------------------------------------------------------------------------

    def test_the_evaluation_reproduces_from_the_committed_inputs(self):
        harness = h.Harness.from_repository()
        evaluations = p2.run_all(harness, p3.TARGETS)
        statuses = p2.statuses(harness, evaluations, p3.TARGETS)
        fresh = p2.results_report(harness, evaluations, statuses, "ignored", p3.PHASE_3)
        # the digest of raw floats can differ between platforms, so it is left out; the numbers themselves are compared to a tolerance
        committed = {k: v for k, v in self.report.items() if k != "determinism"}
        now = {k: v for k, v in fresh.items() if k != "determinism"}
        self.assertTrue(close(json.loads(json.dumps(now)), committed), "a fresh evaluation differs from the committed results")
        self.assertEqual(statuses, self.report["statuses"])
        self.assertTrue(self.report["determinism"]["identical"])
        self.assertEqual((harness.gate.denied, harness.gate.unsealed), ([], 0))

    def test_the_holdout_was_never_touched(self):
        self.assertEqual(self.report["holdout"], {"sealed_events": 23, "denied_reads": 0, "unsealed_loads": 0, "access_log_records_after_genesis": 0})
        self.assertEqual((self.inputs["gate"].denied, self.inputs["gate"].unsealed), ([], 0))
        if not h.ALLOW_HOLDOUT_LOOK:
            self.assertEqual(len(reg.read(reg.HOLDOUT_LOG)), 1)  # the genesis record only: not one access
        self.assertEqual(self.report["scope"]["targets"], list(p3.TARGETS))
        self.assertEqual(sorted(self.report["evaluations"]), sorted(p3.TARGETS))
        for target_id in p3.TARGETS:
            for version in d.VERSIONS:
                self.assertEqual(self.report["evaluations"][target_id][version]["folds"]["holdout_test_block_5"]["test"],
                                 "SEALED: the holdout's own counts are read only at the logged look")


if __name__ == "__main__":
    unittest.main()
