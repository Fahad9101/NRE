"""The committed Phase 2 results: consistent with the experiment log and the predictions file, recomputed independently from the predictions and the development labels,
reproduced by running the evaluation again, and the holdout still sealed. Nothing here writes anything."""
import json
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_independent as independent  # noqa: E402
import m4_support as S  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_metrics as m
from nre import m4_phase2 as p2
from nre import m4_protocol as pr
from nre import m4_registry as reg
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
DATE = "2026-10-07"
RESULTS = ROOT / "reports" / ("m4-phase2-results-%s.json" % DATE)
PREDICTIONS = ROOT / "reports" / ("m4-phase2-predictions-%s.jsonl" % DATE)
EXPERIMENTS = 2 * (18 + 18 + 15)  # two versions x (two binary targets with six predictors and three records each, one regression target with five)
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
TARGETS = d.targets(PROTOCOL)


def pinball(y, f, q):
    e = y - f
    return max(q * e, (q - 1) * e)


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

    def test_the_experiment_log_holds_one_record_per_experiment_and_all_name_the_evaluating_commit(self):
        records = [r for r, _ in reg.read(reg.EXPERIMENT_LOG)]
        self.assertEqual(reg.verify_chain(reg.EXPERIMENT_LOG, "experiments", PROTOCOL)["records"], len(records))
        experiments = records[1:1 + EXPERIMENTS]
        self.assertEqual(len(experiments), EXPERIMENTS)
        commits = {r["harness_commit"] for r in experiments}
        self.assertEqual(len(commits), 1)  # one clean tree produced them all
        self.assertRegex(commits.pop(), r"^[0-9a-f]{40}$")
        self.assertEqual({r["protocol_sha256"] for r in experiments}, {pr.protocol_sha256(PROTOCOL)})
        self.assertEqual({r["target_id"] for r in experiments}, set(p2.TARGETS))
        self.assertEqual({r["version"] for r in experiments}, {"all_event", "clean_window"})
        self.assertEqual({r["state"] for r in experiments}, {"EVALUATED"})

    def test_every_experiment_names_the_hash_of_the_predictions_in_the_predictions_file(self):
        by_fold = {}
        for (target, version, predictor), records in self.by_key.items():
            for record in records:
                by_fold.setdefault((target, version, predictor, record["fold"]), []).append([record["event_id"], tuple(record["prediction"]) if isinstance(record["prediction"], list)
                                                                                           else record["prediction"]])
        checked = 0
        for record, _ in reg.read(reg.EXPERIMENT_LOG)[1:1 + EXPERIMENTS]:
            if record["fold"] == "pooled_development":
                continue
            rows = by_fold[(record["target_id"], record["version"], record["predictor_id"], record["fold"])]
            self.assertEqual(record["predictions_sha256"], digest(canonical(rows)))
            self.assertEqual(record["test_event_ids_sha256"], reg.hash_list(sorted(e for e, _ in rows)))
            checked += 1
        self.assertEqual(checked, 2 * 2 * (6 + 6 + 5))

    def test_every_prediction_is_a_protocol_prediction_record_with_no_other_state(self):
        for records in self.by_key.values():
            for record in records:
                self.assertEqual({k: record[k] for k in ("response_state", "opportunity_state", "confidence_tier")},
                                 {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"})
                for field in PROTOCOL["experiment_log"]["prediction_record_fields"]:
                    self.assertIn(field, record)
        expected = sum(run["metrics"]["counts"]["events"] for target in self.report["evaluations"].values() for ev in target.values() for run in ev["predictors"].values())
        self.assertEqual(sum(len(v) for v in self.by_key.values()), expected)  # one record for every predictor and test event the report counts

    def test_the_scores_and_contrasts_recompute_from_the_predictions_and_the_development_labels(self):
        losses = {}
        for (target_id, version, predictor), records in self.by_key.items():
            target = TARGETS[target_id]
            by_id = {e["event_id"]: e for e in self.versions[version]}
            per_event = {}
            for record in records:
                y = target.function(by_id[record["event_id"]]["labels"])
                self.assertIsNotNone(y)
                p = record["prediction"]
                per_event[record["event_id"]] = ((p - (1.0 if y else 0.0)) ** 2 if target.kind == "binary"
                                                 else math.fsum(pinball(y, f, q) for f, q in zip(p, pr.QUANTILE_LEVELS)) / len(pr.QUANTILE_LEVELS))
            losses[(target_id, version, predictor)] = per_event
            metrics = self.report["evaluations"][target_id][version]["predictors"][predictor]["metrics"]
            self.assertAlmostEqual(math.fsum(per_event.values()) / len(per_event), metrics["brier" if target.kind == "binary" else "mean_pinball_loss"], places=9)
            self.assertEqual(len(per_event), metrics["counts"]["events"])
        for target_id in p2.TARGETS:
            comparator = h.COMPARATOR[TARGETS[target_id].kind]
            for version in ("all_event", "clean_window"):
                for predictor, contrast in self.report["evaluations"][target_id][version]["contrasts"].items():
                    a, b = losses[(target_id, version, predictor)], losses[(target_id, version, comparator)]
                    self.assertEqual(list(a), list(b))
                    self.assertAlmostEqual(math.fsum(a[e] - b[e] for e in a) / len(a), contrast["estimate"], places=9)

    def test_the_predictions_and_the_m2_fits_recompute_from_the_training_labels(self):
        problems, checked = independent.check(h.Harness.from_repository(), self.report, self.by_key)
        self.assertEqual(problems, [])
        self.assertEqual(checked, 2 * 2 * 6 * 2 + 2 * 2 * 2 * 2)  # the two binary targets in both versions: every predictor's predictions in both folds, and each M2 variant's fit as well

    def test_the_confirmatory_bootstrap_intervals_recompute_from_the_seeds(self):
        for target_id in p2.TARGETS:
            kind = TARGETS[target_id].kind
            model, comparator = h.CONFIRMATORY[kind], h.COMPARATOR[kind]
            records = {pid: {r["event_id"]: r for r in self.by_key[(target_id, "clean_window", pid)]} for pid in (model, comparator)}
            by_id = {e["event_id"]: e for e in self.versions["clean_window"]}
            target = TARGETS[target_id]
            differences = {}
            for event_id in records[model]:
                y = target.function(by_id[event_id]["labels"])
                score = {pid: ((records[pid][event_id]["prediction"] - (1.0 if y else 0.0)) ** 2 if kind == "binary"
                               else math.fsum(pinball(y, f, q) for f, q in zip(records[pid][event_id]["prediction"], pr.QUANTILE_LEVELS)) / 3) for pid in (model, comparator)}
                differences[event_id] = score[model] - score[comparator]
            contrast = self.report["evaluations"][target_id]["clean_window"]["contrasts"][model]
            self.assertEqual(contrast["role"], "confirmatory")
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
                    low, high = (self.quantile(replicates, p) for p in (tail, 1 - tail))
                    got = contrast["by_clustering"][name]["intervals"]["%g" % level]
                    self.assertAlmostEqual(low, got[0], places=9)
                    self.assertAlmostEqual(high, got[1], places=9)

    @staticmethod
    def quantile(ordered, p):
        position = (len(ordered) - 1) * p
        low = math.floor(position)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (position - low) * (ordered[high] - ordered[low])

    def test_the_statuses_follow_the_decision_rule_from_the_stored_intervals(self):
        for target_id, by_model in self.report["statuses"].items():
            kind = TARGETS[target_id].kind
            model = h.CONFIRMATORY[kind]
            self.assertEqual(set(by_model), {model})
            clean = self.report["evaluations"][target_id]["clean_window"]
            every = self.report["evaluations"][target_id]["all_event"]
            interval = clean["contrasts"][model]["headline"]["0.99"]
            expected = m.decide({"state": m.EVALUABLE, "claim_interval": [interval["low"], interval["high"]]}, {"estimate": every["contrasts"][model]["estimate"]})
            self.assertEqual(by_model[model], expected)
        allowed = {m.DISTINGUISHABLE_BETTER, m.DISTINGUISHABLE_WORSE, m.NOT_DISTINGUISHABLE, m.INSUFFICIENT_DATA}
        self.assertTrue(all(s in allowed for v in self.report["statuses"].values() for s in v.values()))

    def test_exactly_one_contrast_per_target_is_confirmatory_and_it_is_the_clean_window_model_against_c1(self):
        for target_id in p2.TARGETS:
            kind = TARGETS[target_id].kind
            roles = [(version, pid, c["role"]) for version in ("all_event", "clean_window")
                     for pid, c in self.report["evaluations"][target_id][version]["contrasts"].items() if c["role"] == "confirmatory"]
            self.assertEqual(roles, [("clean_window", h.CONFIRMATORY[kind], "confirmatory")])
            for version in ("all_event", "clean_window"):
                for c in list(self.report["evaluations"][target_id][version]["other_contrasts"].values()) + list(self.report["evaluations"][target_id][version]["fold_contrasts"].values()):
                    self.assertEqual(c["role"], "exploratory")

    def test_the_evaluation_reproduces_from_the_committed_inputs(self):
        harness = h.Harness.from_repository(holdout_log=S.genesis_only_holdout_log(self))  # the holdout log as it was then: genesis only
        evaluations = p2.run_all(harness)
        statuses = p2.statuses(harness, evaluations)
        fresh = p2.results_report(harness, evaluations, statuses, "ignored")
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
        accesses = [record for record, _ in reg.read(reg.HOLDOUT_LOG)][1:]  # the report says no access at its time; since then the log may hold only the one authorized look (Phase 4)
        self.assertLessEqual(len(accesses), 1)
        self.assertTrue(all(a["reason"].startswith("Milestone 4 Phase 4: the one look at the final holdout") for a in accesses))
        self.assertEqual(self.report["scope"]["targets"], ["gap_ge_3pct", "gap_ge_5pct", "day1_close_return"])
        self.assertNotIn("extension_after_open_ge_5pct", self.report["evaluations"])


if __name__ == "__main__":
    unittest.main()
