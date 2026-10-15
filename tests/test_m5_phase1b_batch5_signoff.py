"""Milestone 5 Phase 1b batch 5, the last, after its sealed dry run: the dry-run record (reports/m5-phase1b-batch5-dry-run-2026-10-15.json) is the sealed view and nothing else, and says that the first dry run failed and why it showed only thirty-nine of the forty-three events; the signoff packet
(reports/m5-phase1b-batch5-signoff-packet-2026-10-15.json) is recomputed here from the events file, the sources record, the archived SEC lists, the Milestone 1 events, the review table, the S2 decisions and the calendar: release facts, identity evidence (REKR's Item 3.01 filing is the one
listing or charter item in the five), the in-window filings and the labels each can touch, the filings of the three days before each release, the proposed caveats, JBSS's two dividends, and the two calls to the owner (REKR's pre-announcement and Item 3.01 filing, SLSN's Item 4.02 filing)."""
import json
import re
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
DRY = ROOT / "reports" / "m5-phase1b-batch5-dry-run-2026-10-15.json"
PACKET = ROOT / "reports" / "m5-phase1b-batch5-signoff-packet-2026-10-15.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
EARLIER_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07",
               "payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21",
               "okta-m5b-2026-05-28", "vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "hurn-m5b-2026-07-28", "alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "caci-m5b-2026-08-05", "cxt-m5b-2026-08-05",
               "aspn-m5b-2026-08-06", "coll-m5b-2026-08-06", "pdfs-m5b-2026-08-06", "real-m5b-2026-08-06", "tecx-m5b-2026-08-06", "ttwo-m5b-2026-08-07", "achv-m5b-2026-08-11", "klc-m5b-2026-08-13", "lnsr-m5b-2026-08-13"]
IDS = ["rekr-m5b-2026-08-13", "jbss-m5b-2026-08-19", "slsn-m5b-2026-08-19", "okta-m5b-2026-08-26", "love-m5b-2026-09-10"]
REKR, JBSS, SLSN, OKTA, LOVE = IDS
COMMIT = "1c590a9a0b12fc5578e0ef447f7b3491e653826b"
WATCHED = {"4.02", "4.01", "2.06", "2.04", "1.02", "5.01", "3.01", "3.03", "5.03", "1.03"}


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

    def first_affected(self, accepted):
        sessions = self.calendar.days
        return accepted[:10] if accepted[:10] in sessions and accepted[11:] < "16:00" else next(d for d in sessions if d > accepted[:10])

    @staticmethod
    def accepted(row):
        return datetime.fromisoformat(row["acceptanceDateTime"].replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")


class DryRunRecordTests(Base):
    def test_the_sealed_view_is_the_forty_three_events_and_holds_only_what_the_seal_allows(self):
        events = self.dry["sealed_view"]["events"]
        self.assertEqual(sorted(events), sorted(EARLIER_IDS + IDS))
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
        self.assertEqual([(p["part"], p["all_ok"], p["level"], len(p["events"])) for p in parts], [("%d/9" % n, True, "notice", 4 if n <= 2 else 5) for n in range(1, 10)])
        self.assertLess(max(p["message_characters"] for p in parts), 4000)
        self.assertEqual(max(p["message_characters"] for p in parts), 3924)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(EARLIER_IDS + IDS))

    def test_the_five_quarantine_as_a_dry_run_should_and_the_thirty_eight_pins_matched_again(self):
        events = self.dry["sealed_view"]["events"]
        dividends = [{"ex_date": "2026-08-17", "id": "b819a028-2051-49fd-bcd4-6505d853d06f", "type": "cash_dividends"}, {"ex_date": "2026-08-17", "id": "ef28820a-6a63-4119-b7eb-0d71f55b7a91", "type": "cash_dividends"}]
        for event_id in IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_sha256"], view["session_labels"], view["labels_match_recorded"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], None, None, None))
                self.assertEqual(view["corporate_actions"], dividends if event_id == JBSS else [])
        for event_id in EARLIER_IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_match_recorded"]), ("MAPPED", [], True))
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
        self.assertEqual({k: v["corporate_actions"] for k, v in events.items() if k in EARLIER_IDS and v["corporate_actions"]},
                         {"jbss-m5b-2026-04-29": [{"ex_date": "2026-04-27", "id": "1b6fa9d4-9120-4ce8-946e-700cfe8d9d2a", "type": "cash_dividends"}],
                          "nbix-m5b-2026-05-05": [{"date_field": "effective_date", "ex_date": "2026-05-18", "id": "b8d80b2b-b0e2-4be3-b612-9325d12d1646", "type": "cash_mergers"}],
                          "cxt-m5b-2026-05-06": [{"ex_date": "2026-05-29", "id": "0a5b1554-acfa-4836-9775-8f007fcba86b", "type": "cash_dividends"}],
                          "cxt-m5b-2026-08-05": [{"ex_date": "2026-08-31", "id": "6c4c5bfd-242f-42e0-8f31-61d12a1783ad", "type": "cash_dividends"}]})
        self.assertEqual(self.dry["summary"], {"events_run": 43, "pins_checked": 38, "pins_that_matched": 38, "pins_that_differed": 0, "batch_5_events": 5, "batch_5_quarantined_for_want_of_an_attestation": 5, "errored": {},
                                               "batch_5_events_with_missing_or_zero_volume_sessions": 0, "batch_5_events_with_a_corporate_action": 1, "required_sessions_per_event": 21})
        self.assertEqual((self.dry["schema_version"], self.dry["kind"], self.dry["recorded_on"]), (1, "m5_phase1b_batch5_dry_run", "2026-10-15"))

    def test_jbss_dividends_precede_its_anchor_session_so_they_fall_inside_no_label_window(self):
        _, anchor, ends = self.windows(JBSS)
        found = self.dry["corporate_actions_found"]
        self.assertEqual(list(found), [JBSS])
        self.assertEqual(found[JBSS], [{"type": "cash_dividends", "ex_date": "2026-08-17", "id": "b819a028-2051-49fd-bcd4-6505d853d06f", "windows_it_falls_inside": []},
                                       {"type": "cash_dividends", "ex_date": "2026-08-17", "id": "ef28820a-6a63-4119-b7eb-0d71f55b7a91", "windows_it_falls_inside": []}])
        self.assertEqual(anchor, "2026-08-19")
        self.assertEqual(sorted(name for name, end in ends.items() if anchor < "2026-08-17" <= end), [])
        self.assertEqual(self.dry["sealed_view"]["events"][JBSS]["corporate_actions"], [{"ex_date": a["ex_date"], "id": a["id"], "type": a["type"]} for a in found[JBSS]])

    def test_the_runs_are_pinned_and_it_says_what_it_is_and_what_it_is_not(self):
        dry, run = self.dry, self.dry["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"], run["created_at"]),
                         ("M5 Phase 1b sealed event acquisition", 15, 38743297555, 116450275515, COMMIT, "success", "2026-10-15T13:30:37Z"))
        self.assertTrue(run["trigger"].startswith("workflow_dispatch (event_id all), started by the owner, Fahad9101, from the GitHub Actions page at 2026-10-15T13:30:37Z on commit 1c590a9, the engine fix:"))
        self.assertIn("the sealed workflow runs only on dispatch or on a push of the events file, and the push of the fix changed neither the events file nor the workflow.", run["trigger"])
        self.assertIn("The owner's screenshot of the run's page is in the session transcript, line 49053.", run["trigger"])
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertEqual(dry["how_it_was_read"], "From the check runs' public annotations through the GitHub API (nine sealed parts for this run, ten for the first); the job logs were not read.")
        other = dry["other_runs_of_the_push_of_the_fix"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 261, "run_id": 38738219591, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 116432870365, "conclusion": "success"}, "validate (3.13)": {"job_id": 116432869878, "conclusion": "success"}}})
        self.assertEqual(other["attested_event_acquisition"], {"workflow": "Attested event acquisition", "run_number": 17, "run_id": 38738219641, "job_id": 116432879345, "conclusion": "success",
                                                              "read": "The Milestone 1 workflow, which watches nre/event_acquire.py, ran on that push; its annotations hold all_ok true for the Milestone 1 events, so their pinned matches hold and the unsealed path is unchanged by the fix."})
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        for phrase in ("config/m5-phase1b-events.json as pushed in f430640 and still the same in 1c590a9, which holds the thirty-eight attested and pinned events of batches 1 to 4 followed by batch 5's five events in the dry-run state (no attestation).",
                       "no commitment for batch 5 (an unattested event computes no labels).", "It is the second dry run: the first (run 38735780909) failed and showed only thirty-nine of the forty-three events, as the first_dry_run block says.",
                       "No label value, price, return, day-1 or gap label exists in it."):
            self.assertIn(phrase, dry["what_this_is"])
        text = " ".join(dry["findings"])
        for phrase in ("All five batch 5 events are QUARANTINED on FIRST_PUBLIC_TIME_UNVERIFIED, as a dry run should be: the provider answered for each, all 21 required sessions are present, and none has zero volume.",
                       "JBSS 2026-08-19 lists two cash dividends (ids b819a028-2051-49fd-bcd4-6505d853d06f and ef28820a-6a63-4119-b7eb-0d71f55b7a91), both with ex-date 2026-08-17, two days before its anchor session 2026-08-19: they fall inside no label's window (recomputed from the calendar), "
                       "so once JBSS is attested no label is suppressed by them. The other four list no corporate action.",
                       "LOVE 2026-09-10's window ends 2026-10-31, which had not come on the day of the run; the bars request was capped at yesterday by the fix and all 21 required sessions (the last is 2026-10-07) came back, so nothing about its labels depends on the later days.",
                       "The thirty-eight pins of batches 1 to 4 were checked again and all thirty-eight report labels_match_recorded true with the commitments of the earlier runs; nothing about them changed.",
                       "With the fix the whole view is visible (forty-three events in nine parts, the longest 3,924 characters) and no event errors. The first dry run's failure (first_dry_run) is explained only in part: the annotation limit hid four events, but what failed among them was never seen."):
            self.assertIn(phrase, text)
        nots = " ".join(dry["not_a_claim"])
        for phrase in ("Not an attestation of any event.", "Not a label, a price or a return: the sealed view holds none, and none was read.", "Not a finding that a batch 5 event is eligible",
                       "Not a diagnosis of the first dry run's failure: its dropped part was never seen, and this run's success does not show which event failed or why."):
            self.assertIn(phrase, nots)

    def test_the_first_dry_run_is_recorded_as_it_was_the_annotation_limit_and_the_fix(self):
        first = self.dry["first_dry_run"]
        self.assertEqual((first["workflow"], first["run_number"], first["run_id"], first["job_id"], first["commit"], first["conclusion"], first["created_at"], first["trigger"]),
                         ("M5 Phase 1b sealed event acquisition", 14, 38735780909, 116424585748, "f4306406547a328f58f2cd6320fff180917248d3", "failure", "2026-10-15T12:35:15Z", "the push of 177bb21 and f430640 (3ae1e57..f430640)"))
        self.assertEqual(first["failed_step"], "Fetch real bars and corporate actions and print only the sealed view")
        self.assertEqual(first["other_run_of_that_push"], {"ci": {"workflow": "NRE Milestone 1", "run_number": 260, "run_id": 38735780956, "conclusion": "success",
                                                              "jobs": {"validate (3.12)": {"job_id": 116424585620, "conclusion": "success"}, "validate (3.13)": {"job_id": 116424586100, "conclusion": "success"}}}})
        self.assertEqual(first["what_was_visible"], "Ten annotation parts (1/11 to 10/11), all at level failure (all_ok false): thirty-nine of the forty-three events, of which the thirty-eight pinned ones were MAPPED with labels_match_recorded true and REKR was QUARANTINED on FIRST_PUBLIC_TIME_UNVERIFIED, none with an error.")
        for phrase in ("Part 11/11, which would have held JBSS, SLSN, OKTA and LOVE.", "Forty-three events needed eleven parts at the 3,300-character budget of nre/event_acquire.py's _annotations, and GitHub keeps only the first ten annotations of a kind per step, so the eleventh was never created.",
                       "Batches 1 to 4 (thirty-eight events) had fitted in ten parts.", "all_ok was false and no visible event had an error, so an event in the dropped part errored; which one, and why, was never seen, and the job log was not read."):
            self.assertIn(phrase, first["what_was_not"])
        for phrase in ("Commit 1c590a9, pushed on the owner's word (f430640..1c590a9)", "_annotations packs the parts to 3,900 characters (forty-three events take nine parts)", "the bars request never asks for a day that has not finished (fetch_end: the window's month end or yesterday, whichever is earlier; a window that has ended is asked for as before).",
                       "LOVE's window ends 2026-10-31, a day that had not come, and the provider's basic plan limits historical bars to data older than fifteen minutes: that was my best guess for the hidden error, and it stays a guess, since the dropped part was never seen (a transient provider error is another possibility)."):
            self.assertIn(phrase, first["fix"])
        events = self.dry["sealed_view"]["events"]
        hidden = [IDS[1], IDS[2], IDS[3], IDS[4]]
        self.assertEqual(sorted(set(e for e in events if e not in hidden)), sorted(EARLIER_IDS + [REKR]))                    # the thirty-nine the first run showed
        love = ea.event_window(self.by_id[LOVE], self.calendar)
        self.assertEqual((love["required_sessions"][-1], love["end"]), ("2026-10-07", "2026-10-31"))                          # the window end that was still in the future on the day of the first run (2026-10-15)
        for event_id in hidden[:3]:
            self.assertLess(ea.event_window(self.by_id[event_id], self.calendar)["end"], "2026-10-15")                       # the other three hidden events' windows had all ended


class SignoffPacketTests(Base):
    def test_its_events_are_batch_5s_and_the_sources_record(self):
        sources = {r["event_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-batch5-sources-2026-10-15.json")["events"]}
        self.assertEqual([e["event_id"] for e in self.packet["events"]], IDS)
        self.assertEqual([e["event_id"] for e in self.spec["events"][38:43]], IDS)
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event, row = self.by_id[entry["event_id"]], sources[entry["event_id"]]
                self.assertEqual((entry["candidate_id"], entry["ticker"], entry["cik"], entry["timing_class"]), (event["candidate_id"], event["security"]["ticker"], event["security"]["cik"], event["expected_release_timing"]))
                self.assertEqual(entry["release"], {"wire": row["wire"], "url": row["url"], "displayed_stamp_et": row["displayed_stamp"], "minute_encoded_in_spec": event["published_at"],
                                                    "page_machine_readable_time": row["page_machine_readable_time"], "sec_8k_accepted_et": row["edgar_acceptance_et"], "sec_acceptance_not_before_wire_minute": True})
                window = ea.event_window(event, self.calendar)
                self.assertEqual((entry["anchor_session"], entry["reaction_session"], entry["twentieth_reaction_session"]), (window["anchor_session"], window["reaction_session"], window["required_sessions"][-1]))
                self.assertEqual(entry["chronology_evidence"]["same_day_release_check"], row["same_day_release_check"])
                self.assertTrue(row["edgar_acceptance_et"][:10] > event["published_at"][:10] or row["edgar_acceptance_et"][11:] >= row["minute_et"])
                dividends = entry["event_id"] == JBSS
                self.assertEqual(entry["data_availability"],
                                 "All 21 required sessions present; no zero-volume session; two cash dividends listed, both with ex-date 2026-08-17, two days before the anchor session (2026-08-19), so no label's window contains them (the sealed dry run, workflow run 38743297555). No return was computed or viewed."
                                 if dividends else "All 21 required sessions present; no zero-volume session; no corporate action in the window (the sealed dry run, workflow run 38743297555). No return was computed or viewed.")
                if entry["event_id"] != REKR:
                    self.assertEqual(entry["chronology_evidence"]["earlier_disclosure_of_these_results"],
                                     "None found. The wire page's own stamp is the earliest public time located, EDGAR's acceptance is not earlier than it, and no other release of the issuer that day carries the results. "
                                     "That is absence of evidence, not proof: it is the residual gap the sign-off asks the owner to accept.")
        rekr = next(e for e in self.packet["events"] if e["event_id"] == REKR)
        self.assertEqual(rekr["chronology_evidence"]["earlier_disclosure_of_these_results"],
                         "Preliminary second-quarter figures were public from 2026-07-15 (the pre-announcement, 8-K 0001437749-26-023616, accepted 18:13 ET; see decisions_needed). For this release itself the wire page's own stamp is the earliest public time located, "
                         "EDGAR's acceptance is not earlier than it, and no other release of the issuer that day carries the results. The residual gap the sign-off asks the owner to accept is that open-web research cannot prove nothing earlier was public.")
        self.assertEqual(self.packet["timing_class_balance"], {"premarket": [REKR, LOVE], "after_hours": [JBSS, SLSN, OKTA]})
        self.assertEqual([e["twentieth_reaction_session"] for e in self.packet["events"]], ["2026-09-10", "2026-09-17", "2026-09-17", "2026-09-24", "2026-10-07"])

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
                    flagged[entry["event_id"]] = items
                charter = [r for r in self.history[entry["ticker"]] if r["filingDate"] <= last and {"3.03", "5.03"} & set(r["items"].split(","))]
                self.assertEqual(charter, [])
                self.assertEqual(entry["corporate_actions"]["sec_8k_items"], "No Item 3.03 or 5.03 8-K in the archived history up to the window end.")
        self.assertEqual(flagged, {REKR: ["2026-05-01 3.01"]})

    def test_the_archived_history_the_in_window_filings_and_the_filings_before_each_release_are_recomputed(self):
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event = self.by_id[entry["event_id"]]
                window, anchor, ends = self.windows(entry["event_id"])
                last, release = entry["twentieth_reaction_session"], event["published_at"][:10]
                rows = [r for r in self.history[entry["ticker"]] if r["filingDate"] <= last]
                self.assertEqual(entry["chronology_evidence"]["sec_8k_history_from_2026-03-01_to_the_window_end"],
                                 ["%s %s %s%s" % (r["filingDate"], r["form"], r["items"], " <EVENT>" if r["accessionNumber"] == event["candidate_id"] else "") for r in rows])
                inside, before = [], []
                for r in rows:
                    if r["accessionNumber"] == event["candidate_id"]:
                        continue
                    accepted = self.accepted(r)
                    first = self.first_affected(accepted)
                    row = {"filing_date": r["filingDate"], "accepted_et": accepted, "form": r["form"], "items": r["items"].split(","), "accession": r["accessionNumber"], "first_session_it_can_affect": first}
                    if release <= r["filingDate"] <= last:
                        inside.append(dict(row, labels_whose_windows_it_falls_inside=sorted(n for n, end in ends.items() if end >= first)))
                    elif (date.fromisoformat(release) - timedelta(days=3)).isoformat() <= r["filingDate"] < release:
                        before.append(row)
                        self.assertLessEqual(first, anchor)                                          # it can affect no session after the anchor session: it falls inside no label's window
                self.assertEqual(entry["competing_catalysts_inside_window"], inside)
                self.assertEqual(entry["filings_in_the_three_days_before_the_release"], before)
                caveats = entry["proposed_label_caveats"] or []
                all_label = [c for c in caveats if c["labels"] == ["all"]]
                self.assertEqual(len(all_label), 2 if entry["event_id"] == REKR else 0)              # only REKR's two earlier items travel with every label
                window_caveats = [c for c in caveats if c["labels"] != ["all"]]
                self.assertEqual([c["labels"] for c in window_caveats], [f["labels_whose_windows_it_falls_inside"] for f in inside])
                for caveat, filing in zip(window_caveats, inside):
                    self.assertIn("8-K %s filed %s ET (Items %s) inside the window; content not opened." % (filing["accession"], filing["accepted_et"], ", ".join(filing["items"])), caveat["note"])
                    self.assertIn("Policy: a caveat, not an exclusion (docs/SAME-DAY-COMPETING-CATALYST-POLICY.md; the Milestone 1 OKTA precedent).", caveat["note"])
                    self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES)
        by_event = {e["event_id"]: [(f["filing_date"], f["items"], f["accepted_et"], f["first_session_it_can_affect"], f["labels_whose_windows_it_falls_inside"]) for f in e["competing_catalysts_inside_window"]] for e in self.packet["events"] if e["competing_catalysts_inside_window"]}
        self.assertEqual(by_event, {JBSS: [("2026-08-25", ["7.01", "9.01"], "2026-08-25 09:25", "2026-08-25", ["session_10_close_return", "session_20_close_return", "session_5_close_return"])],
                                    SLSN: [("2026-08-21", ["4.02", "9.01"], "2026-08-21 16:30", "2026-08-24", ["session_10_close_return", "session_20_close_return", "session_5_close_return"])],
                                    OKTA: [("2026-09-18", ["5.02", "9.01"], "2026-09-18 20:24", "2026-09-21", ["session_20_close_return"])]})
        self.assertEqual({e["event_id"]: e["filings_in_the_three_days_before_the_release"] for e in self.packet["events"] if e["filings_in_the_three_days_before_the_release"]}, {})

    def test_the_packets_caveats_are_the_specs_and_the_dry_run_facts_are_the_dry_run_records(self):
        view = self.dry["sealed_view"]["events"]
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event = self.by_id[entry["event_id"]]
                self.assertEqual(event.get("caveats", []), entry["proposed_label_caveats"] or [])      # the signoff carried the packet's caveats into each attested spec, in the packet's order
                self.assertIn("attestations", event)
                self.assertIn("recorded_result", event)                                              # and each commitment was pinned after the attested sealed run printed it (tests/test_m5_phase1b_batch5_sealed_run.py)
                sealed = view[entry["event_id"]]
                self.assertEqual(entry["corporate_actions"]["sealed_dry_run"], {"corporate_actions": sealed["corporate_actions"], "state": "QUARANTINED", "reasons": ["FIRST_PUBLIC_TIME_UNVERIFIED"]})
                for caveat in entry["proposed_label_caveats"] or []:
                    self.assertTrue(set(caveat["labels"]) <= ea.LABEL_NAMES or caveat["labels"] == ["all"])
        self.assertEqual({e["event_id"]: [c["labels"] for c in e["proposed_label_caveats"]] for e in self.packet["events"] if e["proposed_label_caveats"]},
                         {REKR: [["all"], ["all"]], JBSS: [["session_10_close_return", "session_20_close_return", "session_5_close_return"]], SLSN: [["session_10_close_return", "session_20_close_return", "session_5_close_return"]], OKTA: [["session_20_close_return"]]})

    def test_rekrs_call_is_the_archive_the_s2_records_and_the_earlier_precedents(self):
        pre = next(r for r in self.history["REKR"] if r["accessionNumber"] == "0001437749-26-023616")
        self.assertEqual((pre["filingDate"], pre["form"], pre["items"], self.accepted(pre)), ("2026-07-15", "8-K", "2.02,7.01,9.01", "2026-07-15 18:13"))
        listing = next(r for r in self.history["REKR"] if r["accessionNumber"] == "0001437749-26-014478")
        self.assertEqual((listing["filingDate"], listing["form"], listing["items"], self.accepted(listing)), ("2026-05-01", "8-K", "3.01", "2026-05-01 20:30"))
        self.assertEqual((date(2026, 8, 13) - date(2026, 7, 15)).days, 29)
        self.assertEqual((date(2026, 8, 13) - date(2026, 5, 1)).days, 104)
        review = {r["candidate_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]}
        self.assertEqual(review[pre["accessionNumber"]]["assessment"], "recommend_exclude_preliminary_preannouncement")
        self.assertTrue(review[pre["accessionNumber"]]["note"].startswith("The release announces preliminary, unaudited second-quarter results with an outlook and a product launch (Items 2.02 and 7.01); the full second-quarter results followed on 2026-08-13."))
        effects = load(ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json")["effects"]["REKR 2026-07-15"]
        self.assertEqual((effects["candidate_id"], effects["disposition"]), (pre["accessionNumber"], "excluded"))
        step3 = next(e for e in load(ROOT / "config" / "m2-step3-events.json")["events"] if e["event_id"] == "rekr-step3-2025-03-31")
        self.assertIn("already public from the explicitly 'preliminary and unaudited' 2025-03-17 release", step3["caveats"][0]["note"])
        self.assertTrue(step3["caveats"][0]["note"].endswith("Applies to every computed label."))
        batch2 = self.by_id["rekr-m5b-2026-05-11"]
        self.assertEqual(batch2["caveats"][0]["labels"], ["all"])
        self.assertIn("8-K 0001437749-26-014478 filed 2026-05-01 20:30 ET with Item 3.01", batch2["caveats"][0]["note"])
        entry = next(e for e in self.packet["events"] if e["event_id"] == REKR)
        self.assertEqual(entry["proposed_label_caveats"], [
            {"labels": ["all"], "note": "8-K 0001437749-26-014478 filed 2026-05-01 20:30 ET with Item 3.01 (the item for a notice of delisting or of failure to satisfy a continued-listing rule or standard, or a transfer of listing), 104 days before the release; content not opened. "
                                         "The event filing's cover still records the exchange as 'Nasdaq Stock Market' on the release date, and Alpaca lists no corporate action over the window. A caveat, not an exclusion."},
            {"labels": ["all"], "note": "The second-quarter results were preliminarily pre-announced on 2026-07-15 (8-K 0001437749-26-023616, Items 2.02, 7.01, 9.01, accepted 18:13 ET, 29 days before this release; excluded as its own candidate, reports/m5-phase1b-s2-decisions-2026-10-09.json): "
                                         "the S2 review recorded it as preliminary, unaudited second-quarter results with an outlook and a product launch. Whether its headline figures match this release's was not compared, so this event's own reaction may reflect confirmation of already-known numbers "
                                         "rather than a fresh surprise. Applies to every computed label."}])
        call = self.packet["decisions_needed"][REKR]
        for phrase in ("Two items on REKR's record bear on this event, and I opened neither filing (the batch 5 permission was for wire pages only).",
                       "REKR's second-quarter results were preliminarily pre-announced on 2026-07-15 (8-K 0001437749-26-023616, Items 2.02, 7.01, 9.01, accepted 18:13 ET), twenty-nine days before this release.",
                       "you excluded it as its own candidate in the S2 decisions and kept this release, the full results, as the event.", "Whether its headline figures match this release's was not compared, so how much of this release was already known is not established.",
                       "Milestone 2 step 3 kept Rekor's 2025-03-31 full-results event after such a pre-announcement, with a caveat on every computed label (config/m2-step3-events.json, rekr-step3-2025-03-31).",
                       "the 8-K 0001437749-26-014478 filed 2026-05-01 with Item 3.01 (a notice of delisting or of failure to satisfy a continued-listing rule or standard) is in the archived history, 104 days before this release; batch 2 attested REKR's 2026-05-11 event with a caveat on all labels for it.",
                       "The event filing's cover (the S2 review) still lists the stock on the Nasdaq Stock Market on this release date, and Alpaca lists no corporate action in the window. The identity check found no other listing or charter item in the five."):
            self.assertIn(phrase, call["finding"])
        self.assertEqual(call["options"], ["Attest REKR with the two caveats on all labels proposed in its entry (the filings travel with the labels; content not opened, figures not compared).",
                                           "Hold REKR until the pre-announcement and this release are compared: it needs your permission to read the two releases' wire pages or the 8-K exhibits (I would give their names, source and size when asking).",
                                           "Leave REKR quarantined for now, or exclude it."])
        self.assertEqual(call["assistant_recommendation"], "Attest it with the two caveats: the pre-announcement was already excluded as its own event, this release is the full results, and step 3 and batch 2 both treated this kind of item as a caveat, not an exclusion. "
                                                           "The owner may prefer to have the two releases compared first.")

    def test_slsns_call_is_the_archive_and_the_filing_is_the_only_one_of_its_kind_in_any_window(self):
        filing = next(r for r in self.history["SLSN"] if r["accessionNumber"] == "0001171843-26-005702")
        self.assertEqual((filing["filingDate"], filing["form"], filing["items"], self.accepted(filing)), ("2026-08-21", "8-K", "4.02,9.01", "2026-08-21 16:30"))
        found = []
        for event in self.spec["events"][:43]:
            window = ea.event_window(event, self.calendar)
            release, last = event["published_at"][:10], window["required_sessions"][-1]
            found += [(event["event_id"], r["accessionNumber"]) for r in self.history[event["security"]["ticker"]]
                      if release <= r["filingDate"] <= last and r["accessionNumber"] != event["candidate_id"] and WATCHED & set(r["items"].split(","))]
        self.assertEqual(found, [(SLSN, "0001171843-26-005702")])
        slsn = self.by_id[SLSN]
        earnings = next(r for r in self.history["SLSN"] if r["accessionNumber"] == slsn["candidate_id"])
        self.assertEqual((earnings["filingDate"], self.accepted(earnings)), ("2026-08-20", "2026-08-20 16:12"))
        self.assertEqual(self.first_affected("2026-08-21 16:30"), "2026-08-24")
        window, anchor, ends = self.windows(SLSN)
        self.assertEqual((window["reaction_session"], self.calendar.offset(window["reaction_session"], 1), self.calendar.offset(window["reaction_session"], 2)), ("2026-08-20", "2026-08-21", "2026-08-24"))
        self.assertEqual(sorted(name for name, end in ends.items() if end >= "2026-08-24"), ["session_10_close_return", "session_20_close_return", "session_5_close_return"])
        self.assertEqual(ends["session_2_close_return"], "2026-08-21")                                          # the labels that precede the filing
        call = self.packet["decisions_needed"][SLSN]
        for phrase in ("SLSN's archived 8-K history has a filing with Item 4.02 (the item for a conclusion that previously issued financial statements, a related audit report or a completed interim review should no longer be relied on): "
                       "0001171843-26-005702, filed 2026-08-21 16:30 ET, inside this event's window, two days after the 2026-08-19 results release and one day after the earnings 8-K (2026-08-20 16:12 ET).",
                       "I did not open it (wire pages only), so I do not know which statements it concerns or whether they include the results released on 08-19.",
                       "It is the only filing in any window of the forty-three events that carries a listing, charter, auditor, impairment, termination, non-reliance or change-of-control item.",
                       "Accepted after the close on Friday 2026-08-21, the first session it can affect is Monday 2026-08-24, the third reaction session: the day-1 labels and session_2 (2026-08-21) come before it, and the policy gives the labels from session_5 on a caveat (session_5, session_10 and session_20).",
                       "The same-day-competing-catalyst policy that allows an exclusion does not apply to a filing two days later."):
            self.assertIn(phrase, call["finding"])
        self.assertEqual(call["options"], ["Attest SLSN with the caveat on session_5, session_10 and session_20 proposed in its entry (the filing travels with those labels; content not opened).",
                                           "Hold SLSN until I have read that one 8-K: it needs your permission to read one SEC filing (I would give its name, source and size when asking).",
                                           "Leave SLSN quarantined for now, or exclude it."])
        self.assertEqual(call["assistant_recommendation"], "Attest it with the caveat: the policy treats an in-window 8-K as a caveat on the labels it can touch, and the filing comes after the day-1 and session_2 labels. "
                                                           "The owner may well prefer to have the filing read first, because an Item 4.02 can bear on the results themselves.")

    def test_it_puts_two_calls_to_the_owner_and_says_what_a_signoff_is_and_is_not(self):
        self.assertEqual(sorted(self.packet["decisions_needed"]), [REKR, SLSN])
        items = self.packet["signoff_items_requested"]
        self.assertEqual(items, {
            "first_public_time_and_historical_identity": "Accept the release time (the wire page's displayed minute, confirmed by the page's own machine-readable time) and the identity evidence per event below, including the residual gap that open-web research cannot close "
                                                         "(an earlier disclosure with no public trace) and, for REKR, the earlier preliminary disclosure of its results. The identity evidence is the exchange the S2 review recorded from the event filing's cover or the release, "
                                                         "the previous Milestone 1 event and the archived 8-K history; the full cover rows were not re-read, to keep to the batch 5 permission.",
            "corporate_actions": "Accept two signals: no Item 3.03 or 5.03 8-K in the archived history up to the window end, and Alpaca's real answer as the sealed dry run reported it "
                                 "(JBSS two cash dividends with ex-date 2026-08-17, which precedes its anchor session, and none for the other four)."})
        self.assertEqual((self.packet["schema_version"], self.packet["kind"], self.packet["prepared_on"]), (1, "m5_phase1b_batch5_signoff_packet", "2026-10-15"))
        self.assertEqual(self.packet["dry_run"], {"record": "reports/m5-phase1b-batch5-dry-run-2026-10-15.json", "workflow": "M5 Phase 1b sealed event acquisition", "run_id": 38743297555, "commit": self.dry["run"]["commit"],
                                                  "result": "All five events ran with no attestation and quarantined on FIRST_PUBLIC_TIME_UNVERIFIED with every session present and none at zero volume; JBSS listed two cash dividends (ex-date 2026-08-17, before its anchor session) and the other four "
                                                            "no corporate action; the thirty-eight pins of batches 1 to 4 matched again."})
        self.assertEqual(self.packet["dry_run"]["commit"], COMMIT)
        for phrase in ("Evidence for the project owner to sign off, or not, on batch 5, the last, of Milestone 5 Phase 1b: five events built from the last five releases that stand (reports/m5-phase1b-batch5-permission-2026-10-15.json), after a sealed dry run (the second: the first failed, as the dry-run record says).",
                       "Nothing here is an acceptance: every event stays quarantined, and no label is computed, until the owner's attestations are added.",
                       "Two events carry a call for the owner (decisions_needed): REKR, whose second-quarter results were pre-announced on 2026-07-15 and whose history has the Item 3.01 filing of 2026-05-01, and SLSN, whose window holds an Item 4.02 filing two days after its release.",
                       "There is no release at the bell this time.", "The packet proposes label caveats for three filings inside windows (JBSS, SLSN, OKTA) and two on all of REKR's labels, and records two cash dividends for JBSS (ex-date 2026-08-17, before its anchor session)."):
            self.assertIn(phrase, self.packet["purpose"])
        self.assertEqual(self.packet["what_a_sign_off_would_look_like"], "For example: 'attest the five' (keeping REKR with its two caveats and SLSN with its caveat), or 'attest the three and hold REKR and SLSN', or a list of event_ids. "
                                                                          "Then the attestations are added for those events, the sealed workflow runs for real (the push of the events file), and each event's commitment is pinned.")
        for phrase in ("Not an attestation of any event.", "Not Phase 1b acceptance.", "content was not opened for any in-window filing, for REKR's two earlier filings or for the pre-announcement", "No return, price or label was computed or viewed."):
            self.assertIn(phrase, " ".join(self.packet["not_a_claim"]))
        self.assertTrue((ROOT / "docs" / "SAME-DAY-COMPETING-CATALYST-POLICY.md").is_file())
        notes = {e["event_id"]: e["additional_note"] for e in self.packet["events"]}
        self.assertEqual(notes[REKR], "No other 8-K inside the window. Released at 08:00 ET, premarket, although its two earlier events in the repository were after the close (16:05 ET on 2026-03-31 and 2026-05-11); EDGAR accepted the 8-K at 12:00 ET. "
                                      "Its second-quarter results were pre-announced on 2026-07-15 and an Item 3.01 filing of 2026-05-01 sits in its history: both are decisions_needed.")
        self.assertEqual(notes[JBSS], "1 other 8-K(s) sit inside the window (2026-08-25 Items 7.01,9.01); their content was not opened. The 8-K inside the window was accepted at 09:25 ET, before the open, so its first affected session is 2026-08-25 (the fourth reaction session) "
                                      "and it falls inside the session_5, 10 and 20 windows. Two cash dividends with ex-date 2026-08-17 are listed; both precede the anchor session (2026-08-19), so no label is affected.")
        self.assertEqual(notes[SLSN], "1 other 8-K(s) sit inside the window (2026-08-21 Items 4.02,9.01); their content was not opened. The release is after the close (17:05 ET on 2026-08-19) and its 8-K was filed and accepted the next day (2026-08-20 16:12 ET), "
                                      "whereas its two earlier events in the repository were premarket releases (08:02 ET on 2026-03-31 and 08:00 ET on 2026-05-12). The in-window 8-K carries Item 4.02 and is a decisions_needed.")
        self.assertEqual(notes[OKTA], "1 other 8-K(s) sit inside the window (2026-09-18 Items 5.02,9.01); their content was not opened. The wire listing of 2026-09-18 16:05 ET is titled 'Okta Names Helen Riley to Board of Directors'; the 8-K was accepted at 20:24 ET, "
                                      "after the close, so its first affected session is 2026-09-21 and it falls inside the session_20 window only.")
        self.assertEqual(notes[LOVE], "No other 8-K inside the window. EDGAR's acceptance of the 8-K (2026-09-10 07:00 ET) is the same minute as the wire's, not earlier. The window's last session is 2026-10-07; its fetch end was capped at yesterday by the engine fix, and all 21 sessions came back.")
        m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}
        self.assertEqual([m1["REKR"]["published_at"], self.by_id["rekr-m5b-2026-05-11"]["published_at"]], ["2026-03-31T16:05:00-04:00", "2026-05-11T16:05:00-04:00"])
        self.assertEqual([m1["SLSN"]["published_at"], self.by_id["slsn-m5b-2026-05-12"]["published_at"]], ["2026-03-31T08:02:00-04:00", "2026-05-12T08:00:00-04:00"])
        sources = load(ROOT / "reports" / "m5-phase1b-batch5-sources-2026-10-15.json")
        self.assertIn("a board appointment", sources["reading"]["what_was_seen_in_passing"])


if __name__ == "__main__":
    unittest.main()
