"""The owner's signoff of Milestone 5 Phase 1b batch 3 (reports/m5-phase1b-batch3-signoff-2026-10-14.json): his words as given (the pop-up question he cancelled, "what next", the request in my report, and "attest the ten"), what the answer decides, and the events file that
carries it out -- all ten events attested on the record, with the five label caveats the packet proposed. (Their commitments are pinned from the attested sealed run: tests/test_m5_phase1b_batch3_sealed_run.py.)"""
import json
import unittest
from pathlib import Path

from nre import event_acquire as ea

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch3-signoff-2026-10-14.json"
PACKET_PATH = "reports/m5-phase1b-batch3-signoff-packet-2026-10-13.json"
IDS = ["okta-m5b-2026-05-28", "vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "hurn-m5b-2026-07-28", "alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "caci-m5b-2026-08-05", "cxt-m5b-2026-08-05"]
OKTA, LOVE, NBIX, PARR, CXT = IDS[0], IDS[2], IDS[5], IDS[6], IDS[9]
ANSWER = 'Owner sign-off ("attest the ten", 2026-10-14) on '
BASIS = {
    "first_public_time": ANSWER + "the release-time evidence in " + PACKET_PATH + " (the wire page's minute and its machine-readable time, the same-day release check), accepting the residual gap the packet states.",
    "historical_identity": ANSWER + "the identity evidence in " + PACKET_PATH + " (the exchange the S2 review recorded from the event filing's cover or the release, the previous Milestone 1 event, the archived 8-K history checked for Items 1.03, 3.01, 3.03, 4.01 and 5.03; "
                           "none was found in any of the ten).",
    "corporate_actions": ANSWER + "the two signals in " + PACKET_PATH + " (no Item 3.03 or 5.03 8-K in the archived history up to the window end, and Alpaca's real answer as the sealed dry run reported it: CXT one cash dividend, the other nine none).",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class SignoffRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RECORD_PATH)

    def test_the_cancelled_popup_the_request_and_the_owners_words_are_quoted_as_given(self):
        record = self.record
        popup = record["cancelled_popup_question"]
        self.assertEqual((popup["asked"]["at"], popup["asked"]["source"]), ("2026-10-13T15:20:20.424Z", "session transcript, line 45782 (AskUserQuestion)"))
        self.assertEqual((popup["rejected"]["at"], popup["rejected"]["source"]), ("2026-10-13T21:35:39.887Z", "session transcript, line 45783 (the tool result: the owner did not want to proceed with that tool use)"))
        self.assertTrue(popup["rejected"]["text"].startswith("The user doesn't want to proceed with this tool use. The tool use was rejected"))
        self.assertEqual(popup["header"], "Attest 10")
        self.assertEqual(popup["question"], "Do you attest the first-public time, historical identity and corporate actions of the ten batch 3 events (OKTA 05-28, VSAT 05-28, LOVE 06-11, HURN 07-28, ALKT 07-29, NBIX 07-30, PARR 08-04, VSAT 08-04, CACI 08-05, CXT 08-05), "
                                         "with the label caveats the packet proposes?")
        self.assertEqual([o["label"] for o in popup["options_offered"]], ["Yes, attest all ten (Recommended)", "Attest some, hold the rest", "Not yet"])
        self.assertIn("You also accept the residual gap that open-web research cannot close (an earlier disclosure with no public trace).", popup["options_offered"][0]["description"])
        self.assertEqual(popup["read_as"], "Not an answer: the owner cancelled the pop-up, so none of its options was selected.")
        self.assertEqual(record["owner_message_before_the_report"], {"text": "what next", "at": "2026-10-14T03:56:17.779Z", "source": "session transcript, line 45788"})
        request = record["request_in_text"]
        self.assertEqual((request["at"], request["source"], request["recommended_reply"]), ("2026-10-14T03:56:53.982Z", "session transcript, line 45812 (my report)", "attest the ten"))
        for phrase in ("The pop-up question you cancelled was that signoff", "**Recommended next step:** reply \"attest the ten\".", "Name any event you'd rather hold, for example \"attest the nine and hold CXT\". Recommending isn't authorizing.",
                       "- **Calls for you:** none this time.", "CXT has one cash dividend, ex-date 2026-08-31, which falls inside its session_20 window only. That one label will not exist.",
                       "Attesting also accepts the residual gap open-web research can't close (an earlier disclosure with no public trace)."):
            self.assertIn(phrase, request["text"])
        answered = record["answered"]
        self.assertEqual((answered["text"], answered["at"], answered["source"]), ("attest the ten", "2026-10-14T03:57:03.540Z", "session transcript, line 45816"))
        self.assertLess(popup["rejected"]["at"], record["owner_message_before_the_report"]["at"])
        self.assertLess(record["owner_message_before_the_report"]["at"], request["at"])
        self.assertLess(request["at"], answered["at"])
        self.assertIn("Reply to the batch 3 signoff request built from " + PACKET_PATH + " after the sealed dry run (reports/m5-phase1b-batch3-dry-run-2026-10-13.json)", record["context"])
        self.assertIn("The request went out twice: first as a pop-up question that the owner cancelled", record["context"])
        self.assertIn("quoted from the session transcript, not from a summary", record["context"])
        self.assertIn("ten events quarantined as a dry run should, no call for the owner, one corporate action (CXT's cash dividend, ex-date 2026-08-31, inside its session_20 window only) and five proposed label caveats", record["context"])
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch3_signoff", "2026-10-14"))

    def test_it_says_what_the_answer_decides(self):
        scope = self.record["scope"]
        self.assertEqual(scope["attested"]["events"], IDS)
        self.assertEqual(scope["attested"]["attestations"], ["first_public_time", "historical_identity", "corporate_actions"])
        for phrase in ("accepting the residual gap that open-web research cannot close", "as caveats, not exclusions", "the in-window 8-Ks listed for OKTA, LOVE, NBIX, PARR and CXT, whose content was not opened"):
            self.assertIn(phrase, scope["attested"]["read_as"])
        self.assertEqual((scope["cxt"]["event"], scope["cxt"]["decision"]), (CXT, "attest"))
        self.assertIn("its one cash dividend (ex-date 2026-08-31) is a corporate action the sealed engine reports, and it suppresses CXT's session_20 label only; CXT is not held and not excluded", scope["cxt"]["read_as"])
        self.assertEqual(scope["additions_to_the_owners_words"], "None: the attestations and caveats are exactly the packet's proposals.")
        self.assertEqual(self.record["answered"]["read_as"], "The reply the report asked for: the three attestations for all ten events, on the evidence in the packet, with the packet's five label caveats and the residual gap accepted; no event is held.")
        text = " ".join(self.record["not_a_claim"])
        for phrase in ("no label, price or return has been computed or viewed", "Not a clearance of the in-window 8-Ks, whose content was not opened", "Not an answer to the cancelled pop-up question: the owner's answer is the plain-text reply on line 45816."):
            self.assertIn(phrase, text)


class EventsFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load("config/m5-phase1b-events.json")
        cls.events = {e["event_id"]: e for e in cls.spec["events"]}
        cls.packet = load(PACKET_PATH)

    def test_the_ten_events_carry_the_three_attestations_on_that_record(self):
        self.assertTrue((ROOT / RECORD_PATH).is_file())
        self.assertEqual(list(self.events)[19:], IDS)
        for event_id in IDS:
            with self.subTest(event=event_id):
                attestations = self.events[event_id]["attestations"]
                self.assertEqual(sorted(attestations), sorted(ea.ATTESTATIONS))
                for name, attestation in attestations.items():
                    self.assertEqual(attestation, {"reviewer": "Fahad9101", "date": "2026-10-14", "record": RECORD_PATH, "basis": BASIS[name]})
        for event_id in list(self.events)[:19]:
            for attestation in self.events[event_id]["attestations"].values():
                self.assertNotEqual(attestation["record"], RECORD_PATH)                  # the earlier batches' attestations are on their own records

    def test_the_ten_specs_carry_the_packets_caveats(self):
        proposed = {e["event_id"]: e["proposed_label_caveats"] for e in self.packet["events"]}
        for event_id in IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.events[event_id].get("caveats"), proposed[event_id])
        self.assertEqual({e: len(self.events[e]["caveats"]) for e in IDS if "caveats" in self.events[e]}, {OKTA: 1, LOVE: 1, NBIX: 1, PARR: 1, CXT: 1})
        self.assertEqual({e: self.events[e]["caveats"][0]["labels"] for e in IDS if "caveats" in self.events[e]},
                         {OKTA: ["session_20_close_return"], LOVE: ["session_10_close_return", "session_20_close_return", "session_5_close_return"],
                          NBIX: ["session_10_close_return", "session_20_close_return", "session_2_close_return", "session_5_close_return"], PARR: ["session_20_close_return"],
                          CXT: ["session_10_close_return", "session_20_close_return", "session_5_close_return"]})
        notes = {e: self.events[e]["caveats"][0]["note"] for e in IDS if "caveats" in self.events[e]}
        self.assertEqual(sorted(notes), sorted([OKTA, LOVE, NBIX, PARR, CXT]))
        for event_id, note in notes.items():
            self.assertTrue(note.startswith("8-K "), event_id)
            self.assertIn("inside the window; content not opened. Policy: a caveat, not an exclusion (docs/SAME-DAY-COMPETING-CATALYST-POLICY.md; the Milestone 1 OKTA precedent).", note)
        self.assertIn("filed 2026-06-23 21:05 ET (Items 5.02, 5.07, 9.01)", notes[OKTA])
        self.assertIn("filed 2026-06-15 17:00 ET (Items 5.02, 9.01)", notes[LOVE])
        self.assertIn("filed 2026-07-31 20:05 ET (Items 9.01)", notes[NBIX])
        self.assertIn("filed 2026-08-25 21:26 ET (Items 7.01, 8.01, 9.01)", notes[PARR])
        self.assertIn("filed 2026-08-11 10:00 ET (Items 7.01)", notes[CXT])
        for event_id in IDS:
            for caveat in self.events[event_id].get("caveats", []):
                self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES | {"all"})

if __name__ == "__main__":
    unittest.main()
