"""What Phase 3 recorded about itself: the owner's go-ahead and how it was read, and the details settled before any C0-clock evaluation existed."""
import json
import unittest
from pathlib import Path

from nre import m4_harness as h
from nre import m4_phase2 as p2
from nre import m4_phase3 as p3
from nre import m4_protocol as pr
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m4-phase3-authorization-2026-10-07.json"


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual((record["owner_message"]["text"], record["owner_message"]["at"]), ("authorize phase 3", "2026-10-07T11:03:34.484Z"))
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_message"]["at"])
        self.assertTrue(replied["text"].startswith("Phase 2 is done:"))
        self.assertIn("Recommending it does not authorize it.", replied["text"])

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("extension_after_open_ge_5pct", "loses_half_of_gap", "full_gap_fill", "descriptive-only", "INSUFFICIENT_DATA", "not read as an amendment",
                       "protocol stays version 1", "ALLOW_HOLDOUT_LOOK stays False"):
            self.assertIn(phrase, text)

    def test_what_is_and_is_not_authorized_is_listed(self):
        record = self.record
        self.assertEqual(len(record["authorized_under_these_words"]), 4)
        refused = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("holdout", "full_gap_fill", "amendment", "Milestone 5", "Declaring Milestone 4 accepted"):
            self.assertIn(phrase, refused)

    def test_the_details_settled_before_any_c0_evaluation_are_listed_and_none_amends_the_protocol(self):
        settled = self.record["details_settled_before_any_c0_evaluation"]
        self.assertEqual([d["id"] for d in settled["new_in_phase_3"]], ["P3-%d" % n for n in range(1, 8)])
        self.assertIn("Not protocol amendments", settled["status"])
        protocol = pr.load_json(pr.PROTOCOL_PATH)
        self.assertEqual((protocol["protocol_version"], protocol["amendments"]["history"]), ("1", []))
        for detail in settled["new_in_phase_3"]:
            self.assertIsInstance(detail["could_move_a_result"], bool)


class StructureAuditReportTests(unittest.TestCase):
    """The audit taken before any C0-clock predictor was evaluated: facts about the development folds that need only which labels are defined."""
    PATH = ROOT / "reports" / "m4-phase3-structure-audit-2026-10-07.json"

    @classmethod
    def setUpClass(cls):
        cls.committed = json.loads(cls.PATH.read_text(encoding="utf-8"))

    def folds(self, target=None, version=None):
        return {(t, v, name): fold for t, versions in self.committed["targets"].items() for v, by_fold in versions.items() for name, fold in by_fold.items()
                if target in (None, t) and version in (None, v)}

    def test_the_committed_audit_is_what_the_code_produces_from_the_committed_inputs(self):
        fresh = p2.audit_report(h.Harness.from_repository(), p3.PHASE_3)
        self.assertEqual(digest(canonical(fresh)), digest(canonical(self.committed)))

    def test_every_event_in_either_target_has_the_opening_gap_m2_takes_so_no_rule_is_needed_for_one_without(self):
        folds = self.folds()
        self.assertEqual(len(folds), 2 * 2 * 2)  # two targets, two versions, two development folds
        for fold in folds.values():
            self.assertEqual((fold["training_rows_with_an_undefined_opening_gap"], fold["test_events_with_an_undefined_opening_gap"]), (0, 0))
            self.assertEqual(fold["test_events_with_no_earlier_matured_event"], 0)
            self.assertEqual(fold["indicator_features_constant_in_training"], [])  # no feature is dropped

    def test_extension_after_open_needs_no_fallback_and_loses_half_of_gap_falls_back_where_its_cells_are_thin(self):
        for key, fold in self.folds("extension_after_open_ge_5pct").items():
            self.assertEqual(fold["cells_below_the_minimum_of_10"], {"C2_timing": [], "C3_sector_group": []}, key)
            self.assertEqual(fold["test_events_that_would_fall_back_to_the_pooled_value"], {"C2_timing": 0, "C3_sector_group": 0}, key)
        fallbacks = {key[1:]: (f["cells_below_the_minimum_of_10"], f["test_events_that_would_fall_back_to_the_pooled_value"], f["test_events_with_no_earlier_event_of_their_own_issuer"])
                     for key, f in self.folds("loses_half_of_gap").items()}
        self.assertEqual(fallbacks, {
            ("all_event", "dev_test_block_3"): ({"C2_timing": ["premarket"], "C3_sector_group": ["I", "other"]}, {"C2_timing": 5, "C3_sector_group": 8}, 2),
            ("all_event", "dev_test_block_4"): ({"C2_timing": [], "C3_sector_group": []}, {"C2_timing": 0, "C3_sector_group": 0}, 2),
            ("clean_window", "dev_test_block_3"): ({"C2_timing": ["premarket"], "C3_sector_group": ["I", "other"]}, {"C2_timing": 5, "C3_sector_group": 8}, 4),
            ("clean_window", "dev_test_block_4"): ({"C2_timing": [], "C3_sector_group": ["other"]}, {"C2_timing": 0, "C3_sector_group": 2}, 2)})

    def test_the_sizes_of_the_folds_are_those_the_protocol_was_frozen_against(self):
        sizes = {key: (f["training_events_with_the_target_defined"], f["test_events_with_the_target_defined"]) for key, f in self.folds().items()}
        self.assertEqual(sizes, {
            ("extension_after_open_ge_5pct", "all_event", "dev_test_block_3"): (61, 21), ("extension_after_open_ge_5pct", "all_event", "dev_test_block_4"): (82, 23),
            ("extension_after_open_ge_5pct", "clean_window", "dev_test_block_3"): (55, 20), ("extension_after_open_ge_5pct", "clean_window", "dev_test_block_4"): (75, 23),
            ("loses_half_of_gap", "all_event", "dev_test_block_3"): (25, 13), ("loses_half_of_gap", "all_event", "dev_test_block_4"): (38, 10),
            ("loses_half_of_gap", "clean_window", "dev_test_block_3"): (23, 13), ("loses_half_of_gap", "clean_window", "dev_test_block_4"): (36, 10)})

    def test_it_says_it_read_no_outcome_not_even_the_opening_gap_and_evaluated_nothing(self):
        self.assertIn("reads no outcome value", self.committed["purpose"])
        self.assertIn("not the value of the opening gap", self.committed["purpose"])
        self.assertIn("Not a result: nothing was fitted, scored or evaluated.", self.committed["not_a_claim"])
        self.assertEqual(self.committed["holdout"], {"sealed_events": 23, "denied_reads": 0, "unsealed_loads": 0, "access_log_records_after_genesis": 0})


if __name__ == "__main__":
    unittest.main()
