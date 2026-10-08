"""What Milestone 5 scoping recorded about itself: the owner's go-ahead and how it was read (reports/m5-scoping-authorization-2026-10-08.json)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m5-scoping-authorization-2026-10-08.json"


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual([(m["text"], m["at"]) for m in record["owner_messages"]], [("authorize m5 scoping", "2026-10-08T07:43:52.358Z")])
        self.assertIn("line 33553", record["owner_messages"][0]["source"])
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_messages"][0]["at"])
        self.assertTrue(replied["text"].startswith("CI run #236 for `fb33eea` passed on attempt 1"))
        self.assertIn('say "authorize m5 scoping"', replied["text"])
        self.assertIn("It is a recommendation only", replied["text"])

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("a scoping proposal, nothing built", "committed", "does not authorize reading any block-5 outcome again", "Milestone 4 stays as accepted", "decisions the proposal lists are the owner's",
                       "has seen the Milestone 4 holdout's results"):
            self.assertIn(phrase, text)

    def test_what_is_authorized_and_what_is_not_is_listed(self):
        record = self.record
        done = " ".join(record["authorized_and_done_under_these_words"])
        for name in ("docs/M5-ADVANCED-MODELS-SCOPE.md", "nre/m5_scoping_evidence.py", "reports/m5-scoping-evidence-2026-10-08.json", "tests/test_m5_scoping_record.py"):
            self.assertIn(name, done)
        not_authorized = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("Building any Milestone 5", "Pre-registering a Milestone 5 protocol", "Acquiring any data", "Any read of a block-5 outcome", "Declaring Milestone 5 accepted",
                       "Any change to the accepted Milestone 4 work", "Choosing among the decisions"):
            self.assertIn(phrase, not_authorized)
        self.assertIn("Not a start of Milestone 5 building", " ".join(record["not_a_claim"]))


if __name__ == "__main__":
    unittest.main()
