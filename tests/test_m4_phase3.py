"""Phase 3 on synthetic data: the C0-clock targets through the shared runner, the role of a contrast whose clean-window version is INSUFFICIENT_DATA, the prediction time,
the structure audit's extra facts, and the one-shot run's starting point. No real event is evaluated here."""
import contextlib
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
from nre import m4_phase2 as p2  # noqa: E402
from nre import m4_phase3 as p3  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402
from nre.core import DataError, canonical, digest, iso  # noqa: E402

PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
COMMIT, WHEN = "d" * 40, "2026-10-07T12:00:00Z"
SIZES = (24, 44, 36, 36, 20)


def harness(events=None, spec=None, **options):
    if events is None:
        events, spec = S.dataset(sizes=SIZES)
    return h.Harness.for_tests(events, spec, calendar=S.CAL, **options)


def perturbed(events):
    """The events with every existing label value changed and which labels exist left alone."""
    import copy
    out = copy.deepcopy(events)
    for event in out:
        for label in event["labels"].values():
            if label["value"] is not None:
                label["value"] = (not label["value"]) if isinstance(label["value"], bool) else label["value"] + 0.123
    return out


class PhaseDefinitionTests(unittest.TestCase):
    def test_phase_3_is_the_two_c0_primaries_and_phase_2_the_three_b_clock_ones(self):
        self.assertEqual(p3.TARGETS, ("extension_after_open_ge_5pct", "loses_half_of_gap"))
        targets = d.targets(PROTOCOL)
        self.assertEqual({targets[t].clock for t in p3.TARGETS}, {"C0"})
        self.assertEqual({targets[t].clock for t in p2.TARGETS}, {"B"})
        self.assertEqual(set(p3.TARGETS) | set(p2.TARGETS), {t.id for t in targets.values() if t.role == "primary"})  # together, all five primaries
        self.assertFalse(set(p3.TARGETS) & set(p2.TARGETS))
        self.assertEqual((p3.PHASE_3.number, p2.PHASE_2.number), (3, 2))

    def test_the_tripwire_covers_exactly_the_targets_of_the_two_phases_that_were_authorized(self):
        self.assertEqual(set(h.REAL_EVALUATION_TARGETS), set(p2.TARGETS) | set(p3.TARGETS))
        self.assertEqual(len(h.REAL_EVALUATION_TARGETS), len(p2.TARGETS) + len(p3.TARGETS))  # none twice
        self.assertTrue(not h.ALLOW_HOLDOUT_LOOK or len(reg.read(reg.HOLDOUT_LOG)) == 1)  # the holdout tripwire is on only while the one look (Phase 4) is still to come

    def test_phase_3_starts_from_the_log_as_phase_2_left_it(self):
        self.assertEqual((p3.PHASE_3.log_records_before, p3.PHASE_3.earlier_targets), (1 + 102, p2.TARGETS))
        self.assertEqual((p2.PHASE_2.log_records_before, p2.PHASE_2.earlier_targets), (1, ()))

    def test_the_two_phases_name_their_outputs_apart(self):
        self.assertIn("Phase 3", p3.PHASE_3.audit_purpose + p3.PHASE_3.results_purpose + p3.__doc__)
        self.assertIn("loses_half_of_gap", p3.PHASE_3.results_purpose)
        self.assertNotEqual(p3.PHASE_3.results_purpose, p2.PHASE_2.results_purpose)


class RoleTests(unittest.TestCase):
    """P3-3: an all-event contrast is the confirmatory contrast's companion only if the clean-window version can be evaluated."""

    @classmethod
    def setUpClass(cls):
        events, spec = S.dataset()  # the default sizes: loses_half_of_gap is evaluable all-event but INSUFFICIENT_DATA in the clean-window version
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        experiments, holdout = Path(directory.name) / "e.jsonl", Path(directory.name) / "h.jsonl"
        reg.init_logs(PROTOCOL, COMMIT, "2026-10-06T00:00:00Z", experiments, holdout)
        cls.engine = harness(events, spec, experiment_log=experiments, holdout_log=holdout, commit=lambda: "0" * 40, clock=lambda: WHEN)
        cls.every = cls.engine.evaluate("loses_half_of_gap", "all_event", p2.predictors_for(cls.engine.targets["loses_half_of_gap"]))
        cls.clean = cls.engine.evaluate("loses_half_of_gap", "clean_window", p2.predictors_for(cls.engine.targets["loses_half_of_gap"]))
        cls.other = cls.engine.evaluate("gap_ge_3pct", "all_event", p2.predictors_for(cls.engine.targets["gap_ge_3pct"]))

    def test_the_preconditions_hold_in_this_data(self):
        self.assertEqual(self.every["pooled_development_test"]["state"], d.EVALUABLE)
        self.assertEqual(self.clean["pooled_development_test"]["state"], d.INSUFFICIENT_DATA)
        self.assertEqual(self.other["pooled_development_test"]["state"], d.EVALUABLE)

    def test_without_an_evaluable_clean_window_the_all_event_contrast_is_exploratory_and_says_why(self):
        contrast = self.every["contrasts"]["M2_logistic"]
        self.assertEqual(contrast["role"], "exploratory")
        self.assertIn("INSUFFICIENT_DATA", contrast["role_note"])
        self.assertNotIn("companion", json.dumps({k: v for k, v in contrast.items() if k != "role_note"}))
        self.assertEqual({c["role"] for c in self.every["contrasts"].values()}, {"exploratory"})

    def test_with_an_evaluable_clean_window_it_is_still_the_companion(self):
        self.assertEqual(self.other["contrasts"]["M2_logistic"]["role"], "companion_of_the_confirmatory_contrast")
        self.assertNotIn("role_note", self.other["contrasts"]["M2_logistic"])

    def test_the_clean_window_version_gets_no_predictions_and_the_status_is_insufficient_data(self):
        self.assertEqual({pid: run["state"] for pid, run in self.clean["predictors"].items()}, {pid: d.INSUFFICIENT_DATA for pid in self.clean["predictors"]})
        self.assertEqual(self.clean["contrasts"], {})
        self.assertEqual(self.engine.status("M2_logistic", {"all_event": self.every, "clean_window": self.clean}), m.INSUFFICIENT_DATA)

    def test_a_version_that_cannot_be_evaluated_is_still_logged_in_full_with_its_state(self):
        for result, state in ((self.every, "EVALUATED"), (self.clean, d.INSUFFICIENT_DATA)):
            records = self.engine.experiment_records(result)
            self.assertEqual(len(records), 6 * 3)  # six predictors, each with its two development folds and the pooled set
            self.assertEqual({r["state"] for r in records}, {state})
            self.assertEqual({r["fold"] for r in records}, {"dev_test_block_3", "dev_test_block_4", "pooled_development"})


class RunAllTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=SIZES)
        cls.engine = harness(cls.events, cls.spec)
        cls.evaluations = p2.run_all(cls.engine, p3.TARGETS)

    def test_each_c0_target_is_evaluated_in_both_versions_with_the_six_binary_predictors_and_no_cap(self):
        self.assertEqual(sorted(self.evaluations), sorted((t, v) for t in p3.TARGETS for v in d.VERSIONS))
        for result in self.evaluations.values():
            self.assertEqual(sorted(result["predictors"]), ["C1_pooled_rate", "C2_timing_rate", "C3_sector_group_rate", "C4_issuer_history_rate", "M2_logistic", "M2_without_sector"])
            self.assertEqual(result["clock"], "C0")
            for run in result["predictors"].values():
                for fold in run["folds"].values():
                    self.assertEqual((fold.get("diagnostics") or {}).get("repairs_of_the_nested_threshold", 0), 0)  # nothing was capped: these targets are not nested

    def test_only_the_two_m2_variants_use_the_opening_gap(self):
        result = self.evaluations[("extension_after_open_ge_5pct", "all_event")]
        for pid in ("M2_logistic", "M2_without_sector"):
            self.assertEqual(result["predictors"][pid]["folds"]["dev_test_block_3"]["model"]["features"][-1], "open_gap")
        for pid in ("C2_timing_rate", "C3_sector_group_rate", "C4_issuer_history_rate"):
            self.assertNotIn("open_gap", json.dumps(result["predictors"][pid]["folds"]["dev_test_block_3"]["model"]))

    def test_the_confirmatory_contrast_is_the_clean_window_m2_against_c1_for_each_target(self):
        for target in p3.TARGETS:
            roles = [(v, c["role"]) for v in d.VERSIONS for c in [self.evaluations[(target, v)]["contrasts"].get("M2_logistic")] if c and c["role"] == "confirmatory"]
            self.assertEqual(roles, [("clean_window", "confirmatory")])

    def test_statuses_are_one_per_target_for_m2(self):
        statuses = p2.statuses(self.engine, self.evaluations, p3.TARGETS)
        self.assertEqual({t: set(v) for t, v in statuses.items()}, {t: {"M2_logistic"} for t in p3.TARGETS})
        allowed = {m.DISTINGUISHABLE_BETTER, m.DISTINGUISHABLE_WORSE, m.NOT_DISTINGUISHABLE, m.INSUFFICIENT_DATA, "MODEL_FIT_FAILED"}
        self.assertTrue(all(s in allowed for v in statuses.values() for s in v.values()))

    def test_two_evaluations_are_identical_and_the_holdout_is_untouched(self):
        again = p2.run_all(harness(*S.dataset(sizes=SIZES)), p3.TARGETS)
        self.assertEqual(digest(canonical({"%s|%s" % k: p2.plain(v) for k, v in self.evaluations.items()})), digest(canonical({"%s|%s" % k: p2.plain(v) for k, v in again.items()})))
        self.assertEqual((self.engine.gate.denied, self.engine.gate.unsealed), ([], 0))

    def test_every_prediction_is_timed_at_the_regular_open_not_the_cutoff(self):
        records = [json.loads(line) for line in p2.prediction_lines(self.engine, self.evaluations, WHEN, p3.PHASE_3)]
        self.assertGreater(len(records), 500)
        by_id = {e["event_id"]: e for e in self.engine.events}
        for record in records:
            event = by_id[record["event_id"]]
            self.assertEqual(record["prediction_time"], iso(S.CAL.bounds(event["reaction_session"])[0]))
            self.assertNotEqual(record["prediction_time"], iso(event["cutoff"]))
            self.assertEqual({k: record[k] for k in ("response_state", "opportunity_state", "confidence_tier")},
                             {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"})
        self.assertEqual({r["target_id"] for r in records}, set(p3.TARGETS))

    def test_the_report_names_phase_3_and_holds_only_its_targets(self):
        statuses = p2.statuses(self.engine, self.evaluations, p3.TARGETS)
        report = p2.results_report(self.engine, self.evaluations, statuses, "0" * 64, p3.PHASE_3)
        json.dumps(report, allow_nan=False)
        self.assertEqual(report["kind"], "m4_phase3_results")
        self.assertEqual(report["scope"]["targets"], list(p3.TARGETS))
        self.assertEqual(sorted(report["evaluations"]), sorted(p3.TARGETS))
        self.assertIn("C0-clock", report["purpose"])
        self.assertEqual(report["holdout"]["denied_reads"], 0)


class StructureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=SIZES)
        cls.engine = harness(cls.events, cls.spec)
        cls.audit = p2.structure_audit(cls.engine, p3.TARGETS)

    def test_it_reports_whether_the_opening_gap_is_defined_for_the_c0_targets_only(self):
        for versions in self.audit.values():
            for folds in versions.values():
                for fold in folds.values():
                    self.assertEqual((fold["training_rows_with_an_undefined_opening_gap"], fold["test_events_with_an_undefined_opening_gap"]), (0, 0))
        b_audit = p2.structure_audit(self.engine, ("gap_ge_3pct",))
        self.assertNotIn("training_rows_with_an_undefined_opening_gap", b_audit["gap_ge_3pct"]["all_event"]["dev_test_block_3"])

    def test_an_undefined_opening_gap_is_counted_in_the_folds_where_it_falls(self):
        """loses_half_of_gap is defined from a derived label, so an event can have the target and no opening gap; extension_after_open_ge_5pct needs the open itself."""
        import copy
        events = copy.deepcopy(self.events)
        target = self.engine.targets["loses_half_of_gap"]
        caveated = {entry["event_id"] for entry in self.spec["events"] if entry.get("caveats")}
        by_block = {}
        for event in events:
            if event["event_id"] not in caveated and target.function(event["labels"]) is not None:
                by_block.setdefault(self.engine.blocks[event["event_id"]], []).append(event)
        for event in by_block[1][:2] + by_block[3][:1] + by_block[4][:1]:
            event["labels"]["day1_open_return"] = {"value": None, "reason": "TEST_ABSENT"}
        audit = p2.structure_audit(harness(events, self.spec), p3.TARGETS)
        for version in d.VERSIONS:
            self.assertEqual({fold: (f["training_rows_with_an_undefined_opening_gap"], f["test_events_with_an_undefined_opening_gap"]) for fold, f in audit["loses_half_of_gap"][version].items()},
                             {"dev_test_block_3": (2, 1), "dev_test_block_4": (3, 1)}, version)  # block 1's two train both folds; block 3's one is fold 3's test, then fold 4's training
            self.assertEqual({f["training_rows_with_an_undefined_opening_gap"] + f["test_events_with_an_undefined_opening_gap"]
                              for f in audit["extension_after_open_ge_5pct"][version].values()}, {0})  # that target needs the open, so these events are not in it at all

    def test_the_audit_reads_no_value_not_even_the_opening_gap(self):
        changed = harness(perturbed(self.events), self.spec)
        self.assertEqual(digest(canonical(p2.structure_audit(changed, p3.TARGETS))), digest(canonical(self.audit)))

    def test_the_report_is_phase_3s_and_says_what_it_did_not_read(self):
        report = p2.audit_report(self.engine, p3.PHASE_3)
        self.assertEqual(report["kind"], "m4_phase3_structure_audit")
        self.assertIn("not the value of the opening gap", report["purpose"])
        self.assertEqual(sorted(report["targets"]), sorted(p3.TARGETS))


class OneShotRunTests(unittest.TestCase):
    """Phase 3's run() in a temporary directory, with logs shaped as Phase 2 leaves them (a genesis record and 102 experiments on the B-clock targets)."""

    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=SIZES)
        cls.evaluations = p2.run_all(harness(cls.events, cls.spec), p3.TARGETS)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "reports").mkdir()
        self.experiments, self.holdout = self.root / "reports" / "e.jsonl", self.root / "reports" / "h.jsonl"
        reg.init_logs(PROTOCOL, COMMIT, "2026-10-06T00:00:00Z", self.experiments, self.holdout)
        self.engine = harness(self.events, self.spec, experiment_log=self.experiments, holdout_log=self.holdout, commit=lambda: "0" * 40, clock=lambda: WHEN)
        self.requested = []

    def earlier_phase(self, count=102, target="gap_ge_3pct"):
        for n in range(count):
            reg.append(self.experiments, "experiments", reg.experiment_record(PROTOCOL, COMMIT, WHEN, n + 1, target, "B", "C1_pooled_rate", "all_event", "f", [], [], "m4-features-v1",
                                                                              {}, [], {}, "none", {}, "EVALUATED"), PROTOCOL)

    def fake_run_all(self, harness_, targets=None):
        """The evaluations computed once for the class, handed back for whichever targets the runner asks for; what it asked for is kept."""
        self.requested.append(tuple(targets))
        return self.evaluations

    def go(self, phase=p3.PHASE_3, **options):
        with mock.patch.object(p2, "run_all", self.fake_run_all), mock.patch.object(h, "ALLOW_REAL_EVALUATION", True):
            return p2.run(self.engine, "2026-10-07", root=self.root, commit_state=options.pop("commit_state", (COMMIT, True)), phase=phase)

    def test_a_run_appends_to_the_log_phase_2_left_and_writes_phase_3s_files(self):
        self.earlier_phase()
        summary = self.go()
        self.assertEqual(self.requested, [p3.TARGETS, p3.TARGETS])  # evaluated twice, for these targets and no others
        self.assertEqual((summary["state"], summary["experiment_records"]), ("EVALUATED", 2 * (18 + 18)))
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL)["records"], 1 + 102 + 2 * (18 + 18))  # genesis, Phase 2's, and 18 per target and version
        later = [r for r, _ in reg.read(self.experiments)][103:]
        self.assertEqual({r["target_id"] for r in later}, set(p3.TARGETS))
        self.assertEqual({r["clock"] for r in later}, {"C0"})
        self.assertEqual({r["harness_commit"] for r in later}, {COMMIT})
        self.assertEqual([r["experiment_id"] for r in later][:2], ["m4-experiment-00103", "m4-experiment-00104"])
        for name in ("m4-phase3-results-2026-10-07.json", "m4-phase3-predictions-2026-10-07.jsonl"):
            self.assertTrue((self.root / "reports" / name).is_file(), name)
        self.assertEqual(json.loads((self.root / "reports" / "m4-phase3-results-2026-10-07.json").read_text(encoding="utf-8"))["kind"], "m4_phase3_results")
        self.assertEqual(reg.verify_chain(self.holdout, "holdout_access", PROTOCOL)["records"], 1)

    def test_it_refuses_a_log_that_phase_2_has_not_filled(self):
        with self.assertRaisesRegex(DataError, "logs are not as Phase 3 expects"):
            self.go()  # a genesis record only: Phase 2 has not been run
        self.earlier_phase(count=50)
        with self.assertRaisesRegex(DataError, "logs are not as Phase 3 expects"):
            self.go()

    def test_it_refuses_a_log_whose_earlier_experiments_are_not_on_phase_2s_targets(self):
        self.earlier_phase(target="extension_after_open_ge_5pct")  # the right number of records, on a target Phase 3 itself is about to evaluate
        with self.assertRaisesRegex(DataError, "no earlier phase evaluated"):
            self.go()

    def test_it_refuses_unless_authorized_and_on_a_dirty_tree_and_is_run_once(self):
        self.earlier_phase()
        with mock.patch.object(p2, "run_all", self.fake_run_all), mock.patch.object(h, "ALLOW_REAL_EVALUATION", False):
            with self.assertRaises(h.EvaluationNotAuthorized):
                p2.run(self.engine, "2026-10-07", root=self.root, commit_state=(COMMIT, True), phase=p3.PHASE_3)
        self.assertEqual(self.requested, [])  # nothing was evaluated
        with self.assertRaisesRegex(DataError, "uncommitted"):
            self.go(commit_state=(COMMIT, False))
        self.assertEqual(self.requested, [])
        self.go()
        with self.assertRaisesRegex(DataError, "exists"):
            self.go()

    def test_phase_2_cannot_be_run_again_once_its_records_are_in_the_log(self):
        self.earlier_phase()
        with mock.patch.object(p2, "run_all", self.fake_run_all), mock.patch.object(h, "ALLOW_REAL_EVALUATION", True):
            with self.assertRaisesRegex(DataError, "logs are not as Phase 2 expects"):  # the default phase starts from a genesis-only log
                p2.run(self.engine, "2026-10-07", root=self.root, commit_state=(COMMIT, True))
        self.assertEqual(self.requested, [])


class CommandLineTests(unittest.TestCase):
    def test_run_needs_a_date_and_the_tripwire(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            p3.main(["run"])
        with mock.patch.object(h, "ALLOW_REAL_EVALUATION", False):
            with self.assertRaises(h.EvaluationNotAuthorized):
                p3.main(["run", "--date", "2026-10-07"])

    def test_audit_writes_phase_3s_report_for_phase_3s_targets(self):
        engine = harness()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(h.Harness, "from_repository", classmethod(lambda cls: engine)):
            out = Path(directory) / "audit.json"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(p3.main(["audit", "--output", str(out)]), 0)
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual((report["kind"], sorted(report["targets"])), ("m4_phase3_structure_audit", sorted(p3.TARGETS)))
        self.assertEqual(json.loads(printed.getvalue())["state"], "AUDIT")

    def test_run_is_phase_3s_run(self):
        seen = {}

        def fake(harness_, date, root=None, commit_state=None, phase=None):
            seen.update(date=date, phase=phase)
            return {"state": "EVALUATED"}
        with mock.patch.object(h.Harness, "from_repository", classmethod(lambda cls: harness())), mock.patch.object(p2, "run", fake), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(p3.main(["run", "--date", "2026-10-07"]), 0)
        self.assertEqual((seen["date"], seen["phase"]), ("2026-10-07", p3.PHASE_3))


if __name__ == "__main__":
    unittest.main()
