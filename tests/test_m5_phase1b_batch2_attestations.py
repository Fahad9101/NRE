"""The owner's signoff of Milestone 5 Phase 1b batch 2 (reports/m5-phase1b-batch2-signoff-2026-10-10.json): the three answers as given, what each decides, and the events file that carries them out -- all ten events attested on the record, REKR with the caveat
for its Item 3.01 filing and ACHV with the caveat for its separate release, as the packet proposed; nothing pinned yet."""
import json
import unittest
from pathlib import Path

from nre import event_acquire as ea

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch2-signoff-2026-10-10.json"
PACKET_PATH = "reports/m5-phase1b-batch2-signoff-packet-2026-10-10.json"
IDS = ["payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
REKR, ACHV = "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12"
ANSWER = 'Owner sign-off ("Yes, attest them (Recommended)", 2026-10-10) on '
BASIS = {
    "first_public_time": ANSWER + "the release-time evidence in " + PACKET_PATH + " (the wire page's minute and its machine-readable time, the same-day release check), accepting the residual gap the packet states.",
    "historical_identity": ANSWER + "the identity evidence in " + PACKET_PATH + " (the exchange the S2 review recorded from the event filing's cover or the release, the previous Milestone 1 event, the archived 8-K history checked for Items 1.03, 3.01, 3.03, 4.01 and 5.03; "
                           "the one Item 3.01 filing found, REKR's, is carried as a caveat).",
    "corporate_actions": ANSWER + "the two signals in " + PACKET_PATH + " (no Item 3.03 or 5.03 8-K in the archived history up to the window end, and Alpaca's real answer as the sealed dry run reported it: no corporate action for any of the ten).",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class SignoffRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RECORD_PATH)

    def test_the_three_answers_are_quoted_as_given(self):
        record = self.record
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-10T11:53:13.211Z", "session transcript, line 43451 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-10T11:55:42.964Z", "session transcript, line 43452 (the tool result of the questions)"))
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        qa = record["questions_and_answers"]
        self.assertEqual([(q["header"], q["owner_selected"]) for q in qa],
                         [("REKR 05-11", "Attest with the caveat (Recommended)"), ("ACHV 05-12", "Keep it, with the caveat (Recommended)"), ("Attest 10", "Yes, attest them (Recommended)")])
        self.assertEqual(qa[0]["question"], "REKR 2026-05-11: its archived 8-K history has a filing with Item 3.01 (the item for a notice about a continued-listing rule or a transfer of listing), 0001437749-26-014478, filed 2026-05-01 20:30 ET, "
                                            "ten days before the release. I did not open it. How should REKR be handled?")
        self.assertEqual(qa[1]["question"], "ACHV 2026-05-12: a separate release at 07:05 ET, five minutes after the results release, announced three senior leadership appointments (a Board member, a Senior Vice President of Commercial and a Vice President of Sales). "
                                            "On my reading of the policy's third condition it is not independently material. Keep ACHV with a caveat, or exclude it?")
        self.assertEqual(qa[2]["question"], "Attest first-public time, historical identity and corporate actions for the batch 2 events that your two answers leave in (up to ten: PAYO, PDFS, REAL, TECX, LNSR, REKR, ACHV, SLSN, KLC, TTWO), on the evidence in " + PACKET_PATH + "?")
        self.assertEqual([[o["label"] for o in q["options_offered"]] for q in qa],
                         [["Attest with the caveat (Recommended)", "Hold until the 8-K is read", "Exclude it"], ["Keep it, with the caveat (Recommended)", "Exclude it"], ["Yes, attest them (Recommended)", "Not yet"]])
        self.assertIn("The cover of REKR's own 8-K still lists the stock on the Nasdaq Stock Market at the release", qa[0]["options_offered"][0]["description"])
        self.assertIn("they are neither a divestiture, a clinical readout nor an unplanned departure", qa[1]["options_offered"][0]["description"])
        self.assertIn("You accept the residual gap that open-web research cannot close: an earlier public disclosure with no discoverable trace.", qa[2]["options_offered"][0]["description"])
        self.assertIn("quoted from the session transcript, not from a summary", record["context"])
        self.assertIn("ten events quarantined as a dry run should, and two calls for the owner, REKR's Item 3.01 filing of 2026-05-01 (not opened) and ACHV's separate same-day release", record["context"])
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch2_signoff", "2026-10-10"))

    def test_it_says_what_each_answer_decides(self):
        scope = self.record["scope"]
        self.assertEqual(scope["attested"]["events"], IDS)
        self.assertEqual(scope["attested"]["attestations"], ["first_public_time", "historical_identity", "corporate_actions"])
        for phrase in ("accepting the residual gap that open-web research cannot close", "as caveats, not exclusions", "REKR's Item 3.01 filing, ACHV's separate same-day release, and the in-window 8-Ks listed for PDFS, LNSR, REKR, ACHV and KLC, whose content was not opened"):
            self.assertIn(phrase, scope["attested"]["read_as"])
        self.assertEqual((scope["rekr"]["event"], scope["rekr"]["decision"]), (REKR, "attest with the caveat"))
        self.assertIn("naming the 8-K 0001437749-26-014478 filed 2026-05-01 with Item 3.01 (content not opened)", scope["rekr"]["read_as"])
        self.assertIn("it is not held for the filing to be read and not excluded", scope["rekr"]["read_as"])
        self.assertEqual((scope["achv"]["event"], scope["achv"]["decision"]), (ACHV, "keep with the caveat"))
        self.assertIn("it is not excluded", scope["achv"]["read_as"])
        self.assertEqual(scope["additions_to_the_owners_words"], "None: the attestations and caveats are exactly the packet's proposals.")
        text = " ".join(self.record["not_a_claim"])
        for phrase in ("no label, price or return has been computed or viewed", "Not a clearance of the in-window 8-Ks or of REKR's Item 3.01 filing, whose content was not opened", "Not a reading of the Item 3.01 filing: the owner chose to attest without it."):
            self.assertIn(phrase, text)


class EventsFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load("config/m5-phase1b-events.json")
        cls.events = {e["event_id"]: e for e in cls.spec["events"]}
        cls.packet = load(PACKET_PATH)

    def test_the_ten_events_carry_the_three_attestations_on_that_record(self):
        self.assertTrue((ROOT / RECORD_PATH).is_file())
        self.assertEqual(list(self.events)[9:], IDS)
        for event_id in IDS:
            with self.subTest(event=event_id):
                attestations = self.events[event_id]["attestations"]
                self.assertEqual(sorted(attestations), sorted(ea.ATTESTATIONS))
                for name, attestation in attestations.items():
                    self.assertEqual(attestation, {"reviewer": "Fahad9101", "date": "2026-10-10", "record": RECORD_PATH, "basis": BASIS[name]})
        for event_id in list(self.events)[:9]:
            for attestation in self.events[event_id]["attestations"].values():
                self.assertNotEqual(attestation["record"], RECORD_PATH)                  # batch 1's attestations are on its own records

    def test_the_ten_specs_carry_the_packets_caveats_and_nothing_is_pinned_yet(self):
        proposed = {e["event_id"]: e["proposed_label_caveats"] for e in self.packet["events"]}
        for event_id in IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.events[event_id].get("caveats"), proposed[event_id])
                self.assertNotIn("recorded_result", self.events[event_id])
        self.assertEqual({e: len(self.events[e].get("caveats", [])) for e in IDS if "caveats" in self.events[e]},
                         {"pdfs-m5b-2026-05-07": 1, "lnsr-m5b-2026-05-08": 1, REKR: 2, ACHV: 2, "klc-m5b-2026-05-14": 1})
        rekr = self.events[REKR]["caveats"]
        self.assertEqual(rekr[0]["labels"], ["all"])
        self.assertIn("8-K 0001437749-26-014478 filed 2026-05-01 20:30 ET with Item 3.01", rekr[0]["note"])
        self.assertIn("A caveat, not an exclusion.", rekr[0]["note"])
        self.assertEqual(rekr[1]["labels"], ["session_10_close_return", "session_20_close_return", "session_5_close_return"])
        achv = self.events[ACHV]["caveats"]
        self.assertEqual([c["labels"] for c in achv], [["all"], ["session_20_close_return"]])
        self.assertIn("A separate GlobeNewswire release five minutes later (07:05 ET) announced three senior leadership appointments", achv[0]["note"])
        for event_id in IDS:
            for caveat in self.events[event_id].get("caveats", []):
                self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES | {"all"})
            names_a_filing = [c["note"].startswith("8-K ") for c in self.events[event_id].get("caveats", [])]
            self.assertEqual(names_a_filing, [False, True] if event_id == ACHV else [True] * len(names_a_filing))     # ACHV's first caveat is the one it carried at the dry run; every other caveat names a filing


if __name__ == "__main__":
    unittest.main()
