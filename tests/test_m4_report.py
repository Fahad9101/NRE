"""The Milestone 4 report assembler (P4-13), on a rehearsed Phase 4 output: the real Phase 2 and 3 results and records, with Phase 4's outputs and logs from the dress rehearsal (synthetic
block-5 labels, the real block-5 records destroyed). It reads no label and no block-5 outcome, and it is a pure function of the artifacts it reads."""
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_rehearsal as R  # noqa: E402
import m4_support as S  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_phase4 as p4  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_report as rep  # noqa: E402
from nre.core import DataError, canonical, digest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
ACCOUNTING = "m4-phase4-replay-accesses-2026-10-07.json"
LOOKED_ONCE = "the holdout was looked at once"


def with_tests(root):
    (root / "tests").mkdir(exist_ok=True)
    shutil.copy(ROOT / "tests" / "test_m4_harness.py", root / "tests" / "test_m4_harness.py")  # the report names the tests that implement the protocol's required ones
    shutil.copy(ROOT / "reports" / ACCOUNTING, root / "reports" / ACCOUNTING)  # and states every access to the holdout, the counted replays included
    return root


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary, cls.root, cls.harness, _ = R.rehearse(cls, S.holdout_balanced)
        with_tests(cls.root)
        cls.report = rep.assemble(cls.root)

    def test_it_covers_the_five_primaries_and_the_fourteen_other_targets_in_both_versions(self):
        report = self.report
        self.assertEqual(sorted(report["primary_targets"]), sorted(p4.TARGETS))
        self.assertEqual(len(report["other_targets"]), 14)
        self.assertEqual({row["role"] for row in report["other_targets"].values()}, {"descriptive_only", "insufficient_data_by_rule"})
        for row in report["other_targets"].values():
            self.assertEqual({"all_event", "clean_window"} <= set(row), True)
        for entry in report["primary_targets"].values():
            self.assertEqual(set(entry["development"]), set(d.VERSIONS))
            self.assertEqual(set(entry["holdout"]), set(d.VERSIONS))
        self.assertEqual(sorted(report["regression_labels"]["all_event"]), sorted(["day1_open_return", "day1_high_return", "day1_close_return", "session_5_close_return", "session_20_close_return"]))
        json.dumps(report, allow_nan=False)

    def test_the_numbers_are_the_numbers_of_the_artifacts_it_reads(self):
        phase3 = json.loads((self.root / "reports" / "m4-phase3-results-2026-10-07.json").read_text(encoding="utf-8"))
        contrast = phase3["evaluations"]["extension_after_open_ge_5pct"]["clean_window"]["contrasts"]["M2_logistic"]
        got = self.report["primary_targets"]["extension_after_open_ge_5pct"]["development"]["clean_window"]["confirmatory_model_against_c1"]
        self.assertEqual((got["estimate"], got["interval_99"]["low"], got["interval_99"]["high"], got["role"]), (contrast["estimate"], contrast["headline"]["0.99"]["low"],
                                                                                                                contrast["headline"]["0.99"]["high"], "confirmatory"))
        self.assertEqual(self.report["primary_targets"]["extension_after_open_ge_5pct"]["development_status"], "NOT_DISTINGUISHABLE")
        self.assertEqual(self.report["primary_targets"]["loses_half_of_gap"]["development_status"], "INSUFFICIENT_DATA")
        self.assertEqual(self.report["primary_targets"]["loses_half_of_gap"]["development"]["clean_window"]["state"], d.INSUFFICIENT_DATA)
        for target_id in p4.TARGETS:
            for version in d.VERSIONS:
                self.assertEqual(self.report["primary_targets"][target_id]["holdout"][version]["state"], self.summary["states"][target_id][version])
        results = json.loads((self.root / "reports" / "m4-phase4-holdout-results-2026-10-07.json").read_text(encoding="utf-8"))
        holdout = self.report["primary_targets"]["gap_ge_3pct"]["holdout"]["all_event"]
        reported = results["evaluations"]["gap_ge_3pct"]["all_event"]["contrasts"]["M2_logistic"]
        self.assertEqual((holdout["confirmatory_model_against_c1"]["estimate"], holdout["test_counts"]["events"]), (reported["estimate"], 23))
        self.assertEqual(holdout["confirmatory_model_against_c1"]["role"], "holdout_replication_check")
        self.assertIn("against_the_development_result", holdout["confirmatory_model_against_c1"])
        descriptive = json.loads((self.root / "reports" / "m4-phase4-descriptive-2026-10-07.json").read_text(encoding="utf-8"))
        row = descriptive["targets"]["full_gap_fill"]["all_event"]
        self.assertEqual({k: self.report["other_targets"]["full_gap_fill"]["all_event"][k] for k in ("n_defined", "positives", "negatives", "bucket")},
                         {k: row[k] for k in ("n_defined", "positives", "negatives", "bucket")})

    def test_the_estimable_and_the_not_estimable_are_listed(self):
        estimable = self.report["estimable"]
        self.assertIn(["extension_after_open_ge_5pct", "clean_window"], estimable["development"]["evaluated"])
        self.assertEqual(estimable["development"]["insufficient_data"], [["loses_half_of_gap", "clean_window"]])
        self.assertIn(["gap_ge_3pct", "all_event"], estimable["holdout"]["evaluated"])
        self.assertEqual(len(estimable["not_modelled"]), 14)
        every = {tuple(x) for k in ("evaluated", "counts_only", "insufficient_data") for x in estimable["holdout"][k]}
        self.assertEqual(len(every), 10)  # every cell of the 5 x 2 grid is in exactly one list
        self.assertEqual(sum(len(estimable["holdout"][k]) for k in ("evaluated", "counts_only", "insufficient_data")), 10)

    def test_the_summary_counts_what_the_primary_sections_show(self):
        summary = self.report["summary"]
        self.assertEqual(summary["pooled_development_contrasts"]["reported"], 50 + 27)  # Phase 2's 50 and Phase 3's 27
        self.assertEqual(summary["pooled_development_contrasts"]["excluding_zero_at_95"], 0)
        self.assertEqual(summary["development_fold_contrasts"], {"reported": 12 + 6, "excluding_zero_at_95": 2})  # Phase 2 had two per-fold intervals that excluded zero
        evaluated = len(self.report["estimable"]["holdout"]["evaluated"])
        self.assertGreater(summary["holdout_contrasts"]["reported"], 0)
        self.assertEqual(len(summary["holdout_direction_checks"]), evaluated)
        self.assertEqual(summary["development_statuses"]["gap_ge_3pct"], "NOT_DISTINGUISHABLE")

    def test_the_integrity_section_states_one_access_the_logs_and_the_phases(self):
        integrity = self.report["integrity"]
        self.assertEqual(integrity["logs"]["holdout_accesses_after_genesis"], 1)  # the chained log holds the look only
        accounting = json.loads((ROOT / "reports" / ACCOUNTING).read_text(encoding="utf-8"))
        replays = accounting["totals"]["replay_accesses"]
        self.assertGreater(replays, 0)
        self.assertEqual(integrity["logs"]["holdout_accesses"], {"logged_in_the_chain": 1, "replays_counted": replays, "in_total": 1 + replays, "accounting_record": "reports/" + ACCOUNTING,
                                                                  "owner_decision": accounting["owner_decision"]["owner_message"]})
        self.assertEqual(self.report["summary"]["holdout_accesses_in_total"], accounting["totals"]["accesses"])
        self.assertEqual(integrity["logs"]["experiments"]["records"], p4.EXPERIMENTS_BEFORE + 58)
        self.assertEqual([a["events_read"] for a in integrity["logs"]["the_accesses"]], [23])
        self.assertTrue(integrity["protocol"]["matches_the_freeze_record"])
        self.assertEqual(integrity["protocol"]["amendments"], [])
        self.assertEqual(set(integrity["phases"]), {"phase1", "phase2", "phase3", "phase4"})
        self.assertEqual({p: integrity["phases"][p]["suite_tests_run"] for p in ("phase1", "phase2", "phase3")}, {"phase1": 742, "phase2": 835, "phase3": 896})
        self.assertIsNone(integrity["phases"]["phase4"]["suite_tests_run"])  # Phase 4's closing record is written after the report
        self.assertEqual(integrity["determinism"], {"phase2": True, "phase3": True, "phase4": True})
        self.assertEqual({k: v["problems"] for k, v in integrity["independent_recomputation"].items()}, {"phase2": 0, "phase3": 0})
        required = integrity["required_leakage_and_integrity_tests"]
        self.assertEqual(len(required), 8)
        self.assertTrue(all(item["implemented_by"] for item in required))
        self.assertTrue(all(name.startswith("test_%d_" % number) for number, item in enumerate(required, 1) for name in item["implemented_by"]))

    def test_each_acceptance_criterion_is_there_with_its_evidence_and_the_decision_is_the_owners(self):
        criteria = self.report["acceptance_criteria"]["criteria"]
        self.assertEqual(len(criteria), 8)
        self.assertEqual([c["criterion"] for c in criteria][0], "this protocol was frozen before evaluation")
        self.assertTrue(all(c["evidence"] for c in criteria))
        others = [c for c in criteria if c["criterion"] != LOOKED_ONCE]
        self.assertTrue(all(c["met_by_the_evidence"] is True for c in others), [c["criterion"] for c in others if c["met_by_the_evidence"] is not True])
        looked_once = next(c for c in criteria if c["criterion"] == LOOKED_ONCE)
        self.assertEqual(looked_once["met_by_the_evidence"], rep.JUDGMENT)  # one look in the chain, and replays the owner counted as accesses: the facts are stated, the judgment is the owner's
        self.assertIn("Count the replays as accesses.", looked_once["evidence"])
        self.assertIn("%d accesses in all" % self.report["summary"]["holdout_accesses_in_total"], looked_once["evidence"])
        self.assertIn("nothing here declares Milestone 4 accepted", self.report["acceptance_criteria"]["decision"])
        self.assertEqual(self.report["acceptance_criteria"]["does_not_require"], "that any predictor beats the base rate")
        self.assertIn("Not Milestone 4 acceptance", " ".join(self.report["not_a_claim"]))

    def test_the_limits_and_the_open_review_items_are_carried_through(self):
        limits = self.report["limits"]
        self.assertEqual(limits["from_the_protocol"], PROTOCOL["disclosures"]["limits"])
        self.assertIn("confounded", limits["holdout_selection_regime"])
        self.assertEqual(len(limits["cannot_establish"]), 3)
        owner = self.report["open_for_the_owner"]
        self.assertEqual(owner["from_the_protocol_to_review"], PROTOCOL["disclosures"]["to_review"])
        self.assertEqual(len(owner["protocol_silent_details_that_could_move_a_result"]), 5)
        phase2 = json.loads((self.root / "reports" / "m4-phase2-authorization-2026-10-07.json").read_text(encoding="utf-8"))["details_settled_before_any_evaluation"]["new_in_phase_2"]
        self.assertEqual({p: [i["id"] for i in items if i["could_move_a_result"]] for p, items in owner["details_the_assistant_settled_in_later_phases"].items()},
                         {"phase2": [i["id"] for i in phase2 if i["could_move_a_result"]], "phase3": ["P3-1"], "phase4": ["P4-3", "P4-4"]})
        self.assertEqual([len(items) for items in owner["details_the_assistant_settled_in_later_phases"].values()], [10, 7, 14])
        self.assertIn("has not answered", owner["status"])
        self.assertIn("counted as accesses", owner["replay_tests"]["decided"])
        self.assertIn("Count the replays as accesses.", owner["replay_tests"]["decided"])
        self.assertIn("only on request", owner["replay_tests"]["open"])


class ReportPropertiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary, cls.root, cls.harness, _ = R.rehearse(cls, S.holdout_balanced)
        with_tests(cls.root)

    def test_it_is_a_pure_function_of_the_artifacts_and_reads_no_label(self):
        first = rep.assemble(self.root)
        with mock.patch.object(d, "load_inputs", side_effect=AssertionError("the report read labels")):
            second = rep.assemble(self.root)
        self.assertEqual(digest(canonical(first)), digest(canonical(second)))

    def test_it_refuses_without_phase_4_outputs_or_with_an_altered_development_result_or_protocol(self):
        for pattern in R.OUTPUTS:
            for path in (self.root / "reports").glob(pattern):
                path.rename(path.with_name(path.name + ".moved"))
        with self.assertRaisesRegex(DataError, "Phase 4 has not been run"):
            rep.assemble(self.root)
        for path in (self.root / "reports").glob("*.moved"):
            path.rename(path.with_name(path.name[:-len(".moved")]))
        rep.assemble(self.root)
        results = self.root / "reports" / "m4-phase2-results-2026-10-07.json"
        original = results.read_text(encoding="utf-8")
        data = json.loads(original)
        data["statuses"]["gap_ge_3pct"]["M2_logistic"] = "DISTINGUISHABLE_BETTER"
        results.write_text(json.dumps(data), encoding="utf-8")
        try:
            with self.assertRaisesRegex(DataError, "does not match the hash its completion record holds"):
                rep.assemble(self.root)
        finally:
            results.write_text(original, encoding="utf-8")
        protocol = self.root / "config" / "m4-protocol.json"
        original = protocol.read_text(encoding="utf-8")
        protocol.write_text(json.dumps({**json.loads(original), "tampered": True}), encoding="utf-8")
        try:
            with self.assertRaisesRegex(DataError, "does not match the hash in its freeze record"):
                rep.assemble(self.root)
        finally:
            protocol.write_text(original, encoding="utf-8")

    def test_a_second_access_in_the_log_is_visible_in_the_report_and_fails_its_criterion(self):
        h_log = self.root / "reports" / "m4-holdout-access-log.jsonl"
        before = h_log.read_bytes()
        try:
            from nre import m4_registry as reg
            reg.append(h_log, "holdout_access", reg.holdout_access_record(PROTOCOL, "f" * 40, "2026-10-07T20:00:00Z", 2, "a second look", ["x"]), PROTOCOL)
            report = rep.assemble(self.root)
        finally:
            h_log.write_bytes(before)
        self.assertEqual(report["integrity"]["logs"]["holdout_accesses_after_genesis"], 2)
        looked_once = next(c for c in report["acceptance_criteria"]["criteria"] if c["criterion"] == LOOKED_ONCE)
        self.assertIs(looked_once["met_by_the_evidence"], False)

    def test_it_refuses_without_the_replay_accounting_or_with_one_that_does_not_add_up(self):
        path = self.root / "reports" / ACCOUNTING
        original = path.read_text(encoding="utf-8")
        data = json.loads(original)
        try:
            path.unlink()
            with self.assertRaisesRegex(DataError, "the replay accounting is missing"):
                rep.assemble(self.root)
            swapped = json.loads(original)
            swapped["accesses"][2]["access_number"], swapped["accesses"][3]["access_number"] = swapped["accesses"][3]["access_number"], swapped["accesses"][2]["access_number"]
            path.write_text(json.dumps(swapped), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "not a sequence of accesses numbered from the look"):
                rep.assemble(self.root)
            relabelled = json.loads(original)
            relabelled["accesses"][1]["kind"] = "the_look"
            path.write_text(json.dumps(relabelled), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "not a sequence of accesses numbered from the look"):
                rep.assemble(self.root)
            miscounted = json.loads(original)
            miscounted["totals"]["replay_accesses"] += 1
            path.write_text(json.dumps(miscounted), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "totals do not match its accesses"):
                rep.assemble(self.root)
        finally:
            path.write_text(original, encoding="utf-8")
        self.assertEqual(rep.assemble(self.root)["summary"]["holdout_accesses_in_total"], data["totals"]["accesses"])

    def test_with_no_replays_the_criterion_is_met_and_with_replays_it_is_left_to_the_owner(self):
        path = self.root / "reports" / ACCOUNTING
        original = path.read_text(encoding="utf-8")
        look_only = json.loads(original)
        look_only["accesses"] = look_only["accesses"][:1]
        look_only["totals"].update({"accesses": 1, "replay_accesses": 0})
        try:
            path.write_text(json.dumps(look_only), encoding="utf-8")
            report = rep.assemble(self.root)
            looked_once = next(c for c in report["acceptance_criteria"]["criteria"] if c["criterion"] == LOOKED_ONCE)
            self.assertIs(looked_once["met_by_the_evidence"], True)
            self.assertEqual(report["summary"]["holdout_accesses_in_total"], 1)
            self.assertEqual(report["integrity"]["logs"]["holdout_accesses"]["replays_counted"], 0)
        finally:
            path.write_text(original, encoding="utf-8")
        report = rep.assemble(self.root)
        self.assertEqual(next(c for c in report["acceptance_criteria"]["criteria"] if c["criterion"] == LOOKED_ONCE)["met_by_the_evidence"], rep.JUDGMENT)


if __name__ == "__main__":
    unittest.main()
