"""The Milestone 4 experiment log and holdout access log: a hash chain that starts with a genesis record, and records in exactly the protocol's fields."""
import json
import tempfile
import unittest
from pathlib import Path

from nre import m4_protocol as pr
from nre import m4_registry as reg
from nre.core import DataError, canonical, digest

PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
COMMIT, WHEN = "a" * 40, "2026-10-06T16:00:00Z"
line_of = reg.line_of


def experiment(sequence=1, state="EVALUATED"):
    return reg.experiment_record(PROTOCOL, COMMIT, WHEN, sequence, "gap_ge_3pct", "B", "C1_pooled_rate", "all_event", "dev_test_block_3", ["x", "y"], ["z"], "m4-features-v1",
                                 {"rate": 0.3}, [["z", 0.3]], {"n": 1}, "none", {"random_ranking": 410003}, state)


class LogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.experiments, self.holdout = Path(self.directory.name) / "e.jsonl", Path(self.directory.name) / "h.jsonl"

    def start(self):
        return reg.init_logs(PROTOCOL, COMMIT, WHEN, self.experiments, self.holdout)

    def test_both_logs_begin_with_a_genesis_record_that_names_the_protocol(self):
        e, h = self.start()
        for record, kind in ((e, "experiments"), (h, "holdout_access")):
            self.assertEqual((record["kind"], record["log"], record["previous_record_sha256"]), ("genesis", kind, None))
            self.assertEqual(record["protocol_sha256"], pr.protocol_sha256(PROTOCOL))
            self.assertEqual((record["protocol_version"], record["harness_commit"], record["created_at"]), ("1", COMMIT, WHEN))
        self.assertEqual((h["access_number"], h["events_read"]), (0, []))
        self.assertIn("No holdout outcome has been read", h["note"])
        self.assertIn("No predictor has been fitted", e["note"])
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL)["records"], 1)

    def test_a_log_is_started_once(self):
        self.start()
        with self.assertRaises(DataError):
            self.start()

    def test_a_record_carries_the_hash_of_the_line_before_it(self):
        self.start()
        first = reg.append(self.experiments, "experiments", experiment(1), PROTOCOL)
        second = reg.append(self.experiments, "experiments", experiment(2), PROTOCOL)
        lines = self.experiments.read_bytes().split(b"\n")
        self.assertEqual(first["previous_record_sha256"], digest(lines[0]))
        self.assertEqual(second["previous_record_sha256"], digest(lines[1]))
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL), {"records": 3, "last_record_sha256": digest(lines[2]),
                                                                                         "genesis_created_at": WHEN})

    def test_lines_are_canonical_json_one_record_each(self):
        self.start()
        reg.append(self.experiments, "experiments", experiment(1), PROTOCOL)
        for line in self.experiments.read_text(encoding="utf-8").splitlines():
            self.assertEqual(canonical(json.loads(line)).decode("utf-8"), line)

    def test_editing_a_record_in_the_middle_breaks_the_chain(self):
        self.start()
        for n in (1, 2, 3):
            reg.append(self.experiments, "experiments", experiment(n), PROTOCOL)
        lines = self.experiments.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[2])
        record["state"] = "INSUFFICIENT_DATA"
        lines[2] = canonical(record).decode("utf-8")
        self.experiments.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(DataError):
            reg.verify_chain(self.experiments, "experiments", PROTOCOL)

    def test_deleting_a_record_in_the_middle_breaks_the_chain(self):
        self.start()
        for n in (1, 2, 3):
            reg.append(self.experiments, "experiments", experiment(n), PROTOCOL)
        lines = self.experiments.read_text(encoding="utf-8").splitlines()
        self.experiments.write_text("\n".join(lines[:2] + lines[3:]) + "\n", encoding="utf-8")
        with self.assertRaises(DataError):
            reg.verify_chain(self.experiments, "experiments", PROTOCOL)

    def test_the_chain_survives_a_checkout_that_changes_line_endings(self):
        self.start()
        reg.append(self.experiments, "experiments", experiment(1), PROTOCOL)
        self.experiments.write_bytes(self.experiments.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL)["records"], 2)
        reg.append(self.experiments, "experiments", experiment(2), PROTOCOL)  # appending after a CRLF checkout still chains correctly
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL)["records"], 3)

    def test_a_log_without_its_genesis_is_refused(self):
        with self.assertRaises(DataError):
            reg.append(self.experiments, "experiments", experiment(1), PROTOCOL)
        self.experiments.write_text("", encoding="utf-8")
        with self.assertRaises(DataError):
            reg.verify_chain(self.experiments, "experiments", PROTOCOL)

    def test_a_log_whose_first_record_is_not_its_own_genesis_is_refused(self):
        self.start()
        record = {**experiment(1), "previous_record_sha256": None}
        self.experiments.write_text(line_of(record) + "\n", encoding="utf-8")  # an experiment where the genesis belongs
        with self.assertRaises(DataError):
            reg.verify_chain(self.experiments, "experiments", PROTOCOL)
        genesis_of_the_other_log = reg.genesis_record("holdout_access", PROTOCOL, COMMIT, WHEN)
        self.experiments.write_text(line_of({**genesis_of_the_other_log, "previous_record_sha256": None}) + "\n", encoding="utf-8")
        with self.assertRaises(DataError):  # the holdout log's genesis does not start the experiment log
            reg.verify_chain(self.experiments, "experiments", PROTOCOL)

    def test_a_second_genesis_is_refused(self):
        self.start()
        with self.assertRaises(DataError):
            reg.append(self.experiments, "experiments", reg.genesis_record("experiments", PROTOCOL, COMMIT, WHEN), PROTOCOL)

    def test_a_record_must_have_exactly_the_protocols_fields_and_no_chain_field_of_its_own(self):
        self.start()
        extra = {**experiment(1), "extra": 1}
        missing = {k: v for k, v in experiment(1).items() if k != "seed"}
        for bad in (extra, missing, {**experiment(1), "previous_record_sha256": "0" * 64}):
            with self.assertRaises(DataError):
                reg.append(self.experiments, "experiments", bad, PROTOCOL)
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL)["records"], 1)

    def test_the_experiment_record_has_the_protocols_fields_and_nothing_else(self):
        fields = PROTOCOL["experiment_log"]["experiment_record_fields"]
        self.assertEqual(set(experiment(1)) | {"previous_record_sha256"}, set(fields))
        self.assertEqual(set(reg.expected_fields(PROTOCOL, "holdout_access")), {"access_number", "protocol_sha256", "harness_commit", "reason", "events_read",
                                                                               "created_at", "previous_record_sha256"})

    def test_experiment_ids_and_hashes_come_from_the_content(self):
        record = experiment(7)
        self.assertEqual(record["experiment_id"], "m4-experiment-00007")
        self.assertEqual(record["train_event_ids_sha256"], reg.hash_list(["x", "y"]))
        self.assertEqual(experiment(1)["train_event_ids_sha256"], experiment(2)["train_event_ids_sha256"])
        self.assertEqual(record["predictions_sha256"], digest(canonical([["z", 0.3]])))
        self.assertEqual(record["parameters_sha256"], digest(canonical({"rate": 0.3})))

    def test_an_unknown_experiment_state_is_refused(self):
        with self.assertRaises(DataError):
            experiment(1, state="QUALIFIED")

    def test_holdout_access_records_name_the_events_read_and_why(self):
        self.start()
        record = reg.holdout_access_record(PROTOCOL, COMMIT, WHEN, 1, "the one look", ["b", "a"])
        written = reg.append(self.holdout, "holdout_access", record, PROTOCOL)
        self.assertEqual((written["access_number"], written["events_read"], written["reason"]), (1, ["a", "b"], "the one look"))
        self.assertEqual(reg.verify_chain(self.holdout, "holdout_access", PROTOCOL)["records"], 2)


if __name__ == "__main__":
    unittest.main()
