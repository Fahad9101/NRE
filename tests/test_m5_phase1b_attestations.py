"""The owner's signoff of Milestone 5 Phase 1b batch 1 (reports/m5-phase1b-batch1-signoff-2026-10-09.json): the three answers as given, what each decides, and the events file that carries them out -- eight events attested on that record, ASMB not an event --
with the pipeline change that answer (A) authorizes; and the owner's later answer on NBIX (reports/m5-phase1b-nbix-signoff-2026-10-10.json), given after the attested sealed run listed the action NBIX had been blocked on."""
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
NBIX_RECORD_PATH = "reports/m5-phase1b-nbix-signoff-2026-10-10.json"
SEALED_PATH = "reports/m5-phase1b-batch1-sealed-run-2026-10-10.json"
NBIX_ANSWER = 'Owner sign-off ("Yes, attest NBIX (Recommended)", 2026-10-10) on '
NBIX_BASIS = {
    "first_public_time": NBIX_ANSWER + "the release-time evidence in " + PACKET_PATH + " (the wire page's minute and its machine-readable time, the same-day release check), accepting the residual gap the packet states.",
    "historical_identity": NBIX_ANSWER + "the identity evidence in " + PACKET_PATH + " (the event filing's cover row, the previous Milestone 1 event, no Item 1.03, 3.01, 3.03, 4.01 or 5.03 8-K in the archived history).",
    "corporate_actions": NBIX_ANSWER + "the signal in " + PACKET_PATH + " (no Item 3.03 or 5.03 8-K in the archived history up to the window end) and the action its second dry run listed in " + SEALED_PATH
                         + " (one cash_mergers item dated 2026-05-18 by its effective date).",
}
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

    def test_the_eight_events_the_owner_signed_off_on_2026_10_09_carry_the_three_attestations_on_that_record(self):
        self.assertEqual([e for e, event in self.events.items() if "attestations" in event and event["attestations"]["first_public_time"]["record"] == RECORD_PATH], ATTESTED)
        self.assertEqual(self.record["scope"]["attested"]["events"], ATTESTED)
        self.assertTrue((ROOT / RECORD_PATH).is_file())
        for event_id in ATTESTED:
            with self.subTest(event=event_id):
                attestations = self.events[event_id]["attestations"]
                self.assertEqual(sorted(attestations), sorted(ea.ATTESTATIONS))
                for name, attestation in attestations.items():
                    self.assertEqual(attestation, {"reviewer": "Fahad9101", "date": "2026-10-09", "record": RECORD_PATH, "basis": BASIS[name]})

    def test_nbix_is_attested_on_its_own_later_record_and_asmb_is_not_an_event(self):
        self.assertEqual(sorted(e for e in list(self.events)[:9] if "attestations" in self.events[e]), sorted(ATTESTED + [NBIX]))          # batch 2's ten events follow these nine in the file, on their own record (tests/test_m5_phase1b_batch2_attestations.py)
        self.assertEqual([e for e in self.events][:9], ATTESTED[:4] + [NBIX] + ATTESTED[4:])                                              # batch 1 keeps its nine places at the head of the file
        self.assertNotIn("ASMB", {e["security"]["ticker"] for e in self.events.values()})
        self.assertEqual(sorted(set(list(self.events)[:9]) - set(ATTESTED)), [NBIX])
        attestations = self.events[NBIX]["attestations"]
        self.assertEqual(sorted(attestations), sorted(ea.ATTESTATIONS))
        for name, attestation in attestations.items():
            self.assertEqual(attestation, {"reviewer": "Fahad9101", "date": "2026-10-10", "record": NBIX_RECORD_PATH, "basis": NBIX_BASIS[name]})

    def test_the_eight_specs_carry_the_packets_caveats_and_nothing_else_changed_in_them(self):
        packet = {e["event_id"]: e for e in load(PACKET_PATH)["events"]}
        for event_id in ATTESTED + [NBIX]:
            with self.subTest(event=event_id):
                self.assertEqual(self.events[event_id].get("caveats"), packet[event_id]["proposed_label_caveats"])
        self.assertEqual([e for e in ATTESTED + [NBIX] if "caveats" in self.events[e]], ["alkt-m5b-2026-04-29", "hurn-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07", NBIX])
        for event_id in ATTESTED + [NBIX]:
            for caveat in self.events[event_id].get("caveats", []):
                self.assertTrue(caveat["labels"] == ["all"] or "content not opened" in caveat["note"])


class NbixSignoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(NBIX_RECORD_PATH)
        cls.sealed = load("reports/m5-phase1b-batch1-sealed-run-2026-10-10.json")

    def test_the_answer_is_quoted_as_given(self):
        record = self.record
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-10T06:28:55.451Z", "session transcript, line 42108 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-10T08:29:12.870Z", "session transcript, line 42114 (the tool result of the question)"))
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        self.assertEqual(len(record["questions_and_answers"]), 1)
        qa = record["questions_and_answers"][0]
        self.assertEqual((qa["header"], qa["owner_selected"]), ("NBIX 05-05", "Yes, attest NBIX (Recommended)"))
        self.assertEqual(qa["question"], "Attest first-public time, historical identity and corporate actions for NBIX 2026-05-05, on the evidence in " + PACKET_PATH
                         + " and the action its second dry run listed (reports/m5-phase1b-batch1-sealed-run-2026-10-10.json)?")
        self.assertEqual([o["label"] for o in qa["options_offered"]], ["Yes, attest NBIX (Recommended)", "Not yet", "Exclude it"])
        yes = qa["options_offered"][0]["description"]
        for phrase in ("(id b8d80b2b-b0e2-4be3-b612-9325d12d1646) dated 2026-05-18 by its effective date, the day of NBIX's 8-K with Item 2.01", "It falls inside the session_10 and session_20 windows only, so the engine suppresses those two labels.",
                       "The sealed view cannot show whether the item lists NBIX as acquirer or acquiree; the suppression applies either way.", "You accept the same residual gap as for the eight."):
            self.assertIn(phrase, yes)
        self.assertIn("this would be a new reading", qa["options_offered"][2]["description"])
        self.assertIn("quoted from the session transcript, not from a summary", record["context"])
        self.assertIn("which left NBIX unattested until the owner had seen the listed action", record["context"])
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_nbix_signoff", "2026-10-10"))

    def test_the_action_the_owner_saw_is_the_one_the_sealed_run_listed(self):
        seen = self.record["scope"]["listed_action_seen_by_the_owner"]
        listed = self.sealed["corporate_actions_found"][NBIX]
        self.assertEqual(listed, [{"type": seen["type"], "ex_date": seen["ex_date"], "date_field": seen["date_field"], "id": seen["id"], "windows_it_falls_inside": seen["windows_it_falls_inside"]}])
        self.assertEqual((seen["type"], seen["ex_date"], seen["date_field"], seen["windows_it_falls_inside"]), ("cash_mergers", "2026-05-18", "effective_date", ["session_10_close_return", "session_20_close_return"]))
        self.assertIn("The engine suppresses the labels whose windows the date falls inside (CORPORATE_ACTION_IN_WINDOW) and computes the others.", seen["what_it_means"])
        self.assertIn("The sealed view does not show whether the item lists NBIX as acquirer or acquiree; the suppression applies either way.", seen["what_it_means"])
        attested = self.record["scope"]["attested"]
        self.assertEqual((attested["event"], attested["attestations"]), (NBIX, ["first_public_time", "historical_identity", "corporate_actions"]))
        self.assertEqual(attested["evidence"], PACKET_PATH + " (the NBIX entry) and the action its second dry run listed, as recorded in " + SEALED_PATH)
        self.assertIn("accepting the residual gap that open-web research cannot close", attested["read_as"])
        self.assertIn("whose content was not opened", attested["read_as"])
        text = " ".join(self.record["not_a_claim"])
        for phrase in ("Not Phase 1b acceptance and not a claim about any label", "Not a clearance of the in-window 8-Ks whose content was not opened", "Not a finding about the Soleno acquisition, nor that the listed item is that acquisition."):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
