"""What Phase 4 recorded about itself: the owner's go-ahead and how it was read, and the details settled before any Phase 4 code existed and before any block-5 outcome was read."""
import json
import unittest
from pathlib import Path

from nre import m4_protocol as pr

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


if __name__ == "__main__":
    unittest.main()
