"""The Phase 2 runner and the harness extensions it needs, on synthetic data: contrast roles, diagnostics, prediction records, the monotone repair across targets,
the structure audit (which must not read an outcome) and the one-shot real run's refusals. No real event is evaluated here."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_support as S  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_metrics as m  # noqa: E402
from nre import m4_models as mm  # noqa: E402
from nre import m4_phase2 as p2  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402
from nre.core import DataError, canonical, digest, iso  # noqa: E402

PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
COMMIT, WHEN = "c" * 40, "2026-10-07T01:00:00Z"
SIZES = (24, 44, 36, 36, 20)


def harness(events=None, spec=None, **options):
    if events is None:
        events, spec = S.dataset(sizes=SIZES)
    return h.Harness.for_tests(events, spec, calendar=S.CAL, **options)


def perturbed(events):
    """The events with every existing label value changed and which labels exist left alone."""
    out = copy.deepcopy(events)
    for event in out:
        for label in event["labels"].values():
            if label["value"] is not None:
                label["value"] = (not label["value"]) if isinstance(label["value"], bool) else label["value"] + 0.123
    return out


def canonical_digest(value):
    return digest(canonical(value))


class HarnessExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=SIZES)
        cls.engine = harness(cls.events, cls.spec)
        cls.every = cls.engine.evaluate("gap_ge_3pct", "all_event", mm.binary_predictors())
        cls.clean = cls.engine.evaluate("gap_ge_3pct", "clean_window", mm.binary_predictors())
        cls.regression = cls.engine.evaluate("day1_close_return", "clean_window", mm.regression_predictors())

    def test_on_the_real_inputs_only_the_authorized_targets_can_be_evaluated(self):
        real = harness()
        real.real = True  # the guard, exercised on synthetic data
        with mock.patch.object(h, "ALLOW_REAL_EVALUATION", False), mock.patch.object(h, "REAL_EVALUATION_TARGETS", ("gap_ge_3pct",)):
            with self.assertRaises(h.EvaluationNotAuthorized):
                real.evaluate("gap_ge_3pct", "all_event")  # the tripwire is off, whatever targets are listed
        with mock.patch.object(h, "ALLOW_REAL_EVALUATION", True), mock.patch.object(h, "REAL_EVALUATION_TARGETS", ("gap_ge_3pct",)):
            real.evaluate("gap_ge_3pct", "all_event")
            for refused in ("gap_ge_5pct", "extension_after_open_ge_5pct", "loses_half_of_gap"):
                with self.assertRaisesRegex(h.EvaluationNotAuthorized, "not among the targets authorized"):
                    real.evaluate(refused, "all_event")
        with mock.patch.object(h, "ALLOW_REAL_EVALUATION", True), mock.patch.object(h, "REAL_EVALUATION_TARGETS", ()):  # on, but no target authorized
            with self.assertRaises(h.EvaluationNotAuthorized):
                real.evaluate("gap_ge_3pct", "all_event")

    def test_predictions_are_rounded_to_twelve_decimals_when_produced(self):
        class Long(h.Predictor):
            id, kind = "TEST_LONG", "binary"

            def fit(self, train, target):
                return {}

            def predict(self, model, view):
                return 0.1234567890123456789

        result = self.engine.evaluate("gap_ge_3pct", "all_event", [Long()])
        self.assertEqual({r["p"] for r in result["predictors"]["TEST_LONG"]["rows"]}, {0.123456789012})

    def test_only_the_clean_window_model_against_c1_is_confirmatory(self):
        self.assertEqual(self.clean["contrasts"]["M2_logistic"]["role"], "confirmatory")
        self.assertEqual(self.every["contrasts"]["M2_logistic"]["role"], "companion_of_the_confirmatory_contrast")
        for result in (self.every, self.clean):
            self.assertEqual({pid: c["role"] for pid, c in result["contrasts"].items() if pid != "M2_logistic"}, {pid: "exploratory" for pid in (
                "C2_timing_rate", "C3_sector_group_rate", "C4_issuer_history_rate", "M2_without_sector")})
            self.assertEqual({c["baseline"] for c in result["contrasts"].values()}, {"C1_pooled_rate"})
        self.assertEqual(self.regression["contrasts"]["M3_ridge_linear"]["role"], "confirmatory")
        self.assertEqual(sum(1 for c in self.clean["contrasts"].values() if c["role"] == "confirmatory"), 1)

    def test_the_other_contrasts_and_the_per_fold_contrasts_are_exploratory_and_have_their_own_intervals(self):
        self.assertEqual(sorted(self.clean["other_contrasts"]), sorted("M2_logistic_vs_" + b for b in ("C2_timing_rate", "C3_sector_group_rate", "C4_issuer_history_rate",
                                                                                                          "M2_without_sector")))
        self.assertEqual(sorted(self.regression["other_contrasts"]), sorted("M3_ridge_linear_vs_" + b for b in ("C2_timing_quantiles", "C3_sector_group_quantiles",
                                                                                                                  "M3_without_sector")))
        self.assertEqual(sorted(self.clean["fold_contrasts"]), ["dev_test_block_3", "dev_test_block_4"])
        for contrast in list(self.clean["other_contrasts"].values()) + list(self.clean["fold_contrasts"].values()):
            self.assertEqual(contrast["role"], "exploratory")
            self.assertEqual(set(contrast["by_clustering"]), {"reaction_session", "issuer"})
            self.assertEqual(set(contrast["headline"]), {"0.95", "0.99"})
        fold = self.clean["fold_contrasts"]["dev_test_block_3"]
        self.assertEqual(fold["by_clustering"]["issuer"]["events"], self.clean["folds"]["dev_test_block_3"]["test"]["defined"])  # within the fold's own events

    def test_a_pair_contrast_is_the_difference_of_the_two_predictors_pooled_scores(self):
        c = self.clean["other_contrasts"]["M2_logistic_vs_C2_timing_rate"]
        runs = self.clean["predictors"]
        self.assertAlmostEqual(c["estimate"], runs["M2_logistic"]["metrics"]["brier"] - runs["C2_timing_rate"]["metrics"]["brier"])
        c = self.regression["other_contrasts"]["M3_ridge_linear_vs_M3_without_sector"]
        runs = self.regression["predictors"]
        self.assertAlmostEqual(c["estimate"], runs["M3_ridge_linear"]["metrics"]["mean_pinball_loss"] - runs["M3_without_sector"]["metrics"]["mean_pinball_loss"])

    def test_diagnostics_are_collected_for_each_fold(self):
        runs = self.every["predictors"]
        self.assertEqual(runs["C1_pooled_rate"]["folds"]["dev_test_block_3"]["diagnostics"], {})
        for name in ("dev_test_block_3", "dev_test_block_4"):
            self.assertIn("fallbacks_to_the_pooled_rate", runs["C2_timing_rate"]["folds"][name]["diagnostics"])
            self.assertTrue(runs["M2_logistic"]["folds"][name]["diagnostics"]["converged"])
            self.assertIn("test_events_by_prior_source", runs["C4_issuer_history_rate"]["folds"][name]["diagnostics"])
        self.assertIn("training_rows_without_an_earlier_event", self.regression["predictors"]["M3_ridge_linear"]["folds"]["dev_test_block_3"]["diagnostics"])

    def test_every_predictor_is_scored_on_the_same_events(self):
        for result in (self.every, self.clean, self.regression):
            ids = {pid: [r["event_id"] for r in run["rows"]] for pid, run in result["predictors"].items() if run["state"] == h.EVALUATED}
            self.assertEqual(len({tuple(v) for v in ids.values()}), 1)
            self.assertEqual(len(ids), 6 if result["kind"] == "binary" else 5)

    def test_experiment_records_carry_the_diagnostics_and_the_contrasts(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "e.jsonl"
            reg.init_logs(PROTOCOL, COMMIT, WHEN, log, Path(directory) / "h.jsonl")
            run = harness(self.events, self.spec, experiment_log=log, commit=lambda: COMMIT, clock=lambda: WHEN)
            written = run.record_experiments(self.clean)
        self.assertEqual(len(written), 6 * 3)
        pooled = next(r for r in written if r["predictor_id"] == "M2_logistic" and r["fold"] == "pooled_development")
        contrasts = pooled["metrics_with_counts"]["contrasts"]
        self.assertEqual(contrasts["against_the_comparator"]["role"], "confirmatory")
        self.assertEqual(sorted(contrasts["others"]), sorted(self.clean["other_contrasts"]))
        self.assertEqual(sorted(contrasts["by_fold"]), ["dev_test_block_3", "dev_test_block_4"])
        fold = next(r for r in written if r["predictor_id"] == "M2_logistic" and r["fold"] == "dev_test_block_3")
        self.assertTrue(fold["metrics_with_counts"]["diagnostics"]["converged"])
        self.assertEqual(fold["parameters_sha256"], digest(canonical(dict(self.clean["predictors"]["M2_logistic"]["folds"]["dev_test_block_3"]["model"]))))

    def test_prediction_records_cover_every_out_of_fold_prediction_in_the_protocols_fields(self):
        records = self.engine.prediction_records(self.clean, WHEN)
        rows = sum(len(f["rows"]) for run in self.clean["predictors"].values() for f in run["folds"].values() if f["state"] == h.EVALUATED)
        self.assertEqual(len(records), rows)
        for record in records[:50] + records[-50:]:
            for field in PROTOCOL["experiment_log"]["prediction_record_fields"]:
                self.assertIn(field, record)
            self.assertEqual({k: record[k] for k in ("response_state", "opportunity_state", "confidence_tier")},
                             {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"})
            self.assertEqual(record["model_version"], "m4-%s-v1" % record["predictor_id"])
            self.assertNotIn("y", record)
            self.assertNotIn("labels", record)
        by_event = {e["event_id"]: e for e in self.engine.events}
        for record in records[:20]:
            self.assertEqual(record["prediction_time"], by_event[record["event_id"]]["cutoff"].strftime("%Y-%m-%dT%H:%M:%SZ"))  # the B clock: the cutoff
        regression = self.engine.prediction_records(self.regression, WHEN)
        self.assertTrue(all(isinstance(r["prediction"], list) and len(r["prediction"]) == 3 for r in regression))
        c0 = self.engine.prediction_records(self.engine.evaluate("extension_after_open_ge_5pct", "all_event"), WHEN)  # synthetic data: nothing real is evaluated
        self.assertTrue(c0)
        for record in c0[:20]:  # the C0 clock is the regular open of the reaction session
            self.assertEqual(record["prediction_time"], iso(S.CAL.bounds(by_event[record["event_id"]]["reaction_session"])[0]))
        c1 = next(r for r in records if r["predictor_id"] == "C1_pooled_rate")
        fold = self.clean["predictors"]["C1_pooled_rate"]["folds"][c1["fold"]]
        self.assertEqual(c1["model_checksum"], fold["model_checksum"])


class RunAllTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=SIZES)
        cls.engine = harness(cls.events, cls.spec)
        cls.evaluations = p2.run_all(cls.engine)

    def test_every_target_and_version_is_evaluated_and_only_the_b_clock_targets(self):
        self.assertEqual(sorted(self.evaluations), sorted((t, v) for t in ("gap_ge_3pct", "gap_ge_5pct", "day1_close_return") for v in d.VERSIONS))
        self.assertEqual(p2.TARGETS, ("gap_ge_3pct", "gap_ge_5pct", "day1_close_return"))
        self.assertEqual({self.engine.targets[t].clock for t in p2.TARGETS}, {"B"})

    def test_the_5pct_models_are_capped_by_their_own_3pct_probabilities(self):
        for version in d.VERSIONS:
            looser, nested = self.evaluations[("gap_ge_3pct", version)], self.evaluations[("gap_ge_5pct", version)]
            for pid in p2.CAPPED:
                cap = {r["event_id"]: r["p"] for r in looser["predictors"][pid]["rows"]}
                rows = nested["predictors"][pid]["rows"]
                self.assertTrue(rows)
                for row in rows:
                    self.assertLessEqual(row["p"], cap[row["event_id"]])
                diagnostics = [f["diagnostics"] for f in nested["predictors"][pid]["folds"].values()]
                self.assertTrue(all("repairs_of_the_nested_threshold" in x for x in diagnostics))
            for pid in ("C1_pooled_rate", "C2_timing_rate", "C3_sector_group_rate", "C4_issuer_history_rate"):  # the rate baselines nest by construction
                a = {r["event_id"]: r["p"] for r in looser["predictors"][pid]["rows"]}
                for row in nested["predictors"][pid]["rows"]:
                    self.assertLessEqual(row["p"], a[row["event_id"]] + 1e-12)

    def test_a_cap_that_binds_is_applied_and_counted_in_a_full_evaluation(self):
        looser = self.evaluations[("gap_ge_3pct", "all_event")]
        tiny = {pid: {r["event_id"]: 0.001 for r in looser["predictors"][pid]["rows"]} for pid in p2.CAPPED}
        nested = self.engine.evaluate("gap_ge_5pct", "all_event", mm.binary_predictors(tiny))
        for pid in p2.CAPPED:
            rows = nested["predictors"][pid]["rows"]
            self.assertEqual({r["p"] for r in rows}, {0.001})
            self.assertEqual(sum(f["diagnostics"]["repairs_of_the_nested_threshold"] for f in nested["predictors"][pid]["folds"].values()), len(rows))

    def test_if_the_looser_thresholds_model_failed_the_capped_model_fails_and_so_does_its_status(self):
        original = mm.Logistic.fit

        def fit(self, train, target):
            if target.id == "gap_ge_3pct":
                raise h.Abstain("MODEL_FIT_FAILED", "forced for the test")
            return original(self, train, target)
        with mock.patch.object(mm.Logistic, "fit", fit):
            evaluations = p2.run_all(self.engine)
        for version in d.VERSIONS:
            self.assertEqual(evaluations[("gap_ge_3pct", version)]["predictors"]["M2_logistic"]["state"], "MODEL_FIT_FAILED")
            nested = evaluations[("gap_ge_5pct", version)]["predictors"]
            for pid in p2.CAPPED:
                self.assertEqual(nested[pid]["state"], "MODEL_FIT_FAILED")
                self.assertIn("monotone repair", nested[pid]["reason"])
            self.assertEqual(nested["C1_pooled_rate"]["state"], h.EVALUATED)  # the comparators are unaffected
        self.assertEqual(p2.statuses(self.engine, evaluations)["gap_ge_5pct"]["M2_logistic"], "MODEL_FIT_FAILED")

    def test_statuses_are_one_per_target_for_its_confirmatory_model(self):
        statuses = p2.statuses(self.engine, self.evaluations)
        self.assertEqual(statuses.keys(), {"gap_ge_3pct", "gap_ge_5pct", "day1_close_return"})
        self.assertEqual({t: set(v) for t, v in statuses.items()}, {"gap_ge_3pct": {"M2_logistic"}, "gap_ge_5pct": {"M2_logistic"}, "day1_close_return": {"M3_ridge_linear"}})
        allowed = {m.DISTINGUISHABLE_BETTER, m.DISTINGUISHABLE_WORSE, m.NOT_DISTINGUISHABLE, m.INSUFFICIENT_DATA, "MODEL_FIT_FAILED"}
        self.assertTrue(all(s in allowed for v in statuses.values() for s in v.values()))

    def test_two_evaluations_of_the_same_inputs_are_identical(self):
        again = p2.run_all(harness(*S.dataset(sizes=SIZES)))
        first = canonical_digest({"%s|%s" % k: p2.plain(v) for k, v in self.evaluations.items()})
        self.assertEqual(first, canonical_digest({"%s|%s" % k: p2.plain(v) for k, v in again.items()}))

    def test_the_holdout_is_never_touched(self):
        self.assertEqual((self.engine.gate.denied, self.engine.gate.unsealed), ([], 0))

    def test_the_report_is_plain_json_without_rows_and_says_what_it_is_not(self):
        statuses = p2.statuses(self.engine, self.evaluations)
        report = p2.results_report(self.engine, self.evaluations, statuses, "0" * 64)
        json.dumps(report, allow_nan=False)

        def event_rows(node):  # a list of per-event rows, as opposed to the count of rows a model was fitted on
            if isinstance(node, dict):
                return [k for k, v in node.items() if k == "rows" and isinstance(v, list)] + [x for v in node.values() for x in event_rows(v)]
            if isinstance(node, list):
                return [x for v in node for x in event_rows(v)]
            return []
        self.assertEqual(event_rows(report), [])
        self.assertEqual(report["scope"]["targets"], list(p2.TARGETS))
        self.assertEqual(report["statuses"], statuses)
        self.assertEqual(report["holdout"]["denied_reads"], 0)
        self.assertEqual(report["protocol"]["canonical_sha256"], pr.protocol_sha256(PROTOCOL))
        self.assertIn("Not Milestone 4 acceptance.", report["not_a_claim"])
        self.assertNotIn("extension_after_open_ge_5pct", report["evaluations"])
        for target in report["evaluations"].values():
            for result in target.values():
                self.assertEqual(sorted(result), sorted(p2.without_rows(self.evaluations[("gap_ge_3pct", "all_event")])))

    def test_plain_turns_models_and_tuples_into_json_data(self):
        converted = p2.plain({"a": (1, 2), "b": [{"c": (3,)}], "m": h.FittedModel({"x": 1})})
        self.assertEqual(converted, {"a": [1, 2], "b": [{"c": [3]}], "m": {"x": 1}})
        self.assertIs(type(converted["m"]), dict)

    def test_the_prediction_lines_are_one_json_record_each(self):
        lines = p2.prediction_lines(self.engine, self.evaluations, WHEN)
        self.assertGreater(len(lines), 1000)
        for line in lines[:30]:
            record = json.loads(line)
            self.assertEqual(canonical(record).decode("utf-8"), line)
            self.assertEqual(record["generated_at"], WHEN)


class StructureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=SIZES)
        cls.engine = harness(cls.events, cls.spec)
        cls.audit = p2.structure_audit(cls.engine)

    def test_it_recounts_the_cells_the_baselines_will_use(self):
        blocks = self.engine.blocks
        target = self.engine.targets["gap_ge_3pct"]
        train = [e for e in self.events if blocks[e["event_id"]] in (1, 2) and e["labels"]["gap_ge_3pct"]["value"] is not None]
        fold = self.audit["gap_ge_3pct"]["all_event"]["dev_test_block_3"]
        self.assertEqual(fold["training_events_with_the_target_defined"], len(train))
        self.assertEqual(fold["training_cells"]["C2_timing"], {t: sum(1 for e in train if e["release_timing"] == t) for t in ("after_hours", "premarket")})
        self.assertEqual(sum(fold["training_cells"]["C3_sector_group"].values()), len(train))
        self.assertEqual(fold["training_rows_with_no_earlier_matured_event"], sum(1 for e in train if not [x for x in train if x["reaction_session"] < e["reaction_session"]
                                                                                                           and x["available_at"][target.source_labels[0]] <= e["cutoff"]]))
        self.assertEqual(fold["test_events_with_no_earlier_matured_event"], 0)

    def test_it_flags_the_cells_that_would_fall_back(self):
        clean = self.audit["gap_ge_3pct"]["clean_window"]["dev_test_block_3"]
        small = clean["cells_below_the_minimum_of_10"]
        self.assertEqual(small["C3_sector_group"], sorted(k for k, n in clean["training_cells"]["C3_sector_group"].items() if n < 10))
        self.assertEqual(clean["test_events_that_would_fall_back_to_the_pooled_value"]["C3_sector_group"],
                         sum(n for k, n in clean["test_events_by_cell"]["C3_sector_group"].items() if k in small["C3_sector_group"]))

    def test_it_reads_no_outcome_value_only_which_labels_are_defined(self):
        changed = harness(perturbed(self.events), self.spec)
        self.assertEqual(canonical_digest(p2.structure_audit(changed)), canonical_digest(self.audit))  # every value changed, the same labels defined
        def keys(node):
            if isinstance(node, dict):
                return set(node) | {x for v in node.values() for x in keys(v)}
            return set()
        outcome_words = {"positives", "negatives", "rate", "mean", "base_rate", "brier", "return", "returns", "outcome"}
        self.assertEqual(keys(self.audit) & outcome_words, set())  # nothing in the audit is named after an outcome

    def test_the_report_names_what_it_did_not_do(self):
        report = p2.audit_report(self.engine)
        self.assertEqual((report["kind"], report["holdout"]["denied_reads"], report["holdout"]["unsealed_loads"]), ("m4_phase2_structure_audit", 0, 0))
        self.assertIn("reads no outcome value", report["purpose"])
        self.assertIn("Not a result: nothing was fitted, scored or evaluated.", report["not_a_claim"])


class OneShotRunTests(unittest.TestCase):
    """run() on a synthetic harness, in a temporary directory with its own logs. The evaluations are computed once and handed to run() by a stand-in for
    run_all wherever a test is about what run() does with them rather than about the evaluations."""

    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=SIZES)
        cls.evaluations = p2.run_all(harness(cls.events, cls.spec))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "reports").mkdir()
        self.experiments, self.holdout = self.root / "reports" / "e.jsonl", self.root / "reports" / "h.jsonl"
        reg.init_logs(PROTOCOL, COMMIT, "2026-10-06T00:00:00Z", self.experiments, self.holdout)
        self.engine = harness(self.events, self.spec, experiment_log=self.experiments, holdout_log=self.holdout, commit=lambda: "0" * 40, clock=lambda: WHEN)

    def go(self, authorized=True, **options):
        with mock.patch.object(p2, "run_all", lambda harness, targets=p2.TARGETS: self.evaluations), mock.patch.object(h, "ALLOW_REAL_EVALUATION", authorized):
            return p2.run(self.engine, "2026-10-07", root=self.root, commit_state=options.pop("commit_state", (COMMIT, True)))

    def test_a_run_writes_the_logs_the_report_and_the_predictions(self):
        summary = self.go()
        self.assertEqual((summary["state"], summary["harness_commit"], summary["experiment_records"]), ("EVALUATED", COMMIT, 2 * (18 + 18 + 15)))
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL)["records"], 1 + summary["experiment_records"])
        records = [r for r, _ in reg.read(self.experiments)][1:]
        self.assertEqual({r["harness_commit"] for r in records}, {COMMIT})  # the commit read from a clean tree, not the harness's own default
        self.assertEqual({r["target_id"] for r in records}, set(p2.TARGETS))
        self.assertEqual({r["version"] for r in records}, set(d.VERSIONS))
        self.assertEqual([r["experiment_id"] for r in records][:2], ["m4-experiment-00001", "m4-experiment-00002"])
        report = json.loads((self.root / "reports" / "m4-phase2-results-2026-10-07.json").read_text(encoding="utf-8"))
        self.assertEqual(canonical_digest(report), summary["results_canonical_sha256"])
        self.assertTrue(report["determinism"]["identical"])
        lines = (self.root / "reports" / "m4-phase2-predictions-2026-10-07.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), summary["prediction_records"])
        self.assertEqual(reg.verify_chain(self.holdout, "holdout_access", PROTOCOL)["records"], 1)  # no access: only the genesis
        self.assertEqual((self.engine.gate.denied, self.engine.gate.unsealed), ([], 0))

    def test_the_experiment_records_name_the_hash_of_the_predictions_in_the_predictions_file(self):
        self.go()
        by_key = {}
        for line in (self.root / "reports" / "m4-phase2-predictions-2026-10-07.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            by_key.setdefault((r["target_id"], r["version"], r["predictor_id"], r["fold"]), []).append([r["event_id"], r["prediction"]])
        checked = 0
        for record, _ in reg.read(self.experiments)[1:]:
            if record["fold"] == "pooled_development" or record["state"] != "EVALUATED":
                continue
            rows = by_key[(record["target_id"], record["version"], record["predictor_id"], record["fold"])]
            self.assertEqual(record["predictions_sha256"], canonical_digest([[e, tuple(p) if isinstance(p, list) else p] for e, p in rows]))
            checked += 1
        self.assertGreater(checked, 50)

    def test_it_refuses_unless_authorized(self):
        with self.assertRaises(h.EvaluationNotAuthorized):
            self.go(authorized=False)
        self.assertEqual(len(reg.read(self.experiments)), 1)

    def test_it_refuses_on_a_dirty_tree(self):
        with self.assertRaisesRegex(DataError, "uncommitted"):
            self.go(commit_state=(COMMIT, False))
        self.assertEqual(len(reg.read(self.experiments)), 1)

    def test_it_is_run_once(self):
        self.go()
        with self.assertRaisesRegex(DataError, "exists"):
            self.go()

    def test_it_starts_only_from_logs_holding_their_genesis(self):
        record = reg.experiment_record(PROTOCOL, COMMIT, WHEN, 1, "gap_ge_3pct", "B", "C1_pooled_rate", "all_event", "f", [], [], "m4-features-v1", {}, [], {}, "none", {}, "EVALUATED")
        reg.append(self.experiments, "experiments", record, PROTOCOL)
        with self.assertRaisesRegex(DataError, "more than its genesis"):
            self.go()

    def test_it_refuses_to_record_two_evaluations_that_differ(self):
        calls = []

        def drifting(harness, targets=p2.TARGETS):
            calls.append(1)
            if len(calls) == 1:
                return self.evaluations
            key = ("gap_ge_3pct", "all_event")
            result = dict(self.evaluations[key])
            run = dict(result["predictors"]["C1_pooled_rate"])
            run["rows"] = [{**run["rows"][0], "p": run["rows"][0]["p"] + 1e-9}] + run["rows"][1:]
            result["predictors"] = {**result["predictors"], "C1_pooled_rate": run}
            return {**self.evaluations, key: result}
        with mock.patch.object(p2, "run_all", drifting), mock.patch.object(h, "ALLOW_REAL_EVALUATION", True):
            with self.assertRaisesRegex(DataError, "differ"):
                p2.run(self.engine, "2026-10-07", root=self.root, commit_state=(COMMIT, True))
        self.assertEqual(len(reg.read(self.experiments)), 1)
        self.assertEqual(list((self.root / "reports").glob("m4-phase2-*")), [])


class CommandLineTests(unittest.TestCase):
    def test_run_needs_a_date_and_the_tripwire(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            p2.main(["run"])
        with mock.patch.object(h, "ALLOW_REAL_EVALUATION", False):  # whatever the real setting, a run with the tripwire off is refused before it reads anything
            with self.assertRaises(h.EvaluationNotAuthorized):
                p2.main(["run", "--date", "2026-10-07"])


if __name__ == "__main__":
    unittest.main()
