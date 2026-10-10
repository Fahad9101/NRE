"""Milestone 5 Phase 1b batch 2 after its sealed dry run: the dry-run record (reports/m5-phase1b-batch2-dry-run-2026-10-10.json) is the sealed view and nothing else, and the signoff packet (reports/m5-phase1b-batch2-signoff-packet-2026-10-10.json) is recomputed
here from the events file, the sources record, the archived SEC lists, the Milestone 1 events, the review table and the calendar: release facts, identity evidence (including the one Item 3.01 filing the identity check found), the in-window filings and the labels each can touch,
the caveats, and the two calls it puts to the owner."""
import json
import re
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
DRY = ROOT / "reports" / "m5-phase1b-batch2-dry-run-2026-10-10.json"
PACKET = ROOT / "reports" / "m5-phase1b-batch2-signoff-packet-2026-10-10.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
BATCH_1_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"]
IDS = ["payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
REKR, ACHV = "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calendar = Calendar()
        cls.spec = load(ROOT / "config" / "m5-phase1b-events.json")
        cls.by_id = {e["event_id"]: e for e in cls.spec["events"]}
        cls.dry = load(DRY)
        cls.packet = load(PACKET)
        cohort = load(ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json")["issuers"]
        metas = {meta["url"]: meta for meta in (load(path) for path in sorted(RAW.glob("*.json")))}
        cls.history = {}
        for issuer in cohort:
            recent = json.loads((RAW / metas[issuer["submissions_url"]]["raw_file"]).read_bytes())["filings"]["recent"]
            cls.history[issuer["ticker"]] = sorted(({k: recent[k][i] for k in ("accessionNumber", "filingDate", "form", "items", "acceptanceDateTime")} for i in range(len(recent["accessionNumber"]))),
                                                   key=lambda r: r["acceptanceDateTime"])

    def windows(self, event_id):
        window = ea.event_window(self.by_id[event_id], self.calendar)
        session = window["reaction_session"]
        ends = {name: session for name in ea.LABEL_NAMES if name not in ea.SESSION_LABEL_NAMES}
        ends.update({"session_%d_close_return" % n: self.calendar.offset(session, n - 1) for n in (2, 5, 10, 20)})
        return window, window["anchor_session"], ends


class DryRunRecordTests(Base):
    def test_the_sealed_view_is_the_nineteen_events_and_holds_only_what_the_seal_allows(self):
        events = self.dry["sealed_view"]["events"]
        self.assertEqual(sorted(events), sorted(BATCH_1_IDS + IDS))
        text = json.dumps(events, sort_keys=True)
        self.assertIsNone(re.search(r"\d\.\d", text))
        self.assertNotIn("NOT_POSITIVE", text)
        for event_id, view in events.items():
            with self.subTest(event=event_id):
                self.assertLessEqual(set(view), ea.SEALED_REPORT_KEYS)
                self.assertEqual((view["event_id"], view["sealed"], view["access_check_passed"], view["missing_sessions"], view["zero_volume_sessions"]), (event_id, True, True, [], []))
                self.assertNotIn("error", view)
                window = ea.event_window(self.by_id[event_id], self.calendar)
                self.assertEqual(view["window"], {"anchor_session": window["anchor_session"], "asof": window["asof"], "end": window["end"], "reaction_session": window["reaction_session"],
                                                  "release_timing": window["release_timing"], "required_sessions": 21, "start": window["start"]})
        parts = self.dry["annotation_parts"]
        self.assertEqual([(p["part"], p["all_ok"], p["level"], len(p["events"])) for p in parts], [("1/5", True, "notice", 4), ("2/5", True, "notice", 3), ("3/5", True, "notice", 5), ("4/5", True, "notice", 6), ("5/5", True, "notice", 1)])
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(BATCH_1_IDS + IDS))

    def test_the_ten_quarantine_as_a_dry_run_should_and_batch_1s_nine_pins_matched_again(self):
        events = self.dry["sealed_view"]["events"]
        for event_id in IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["corporate_actions"], view["labels_sha256"], view["session_labels"], view["labels_match_recorded"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], [], None, None, None))
        for event_id in BATCH_1_IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_match_recorded"]), ("MAPPED", [], True))
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
        self.assertEqual(self.dry["summary"], {"events_run": 19, "batch_1_pins_checked": 9, "batch_1_pins_that_matched": 9, "batch_1_pins_that_differed": 0, "batch_2_events": 10, "batch_2_quarantined_for_want_of_an_attestation": 10, "errored": {},
                                               "batch_2_events_with_missing_or_zero_volume_sessions": 0, "batch_2_events_with_a_corporate_action": 0, "required_sessions_per_event": 21})
        self.assertEqual((self.dry["kind"], self.dry["recorded_on"]), ("m5_phase1b_batch2_dry_run", "2026-10-10"))

    def test_the_runs_are_pinned_and_it_says_what_it_is_and_what_it_is_not(self):
        dry, run = self.dry, self.dry["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"]),
                         ("M5 Phase 1b sealed event acquisition", 5, 38048952680, 114204024813, "cd3faaa7d6fe42d3db9063a118bc87569a4825da", "success"))
        self.assertIn("the push of cd3faaa (f502e9e..cd3faaa)", run["trigger"])
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertIn("the job log was not read", dry["how_it_was_read"])
        other = dry["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 249, "run_id": 38048952697, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 114204024855, "conclusion": "success"}, "validate (3.13)": {"job_id": 114204024972, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        self.assertIn("config/m5-phase1b-events.json as pushed in cd3faaa, which holds batch 1's nine attested and pinned events followed by batch 2's ten events in the dry-run state", dry["what_this_is"])
        self.assertIn("No label value, price, return, day-1 or gap label exists in it.", dry["what_this_is"])
        text = " ".join(dry["findings"])
        for phrase in ("All ten batch 2 events are QUARANTINED on FIRST_PUBLIC_TIME_UNVERIFIED, as a dry run should be", "Alpaca lists no corporate action for any of the ten over its window",
                       "No batch 2 event errored, so there is no pipeline question this time", "Batch 1's nine pins were checked again and all nine report labels_match_recorded true"):
            self.assertIn(phrase, text)
        nots = " ".join(dry["not_a_claim"])
        for phrase in ("Not an attestation of any event.", "Not a label, a price or a return: the sealed view holds none, and none was read.", "Not a finding that a batch 2 event is eligible"):
            self.assertIn(phrase, nots)


class SignoffPacketTests(Base):
    def test_its_events_are_batch_2s_and_the_sources_record(self):
        sources = {r["event_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-batch2-sources-2026-10-10.json")["events"]}
        self.assertEqual([e["event_id"] for e in self.packet["events"]], IDS)
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event, row = self.by_id[entry["event_id"]], sources[entry["event_id"]]
                self.assertEqual((entry["candidate_id"], entry["ticker"], entry["cik"], entry["timing_class"]), (event["candidate_id"], event["security"]["ticker"], event["security"]["cik"], event["expected_release_timing"]))
                self.assertEqual(entry["release"], {"wire": row["wire"], "url": row["url"], "displayed_stamp_et": row["displayed_stamp"], "minute_encoded_in_spec": event["published_at"],
                                                    "page_machine_readable_time": row["page_machine_readable_time"], "sec_8k_accepted_et": row["edgar_acceptance_et"], "sec_acceptance_not_before_wire_minute": True})
                window = ea.event_window(event, self.calendar)
                self.assertEqual((entry["anchor_session"], entry["reaction_session"], entry["twentieth_reaction_session"]), (window["anchor_session"], window["reaction_session"], window["required_sessions"][-1]))
                self.assertEqual(entry["chronology_evidence"]["same_day_release_check"], row["same_day_release_check"])
                self.assertEqual(entry["chronology_evidence"]["earlier_disclosure_of_these_results"],
                                 "None found. The wire page's own stamp is the earliest public time located, EDGAR's acceptance is not earlier than it, and no other release of the issuer that day carries the results. "
                                 "That is absence of evidence, not proof: it is the residual gap the sign-off asks the owner to accept.")
                self.assertEqual(entry["data_availability"], "All 21 required sessions present; no zero-volume session; no corporate action in the window (the sealed dry run, workflow run 38048952680). No return was computed or viewed.")
        self.assertEqual(self.packet["timing_class_balance"], {"premarket": ["payo-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12"],
                                                               "after_hours": ["pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "rekr-m5b-2026-05-11", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]})

    def test_the_identity_evidence_is_the_archive_the_milestone_1_events_and_the_review_and_only_rekr_has_a_listing_item(self):
        m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}
        review = {r["candidate_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]}
        flagged = {}
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event, ident = self.by_id[entry["event_id"]], entry["identity_evidence"]
                self.assertEqual(ident["event_filing_url"], review[event["candidate_id"]]["primary_url"])
                self.assertEqual(ident["exchange_on_the_event_filings_cover_or_release_as_recorded_in_the_s2_review"], review[event["candidate_id"]]["exchange_on_cover_or_release"])
                self.assertEqual(ident["spec_exchange_and_ticker"], "%s | %s" % (event["security"]["exchange"], entry["ticker"]))
                previous = m1[entry["ticker"]]
                self.assertEqual(ident["previous_earnings_event_in_milestone_1"], {"event_id": previous["event_id"], "published_at": previous["published_at"], "candidate_id": previous["candidate_id"]})
                self.assertEqual((ident["spec_valid_from"], ident["spec_available_at"]), (event["security"]["valid_from"], event["security"]["available_at"]))
                self.assertEqual(datetime.fromisoformat(ident["spec_valid_from"]), datetime.fromisoformat(previous["published_at"][:10] + "T00:00:00").replace(tzinfo=ZONE))
                last = entry["twentieth_reaction_session"]
                items = [r["filingDate"] + " " + r["items"] for r in self.history[entry["ticker"]] if r["filingDate"] <= last and {"1.03", "3.01", "3.03", "4.01", "5.03"} & set(r["items"].split(","))]
                self.assertEqual(ident["listing_or_charter_items_in_the_archived_history_up_to_the_window_end"], items or "None (no Item 1.03, 3.01, 3.03, 4.01 or 5.03 8-K)")
                if items:
                    flagged[entry["ticker"]] = items
                self.assertEqual(entry["corporate_actions"]["sec_8k_items"], "No Item 3.03 or 5.03 8-K in the archived history up to the window end.")
        self.assertEqual(flagged, {"REKR": ["2026-05-01 3.01"]})

    def test_the_archived_history_and_the_in_window_filings_are_recomputed(self):
        sessions = self.calendar.days
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event = self.by_id[entry["event_id"]]
                _, anchor, ends = self.windows(entry["event_id"])
                last, release = entry["twentieth_reaction_session"], event["published_at"][:10]
                rows = [r for r in self.history[entry["ticker"]] if r["filingDate"] <= last]
                self.assertEqual(entry["chronology_evidence"]["sec_8k_history_from_2026-03-01_to_the_window_end"],
                                 ["%s %s %s%s" % (r["filingDate"], r["form"], r["items"], " <EVENT>" if r["accessionNumber"] == event["candidate_id"] else "") for r in rows])
                inside = []
                for r in rows:
                    if r["accessionNumber"] == event["candidate_id"] or not release <= r["filingDate"] <= last:
                        continue
                    accepted = datetime.fromisoformat(r["acceptanceDateTime"].replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")
                    first = accepted[:10] if accepted[:10] in sessions and accepted[11:] < "16:00" else next(d for d in sessions if d > accepted[:10])
                    inside.append({"filing_date": r["filingDate"], "accepted_et": accepted, "form": r["form"], "items": r["items"].split(","), "accession": r["accessionNumber"],
                                   "first_session_it_can_affect": first, "labels_whose_windows_it_falls_inside": sorted(n for n, end in ends.items() if end >= first)})
                self.assertEqual(entry["competing_catalysts_inside_window"], inside)
                caveats = [c for c in (entry["proposed_label_caveats"] or []) if c["labels"] != ["all"]]
                self.assertEqual([c["labels"] for c in caveats], [f["labels_whose_windows_it_falls_inside"] for f in inside])
                for caveat, filing in zip(caveats, inside):
                    self.assertIn(filing["accession"], caveat["note"])
                    self.assertIn("content not opened", caveat["note"])
                    self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES)
        by_event = {e["event_id"]: e["competing_catalysts_inside_window"] for e in self.packet["events"]}
        self.assertEqual({k: len(v) for k, v in by_event.items()}, {"payo-m5b-2026-05-07": 0, "pdfs-m5b-2026-05-07": 1, "real-m5b-2026-05-07": 0, "tecx-m5b-2026-05-07": 0, "lnsr-m5b-2026-05-08": 1, "rekr-m5b-2026-05-11": 1, "achv-m5b-2026-05-12": 1,
                                                                  "slsn-m5b-2026-05-12": 0, "klc-m5b-2026-05-14": 1, "ttwo-m5b-2026-05-21": 0})

    def test_the_packets_caveats_are_the_specs_and_the_dry_run_facts_are_the_dry_run_records(self):
        view = self.dry["sealed_view"]["events"]
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                self.assertEqual(self.by_id[entry["event_id"]].get("caveats", []), entry["proposed_label_caveats"] or [])         # the signoff carried the packet's caveats into each attested spec, in the packet's order
                sealed = view[entry["event_id"]]
                self.assertEqual(entry["corporate_actions"]["sealed_dry_run"], {"corporate_actions": sealed["corporate_actions"], "state": "QUARANTINED", "reasons": ["FIRST_PUBLIC_TIME_UNVERIFIED"]})
        rekr = next(e for e in self.packet["events"] if e["event_id"] == REKR)
        filing = next(r for r in self.history["REKR"] if r["filingDate"] == "2026-05-01" and r["items"] == "3.01")
        accepted = datetime.fromisoformat(filing["acceptanceDateTime"].replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")
        first = rekr["proposed_label_caveats"][0]
        self.assertEqual(first["labels"], ["all"])
        self.assertIn("8-K %s filed %s ET with Item 3.01" % (filing["accessionNumber"], accepted), first["note"])
        self.assertIn("content not opened", first["note"])
        self.assertIn("A caveat, not an exclusion.", first["note"])
        achv = next(e for e in self.packet["events"] if e["event_id"] == ACHV)
        self.assertEqual([c["labels"] for c in achv["proposed_label_caveats"]], [["all"], ["session_20_close_return"]])
        self.assertEqual(achv["proposed_label_caveats"][0]["note"], self.by_id[ACHV]["caveats"][0]["note"])

    def test_it_puts_two_calls_to_the_owner_and_says_what_a_signoff_is_and_is_not(self):
        decisions = self.packet["decisions_needed"]
        self.assertEqual(sorted(decisions), [ACHV, REKR])
        rekr = decisions[REKR]
        filing = next(r for r in self.history["REKR"] if r["filingDate"] == "2026-05-01" and r["items"] == "3.01")
        for phrase in ("REKR's archived 8-K history has a filing with Item 3.01", filing["accessionNumber"], "ten days before the 2026-05-11 release", "I did not open it: it is not one of the 47 candidates' filings, and the batch 2 permission was for wire pages only.",
                       "still lists the stock on the Nasdaq Stock Market on the release date", "The identity check found no other listing or charter item in the ten."):
            self.assertIn(phrase, rekr["finding"])
        self.assertEqual(len(rekr["options"]), 3)
        self.assertTrue(rekr["options"][0].startswith("Attest REKR with the caveat") and rekr["options"][1].startswith("Hold REKR until I have read that one 8-K") and rekr["options"][2].startswith("Leave REKR quarantined"))
        self.assertTrue(rekr["assistant_recommendation"].startswith("Attest it with the caveat"))
        achv = decisions[ACHV]
        sources = load(ROOT / "reports" / "m5-phase1b-batch2-sources-2026-10-10.json")
        self.assertIn(next(r for r in sources["events"] if r["ticker"] == "ACHV")["same_day_release_check"]["result"], achv["finding"])
        for phrase in ("Conditions 1 and 2 of docs/SAME-DAY-COMPETING-CATALYST-POLICY.md hold", "Condition 3 asks whether the content is fresh and weighty enough to move the price on its own"):
            self.assertIn(phrase, achv["finding"])
        self.assertEqual(len(achv["options"]), 2)
        self.assertTrue(achv["options"][0].startswith("Keep it, with the caveat") and achv["options"][1].startswith("Exclude it as a same-day competing catalyst"))
        self.assertTrue(achv["assistant_recommendation"].startswith("Keep it, with the caveat"))
        self.assertTrue((ROOT / "docs" / "SAME-DAY-COMPETING-CATALYST-POLICY.md").is_file())
        items = self.packet["signoff_items_requested"]
        self.assertIn("the full cover rows were not re-read, to keep to the batch 2 permission", items["first_public_time_and_historical_identity"])
        self.assertIn("(no corporate action for any of the ten)", items["corporate_actions"])
        self.assertEqual((self.packet["kind"], self.packet["prepared_on"]), ("m5_phase1b_batch2_signoff_packet", "2026-10-10"))
        self.assertEqual(self.packet["dry_run"], {"record": "reports/m5-phase1b-batch2-dry-run-2026-10-10.json", "workflow": "M5 Phase 1b sealed event acquisition", "run_id": 38048952680, "commit": self.dry["run"]["commit"],
                                                  "result": "All ten events ran with no attestation and quarantined on FIRST_PUBLIC_TIME_UNVERIFIED with every session present, none at zero volume and no corporate action over any window; batch 1's nine pins matched again."})
        self.assertEqual(self.packet["dry_run"]["commit"], "cd3faaa7d6fe42d3db9063a118bc87569a4825da")
        self.assertIn("Two events carry a call for the owner (decisions_needed): REKR, whose history has an Item 3.01 8-K ten days before the release, and ACHV, which had a separate same-day release.", self.packet["purpose"])
        self.assertEqual(self.packet["what_a_sign_off_would_look_like"], "For example: 'attest the ten' (keeping ACHV with its caveat), or 'attest the nine and exclude ACHV', or a list of event_ids. Then the attestations are added for those events, "
                                                                          "the sealed workflow runs for real (the push of the events file), and each event's commitment is pinned.")
        for phrase in ("Not an attestation of any event.", "Not Phase 1b acceptance.", "content was not opened for any in-window filing", "No return, price or label was computed or viewed."):
            self.assertIn(phrase, " ".join(self.packet["not_a_claim"]))
        self.assertIn("Nothing here is an acceptance: every event stays quarantined, and no label is computed, until the owner's attestations are added.", self.packet["purpose"])
        notes = {e["event_id"]: e.get("additional_note", "") for e in self.packet["events"]}
        self.assertIn("comes after the 20th reaction session (2026-06-04), so it is inside no label's window", notes["payo-m5b-2026-05-07"])
        self.assertIn("after the 20th reaction session (2026-06-22), so it is inside no label's window", notes["ttwo-m5b-2026-05-21"])
        self.assertIn("An 8-K with Item 3.01 filed 2026-05-01, before the release, is flagged by the identity check: see decisions_needed.", notes[REKR])
        self.assertIn("A separate release five minutes later announced three senior leadership appointments: see decisions_needed.", notes[ACHV])


if __name__ == "__main__":
    unittest.main()
