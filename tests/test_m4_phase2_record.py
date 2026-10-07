"""What Phase 2 recorded about itself: the owner's go-ahead and how it was read, and the details settled before any real evaluation existed."""
import json
import unittest
from pathlib import Path

from nre import m4_protocol as pr

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


if __name__ == "__main__":
    unittest.main()
