"""What Milestone 5 Phase 1a recorded about itself: the owner's go-ahead and how it was read (reports/m5-phase1a-authorization-2026-10-08.json)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m5-phase1a-authorization-2026-10-08.json"
PROPOSAL = ROOT / "docs" / "M5-ADVANCED-MODELS-SCOPE.md"


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual([(m["text"], m["at"]) for m in record["owner_messages"]], [("authorize phase 1a", "2026-10-08T16:25:07.994Z")])
        self.assertIn("line 35069", record["owner_messages"][0]["source"])
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_messages"][0]["at"])
        self.assertTrue(replied["text"].startswith("`1e2375b` is on `origin/main`, and CI is green."))
        for phrase in ('say "authorize phase 1a" to start the availability probe', "a small read-only check", "no prices, and nothing would enter the dataset", "This is a recommendation, not an authorization."):
            self.assertIn(phrase, replied["text"])

    def test_the_phase_it_authorizes_is_worded_as_in_the_proposal(self):
        words = self.record["phase_as_proposed"]["words"]
        self.assertIn(words, " ".join(PROPOSAL.read_text(encoding="utf-8").split()))
        self.assertTrue(words.startswith("an availability probe (no acquisition into the dataset)"))
        self.assertEqual(self.record["phase_as_proposed"]["document"], "docs/M5-ADVANCED-MODELS-SCOPE.md")

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("It authorizes Phase 1a of docs/M5-ADVANCED-MODELS-SCOPE.md", "committed before the probe is run", "Nothing is bought", "no event, label, feature or price is added to the dataset or committed",
                       "The words do not carry a push", "It does not authorize 1b, 0, 1c or any later phase", "Disclosure:", "a test checks that its report holds no price or volume value"):
            self.assertIn(phrase, text)

    def test_what_is_authorized_and_what_is_not_is_listed(self):
        record = self.record
        authorized = " ".join(record["authorized_under_these_words"])
        for phrase in ("The probe spec, the probe module, its tests and its GitHub Actions workflow", "once the owner has said \"push\"", "Reading primary-source documentation (Alpaca, SEC, FINRA, CBOE)",
                       "A findings record and a findings document"):
            self.assertIn(phrase, authorized)
        not_authorized = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("Phase 1b, enumerating or collecting any event since 2026-04-01", "Phase 1c, acquiring any derived feature", "Phase 0, pre-registering", "Phase 2", "Phase 3", "Phase 4",
                       "Computing or storing any return, label, feature, price or volume value", "Fetching data from a provider the project has not reviewed", "Any read of a block-5 outcome",
                       "provider-rights-at-scale question", "Pushing without the owner's word", "Declaring Milestone 5 accepted", "Any change to the accepted Milestone 4 work"):
            self.assertIn(phrase, not_authorized)
        self.assertIn("does not change a confirmed default on its own", record["change_rule"])
        self.assertIn("Not a claim that any feature family will be used", " ".join(record["not_a_claim"]))
        self.assertEqual(record["kind"], "m5_phase1a_authorization")


if __name__ == "__main__":
    unittest.main()
