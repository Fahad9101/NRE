"""What Phase 2 recorded about itself: the owner's go-ahead and how it was read, and the details settled before any real evaluation existed."""
import json
import unittest
from pathlib import Path

from nre import m4_harness as h
from nre import m4_phase2 as p2
from nre import m4_protocol as pr
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m4-phase2-authorization-2026-10-07.json"


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual((record["owner_message"]["text"], record["owner_message"]["at"]), ("authorize phase 2", "2026-10-07T04:40:50.937Z"))
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_message"]["at"])
        self.assertTrue(replied["text"].startswith("Phase 1 is done:"))
        self.assertIn("Recommending it does not authorize it.", replied["text"])

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("gap_ge_3pct, gap_ge_5pct and day1_close_return", "Phase 3", "not read as an amendment", "protocol stays version 1", "ALLOW_HOLDOUT_LOOK stays False"):
            self.assertIn(phrase, text)

    def test_what_is_and_is_not_authorized_is_listed(self):
        record = self.record
        self.assertEqual(len(record["authorized_under_these_words"]), 4)
        refused = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("holdout", "extension_after_open_ge_5pct", "loses_half_of_gap", "amendment", "Milestone 5", "Declaring Milestone 4 accepted"):
            self.assertIn(phrase, refused)

    def test_the_details_settled_before_any_evaluation_are_listed_and_none_amends_the_protocol(self):
        settled = self.record["details_settled_before_any_evaluation"]
        self.assertEqual([d["id"] for d in settled["new_in_phase_2"]], ["P2-%d" % n for n in range(1, 11)])
        self.assertIn("Not protocol amendments", settled["status"])
        protocol = pr.load_json(pr.PROTOCOL_PATH)
        self.assertEqual((protocol["protocol_version"], protocol["amendments"]["history"]), ("1", []))
        for detail in settled["new_in_phase_2"]:
            self.assertIsInstance(detail["could_move_a_result"], bool)


class StructureAuditReportTests(unittest.TestCase):
    """The audit taken before any Phase 2 predictor was evaluated: facts about the development folds that need only which labels are defined."""
    PATH = ROOT / "reports" / "m4-phase2-structure-audit-2026-10-07.json"

    @classmethod
    def setUpClass(cls):
        cls.committed = json.loads(cls.PATH.read_text(encoding="utf-8"))

    def test_the_committed_audit_is_what_the_code_produces_from_the_committed_inputs(self):
        fresh = p2.audit_report(h.Harness.from_repository())
        self.assertEqual(digest(canonical(fresh)), digest(canonical(self.committed)))

    def test_it_found_nothing_that_the_pre_registered_rules_do_not_already_cover(self):
        folds = [f for versions in self.committed["targets"].values() for fold in versions.values() for f in fold.values()]
        self.assertEqual(len(folds), 3 * 2 * 2)  # three targets, two versions, two development folds
        for fold in folds:
            self.assertEqual(fold["cells_below_the_minimum_of_10"], {"C2_timing": [], "C3_sector_group": []})  # no baseline falls back to the pooled value
            self.assertEqual(fold["test_events_that_would_fall_back_to_the_pooled_value"], {"C2_timing": 0, "C3_sector_group": 0})
            self.assertEqual(fold["test_events_with_no_earlier_matured_event"], 0)  # every test event has a history mean
            self.assertEqual(fold["test_events_with_no_earlier_event_of_their_own_issuer"], 0)
            self.assertEqual(fold["indicator_features_constant_in_training"], [])  # no feature is dropped
            self.assertIn(fold["training_rows_with_no_earlier_matured_event"], (2, 3))  # the ridge model leaves these out
        self.assertEqual(self.committed["holdout"], {"sealed_events": 23, "denied_reads": 0, "unsealed_loads": 0, "access_log_records_after_genesis": 0})

    def test_it_says_it_read_no_outcome_and_evaluated_nothing(self):
        self.assertIn("reads no outcome value", self.committed["purpose"])
        self.assertIn("Not a result: nothing was fitted, scored or evaluated.", self.committed["not_a_claim"])


if __name__ == "__main__":
    unittest.main()
