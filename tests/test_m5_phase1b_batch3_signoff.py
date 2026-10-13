"""Milestone 5 Phase 1b batch 3 after its sealed dry run: the dry-run record (reports/m5-phase1b-batch3-dry-run-2026-10-13.json) is the sealed view and nothing else, and the signoff packet (reports/m5-phase1b-batch3-signoff-packet-2026-10-13.json) is recomputed
here from the events file, the sources record, the archived SEC lists, the Milestone 1 events, the review table and the calendar: release facts, identity evidence (no listing or charter item in any of the ten), the in-window filings and the labels each can touch, the
filings of the three days before each release, the proposed caveats, CXT's one cash dividend, and the absence of any call to the owner."""
import json
import re
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
DRY = ROOT / "reports" / "m5-phase1b-batch3-dry-run-2026-10-13.json"
PACKET = ROOT / "reports" / "m5-phase1b-batch3-signoff-packet-2026-10-13.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
EARLIER_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07",
               "payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
IDS = ["okta-m5b-2026-05-28", "vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "hurn-m5b-2026-07-28", "alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "caci-m5b-2026-08-05", "cxt-m5b-2026-08-05"]
CXT = "cxt-m5b-2026-08-05"
COMMIT = "b00783ed550a4402cdf94da07d90fefe127042e6"


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


class DryRunRecordTests(Base):
    def test_the_sealed_view_is_the_twenty_nine_events_and_holds_only_what_the_seal_allows(self):
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
        self.assertEqual([(p["part"], p["all_ok"], p["level"], len(p["events"])) for p in parts],
                         [("1/7", True, "notice", 4), ("2/7", True, "notice", 3), ("3/7", True, "notice", 4), ("4/7", True, "notice", 4), ("5/7", True, "notice", 4), ("6/7", True, "notice", 6), ("7/7", True, "notice", 4)])
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(EARLIER_IDS + IDS))

    def test_the_ten_quarantine_as_a_dry_run_should_and_the_nineteen_pins_matched_again(self):
        events = self.dry["sealed_view"]["events"]
        for event_id in IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_sha256"], view["session_labels"], view["labels_match_recorded"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], None, None, None))
                self.assertEqual(view["corporate_actions"], [{"ex_date": "2026-08-31", "id": "6c4c5bfd-242f-42e0-8f31-61d12a1783ad", "type": "cash_dividends"}] if event_id == CXT else [])
        for event_id in EARLIER_IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_match_recorded"]), ("MAPPED", [], True))
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
        self.assertEqual(self.dry["summary"], {"events_run": 29, "pins_checked": 19, "pins_that_matched": 19, "pins_that_differed": 0, "batch_3_events": 10, "batch_3_quarantined_for_want_of_an_attestation": 10, "errored": {},
                                               "batch_3_events_with_missing_or_zero_volume_sessions": 0, "batch_3_events_with_a_corporate_action": 1, "required_sessions_per_event": 21})
        self.assertEqual((self.dry["kind"], self.dry["recorded_on"]), ("m5_phase1b_batch3_dry_run", "2026-10-13"))

    def test_cxts_one_action_falls_inside_one_label_window_by_the_calendar(self):
        _, anchor, ends = self.windows(CXT)
        found = self.dry["corporate_actions_found"]
        self.assertEqual(list(found), [CXT])
        self.assertEqual(found[CXT], [{"type": "cash_dividends", "ex_date": "2026-08-31", "id": "6c4c5bfd-242f-42e0-8f31-61d12a1783ad",
                                       "windows_it_falls_inside": sorted(name for name, end in ends.items() if anchor < "2026-08-31" <= end)}])
        self.assertEqual(found[CXT][0]["windows_it_falls_inside"], ["session_20_close_return"])
        self.assertEqual(self.dry["sealed_view"]["events"][CXT]["corporate_actions"], [{"ex_date": found[CXT][0]["ex_date"], "id": found[CXT][0]["id"], "type": found[CXT][0]["type"]}])

    def test_the_runs_are_pinned_and_it_says_what_it_is_and_what_it_is_not(self):
        dry, run = self.dry, self.dry["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"]),
                         ("M5 Phase 1b sealed event acquisition", 8, 38418113326, 115367885297, COMMIT, "success"))
        self.assertIn("the push of b00783e (2bd7dfe..b00783e)", run["trigger"])
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertIn("the job log was not read", dry["how_it_was_read"])
        self.assertIn("(seven sealed parts)", dry["how_it_was_read"])
        other = dry["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 253, "run_id": 38418113227, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 115367879459, "conclusion": "success"}, "validate (3.13)": {"job_id": 115367879299, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        self.assertIn("config/m5-phase1b-events.json as pushed in b00783e, which holds the nineteen attested and pinned events of batches 1 and 2 followed by batch 3's ten events in the dry-run state", dry["what_this_is"])
        self.assertIn("no commitment for batch 3 (an unattested event computes no labels)", dry["what_this_is"])
        self.assertIn("No label value, price, return, day-1 or gap label exists in it.", dry["what_this_is"])
        text = " ".join(dry["findings"])
        for phrase in ("All ten batch 3 events are QUARANTINED on FIRST_PUBLIC_TIME_UNVERIFIED, as a dry run should be", "all 21 required sessions are present, and none has zero volume",
                       "Nine of the ten list no corporate action over their windows. CXT 2026-08-05 lists one: a cash_dividends item (id 6c4c5bfd-242f-42e0-8f31-61d12a1783ad) with ex-date 2026-08-31",
                       "inside the window of its session_20 label only, so once CXT is attested that label will not exist (CORPORATE_ACTION_IN_WINDOW) and its other labels will.",
                       "No batch 3 event errored, so there is no pipeline question this time", "The nineteen pins of batches 1 and 2 were checked again and all nineteen report labels_match_recorded true"):
            self.assertIn(phrase, text)
        nots = " ".join(dry["not_a_claim"])
        for phrase in ("Not an attestation of any event.", "Not a label, a price or a return: the sealed view holds none, and none was read.", "Not a finding that a batch 3 event is eligible"):
            self.assertIn(phrase, nots)


class SignoffPacketTests(Base):
    def test_its_events_are_batch_3s_and_the_sources_record(self):
        sources = {r["event_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-batch3-sources-2026-10-10.json")["events"]}
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
                action = "one cash dividend in the window (see the corporate actions above)" if entry["event_id"] == CXT else "no corporate action in the window"
                self.assertEqual(entry["data_availability"], "All 21 required sessions present; no zero-volume session; %s (the sealed dry run, workflow run 38418113326). No return was computed or viewed." % action)
        self.assertEqual(self.packet["timing_class_balance"], {"premarket": ["love-m5b-2026-06-11"], "after_hours": [i for i in IDS if i != "love-m5b-2026-06-11"]})

    def test_the_identity_evidence_is_the_archive_the_milestone_1_events_and_the_review_and_no_event_has_a_listing_item(self):
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
                self.assertEqual(entry["corporate_actions"]["sec_8k_items"], "No Item 3.03 or 5.03 8-K in the archived history up to the window end.")
        self.assertEqual(flagged, {})

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
                    accepted = datetime.fromisoformat(r["acceptanceDateTime"].replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")
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
                self.assertEqual([c["labels"] for c in caveats], [f["labels_whose_windows_it_falls_inside"] for f in inside])
                for caveat, filing in zip(caveats, inside):
                    self.assertIn("8-K %s filed %s ET (Items %s) inside the window; content not opened." % (filing["accession"], filing["accepted_et"], ", ".join(filing["items"])), caveat["note"])
                    self.assertIn("Policy: a caveat, not an exclusion (docs/SAME-DAY-COMPETING-CATALYST-POLICY.md; the Milestone 1 OKTA precedent).", caveat["note"])
                    self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES)
        by_event = {e["event_id"]: [(f["filing_date"], f["items"]) for f in e["competing_catalysts_inside_window"]] for e in self.packet["events"]}
        self.assertEqual({k: v for k, v in by_event.items() if v}, {"okta-m5b-2026-05-28": [("2026-06-23", ["5.02", "5.07", "9.01"])], "love-m5b-2026-06-11": [("2026-06-15", ["5.02", "9.01"])], "nbix-m5b-2026-07-30": [("2026-07-31", ["9.01"])],
                                                                    "parr-m5b-2026-08-04": [("2026-08-25", ["7.01", "8.01", "9.01"])], "cxt-m5b-2026-08-05": [("2026-08-11", ["7.01"])]})
        before = {e["event_id"]: [(f["filing_date"], f["items"]) for f in e["filings_in_the_three_days_before_the_release"]] for e in self.packet["events"]}
        self.assertEqual({k: v for k, v in before.items() if v}, {"love-m5b-2026-06-11": [("2026-06-09", ["5.07", "9.01"])], "hurn-m5b-2026-07-28": [("2026-07-27", ["5.02"])]})
        nbix = next(e for e in self.packet["events"] if e["ticker"] == "NBIX")["competing_catalysts_inside_window"][0]
        self.assertEqual((nbix["form"], nbix["labels_whose_windows_it_falls_inside"]), ("8-K/A", ["session_10_close_return", "session_20_close_return", "session_2_close_return", "session_5_close_return"]))

    def test_no_spec_carries_a_caveat_yet_and_the_dry_run_facts_are_the_dry_run_records(self):
        view = self.dry["sealed_view"]["events"]
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                self.assertNotIn("caveats", self.by_id[entry["event_id"]])                           # the dry-run state: the signoff carries the packet's caveats into the attested specs
                sealed = view[entry["event_id"]]
                self.assertEqual(entry["corporate_actions"]["sealed_dry_run"], {"corporate_actions": sealed["corporate_actions"], "state": "QUARANTINED", "reasons": ["FIRST_PUBLIC_TIME_UNVERIFIED"]})
        cxt = next(e for e in self.packet["events"] if e["event_id"] == CXT)
        self.assertEqual(cxt["corporate_actions"]["sealed_dry_run"]["corporate_actions"], [{"ex_date": "2026-08-31", "id": "6c4c5bfd-242f-42e0-8f31-61d12a1783ad", "type": "cash_dividends"}])
        self.assertEqual([c["labels"] for c in cxt["proposed_label_caveats"]], [["session_10_close_return", "session_20_close_return", "session_5_close_return"]])

    def test_it_puts_no_call_to_the_owner_and_says_what_a_signoff_is_and_is_not(self):
        self.assertEqual(self.packet["decisions_needed"], {})
        items = self.packet["signoff_items_requested"]
        self.assertIn("the full cover rows were not re-read, to keep to the batch 3 permission", items["first_public_time_and_historical_identity"])
        self.assertIn("(CXT one cash dividend, the other nine none)", items["corporate_actions"])
        self.assertEqual((self.packet["kind"], self.packet["prepared_on"]), ("m5_phase1b_batch3_signoff_packet", "2026-10-13"))
        self.assertEqual(self.packet["dry_run"], {"record": "reports/m5-phase1b-batch3-dry-run-2026-10-13.json", "workflow": "M5 Phase 1b sealed event acquisition", "run_id": 38418113326, "commit": self.dry["run"]["commit"],
                                                  "result": "All ten events ran with no attestation and quarantined on FIRST_PUBLIC_TIME_UNVERIFIED with every session present and none at zero volume; CXT listed one cash dividend and the other nine no corporate action; "
                                                            "the nineteen pins of batches 1 and 2 matched again."})
        self.assertEqual(self.packet["dry_run"]["commit"], COMMIT)
        for phrase in ("No event carries a call for the owner this time (decisions_needed is empty): the identity check found no listing or charter item in any of the ten histories, and no separate same-day release was found.",
                       "The packet proposes label caveats for five filings inside windows and records one cash dividend (CXT).",
                       "Nothing here is an acceptance: every event stays quarantined, and no label is computed, until the owner's attestations are added."):
            self.assertIn(phrase, self.packet["purpose"])
        self.assertEqual(self.packet["what_a_sign_off_would_look_like"], "For example: 'attest the ten', or 'attest the nine and hold CXT', or a list of event_ids. Then the attestations are added for those events, "
                                                                          "the sealed workflow runs for real (the push of the events file), and each event's commitment is pinned.")
        for phrase in ("Not an attestation of any event.", "Not Phase 1b acceptance.", "content was not opened for any in-window filing", "No return, price or label was computed or viewed."):
            self.assertIn(phrase, " ".join(self.packet["not_a_claim"]))
        self.assertTrue((ROOT / "docs" / "SAME-DAY-COMPETING-CATALYST-POLICY.md").is_file())
        notes = {e["event_id"]: e["additional_note"] for e in self.packet["events"]}
        self.assertEqual(notes["okta-m5b-2026-05-28"], "1 other 8-K(s) sit inside the window (2026-06-23 Items 5.02,5.07,9.01); their content was not opened. "
                                                       "Okta's next earnings release, on 2026-08-26, is outside this window (it ends 2026-06-26) and is a candidate of a later batch.")
        first_window = ea.event_window(self.by_id["vsat-m5b-2026-05-28"], self.calendar)["required_sessions"]
        second_window = ea.event_window(self.by_id["vsat-m5b-2026-08-04"], self.calendar)["required_sessions"]
        self.assertEqual((first_window[-1], second_window[0]), ("2026-06-26", "2026-08-04"))
        self.assertLess(first_window[-1], second_window[0])                                          # VSAT's two windows do not overlap
        self.assertEqual(notes["vsat-m5b-2026-05-28"], "No other 8-K inside the window. VSAT's other batch 3 event (2026-08-04) has a window that starts 2026-08-04, after this window ends (2026-06-26), so the two windows do not overlap.")
        self.assertEqual(notes["love-m5b-2026-06-11"], "1 other 8-K(s) sit inside the window (2026-06-15 Items 5.02,9.01); their content was not opened. "
                                                       "An Item 5.07 8-K was filed 2026-06-09 16:49 ET, two days before the release; its first affected session (2026-06-10) is on or before the anchor session, so it falls inside no label's window.")
        self.assertEqual(notes["hurn-m5b-2026-07-28"], "No other 8-K inside the window. An Item 5.02 8-K was filed 2026-07-27 21:29 ET, the evening before the release; its first affected session (2026-07-28) is the anchor session, so it falls inside no label's window.")
        self.assertEqual(notes["alkt-m5b-2026-07-29"], "No other 8-K inside the window.")
        self.assertEqual(notes["nbix-m5b-2026-07-30"], "1 other 8-K(s) sit inside the window (2026-07-31 Items 9.01); their content was not opened. "
                                                       "The only filing inside the window is an 8-K/A (Item 9.01) filed the evening after the release; an amendment, content not opened.")
        self.assertEqual(notes["parr-m5b-2026-08-04"], "1 other 8-K(s) sit inside the window (2026-08-25 Items 7.01,8.01,9.01); their content was not opened. The release came at 16:53 ET, later than this issuer's usual minute, "
                                                       "and the 8-K carries the filing date 2026-08-05 although it was accepted at 21:37 ET on 2026-08-04, after the release.")
        self.assertEqual(notes["vsat-m5b-2026-08-04"], "No other 8-K inside the window. VSAT's other batch 3 event (2026-05-28) has a window that ends 2026-06-26, before this window starts (2026-08-04).")
        self.assertEqual(notes["caci-m5b-2026-08-05"], "No other 8-K inside the window.")
        self.assertEqual(notes[CXT], "1 other 8-K(s) sit inside the window (2026-08-11 Items 7.01); their content was not opened. A cash dividend with ex-date 2026-08-31 falls inside session_20's window only "
                                     "(the engine suppresses that one label); the 2026-08-11 Item 7.01 filing sits inside the window.")


if __name__ == "__main__":
    unittest.main()
