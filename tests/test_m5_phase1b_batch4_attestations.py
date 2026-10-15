"""The owner's signoff of Milestone 5 Phase 1b batch 4 (reports/m5-phase1b-batch4-signoff-2026-10-14.json): his words as given (the request in my report and "attest the nine"), what the answer decides (all nine events attested, ACHV with its caveat on all labels,
ASMB's release at the bell left quarantined), and the events file that carries it out -- the nine events attested on the record, with the four label caveats the packet proposed and ACHV's Item 5.03 filing. (Their commitments are pinned from the attested sealed run:
tests/test_m5_phase1b_batch4_sealed_run.py.)"""
import json
import unittest
from pathlib import Path

from nre import event_acquire as ea

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch4-signoff-2026-10-14.json"
PACKET_PATH = "reports/m5-phase1b-batch4-signoff-packet-2026-10-14.json"
IDS = ["aspn-m5b-2026-08-06", "coll-m5b-2026-08-06", "pdfs-m5b-2026-08-06", "real-m5b-2026-08-06", "tecx-m5b-2026-08-06", "ttwo-m5b-2026-08-07", "achv-m5b-2026-08-11", "klc-m5b-2026-08-13", "lnsr-m5b-2026-08-13"]
COLL, ACHV, KLC = IDS[1], IDS[6], IDS[7]
ANSWER = 'Owner sign-off ("attest the nine", 2026-10-14) on '
BASIS = {
    "first_public_time": ANSWER + "the release-time evidence in " + PACKET_PATH + " (the wire page's minute and its machine-readable time, the same-day release check), accepting the residual gap the packet states.",
    "historical_identity": ANSWER + "the identity evidence in " + PACKET_PATH + " (the exchange the S2 review recorded from the event filing's cover or the release, the previous Milestone 1 event, the archived 8-K history checked for Items 1.03, 3.01, 3.03, 4.01 and 5.03; "
                           "the one Item 5.03 filing found, ACHV's, is carried as a caveat).",
    "corporate_actions": ANSWER + "the two signals in " + PACKET_PATH + " (no Item 3.03 or 5.03 8-K in the archived history up to the window end, except ACHV's Item 5.03 filing, which is carried as a caveat, and Alpaca's real answer as the sealed dry run reported it: "
                         "no corporate action for any of the nine).",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class SignoffRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RECORD_PATH)

    def test_the_request_and_the_owners_words_are_quoted_as_given(self):
        record = self.record
        request = record["request_in_text"]
        self.assertEqual((request["at"], request["source"], request["recommended_reply"]), ("2026-10-14T15:14:05.196Z", "session transcript, line 47893 (my report)", "attest the nine"))
        for phrase in ("Batch 4's signoff packet is pushed and CI is green. I need your signoff on the nine events and two calls.", "**Two calls for you**",
                       "1. **ACHV (08-11):** its 8-K history has a filing with Items 5.03, 5.07 and 9.01 (accession 0001193125-26-296174, filed 2026-07-06 20:06 ET).",
                       "Options: attest ACHV with a caveat on all labels (my recommendation, as with REKR's Item 3.01 filing in batch 2), hold it until I read the filing (which needs your permission to read one SEC filing), or leave it quarantined or exclude it.",
                       "2. **ASMB (08-13):** its release was at exactly 16:00 ET, which the calendar can't classify, so there is no spec. Options: leave it quarantined (my recommendation, as with ASMB 05-07) or exclude it.",
                       "**Recommended reply:** `attest the nine`. That attests first-public time, historical identity and corporate actions for all nine events. It attaches ACHV's all-label caveat plus the three in-window caveats, and leaves ASMB's release quarantined. "
                       "Reply with different wording if you want a different call on ACHV or ASMB.",
                       "COLL: 8-K of 08-13, Item 8.01.", "ACHV: 8-K of 08-14, Items 8.01 and 9.01.", "KLC: 8-K of 08-14, Items 1.01 and 9.01."):
            self.assertIn(phrase, request["text"])
        answered = record["answered"]
        self.assertEqual((answered["text"], answered["at"], answered["source"]), ("attest the nine", "2026-10-14T15:15:43.454Z", "session transcript, line 47897 (queued at line 47895)"))
        self.assertLess(request["at"], answered["at"])
        self.assertIn("Reply to the batch 4 signoff request built from " + PACKET_PATH + " after the sealed dry run (reports/m5-phase1b-batch4-dry-run-2026-10-14.json)", record["context"])
        self.assertIn("nine events quarantined as a dry run should, no corporate action, two calls for the owner (ACHV's Item 5.03 filing of 2026-07-06 and ASMB's release at the bell) and proposed label caveats for four filings", record["context"])
        self.assertIn("The request went out as plain text in my report (no pop-up this time).", record["context"])
        self.assertIn("quoted from the session transcript, not from a summary", record["context"])
        self.assertEqual((record["schema_version"], record["kind"], record["recorded_on"]), (1, "m5_phase1b_batch4_signoff", "2026-10-14"))
        self.assertEqual(sorted(record),["answered", "context", "kind", "not_a_claim", "recorded_on", "request_in_text", "schema_version", "scope"])

    def test_it_says_what_the_answer_decides(self):
        scope = self.record["scope"]
        self.assertEqual(scope["attested"]["events"], IDS)
        self.assertEqual(scope["attested"]["attestations"], ["first_public_time", "historical_identity", "corporate_actions"])
        for phrase in ("accepting the residual gap that open-web research cannot close", "as caveats, not exclusions",
                       "ACHV's Item 5.03 filing of 2026-07-06 on all of its labels, and the in-window 8-Ks listed for COLL, ACHV and KLC, whose content was not opened"):
            self.assertIn(phrase, scope["attested"]["read_as"])
        self.assertEqual((scope["achv"]["event"], scope["achv"]["decision"]), (ACHV, "attest with the caveat"))
        for phrase in ("carries a caveat on all labels naming the 8-K 0001193125-26-296174 filed 2026-07-06 20:06 ET with Items 5.03, 5.07 and 9.01 (content not opened)", "it is not held for the filing to be read, not left quarantined and not excluded",
                       "No permission to read that filing was asked for or given."):
            self.assertIn(phrase, scope["achv"]["read_as"])
        self.assertEqual((scope["asmb"]["candidate"], scope["asmb"]["release"], scope["asmb"]["decision"]), ("0001193125-26-352193", "asmb-2026-08-13", "leave it quarantined, not excluded"))
        for phrase in ("(2026-08-13, exactly 16:00 ET, which the calendar classes as bell_ambiguous) stays quarantined, not excluded: no event spec is built, nothing is attested for it and nothing is computed for it.",
                       "It is the disposition the owner gave ASMB 2026-05-07 (reports/m5-phase1b-batch1-signoff-2026-10-09.json), as Milestone 1's GALT and step 2's PDFS 2025-08-07 were left."):
            self.assertIn(phrase, scope["asmb"]["read_as"])
        self.assertEqual(scope["additions_to_the_owners_words"], "None: the attestations, caveats and the two dispositions are exactly the packet's recommendations and proposals.")
        self.assertEqual(self.record["answered"]["read_as"], "The reply the report asked for: the three attestations for all nine events, on the evidence in the packet, with ACHV's caveat on all labels and the packet's three in-window caveats and the residual gap accepted; "
                                                              "no event is held, and ASMB's release stays quarantined.")
        text = " ".join(self.record["not_a_claim"])
        for phrase in ("no label, price or return has been computed or viewed", "Not a clearance of the filings that travel as caveats (ACHV's Item 5.03 filing and the in-window 8-Ks of COLL, ACHV and KLC): their content was not opened.",
                       "Not an attestation of ASMB's release, which has no spec and stays quarantined.", "Not a permission to read any filing or any other page: later batches ask again."):
            self.assertIn(phrase, text)
        packet = load(PACKET_PATH)
        self.assertEqual(sorted(packet["decisions_needed"]), [ACHV, "asmb-2026-08-13"])                 # the two calls the answer settles
        self.assertEqual(scope["asmb"]["candidate"], load("reports/m5-phase1b-batch4-sources-2026-10-14.json")["quarantined_before_the_spec"]["candidate_id"])
        self.assertEqual(load("reports/m5-phase1b-batch1-signoff-2026-10-09.json")["questions_and_answers"][2]["owner_selected"], "Leave it quarantined (Recommended)")


class EventsFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load("config/m5-phase1b-events.json")
        cls.events = {e["event_id"]: e for e in cls.spec["events"]}
        cls.packet = load(PACKET_PATH)

    def test_the_nine_events_carry_the_three_attestations_on_that_record(self):
        self.assertTrue((ROOT / RECORD_PATH).is_file())
        self.assertEqual(list(self.events)[29:38], IDS)
        for event_id in IDS:
            with self.subTest(event=event_id):
                attestations = self.events[event_id]["attestations"]
                self.assertEqual(sorted(attestations), sorted(ea.ATTESTATIONS))
                for name, attestation in attestations.items():
                    self.assertEqual(attestation, {"reviewer": "Fahad9101", "date": "2026-10-14", "record": RECORD_PATH, "basis": BASIS[name]})
        for event_id in list(self.events)[:29]:
            for attestation in self.events[event_id]["attestations"].values():
                self.assertNotEqual(attestation["record"], RECORD_PATH)                  # the earlier batches' attestations are on their own records

    def test_the_nine_specs_carry_the_packets_caveats(self):
        proposed = {e["event_id"]: e["proposed_label_caveats"] for e in self.packet["events"]}
        for event_id in IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.events[event_id].get("caveats"), proposed[event_id])
        self.assertEqual({e: len(self.events[e]["caveats"]) for e in IDS if "caveats" in self.events[e]}, {COLL: 1, ACHV: 2, KLC: 1})
        self.assertEqual({e: [c["labels"] for c in self.events[e]["caveats"]] for e in IDS if "caveats" in self.events[e]},
                         {COLL: [["session_10_close_return", "session_20_close_return"]],
                          ACHV: [["all"], ["session_10_close_return", "session_20_close_return", "session_5_close_return"]],
                          KLC: [["session_10_close_return", "session_20_close_return", "session_2_close_return", "session_5_close_return"]]})
        notes = {e: [c["note"] for c in self.events[e]["caveats"]] for e in IDS if "caveats" in self.events[e]}
        for event_id, event_notes in notes.items():
            for note in event_notes:
                self.assertTrue(note.startswith("8-K "), event_id)
        policy = "inside the window; content not opened. Policy: a caveat, not an exclusion (docs/SAME-DAY-COMPETING-CATALYST-POLICY.md; the Milestone 1 OKTA precedent)."
        self.assertIn("filed 2026-08-13 11:30 ET (Items 8.01) " + policy, notes[COLL][0])
        self.assertIn("filed 2026-08-14 20:09 ET (Items 8.01, 9.01) " + policy, notes[ACHV][1])
        self.assertIn("filed 2026-08-14 17:00 ET (Items 1.01, 9.01) " + policy, notes[KLC][0])
        self.assertEqual(notes[ACHV][0], "8-K 0001193125-26-296174 filed 2026-07-06 20:06 ET with Items 5.03, 5.07 and 9.01 (Item 5.03: amendments to the articles of incorporation or bylaws; Item 5.07: matters submitted to a vote of security holders), "
                                         "36 days before the release and before the window starts; content not opened. The event filing's cover still records the exchange as 'Nasdaq Stock Market LLC' on the release date, and Alpaca lists no corporate action over the window. "
                                         "A caveat, not an exclusion.")
        for event_id in IDS:
            for caveat in self.events[event_id].get("caveats", []):
                self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES | {"all"})

    def test_asmbs_release_has_no_spec(self):
        self.assertEqual(len(self.spec["events"][:38]), 38)                                         # batches 1 to 4; batch 5's events follow
        self.assertNotIn("asmb-m5b-2026-08-13", self.events)
        self.assertFalse([e for e in self.spec["events"] if e["candidate_id"] == "0001193125-26-352193"])
        self.assertFalse([e for e in self.spec["events"] if e["security"]["ticker"] == "ASMB" and e["published_at"][:10] == "2026-08-13"])


if __name__ == "__main__":
    unittest.main()
