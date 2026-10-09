"""Milestone 5 Phase 1b batch 1 after its sealed dry run: the dry-run record (reports/m5-phase1b-batch1-dry-run-2026-10-09.json) is the sealed view and nothing else, and the signoff packet (reports/m5-phase1b-batch1-signoff-packet-2026-10-09.json)
is recomputed here from the events file, the sources record, the archived SEC lists, the Milestone 1 events and the calendar: release facts, identity evidence, the in-window filings and the labels each can touch, the caveats, and the two decisions it puts to
the owner."""
import json
import re
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
DRY = ROOT / "reports" / "m5-phase1b-batch1-dry-run-2026-10-09.json"
PACKET = ROOT / "reports" / "m5-phase1b-batch1-signoff-packet-2026-10-09.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"]


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
        session, anchor = window["reaction_session"], window["anchor_session"]
        ends = {name: session for name in ea.LABEL_NAMES if name not in ea.SESSION_LABEL_NAMES}
        ends.update({"session_%d_close_return" % n: self.calendar.offset(session, n - 1) for n in (2, 5, 10, 20)})
        return window, anchor, ends


class DryRunRecordTests(Base):
    def test_the_sealed_view_is_the_nine_events_and_holds_only_what_the_seal_allows(self):
        events = self.dry["sealed_view"]["events"]
        self.assertEqual(sorted(events), sorted(IDS))
        text = json.dumps(events, sort_keys=True)
        self.assertIsNone(re.search(r"\d\.\d", text))
        self.assertNotIn("NOT_POSITIVE_GAP", text)
        for event_id, view in events.items():
            with self.subTest(event=event_id):
                self.assertLessEqual(set(view), ea.SEALED_REPORT_KEYS)
                self.assertEqual((view["event_id"], view["sealed"], view["labels_sha256"], view["session_labels"], view["labels_match_recorded"]), (event_id, True, None, None, None))
                window = ea.event_window(self.by_id[event_id], self.calendar)
                self.assertEqual(view["window"], {"anchor_session": window["anchor_session"], "asof": window["asof"], "end": window["end"], "reaction_session": window["reaction_session"],
                                                  "release_timing": window["release_timing"], "required_sessions": 21, "start": window["start"]})
        parts = self.dry["annotation_parts"]
        self.assertEqual([(p["part"], p["all_ok"], p["level"]) for p in parts], [("1/2", False, "failure"), ("2/2", False, "failure")])
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(IDS))

    def test_eight_quarantine_as_a_dry_run_should_and_nbix_errors(self):
        events = self.dry["sealed_view"]["events"]
        for event_id in IDS:
            view = events[event_id]
            if event_id == "nbix-m5b-2026-05-05":
                self.assertEqual((view["error"], view["state"], view["access_check_passed"], view["reasons"]), ("DATA_VALIDATION_FAILED: corporate action missing ex_date", None, False, []))
            else:
                self.assertEqual((view["state"], view["reasons"], view["access_check_passed"], view["missing_sessions"], view["zero_volume_sessions"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], True, [], []))
                self.assertNotIn("error", view)
        self.assertEqual(self.dry["summary"], {"events_run": 9, "quarantined_for_want_of_an_attestation": 8, "errored": {"nbix-m5b-2026-05-05": "DATA_VALIDATION_FAILED: corporate action missing ex_date"},
                                               "events_with_missing_or_zero_volume_sessions": 0, "required_sessions_per_event": 21})
        self.assertEqual((self.dry["kind"], self.dry["recorded_on"]), ("m5_phase1b_batch1_dry_run", "2026-10-09"))
        self.assertEqual(self.dry["run"]["conclusion"], "failure")
        self.assertEqual((self.dry["run"]["run_id"], self.dry["run"]["job_id"], self.dry["run"]["commit"]), (37969688947, 113952834834, "22c98382ac74f8831dc350d200fb2dd91d4617b9"))

    def test_the_corporate_actions_are_two_cash_dividends_and_the_windows_they_fall_inside_are_recomputed(self):
        events = self.dry["sealed_view"]["events"]
        actions = {k: v["corporate_actions"] for k, v in events.items() if v["corporate_actions"]}
        self.assertEqual(actions, {"cxt-m5b-2026-05-06": [{"ex_date": "2026-05-29", "id": "0a5b1554-acfa-4836-9775-8f007fcba86b", "type": "cash_dividends"}],
                                   "jbss-m5b-2026-04-29": [{"ex_date": "2026-04-27", "id": "1b6fa9d4-9120-4ce8-946e-700cfe8d9d2a", "type": "cash_dividends"}]})
        for event_id, listed in actions.items():
            window, anchor, ends = self.windows(event_id)
            sessions = {"session_%d_close_return" % n: [anchor, self.calendar.offset(window["reaction_session"], n - 1)] for n in (2, 5, 10, 20)}
            sessions["day1"] = [anchor, window["reaction_session"]]
            expected = sorted(name for name, w in sessions.items() if w[0] < listed[0]["ex_date"] <= w[1])
            self.assertEqual(sorted(self.dry["corporate_actions_found"][event_id][0]["windows_it_falls_inside"]), expected)
        self.assertEqual(self.dry["corporate_actions_found"]["cxt-m5b-2026-05-06"][0]["windows_it_falls_inside"], ["session_20_close_return"])
        self.assertEqual(self.dry["corporate_actions_found"]["jbss-m5b-2026-04-29"][0]["windows_it_falls_inside"], [])

    def test_the_nbix_finding_is_an_inference_and_says_so(self):
        text = " ".join(self.dry["findings"])
        for phrase in ("the reading that this is that merger is an inference, not something the run showed", "The sealed view cannot show which item", "fails closed on that (DATA_VALIDATION_FAILED: corporate action missing ex_date)",
                       "The Phase 1a probe recorded exactly one corporate action for NBIX over three years, a cash merger"):
            self.assertIn(phrase, text)
        probe = load(ROOT / "reports" / "m5-phase1a-probe-run2-2026-10-09.json")["report"]["corporate_actions"]
        self.assertEqual(probe["NBIX"]["by_type"], {"cash_mergers": 1})
        nbix = [r for r in self.history["NBIX"] if r["filingDate"] == "2026-05-18"]
        self.assertEqual([r["items"] for r in nbix], ["1.01,2.01,2.03,7.01,9.01"])
        self.assertIn("The step exited with code 2 because one event (NBIX) returned an error", self.dry["run"]["why"])
        self.assertIn("the job log was not read", self.dry["how_it_was_read"])
        self.assertTrue(any("Not an attestation of any event." == s for s in self.dry["not_a_claim"]))


class SignoffPacketTests(Base):
    def test_its_events_are_the_events_file_and_the_sources_record(self):
        sources = {r["event_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-batch1-sources-2026-10-09.json")["events"]}
        self.assertEqual([e["event_id"] for e in self.packet["events"]], IDS)
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event, row = self.by_id[entry["event_id"]], sources[entry["event_id"]]
                self.assertEqual((entry["candidate_id"], entry["ticker"], entry["cik"], entry["timing_class"]), (event["candidate_id"], event["security"]["ticker"], event["security"]["cik"], event["expected_release_timing"]))
                self.assertEqual(entry["release"], {"wire": row["wire"], "url": row["url"], "displayed_stamp_et": row["displayed_stamp"], "minute_encoded_in_spec": event["published_at"],
                                                    "page_machine_readable_time": row["page_machine_readable_time"], "sec_8k_accepted_et": row["edgar_acceptance_et"],
                                                    "sec_acceptance_not_before_wire_minute": True})
                window = ea.event_window(event, self.calendar)
                self.assertEqual((entry["anchor_session"], entry["reaction_session"], entry["twentieth_reaction_session"]), (window["anchor_session"], window["reaction_session"], window["required_sessions"][-1]))
                self.assertEqual(entry["chronology_evidence"]["same_day_release_check"], row["same_day_release_check"])
                self.assertEqual(entry["chronology_evidence"]["earlier_disclosure_of_these_results"],
                                 "None found. The wire page's own stamp is the earliest public time located, EDGAR's acceptance is not earlier than it, and no other release of the issuer that day carries the results. "
                                 "That is absence of evidence, not proof: it is the residual gap the sign-off asks the owner to accept.")
        self.assertEqual(self.packet["timing_class_balance"], {"premarket": ["aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"], "after_hours": [i for i in IDS if i not in ("aspn-m5b-2026-05-07", "coll-m5b-2026-05-07")]})

    def test_the_identity_evidence_is_the_archive_the_milestone_1_events_and_the_covers(self):
        m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}
        review = {r["candidate_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]}
        exchange = {"New York Stock Exchange": "New York Stock Exchange", "Nasdaq Global Select Market": "Nasdaq Global Select Market"}
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event, ident = self.by_id[entry["event_id"]], entry["identity_evidence"]
                self.assertEqual(ident["event_filing_url"], review[event["candidate_id"]]["primary_url"])
                previous = m1[entry["ticker"]]
                self.assertEqual(ident["previous_earnings_event_in_milestone_1"], {"event_id": previous["event_id"], "published_at": previous["published_at"], "candidate_id": previous["candidate_id"]})
                self.assertEqual((ident["spec_valid_from"], ident["spec_available_at"]), (event["security"]["valid_from"], event["security"]["available_at"]))
                self.assertTrue(ident["spec_valid_from"].startswith(previous["published_at"][:10]))
                self.assertEqual(ident["listing_or_charter_items_in_the_archived_history_up_to_the_window_end"], "None (no Item 1.03, 3.01, 3.03, 4.01 or 5.03 8-K)")
                last = entry["twentieth_reaction_session"]
                items = {i for r in self.history[entry["ticker"]] if r["filingDate"] <= last for i in r["items"].split(",")}
                self.assertFalse(items & {"1.03", "3.01", "3.03", "4.01", "5.03"})
                self.assertEqual(entry["corporate_actions"]["sec_8k_items"], "No Item 3.03 or 5.03 8-K in the archived history up to the window end.")
                self.assertEqual(ident["event_filing_cover"].split(" | ")[1], entry["ticker"])
                self.assertTrue(ident["event_filing_cover"].startswith("Common ") or ident["event_filing_cover"].startswith("Common stock"))
                self.assertIn("New York Stock Exchange" if event["security"]["exchange"] == "NYSE" else "Nasdaq", ident["event_filing_cover"] if event["security"]["exchange"] == "NYSE" else ident["event_filing_cover"].replace("NASDAQ", "Nasdaq"))
        self.assertIn("NYSE Texas, Inc.", next(e for e in self.packet["events"] if e["ticker"] == "PARR")["identity_evidence"]["event_filing_cover"])

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
        self.assertEqual({k: len(v) for k, v in by_event.items()}, {"caci-m5b-2026-04-22": 0, "alkt-m5b-2026-04-29": 2, "jbss-m5b-2026-04-29": 0, "hurn-m5b-2026-05-05": 1, "nbix-m5b-2026-05-05": 2, "parr-m5b-2026-05-05": 2,
                                                                  "cxt-m5b-2026-05-06": 1, "aspn-m5b-2026-05-07": 1, "coll-m5b-2026-05-07": 2})

    def test_the_spec_caveats_travel_into_the_packet_and_the_dry_run_facts_are_the_dry_run_records(self):
        view = self.dry["sealed_view"]["events"]
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                spec_caveats = [{"labels": ["all"], "note": c["note"]} for c in self.by_id[entry["event_id"]].get("caveats", [])]
                self.assertEqual([c for c in (entry["proposed_label_caveats"] or []) if c["labels"] == ["all"]], spec_caveats)
                sealed = view[entry["event_id"]]
                if "error" in sealed:
                    self.assertEqual(entry["corporate_actions"]["sealed_dry_run"], "ERROR: " + sealed["error"])
                    self.assertIn("no data facts exist for this event yet", entry["data_availability"])
                else:
                    self.assertEqual(entry["corporate_actions"]["sealed_dry_run"], {"corporate_actions": sealed["corporate_actions"], "state": "QUARANTINED", "reasons": ["FIRST_PUBLIC_TIME_UNVERIFIED"]})
                    self.assertIn("All 21 required sessions present; no zero-volume session", entry["data_availability"])
        self.assertEqual({e["event_id"] for e in self.packet["events"] if e["corporate_actions"]["sealed_dry_run"] != "ERROR: DATA_VALIDATION_FAILED: corporate action missing ex_date" and view[e["event_id"]]["corporate_actions"]},
                         {"cxt-m5b-2026-05-06", "jbss-m5b-2026-04-29"})

    def test_it_puts_two_decisions_to_the_owner_and_says_what_a_signoff_is_and_is_not(self):
        decisions = self.packet["decisions_needed"]
        self.assertEqual(set(decisions), {"nbix-m5b-2026-05-05", "asmb-2026-05-07"})
        nbix = decisions["nbix-m5b-2026-05-05"]
        self.assertEqual(len(nbix["options"]), 2)
        self.assertTrue(nbix["options"][0].startswith("(A) An additive change to fetch_actions") and nbix["options"][1].startswith("(B) Leave the event quarantined"))
        self.assertIn("still fails closed if it has none of them", nbix["options"][0])
        self.assertIn("results already computed are unchanged", nbix["options"][0])
        self.assertIn("the Milestone 1 pinned matches re-run on real data as the check", nbix["options"][0])
        self.assertTrue(nbix["assistant_recommendation"].startswith("(A), because it keeps a legitimate event and fixes the rule before any commitment is made"))
        self.assertEqual(nbix["finding"], self.dry["findings"][2])
        asmb = decisions["asmb-2026-05-07"]
        self.assertEqual(asmb["options"], ["Leave it quarantined, not excluded (the precedent).", "Exclude it."])
        self.assertEqual(asmb["assistant_recommendation"], "Leave it quarantined.")
        self.assertEqual(asmb["finding"], load(ROOT / "reports" / "m5-phase1b-batch1-sources-2026-10-09.json")["quarantined_before_the_spec"]["reason"])
        items = self.packet["signoff_items_requested"]
        self.assertIn("NBIX is not asked for: its action cannot be listed yet.", items["corporate_actions"])
        self.assertIn("the residual gap that open-web research cannot close", items["first_public_time_and_historical_identity"])
        self.assertEqual((self.packet["kind"], self.packet["prepared_on"]), ("m5_phase1b_batch1_signoff_packet", "2026-10-09"))
        self.assertEqual(self.packet["dry_run"]["run_id"], 37969688947)
        for phrase in ("Not an attestation of any event.", "Not Phase 1b acceptance.", "content was not opened for any in-window filing", "No return, price or label was computed or viewed."):
            self.assertIn(phrase, " ".join(self.packet["not_a_claim"]))
        self.assertIn("Nothing here is an acceptance: every event stays quarantined, and no label is computed, until the owner's attestations are added.", self.packet["purpose"])
        notes = {e["event_id"]: e.get("additional_note", "") for e in self.packet["events"]}
        self.assertIn("BLOCKED: the dry run errored on a corporate action with no ex_date", notes["nbix-m5b-2026-05-05"])
        self.assertIn("cash dividend with ex-date 2026-05-29 falls inside session_20's window only", notes["cxt-m5b-2026-05-06"])
        self.assertIn("cash dividend with ex-date 2026-04-27 precedes the anchor session", notes["jbss-m5b-2026-04-29"])


if __name__ == "__main__":
    unittest.main()
