"""What Phase 1 committed alongside the harness: the two logs' genesis records, the dry-run report, and the mutation check's source patterns."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_support as S  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402
from nre.core import canonical, digest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
REPORT = ROOT / "reports" / "m4-harness-dry-run-2026-10-06.json"


class LogTests(unittest.TestCase):
    def test_the_committed_logs_are_intact_chains_that_begin_with_a_genesis_naming_the_protocol(self):
        for path, kind in ((reg.EXPERIMENT_LOG, "experiments"), (reg.HOLDOUT_LOG, "holdout_access")):
            self.assertTrue(path.is_file(), "%s must be committed with its genesis record" % path.name)
            self.assertGreaterEqual(reg.verify_chain(path, kind, PROTOCOL)["records"], 1)
            genesis = reg.read(path)[0][0]
            self.assertEqual((genesis["kind"], genesis["log"], genesis["protocol_sha256"]), ("genesis", kind, pr.protocol_sha256(PROTOCOL)))
            self.assertRegex(genesis["harness_commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(genesis["created_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_while_the_tripwires_are_off_each_log_holds_only_what_an_authorized_phase_put_there(self):
        # An experiment record or a holdout access can exist only once the phase that makes it has been authorized and has turned its tripwire on.
        if not h.ALLOW_REAL_EVALUATION:
            self.assertEqual(len(reg.read(reg.EXPERIMENT_LOG)), 1)
        # The holdout tripwire is turned on for the one look and off again after it (reports/m4-phase4-authorization-2026-10-07.json, P4-11): whatever its setting, the log holds
        # its genesis and at most that one access, which names the Phase 4 look and all 23 holdout events, and nothing else can have been added.
        accesses = [record for record, _ in reg.read(reg.HOLDOUT_LOG)][1:]
        self.assertLessEqual(len(accesses), 1)
        for access in accesses:
            self.assertEqual(access["access_number"], 1)
            self.assertTrue(access["reason"].startswith("Milestone 4 Phase 4: the one look at the final holdout"))
            self.assertEqual(len(access["events_read"]), 23)
        if accesses:
            self.assertFalse(h.ALLOW_HOLDOUT_LOOK, "after the look the tripwire is turned off again")

    def test_the_genesis_records_were_written_before_anything_was_evaluated(self):
        self.assertIn("No predictor has been fitted", reg.read(reg.EXPERIMENT_LOG)[0][0]["note"])
        self.assertIn("No holdout outcome has been read", reg.read(reg.HOLDOUT_LOG)[0][0]["note"])
        self.assertEqual(reg.read(reg.HOLDOUT_LOG)[0][0]["events_read"], [])


class DryRunReportTests(unittest.TestCase):
    def test_the_committed_dry_run_report_is_what_the_harness_produces_from_the_committed_inputs(self):
        committed = json.loads(REPORT.read_text(encoding="utf-8"))
        fresh = h.Harness.from_repository(holdout_log=S.genesis_only_holdout_log(self)).dry_run()  # the holdout log as it was then: genesis only
        self.assertEqual(digest(canonical(fresh)), digest(canonical(committed)))

    def test_the_report_says_nothing_was_evaluated_and_nothing_disagrees_with_the_freeze_record(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertTrue(report["integrity_ok"])
        self.assertEqual(report["agreement_with_the_freeze_record"]["disagreements"], [])
        self.assertEqual(report["evaluated"], {"predictors_fitted": 0, "predictions_made": 0, "metrics_computed": 0})
        self.assertEqual((report["holdout"]["denied_reads"], report["holdout"]["unsealed_loads"]), (0, 0))
        self.assertEqual(report["protocol"]["canonical_sha256"], pr.protocol_sha256(PROTOCOL))


class CompletionRecordTests(unittest.TestCase):
    """The closing record is a snapshot of Phase 1; these check it against the artifacts it names, not against the code as later phases change it."""
    RECORD = ROOT / "reports" / "m4-phase1-completion-2026-10-06.json"

    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(cls.RECORD.read_text(encoding="utf-8"))

    def test_the_record_names_the_artifacts_it_describes_and_their_hashes_match(self):
        record = self.record
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(record["run_on_the_real_inputs"]["dry_run_report_canonical_sha256"], digest(canonical(report)))
        self.assertEqual(record["protocol"]["canonical_sha256"], pr.protocol_sha256(PROTOCOL))
        for key, path in (("experiments", reg.EXPERIMENT_LOG), ("holdout_access", reg.HOLDOUT_LOG)):
            genesis, line_sha = reg.read(path)[0]
            self.assertEqual(record["logs"][key]["genesis_line_sha256"], line_sha)
            self.assertEqual(record["logs"][key]["genesis_harness_commit"], genesis["harness_commit"])
        for name in record["built"]["modules"] + record["built"]["tests"] + [record["built"]["tool"], record["built"]["doc"]]:
            self.assertTrue((ROOT / name).is_file(), name)
        for commit in (record["built"]["commit"], record["authorization"]["commit"]):
            self.assertRegex(commit, r"^[0-9a-f]{40}$")

    def test_the_record_says_nothing_was_evaluated_and_both_tripwires_were_off(self):
        record = self.record
        self.assertEqual(record["run_on_the_real_inputs"]["evaluated"], {"predictors_fitted": 0, "predictions_made": 0, "metrics_computed": 0})
        self.assertEqual((record["run_on_the_real_inputs"]["holdout"]["denied_reads"], record["run_on_the_real_inputs"]["holdout"]["unsealed_loads"]), (0, 0))
        self.assertEqual((record["tripwires"]["ALLOW_REAL_EVALUATION"], record["tripwires"]["ALLOW_HOLDOUT_LOOK"]), (False, False))
        self.assertFalse(record["protocol"]["amended"])
        self.assertEqual(record["tests"]["mutation_check"]["caught"], record["tests"]["mutation_check"]["deliberate_defects"])
        self.assertIn("Not Milestone 4 acceptance.", record["not_a_claim"])

    def test_what_is_not_authorized_is_listed_and_the_phases_after_this_one_are_among_it(self):
        text = " ".join(self.record["not_done_and_not_authorized"])
        for phrase in ("Phase 2", "Phase 3", "Phase 4", "holdout", "Milestone 4 accepted"):
            self.assertIn(phrase, text)


class MutationCheckTests(unittest.TestCase):
    def test_every_deliberate_defect_in_the_mutation_check_still_matches_the_source_exactly_once(self):
        spec = importlib.util.spec_from_file_location("m4_mutation_check", ROOT / "scripts" / "m4_mutation_check.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertGreaterEqual(len(module.MUTATIONS), 40)
        self.assertEqual([m[0] for m in module.MUTATIONS if module.occurrences(m) != 1], [])
        self.assertEqual(len({m[0] for m in module.MUTATIONS}), len(module.MUTATIONS), "defect descriptions must be unique")


if __name__ == "__main__":
    unittest.main()
