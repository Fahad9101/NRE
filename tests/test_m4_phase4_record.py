"""What Phase 4 recorded about itself: the owner's go-ahead and how it was read, and the details settled before any Phase 4 code existed and before any block-5 outcome was read."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_support as S  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_phase4 as p4  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre.core import canonical, digest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m4-phase4-authorization-2026-10-07.json"


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual((record["owner_message"]["text"], record["owner_message"]["at"]), ("authorize phase 4", "2026-10-07T12:16:31.579Z"))
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_message"]["at"])
        self.assertTrue(replied["text"].startswith("Phase 3 is done. The two C0-clock targets ran on the development folds only"))
        self.assertIn("Decide on Phase 4: the one logged look at block 5, the descriptive report, and the Milestone 4 report.", replied["text"])
        self.assertIn("This is a recommendation only; it authorizes nothing.", replied["text"])

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("one look at the sealed holdout", "the descriptive report with block-5 counts", "the Milestone 4 report", "COUNTS_ONLY", "technical rerun",
                       "They do not declare Milestone 4 accepted", "not read as an amendment", "protocol stays version 1", "ALLOW_HOLDOUT_LOOK stays False"):
            self.assertIn(phrase, text)

    def test_what_is_and_is_not_authorized_is_listed(self):
        record = self.record
        self.assertEqual(len(record["authorized_under_these_words"]), 5)
        authorized = " ".join(record["authorized_under_these_words"])
        for phrase in ("without reading a block-5 outcome", "ALLOW_HOLDOUT_LOOK on", "exactly one logged access", "closing record"):
            self.assertIn(phrase, authorized)
        refused = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("A second look", "amendment", "Any status, claim or edge statement", "Milestone 5", "Declaring Milestone 4 accepted"):
            self.assertIn(phrase, refused)

    def test_the_details_settled_before_the_look_are_listed_and_none_amends_the_protocol(self):
        settled = self.record["details_settled_before_the_look"]
        self.assertEqual([d["id"] for d in settled["new_in_phase_4"]], ["P4-%d" % n for n in range(1, 15)])
        self.assertIn("Not protocol amendments", settled["status"])
        protocol = pr.load_json(pr.PROTOCOL_PATH)
        self.assertEqual((protocol["protocol_version"], protocol["amendments"]["history"]), ("1", []))
        for detail in settled["new_in_phase_4"]:
            self.assertIsInstance(detail["could_move_a_result"], bool)
        self.assertEqual([d["id"] for d in settled["new_in_phase_4"] if d["could_move_a_result"]], ["P4-3", "P4-4"])

    def test_the_numbers_it_commits_to_follow_from_the_protocol_and_the_logs(self):
        text = " ".join(d["detail"] for d in self.record["details_settled_before_the_look"]["new_in_phase_4"])
        self.assertIn("58 records (four binary targets x six predictors x two versions, and the regression target x five predictors x two versions)", text)
        self.assertEqual(4 * 6 * 2 + 1 * 5 * 2, 58)
        self.assertIn("goes from 175 to 233 records", text)
        self.assertEqual(175 + 58, 233)
        self.assertIn("all 19 targets", text)
        protocol = pr.load_json(pr.PROTOCOL_PATH)
        self.assertEqual(sum(len(protocol["targets"][k]) for k in ("primary", "descriptive_only", "insufficient_data_by_rule")), 19)
        self.assertEqual(self.record["not_a_claim"][0], "Not a result: no block-5 outcome has been read when this record is written.")


class HoldoutAuditReportTests(unittest.TestCase):
    """The audit taken before the look: facts about the holdout fold that need no block-5 outcome."""
    PATH = ROOT / "reports" / "m4-phase4-holdout-structure-audit-2026-10-07.json"

    @classmethod
    def setUpClass(cls):
        cls.committed = json.loads(cls.PATH.read_text(encoding="utf-8"))

    def folds(self):
        return {(t, v): entry for t, versions in self.committed["targets"].items() for v, entry in versions.items()}

    def test_the_committed_audit_is_what_the_code_produces_from_the_committed_inputs(self):
        fresh = p4.audit_report(h.Harness.from_repository(holdout_log=S.genesis_only_holdout_log(self)))  # the holdout log as it was then: genesis only
        self.assertEqual(digest(canonical(fresh)), digest(canonical(self.committed)))

    def test_it_found_nothing_that_stops_the_look(self):
        folds = self.folds()
        self.assertEqual(len(folds), 5 * 2)  # five primary targets, two versions
        for key, entry in folds.items():
            self.assertEqual(entry["test_events"], 23, key)
            self.assertEqual(entry["cells_below_the_minimum_of_10"], {"C2_timing": [], "C3_sector_group": []}, key)  # no baseline falls back to the pooled value
            self.assertEqual(entry["test_events_that_would_fall_back_to_the_pooled_value"], {"C2_timing": 0, "C3_sector_group": 0}, key)
            self.assertEqual(entry["test_events_with_no_earlier_matured_event"], 0, key)  # every test event has a history
            self.assertEqual(entry["indicator_features_constant_in_training"], [], key)  # no feature is dropped
            self.assertEqual(entry["test_events_by_issuer_count"], {"1": 23}, key)  # 23 events from 23 issuers: no issuer has two events in the holdout
        for version in ("all_event", "clean_window"):
            self.assertEqual(self.committed["targets"]["day1_close_return"][version]["test_events_whose_history_mean_would_stop_the_run"], 0)

    def test_the_few_things_it_counts(self):
        folds = self.folds()
        own = {key: entry["test_events_with_no_earlier_event_of_their_own_issuer"] for key, entry in folds.items()}
        self.assertEqual({k: n for k, n in own.items() if n}, {("loses_half_of_gap", "all_event"): 2, ("loses_half_of_gap", "clean_window"): 2})
        training = {key: entry["training_events_with_the_target_defined"] for key, entry in folds.items()}
        self.assertEqual({t: (training[(t, "all_event")], training[(t, "clean_window")]) for t in p4.TARGETS},
                         {"gap_ge_3pct": (105, 98), "gap_ge_5pct": (105, 98), "day1_close_return": (105, 98), "extension_after_open_ge_5pct": (105, 98), "loses_half_of_gap": (48, 46)})
        entry = folds[("gap_ge_3pct", "all_event")]
        self.assertEqual((entry["test_events_by_cell"]["C2_timing"], entry["test_events_by_cell"]["C3_sector_group"]),
                         ({"after_hours": 16, "premarket": 7}, {"D": 10, "I": 8, "other": 5}))

    def test_it_says_it_read_no_outcome_and_evaluated_nothing(self):
        self.assertIn("no block-5 outcome", self.committed["purpose"])
        self.assertIn("not the opening gap", self.committed["purpose"])
        self.assertIn("Not a result: nothing was fitted, scored or evaluated.", self.committed["not_a_claim"])
        self.assertEqual(self.committed["holdout"], {"sealed_events": 23, "denied_reads": 0, "unsealed_loads": 0, "access_log_records_after_genesis": 0})


if __name__ == "__main__":
    unittest.main()
