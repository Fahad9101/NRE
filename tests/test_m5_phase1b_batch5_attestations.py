"""The owner's signoff of Milestone 5 Phase 1b batch 5, the last (reports/m5-phase1b-batch5-signoff-2026-10-15.json): his words as given (the request in my report and "attest the five"), what the answer decides (all five events attested, REKR with its two caveats on all
labels, SLSN with its Item 4.02 caveat on three labels), and the events file that carries it out -- the five events attested on the record, with the caveats the packet proposed for REKR, JBSS, SLSN and OKTA. (Their commitments are pinned from the attested sealed run:
tests/test_m5_phase1b_batch5_sealed_run.py.)"""
import json
import unittest
from pathlib import Path

from nre import event_acquire as ea

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch5-signoff-2026-10-15.json"
PACKET_PATH = "reports/m5-phase1b-batch5-signoff-packet-2026-10-15.json"
IDS = ["rekr-m5b-2026-08-13", "jbss-m5b-2026-08-19", "slsn-m5b-2026-08-19", "okta-m5b-2026-08-26", "love-m5b-2026-09-10"]
REKR, JBSS, SLSN, OKTA, LOVE = IDS
ANSWER = 'Owner sign-off ("attest the five", 2026-10-15) on '
BASIS = {
    "first_public_time": ANSWER + "the release-time evidence in " + PACKET_PATH + " (the wire page's minute and its machine-readable time, the same-day release check), accepting the residual gap the packet states; REKR's 2026-07-15 pre-announcement is carried as a caveat.",
    "historical_identity": ANSWER + "the identity evidence in " + PACKET_PATH + " (the exchange the S2 review recorded from the event filing's cover or the release, the previous Milestone 1 event, the archived 8-K history checked for Items 1.03, 3.01, 3.03, 4.01 and 5.03; "
                           "the one Item 3.01 filing found, REKR's, is carried as a caveat).",
    "corporate_actions": ANSWER + "the two signals in " + PACKET_PATH + " (no Item 3.03 or 5.03 8-K in the archived history up to the window end, and Alpaca's real answer as the sealed dry run reported it: "
                         "JBSS two cash dividends with ex-date 2026-08-17, before its anchor session, and none for the other four).",
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
        self.assertEqual((request["at"], request["source"], request["recommended_reply"]), ("2026-10-15T13:52:15.432Z", "session transcript, line 49256 (my report)", "attest the five"))
        for phrase in ("Batch 5's signoff packet is ready, and I need your call on two events. The packet and the dry-run record are committed locally as `9e2021f` and not pushed.",
                       "**What the packet covers:** five events, REKR, JBSS, SLSN, OKTA and LOVE.", "- **Filings:** I opened none, so none of them is verified.", "**Two calls for you**",
                       "1. **REKR:**", "- **Pre-announcement:** its second-quarter results were pre-announced on 2026-07-15. You already excluded that release as its own event, and I did not compare its figures with the 08-13 release.",
                       "- **Item 3.01 filing:** the 2026-05-01 filing that batch 2 handled with a caveat is still in its history.",
                       "- **My recommendation:** attest it with two all-label caveats. That follows the step 3 precedent for Rekor's 2025-03-31 event and the batch 2 precedent for the 3.01 filing.",
                       "2. **SLSN:**", "- **The filing:** an Item 4.02 8-K, which reports a conclusion that earlier financial statements shouldn't be relied on. It was filed 2026-08-21 at 16:30 ET, two days after its release. It's the only filing of that kind in any of the 43 windows.",
                       "- **My recommendation:** attest it with a caveat on the session_5, 10 and 20 labels. You may prefer to have the filing read first.",
                       "- JBSS gets one for an 8-K filed 2026-08-25.", "- OKTA gets one for an 8-K filed 2026-09-18.", "- LOVE is clean.",
                       "**Recommended reply:** `attest the five`. That attests first-public time, historical identity and corporate actions for all five events. It also attaches REKR's two caveats, SLSN's 4.02 caveat and the JBSS and OKTA caveats. "
                       "Other replies work too, for example \"attest the three and hold REKR and SLSN\", or a different call on either.",
                       "your next \"push\" publishes `9e2021f` together with that signoff commit and starts the attested sealed run."):
            self.assertIn(phrase, request["text"])
        answered = record["answered"]
        self.assertEqual((answered["text"], answered["at"], answered["source"]), ("attest the five", "2026-10-15T13:54:23.394Z", "session transcript, line 49260 (queued at line 49258)"))
        self.assertLess(request["at"], answered["at"])
        self.assertIn("Reply to the batch 5 signoff request built from " + PACKET_PATH + " after the sealed dry run (reports/m5-phase1b-batch5-dry-run-2026-10-15.json)", record["context"])
        self.assertIn("five events quarantined as a dry run should, two cash dividends for JBSS before its anchor session, two calls for the owner (REKR's pre-announcement and Item 3.01 filing, SLSN's Item 4.02 filing) and proposed label caveats for five filings", record["context"])
        self.assertIn("The request went out as plain text in my report.", record["context"])
        self.assertIn("quoted from the session transcript, not from a summary", record["context"])
        self.assertEqual((record["schema_version"], record["kind"], record["recorded_on"]), (1, "m5_phase1b_batch5_signoff", "2026-10-15"))
        self.assertEqual(sorted(record), ["answered", "context", "kind", "not_a_claim", "recorded_on", "request_in_text", "schema_version", "scope"])

    def test_it_says_what_the_answer_decides(self):
        scope = self.record["scope"]
        self.assertEqual(scope["attested"]["events"], IDS)
        self.assertEqual(scope["attested"]["attestations"], ["first_public_time", "historical_identity", "corporate_actions"])
        for phrase in ("The three attestations for all five batch 5 events, on the evidence in the packet, accepting the residual gap that open-web research cannot close (an earlier public disclosure with no discoverable trace), "
                       "and carrying the packet's proposed label caveats into the events' specs as caveats, not exclusions:",
                       "REKR's Item 3.01 filing of 2026-05-01 and its 2026-07-15 pre-announcement on all of its labels, and the in-window 8-Ks listed for JBSS, SLSN and OKTA, whose content was not opened"):
            self.assertIn(phrase, scope["attested"]["read_as"])
        self.assertEqual((scope["rekr"]["event"], scope["rekr"]["decision"]), (REKR, "attest with the two caveats"))
        for phrase in ("carries two caveats on all labels: the 8-K 0001437749-26-014478 filed 2026-05-01 20:30 ET with Item 3.01 (content not opened), and the pre-announcement of 2026-07-15 (8-K 0001437749-26-023616; its figures were not compared with this release's).",
                       "It is not held for the two releases to be compared, not left quarantined and not excluded.", "No permission to read any filing or release was asked for or given."):
            self.assertIn(phrase, scope["rekr"]["read_as"])
        self.assertEqual((scope["slsn"]["event"], scope["slsn"]["decision"]), (SLSN, "attest with the caveat"))
        for phrase in ("carries a caveat on session_5, session_10 and session_20 naming the 8-K 0001171843-26-005702 filed 2026-08-21 16:30 ET with Items 4.02 and 9.01 (content not opened); it is not held for the filing to be read, not left quarantined and not excluded.",
                       "No permission to read that filing was asked for or given."):
            self.assertIn(phrase, scope["slsn"]["read_as"])
        self.assertEqual(scope["additions_to_the_owners_words"], "None: the attestations, caveats and the two decisions are exactly the packet's recommendations and proposals.")
        self.assertEqual(self.record["answered"]["read_as"], "The reply the report asked for: the three attestations for all five events, on the evidence in the packet, with REKR's two caveats on all labels, SLSN's Item 4.02 caveat on session_5, session_10 and session_20, "
                                                              "the packet's in-window caveats for JBSS and OKTA and the residual gap accepted; no event is held.")
        self.assertEqual(len(self.record["not_a_claim"]), 4)
        text = " ".join(self.record["not_a_claim"])
        for phrase in ("Not Phase 1b acceptance and not a claim about any event's outcome: no label, price or return has been computed or viewed.",
                       "Not a clearance of the filings that travel as caveats (REKR's Item 3.01 filing and pre-announcement, and the in-window 8-Ks of JBSS, SLSN and OKTA): their content was not opened.",
                       "Not a comparison of REKR's pre-announcement with its 2026-08-13 release: the figures were not compared.", "Not a permission to read any filing or any other page."):
            self.assertIn(phrase, text)
        packet = load(PACKET_PATH)
        self.assertEqual(sorted(packet["decisions_needed"]), [REKR, SLSN])                              # the two calls the answer settles
        self.assertEqual([e["event_id"] for e in packet["events"]], IDS)


class EventsFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load("config/m5-phase1b-events.json")
        cls.events = {e["event_id"]: e for e in cls.spec["events"]}
        cls.packet = load(PACKET_PATH)

    def test_the_five_events_carry_the_three_attestations_on_that_record(self):
        self.assertTrue((ROOT / RECORD_PATH).is_file())
        self.assertEqual(len(self.spec["events"]), 43)
        self.assertEqual(list(self.events)[38:43], IDS)
        for event_id in IDS:
            with self.subTest(event=event_id):
                attestations = self.events[event_id]["attestations"]
                self.assertEqual(sorted(attestations), sorted(ea.ATTESTATIONS))
                for name, attestation in attestations.items():
                    self.assertEqual(attestation, {"reviewer": "Fahad9101", "date": "2026-10-15", "record": RECORD_PATH, "basis": BASIS[name]})
        for event_id in list(self.events)[:38]:
            for attestation in self.events[event_id]["attestations"].values():
                self.assertNotEqual(attestation["record"], RECORD_PATH)                  # the earlier batches' attestations are on their own records

    def test_the_five_specs_carry_the_packets_caveats(self):
        proposed = {e["event_id"]: e["proposed_label_caveats"] for e in self.packet["events"]}
        for event_id in IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.events[event_id].get("caveats"), proposed[event_id])
        self.assertEqual({e: len(self.events[e]["caveats"]) for e in IDS if "caveats" in self.events[e]}, {REKR: 2, JBSS: 1, SLSN: 1, OKTA: 1})
        self.assertNotIn("caveats", self.events[LOVE])                                         # LOVE is clean: no filing of the window can touch a label
        self.assertEqual({e: [c["labels"] for c in self.events[e]["caveats"]] for e in IDS if "caveats" in self.events[e]},
                         {REKR: [["all"], ["all"]],
                          JBSS: [["session_10_close_return", "session_20_close_return", "session_5_close_return"]],
                          SLSN: [["session_10_close_return", "session_20_close_return", "session_5_close_return"]],
                          OKTA: [["session_20_close_return"]]})
        notes = {e: [c["note"] for c in self.events[e]["caveats"]] for e in IDS if "caveats" in self.events[e]}
        policy = "inside the window; content not opened. Policy: a caveat, not an exclusion (docs/SAME-DAY-COMPETING-CATALYST-POLICY.md; the Milestone 1 OKTA precedent)."
        self.assertEqual(notes[JBSS], ["8-K 0001193125-26-364284 filed 2026-08-25 09:25 ET (Items 7.01, 9.01) " + policy])
        self.assertEqual(notes[SLSN], ["8-K 0001171843-26-005702 filed 2026-08-21 16:30 ET (Items 4.02, 9.01) " + policy])
        self.assertEqual(notes[OKTA], ["8-K 0001660134-26-000072 filed 2026-09-18 20:24 ET (Items 5.02, 9.01) " + policy])
        self.assertEqual(notes[REKR][0], "8-K 0001437749-26-014478 filed 2026-05-01 20:30 ET with Item 3.01 (the item for a notice of delisting or of failure to satisfy a continued-listing rule or standard, or a transfer of listing), 104 days before the release; content not opened. "
                                         "The event filing's cover still records the exchange as 'Nasdaq Stock Market' on the release date, and Alpaca lists no corporate action over the window. A caveat, not an exclusion.")
        self.assertEqual(notes[REKR][1], "The second-quarter results were preliminarily pre-announced on 2026-07-15 (8-K 0001437749-26-023616, Items 2.02, 7.01, 9.01, accepted 18:13 ET, 29 days before this release; excluded as its own candidate, "
                                         "reports/m5-phase1b-s2-decisions-2026-10-09.json): the S2 review recorded it as preliminary, unaudited second-quarter results with an outlook and a product launch. Whether its headline figures match this release's was not compared, "
                                         "so this event's own reaction may reflect confirmation of already-known numbers rather than a fresh surprise. Applies to every computed label.")
        for event_id in IDS:
            for caveat in self.events[event_id].get("caveats", []):
                self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES | {"all"})
        batch2_rekr = self.events["rekr-m5b-2026-05-11"]["caveats"][0]                         # the batch 2 precedent: the same Item 3.01 filing, on all labels
        self.assertEqual(batch2_rekr["labels"], ["all"])
        self.assertTrue(batch2_rekr["note"].startswith("8-K 0001437749-26-014478 filed 2026-05-01 20:30 ET with Item 3.01"))

    def test_all_five_have_specs_and_were_pinned_from_the_attested_sealed_run(self):
        self.assertEqual(len([e for e in self.spec["events"] if e["event_id"] in IDS]), 5)       # no event of the batch is excluded or left without a spec
        for event_id in IDS:
            self.assertEqual(self.events[event_id]["recorded_result"]["recorded_in"], "reports/m5-phase1b-batch5-sealed-run-2026-10-15.json")
        for event_id in list(self.events)[:38]:
            self.assertIn("recorded_result", self.events[event_id])                              # the thirty-eight of batches 1 to 4 stay pinned


if __name__ == "__main__":
    unittest.main()
