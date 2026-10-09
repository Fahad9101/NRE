"""The owner's signoff of Milestone 5 Phase 1b batch 1 (reports/m5-phase1b-batch1-signoff-2026-10-09.json): the three answers as given, what each decides, and the events file that carries them out -- eight events attested on the record,
NBIX and ASMB not -- with the pipeline change that answer (A) authorizes."""
import json
import re
import unittest
from pathlib import Path

from nre import event_acquire as ea

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch1-signoff-2026-10-09.json"
PACKET_PATH = "reports/m5-phase1b-batch1-signoff-packet-2026-10-09.json"
ATTESTED = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"]
NBIX = "nbix-m5b-2026-05-05"
ANSWER = 'Owner sign-off ("Yes, attest all eight (Recommended)", 2026-10-09) on '
BASIS = {
    "first_public_time": ANSWER + "the release-time evidence in " + PACKET_PATH + " (the wire page's minute and its machine-readable time, the same-day release check), accepting the residual gap the packet states.",
    "historical_identity": ANSWER + "the identity evidence in " + PACKET_PATH + " (the event filing's cover row, the previous Milestone 1 event, no Item 1.03, 3.01, 3.03, 4.01 or 5.03 8-K in the archived history).",
    "corporate_actions": ANSWER + "the two signals in " + PACKET_PATH + " (no Item 3.03 or 5.03 8-K in the archived history up to the window end, and Alpaca's real answer as the sealed dry run reported it).",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class SignoffRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RECORD_PATH)

    def test_the_three_answers_are_quoted_as_given(self):
        record = self.record
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-09T18:15:39.381Z", "session transcript, line 41007 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-09T18:30:06.367Z", "session transcript, line 41013 (the tool result of the questions)"))
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        qa = record["questions_and_answers"]
        self.assertEqual([(q["header"], q["owner_selected"]) for q in qa],
                         [("Attest 8", "Yes, attest all eight (Recommended)"), ("NBIX 05-05", "(A) Additive pipeline change (Recommended)"), ("ASMB 05-07", "Leave it quarantined (Recommended)")])
        self.assertEqual(qa[0]["question"], "Attest first-public time, historical identity and corporate actions for the eight batch 1 events that ran (CACI, ALKT, JBSS, HURN, PARR, CXT, ASPN, COLL), on the evidence in " + PACKET_PATH + "?")
        self.assertEqual(qa[1]["question"], "NBIX 2026-05-05 errored in the dry run on a corporate action with no ex-date (probably the Soleno merger entry). How should it be handled?")
        self.assertEqual(qa[2]["question"], "ASMB 2026-05-07 was released at 16:00 ET, the instant of the close, which the calendar classes as bell-ambiguous, so no event spec can be built. Leave it quarantined or exclude it?")
        self.assertEqual([[o["label"] for o in q["options_offered"]] for q in qa],
                         [["Yes, attest all eight (Recommended)", "Not yet"], ["(A) Additive pipeline change (Recommended)", "(B) Leave it quarantined"], ["Leave it quarantined (Recommended)", "Exclude it"]])
        self.assertIn("You accept the residual gap that open-web research cannot close: an earlier public disclosure with no discoverable trace.", qa[0]["options_offered"][0]["description"])
        self.assertIn("In nre/event_acquire.py an action with no ex_date uses its effective date (then its payable or process date) and still fails closed if it has none", qa[1]["options_offered"][0]["description"])
        self.assertIn("the Milestone 1 pinned matches re-run on real data as the check", qa[1]["options_offered"][0]["description"])
        self.assertIn("A second dry run then lists the action for you to see before NBIX is attested.", qa[1]["options_offered"][0]["description"])
        self.assertIn("as GALT and PDFS were", qa[1]["options_offered"][1]["description"])

    def test_it_says_what_each_answer_decides(self):
        scope = self.record["scope"]
        self.assertEqual(scope["attested"]["events"], ATTESTED)
        self.assertEqual(scope["attested"]["attestations"], ["first_public_time", "historical_identity", "corporate_actions"])
        self.assertIn("accepting the residual gap that open-web research cannot close", scope["attested"]["read_as"])
        self.assertIn("as caveats, not exclusions", scope["attested"]["read_as"])
        nbix = scope["nbix"]
        self.assertEqual((nbix["event"], nbix["decision"]), (NBIX, "(A)"))
        self.assertIn("it does not attest NBIX, which stays unattested until the owner has seen the listed action", nbix["read_as"])
        self.assertIn("labels crossing it are suppressed as for any action", nbix["read_as"])
        self.assertEqual(scope["asmb"]["disposition"], "quarantined")
        self.assertIn("Left quarantined, not excluded", scope["asmb"]["read_as"])
        text = " ".join(self.record["not_a_claim"])
        for phrase in ("no label, price or return has been computed or viewed", "Not an attestation of NBIX 2026-05-05, which stays unattested.", "they travel with the labels as caveats"):
            self.assertIn(phrase, text)
        self.assertEqual((self.record["kind"], self.record["recorded_on"]), ("m5_phase1b_batch1_signoff", "2026-10-09"))
        self.assertIn("quoted from the session transcript, not from a summary", self.record["context"])

    def test_the_two_additions_to_answer_a_are_visible_and_say_what_the_code_does(self):
        additions = self.record["scope"]["nbix"]["assistant_additions_for_the_owner_to_veto"]
        self.assertEqual(len(additions), 2)
        self.assertIn("The sealed view gains a date_field entry on an action only when its date is not an ex_date", additions[0])
        self.assertIn("so this is a small addition to it, made visible here.", additions[0])
        self.assertIn("never falls through to the next field", additions[1])
        self.assertIn("It changes nothing for an input that worked before, because such an input has a valid ex_date, which still decides.", additions[1])
        listed = re.search(r"the first of (.*?) that is present", additions[1]).group(1)
        self.assertEqual(re.split(r", | and ", listed), list(ea.ACTION_DATE_FIELDS))                      # the record names the fields in the order the code tries them

    def test_the_code_is_the_change_answer_a_describes(self):
        self.assertEqual(ea.ACTION_DATE_FIELDS, ("ex_date", "effective_date", "payable_date", "process_date"))
        fetch = lambda items: ea.fetch_actions(lambda p: json.dumps({"corporate_actions": {"cash_mergers": items}, "next_page_token": None}).encode(), {})[0]
        self.assertEqual(fetch([{"effective_date": "2026-05-18", "id": "m"}]), [{"type": "cash_mergers", "ex_date": "2026-05-18", "id": "m", "date_field": "effective_date"}])
        with self.assertRaises(ea.DataError):
            fetch([{"id": "m"}])


class EventsFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load("config/m5-phase1b-events.json")
        cls.events = {e["event_id"]: e for e in cls.spec["events"]}
        cls.record = load(RECORD_PATH)

    def test_exactly_the_eight_events_the_owner_signed_off_carry_the_three_attestations(self):
        self.assertEqual([e for e, event in self.events.items() if "attestations" in event], ATTESTED)
        self.assertEqual(self.record["scope"]["attested"]["events"], ATTESTED)
        self.assertTrue((ROOT / RECORD_PATH).is_file())
        for event_id in ATTESTED:
            with self.subTest(event=event_id):
                attestations = self.events[event_id]["attestations"]
                self.assertEqual(sorted(attestations), sorted(ea.ATTESTATIONS))
                for name, attestation in attestations.items():
                    self.assertEqual(attestation, {"reviewer": "Fahad9101", "date": "2026-10-09", "record": RECORD_PATH, "basis": BASIS[name]})

    def test_nbix_is_not_attested_and_asmb_is_not_an_event(self):
        self.assertNotIn("attestations", self.events[NBIX])
        self.assertEqual(len(self.events), 9)
        self.assertNotIn("ASMB", {e["security"]["ticker"] for e in self.events.values()})
        self.assertEqual(sorted(set(self.events) - set(ATTESTED)), [NBIX])

    def test_the_eight_specs_carry_the_packets_caveats_and_nothing_else_changed_in_them(self):
        packet = {e["event_id"]: e for e in load(PACKET_PATH)["events"]}
        for event_id in ATTESTED:
            with self.subTest(event=event_id):
                self.assertEqual(self.events[event_id].get("caveats"), packet[event_id]["proposed_label_caveats"])
        self.assertEqual([e for e in ATTESTED if "caveats" in self.events[e]], ["alkt-m5b-2026-04-29", "hurn-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"])
        for event_id in ATTESTED:
            for caveat in self.events[event_id].get("caveats", []):
                self.assertTrue(caveat["labels"] == ["all"] or "content not opened" in caveat["note"])


if __name__ == "__main__":
    unittest.main()
