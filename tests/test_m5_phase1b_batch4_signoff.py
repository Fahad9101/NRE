"""Milestone 5 Phase 1b batch 4 after its sealed dry run: the dry-run record (reports/m5-phase1b-batch4-dry-run-2026-10-14.json) is the sealed view and nothing else, and the signoff packet (reports/m5-phase1b-batch4-signoff-packet-2026-10-14.json) is recomputed
here from the events file, the sources record, the archived SEC lists, the Milestone 1 events, the review table and the calendar: release facts, identity evidence (ACHV's Item 5.03 filing is the one listing or charter item in the nine), the in-window filings and
the labels each can touch, the filings of the three days before each release, the proposed caveats, the absence of any corporate action, and the two calls to the owner (ACHV's filing, ASMB's release at the bell)."""
import json
import re
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
DRY = ROOT / "reports" / "m5-phase1b-batch4-dry-run-2026-10-14.json"
PACKET = ROOT / "reports" / "m5-phase1b-batch4-signoff-packet-2026-10-14.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
EARLIER_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07",
               "payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21",
               "okta-m5b-2026-05-28", "vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "hurn-m5b-2026-07-28", "alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "caci-m5b-2026-08-05", "cxt-m5b-2026-08-05"]
IDS = ["aspn-m5b-2026-08-06", "coll-m5b-2026-08-06", "pdfs-m5b-2026-08-06", "real-m5b-2026-08-06", "tecx-m5b-2026-08-06", "ttwo-m5b-2026-08-07", "achv-m5b-2026-08-11", "klc-m5b-2026-08-13", "lnsr-m5b-2026-08-13"]
ACHV = "achv-m5b-2026-08-11"
COMMIT = "a0ce7acfe6d6693a74881d4e584eb172d35b7b79"


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
    def test_the_sealed_view_is_the_thirty_eight_events_and_holds_only_what_the_seal_allows(self):
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
                         [("1/9", True, "notice", 4), ("2/9", True, "notice", 3), ("3/9", True, "notice", 4), ("4/9", True, "notice", 4), ("5/9", True, "notice", 4), ("6/9", True, "notice", 4), ("7/9", True, "notice", 4),
                          ("8/9", True, "notice", 5), ("9/9", True, "notice", 6)])
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(EARLIER_IDS + IDS))

    def test_the_nine_quarantine_as_a_dry_run_should_and_the_twenty_nine_pins_matched_again(self):
        events = self.dry["sealed_view"]["events"]
        for event_id in IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_sha256"], view["session_labels"], view["labels_match_recorded"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], None, None, None))
                self.assertEqual(view["corporate_actions"], [])
        for event_id in EARLIER_IDS:
            view = events[event_id]
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_match_recorded"]), ("MAPPED", [], True))
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
        self.assertEqual({k: v["corporate_actions"] for k, v in events.items() if k in EARLIER_IDS and v["corporate_actions"]},
                         {"jbss-m5b-2026-04-29": [{"ex_date": "2026-04-27", "id": "1b6fa9d4-9120-4ce8-946e-700cfe8d9d2a", "type": "cash_dividends"}],
                          "nbix-m5b-2026-05-05": [{"date_field": "effective_date", "ex_date": "2026-05-18", "id": "b8d80b2b-b0e2-4be3-b612-9325d12d1646", "type": "cash_mergers"}],
                          "cxt-m5b-2026-05-06": [{"ex_date": "2026-05-29", "id": "0a5b1554-acfa-4836-9775-8f007fcba86b", "type": "cash_dividends"}],
                          "cxt-m5b-2026-08-05": [{"ex_date": "2026-08-31", "id": "6c4c5bfd-242f-42e0-8f31-61d12a1783ad", "type": "cash_dividends"}]})       # the four earlier events that list an action still list exactly it
        self.assertEqual(self.dry["summary"], {"events_run": 38, "pins_checked": 29, "pins_that_matched": 29, "pins_that_differed": 0, "batch_4_events": 9, "batch_4_quarantined_for_want_of_an_attestation": 9, "errored": {},
                                               "batch_4_events_with_missing_or_zero_volume_sessions": 0, "batch_4_events_with_a_corporate_action": 0, "required_sessions_per_event": 21})
        self.assertEqual((self.dry["kind"], self.dry["recorded_on"]), ("m5_phase1b_batch4_dry_run", "2026-10-14"))

    def test_the_runs_are_pinned_and_it_says_what_it_is_and_what_it_is_not(self):
        dry, run = self.dry, self.dry["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"]),
                         ("M5 Phase 1b sealed event acquisition", 11, 38581973492, 115913924328, COMMIT, "success"))
        self.assertEqual(run["trigger"], "the push of a0ce7ac (c709280..a0ce7ac); config/m5-phase1b-events.json changed in it")
        self.assertEqual(run["created_at"], "2026-10-14T14:36:07Z")
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertIn("the job log was not read", dry["how_it_was_read"])
        self.assertIn("(nine sealed parts)", dry["how_it_was_read"])
        other = dry["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 256, "run_id": 38581973519, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 115913924894, "conclusion": "success"}, "validate (3.13)": {"job_id": 115913924098, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        self.assertIn("config/m5-phase1b-events.json as pushed in a0ce7ac, which holds the twenty-nine attested and pinned events of batches 1 to 3 followed by batch 4's nine events in the dry-run state", dry["what_this_is"])
        self.assertIn("no commitment for batch 4 (an unattested event computes no labels)", dry["what_this_is"])
        self.assertIn("ASMB's release at the bell is not an event and is not in it.", dry["what_this_is"])
        self.assertIn("No label value, price, return, day-1 or gap label exists in it.", dry["what_this_is"])
        text = " ".join(dry["findings"])
        for phrase in ("All nine batch 4 events are QUARANTINED on FIRST_PUBLIC_TIME_UNVERIFIED, as a dry run should be", "all 21 required sessions are present, none has zero volume, and Alpaca lists no corporate action for any of the nine over its window.",
                       "No batch 4 event errored, so there is no pipeline question this time: the merger-dating change of ac370f9 was not needed by any of them.",
                       "The twenty-nine pins of batches 1 to 3 were checked again and all twenty-nine report labels_match_recorded true with the commitments of the earlier runs; nothing about them changed."):
            self.assertIn(phrase, text)
        nots = " ".join(dry["not_a_claim"])
        for phrase in ("Not an attestation of any event.", "Not a label, a price or a return: the sealed view holds none, and none was read.", "Not a finding that a batch 4 event is eligible"):
            self.assertIn(phrase, nots)


class SignoffPacketTests(Base):
    def test_its_events_are_batch_4s_and_the_sources_record(self):
        sources = {r["event_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-batch4-sources-2026-10-14.json")["events"]}
        self.assertEqual([e["event_id"] for e in self.packet["events"]], IDS)
        self.assertEqual([e["event_id"] for e in self.spec["events"][29:]], IDS)
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
                self.assertEqual(entry["data_availability"], "All 21 required sessions present; no zero-volume session; no corporate action in the window (the sealed dry run, workflow run 38581973492). No return was computed or viewed.")
                self.assertTrue(row["edgar_acceptance_et"][:10] > event["published_at"][:10] or row["edgar_acceptance_et"][11:] >= row["minute_et"])
        self.assertEqual(self.packet["timing_class_balance"], {"premarket": ["aspn-m5b-2026-08-06", "coll-m5b-2026-08-06", "ttwo-m5b-2026-08-07", ACHV, "lnsr-m5b-2026-08-13"],
                                                               "after_hours": ["pdfs-m5b-2026-08-06", "real-m5b-2026-08-06", "tecx-m5b-2026-08-06", "klc-m5b-2026-08-13"]})

    def test_no_issuers_events_share_a_session_across_the_thirty_eight(self):
        spans = {}
        for event in self.spec["events"]:
            window = ea.event_window(event, self.calendar)
            spans.setdefault(event["security"]["ticker"], []).append((window["required_sessions"][0], window["required_sessions"][-1], event["event_id"]))
        self.assertEqual(len(sum(spans.values(), [])), 38)
        for ticker, rows in spans.items():
            rows.sort()
            for earlier, later in zip(rows, rows[1:]):
                with self.subTest(issuer=ticker):
                    self.assertLess(earlier[1], later[0])

    def test_the_identity_evidence_is_the_archive_the_milestone_1_events_and_the_review_and_only_achv_has_a_charter_item(self):
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
                if not charter:
                    expected = "No Item 3.03 or 5.03 8-K in the archived history up to the window end."
                else:
                    self.assertTrue(all("3.03" not in r["items"].split(",") for r in charter))                       # the sentence says there is no Item 3.03 8-K
                    expected = ("No Item 3.03 8-K in the archived history up to the window end. An Item 5.03 8-K sits before the release (%s): SEE the item listed under identity_evidence and decisions_needed."
                                % ", ".join("%s filed %s ET, Items %s" % (r["accessionNumber"], self.accepted(r), r["items"]) for r in charter))
                self.assertEqual(entry["corporate_actions"]["sec_8k_items"], expected)
        self.assertEqual(flagged, {ACHV: ["2026-07-06 5.03,5.07,9.01"]})

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
                identity_caveats = [c for c in caveats if c["labels"] == ["all"]]
                self.assertEqual(len(identity_caveats), 1 if entry["event_id"] == ACHV else 0)               # only ACHV's earlier Item 5.03 filing travels with every label
                window_caveats = [c for c in caveats if c["labels"] != ["all"]]
                self.assertEqual([c["labels"] for c in window_caveats], [f["labels_whose_windows_it_falls_inside"] for f in inside])
                for caveat, filing in zip(window_caveats, inside):
                    self.assertIn("8-K %s filed %s ET (Items %s) inside the window; content not opened." % (filing["accession"], filing["accepted_et"], ", ".join(filing["items"])), caveat["note"])
                    self.assertIn("Policy: a caveat, not an exclusion (docs/SAME-DAY-COMPETING-CATALYST-POLICY.md; the Milestone 1 OKTA precedent).", caveat["note"])
                    self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES)
        by_event = {e["event_id"]: [(f["filing_date"], f["items"]) for f in e["competing_catalysts_inside_window"]] for e in self.packet["events"]}
        self.assertEqual({k: v for k, v in by_event.items() if v}, {"coll-m5b-2026-08-06": [("2026-08-13", ["8.01"])], ACHV: [("2026-08-14", ["8.01", "9.01"])], "klc-m5b-2026-08-13": [("2026-08-14", ["1.01", "9.01"])]})
        before = {e["event_id"]: [(f["filing_date"], f["items"], f["accepted_et"], f["first_session_it_can_affect"]) for f in e["filings_in_the_three_days_before_the_release"]] for e in self.packet["events"]}
        self.assertEqual({k: v for k, v in before.items() if v}, {"lnsr-m5b-2026-08-13": [("2026-08-10", ["5.07"], "2026-08-10 16:05", "2026-08-11")]})
        labels = {e["event_id"]: e["competing_catalysts_inside_window"][0]["labels_whose_windows_it_falls_inside"] for e in self.packet["events"] if e["competing_catalysts_inside_window"]}
        self.assertEqual(labels, {"coll-m5b-2026-08-06": ["session_10_close_return", "session_20_close_return"], ACHV: ["session_10_close_return", "session_20_close_return", "session_5_close_return"],
                                  "klc-m5b-2026-08-13": ["session_10_close_return", "session_20_close_return", "session_2_close_return", "session_5_close_return"]})

    def test_the_packets_caveats_are_the_specs_and_the_dry_run_facts_are_the_dry_run_records(self):
        view = self.dry["sealed_view"]["events"]
        for entry in self.packet["events"]:
            with self.subTest(event=entry["event_id"]):
                event = self.by_id[entry["event_id"]]
                self.assertEqual(event.get("caveats", []), entry["proposed_label_caveats"] or [])      # the signoff carried the packet's caveats into each attested spec, in the packet's order
                self.assertIn("attestations", event)
                self.assertIn("recorded_result", event)                                              # and each commitment was pinned after the attested sealed run printed it (tests/test_m5_phase1b_batch4_sealed_run.py)
                sealed = view[entry["event_id"]]
                self.assertEqual(entry["corporate_actions"]["sealed_dry_run"], {"corporate_actions": sealed["corporate_actions"], "state": "QUARANTINED", "reasons": ["FIRST_PUBLIC_TIME_UNVERIFIED"]})
                self.assertEqual(sealed["corporate_actions"], [])
                for caveat in entry["proposed_label_caveats"] or []:
                    self.assertTrue(set(caveat["labels"]) <= ea.LABEL_NAMES or caveat["labels"] == ["all"])
        achv = next(e for e in self.packet["events"] if e["event_id"] == ACHV)
        self.assertEqual([c["labels"] for c in achv["proposed_label_caveats"]], [["all"], ["session_10_close_return", "session_20_close_return", "session_5_close_return"]])
        klc = next(e for e in self.packet["events"] if e["event_id"] == "klc-m5b-2026-08-13")
        self.assertEqual([c["labels"] for c in klc["proposed_label_caveats"]], [["session_10_close_return", "session_20_close_return", "session_2_close_return", "session_5_close_return"]])
        # the Item 1.01 precedent the KLC note cites is in the earlier specs
        for event_id in ("alkt-m5b-2026-04-29", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05"):
            self.assertTrue(any("Items 1.01" in c["note"] for c in self.by_id[event_id]["caveats"]), event_id)

    def test_achvs_item_5_03_filing_is_the_archive_and_its_caveat_and_call_say_what_was_and_was_not_read(self):
        rows = [r for r in self.history["ACHV"] if "5.03" in r["items"].split(",")]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["form"], row["filingDate"], row["items"], self.accepted(row)), ("8-K", "2026-07-06", "5.03,5.07,9.01", "2026-07-06 20:06"))
        window = ea.event_window(self.by_id[ACHV], self.calendar)
        self.assertLess(row["filingDate"], window["required_sessions"][0])                          # before the window starts
        days = (date.fromisoformat("2026-08-11") - date.fromisoformat(row["filingDate"])).days
        self.assertEqual(days, 36)
        ledger = {c["candidate_id"] for c in load(ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json")["candidates"]}
        self.assertNotIn(row["accessionNumber"], ledger)                                             # not one of the 47 candidates' filings: its content was not opened
        review = {r["candidate_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]}
        cover = review[self.by_id[ACHV]["candidate_id"]]["exchange_on_cover_or_release"]
        self.assertEqual(cover, "Nasdaq Stock Market LLC")
        security = ("company_id", "cik", "ticker", "exchange", "security_type")
        m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}
        shapes = {tuple(s[k] for k in security) for s in (m1["ACHV"]["security"], self.by_id["achv-m5b-2026-05-12"]["security"], self.by_id[ACHV]["security"])}
        self.assertEqual(shapes, {("0000949858", "0000949858", "ACHV", "NASDAQ", "common_stock")})   # the Milestone 1 event, batch 2's event and this one name the same security
        entry = next(e for e in self.packet["events"] if e["event_id"] == ACHV)
        self.assertEqual(entry["proposed_label_caveats"][0], {"labels": ["all"], "note": (
            "8-K %s filed 2026-07-06 20:06 ET with Items 5.03, 5.07 and 9.01 (Item 5.03: amendments to the articles of incorporation or bylaws; Item 5.07: matters submitted to a vote of security holders), 36 days before the release and before the window starts; content not opened. "
            "The event filing's cover still records the exchange as 'Nasdaq Stock Market LLC' on the release date, and Alpaca lists no corporate action over the window. A caveat, not an exclusion." % row["accessionNumber"])})
        call = self.packet["decisions_needed"][ACHV]
        for phrase in ("ACHV's archived 8-K history has a filing with Item 5.03 (the item for amendments to the articles of incorporation or bylaws), together with Item 5.07 (matters submitted to a vote of security holders) and Item 9.01: %s, filed 2026-07-06 20:06 ET, "
                       "36 days before the 2026-08-11 release and before the window starts (2026-08-10)." % row["accessionNumber"],
                       "I did not open it: it is not one of the 47 candidates' filings, and the batch 4 permission was for wire pages only.",
                       "Items 5.03 and 5.07 together could report a shareholder vote on a charter amendment (an increase in authorized shares, a name change, a reverse split), but that is an inference from the item numbers, not something I have read.",
                       "records the exchange as 'Nasdaq Stock Market LLC' on the release date, the spec's identity (the CIK, ACHV, common stock, NASDAQ) is the one Milestone 1's ACHV event and batch 2's ACHV event name,",
                       "the sealed dry run reports all 21 sessions of the window present and none at zero volume under that ticker, and Alpaca lists no corporate action over the window, so no split or other action falls inside it.",
                       "The identity check found no other listing or charter item in the nine."):
            self.assertIn(phrase, call["finding"])
        self.assertEqual(call["options"], ["Attest ACHV with the caveat on all labels proposed in its entry (the filing travels with the labels; content not opened).",
                                           "Hold ACHV until I have read that one 8-K: it needs your permission to read one SEC filing (I would give its name, source and size when asking).",
                                           "Leave ACHV quarantined for now, or exclude it."])
        self.assertEqual(call["assistant_recommendation"], "Attest it with the caveat: the policy treats an item like this as a caveat, not an exclusion (REKR's Item 3.01 filing of batch 2 was handled the same way), and nothing I can show touches the window; "
                                                           "the filing is before it, the cover shows the listing unchanged at the release and Alpaca lists no action. The owner may prefer to have the filing read first.")
        rekr = self.by_id["rekr-m5b-2026-05-11"]["caveats"][0]                                       # the precedent the recommendation cites
        self.assertEqual(rekr["labels"], ["all"])
        self.assertIn("Item 3.01", rekr["note"])
        self.assertIn("A caveat, not an exclusion.", rekr["note"])

    def test_asmbs_release_at_the_bell_is_the_calendar_and_the_sources_record_and_the_precedent_is_the_owners_word(self):
        sources = load(ROOT / "reports" / "m5-phase1b-batch4-sources-2026-10-14.json")["quarantined_before_the_spec"]
        self.assertEqual((sources["ticker"], sources["candidate_id"], sources["displayed_stamp"], sources["page_machine_readable_time"], sources["edgar_acceptance_et"]),
                         ("ASMB", "0001193125-26-352193", "August 13, 2026 16:00 ET", "2026-08-13T20:00:00Z", "2026-08-14 16:05"))
        self.assertEqual(self.calendar.classify(sources["page_machine_readable_time"])[1], "bell_ambiguous")
        self.assertNotIn("asmb-m5b-2026-08-13", self.by_id)                                          # no spec was built for it
        decisions = load(ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json")["effects"]["ASMB 2026-08-14"]
        self.assertEqual((decisions["candidate_id"], decisions["disposition"]), ("0001193125-26-352193", "kept_with_caveat"))
        first = load(ROOT / "reports" / "m5-phase1b-batch1-signoff-2026-10-09.json")
        asmb = next(q for q in first["questions_and_answers"] if q["header"] == "ASMB 05-07")
        self.assertEqual(asmb["owner_selected"], "Leave it quarantined (Recommended)")
        call = self.packet["decisions_needed"]["asmb-2026-08-13"]
        for phrase in ("ASMB's second-quarter release was made at exactly 16:00 ET (GlobeNewswire, displayed August 13, 2026 16:00 ET, machine-readable 2026-08-13T20:00:00Z), the regular-session close: nre/calendar.py's classify() returns bell_ambiguous for the instant of the close, "
                       "which event_acquire.validate_spec() does not accept at minute precision, so no event spec can be built.",
                       "ASMB 2026-05-07 was left quarantined, not excluded, for the same reason on the owner's word (reports/m5-phase1b-batch1-signoff-2026-10-09.json), as were Milestone 1's GALT and step 2's PDFS 2025-08-07.",
                       "The candidate for this release is the 8-K/A 0001193125-26-352193 (accepted 2026-08-14 16:05 ET, the next day), which the owner kept with a caveat in the S2 decisions as the filing that stands for the 2026-08-13 release; "
                       "the original 8-K (0001193125-26-349198, Items 2.01,9.01, accepted 2026-08-13 16:11 ET) is not a candidate.",
                       "That earlier decision does not settle the timing question. The same disposition is proposed here."):
            self.assertIn(phrase, call["finding"])
        self.assertEqual(call["options"], ["Leave it quarantined, not excluded (the precedent).", "Exclude it."])
        self.assertEqual(call["assistant_recommendation"], "Leave it quarantined.")

    def test_it_puts_two_calls_to_the_owner_and_says_what_a_signoff_is_and_is_not(self):
        self.assertEqual(sorted(self.packet["decisions_needed"]), [ACHV, "asmb-2026-08-13"])
        items = self.packet["signoff_items_requested"]
        self.assertEqual(items, {
            "first_public_time_and_historical_identity": "Accept the release time (the wire page's displayed minute, confirmed by the page's own machine-readable time) and the identity evidence per event below, including the residual gap that open-web research cannot close "
                                                         "(an earlier disclosure with no public trace). The identity evidence is the exchange the S2 review recorded from the event filing's cover or the release, the previous Milestone 1 event and the archived 8-K history; "
                                                         "the full cover rows were not re-read, to keep to the batch 4 permission.",
            "corporate_actions": "Accept two signals: no Item 3.03 or 5.03 8-K in the archived history up to the window end (except ACHV's Item 5.03 filing of 2026-07-06, which is decisions_needed), "
                                 "and Alpaca's real answer as the sealed dry run reported it (no corporate action for any of the nine)."})
        self.assertEqual((self.packet["kind"], self.packet["prepared_on"]), ("m5_phase1b_batch4_signoff_packet", "2026-10-14"))
        self.assertEqual(self.packet["dry_run"], {"record": "reports/m5-phase1b-batch4-dry-run-2026-10-14.json", "workflow": "M5 Phase 1b sealed event acquisition", "run_id": 38581973492, "commit": self.dry["run"]["commit"],
                                                  "result": "All nine events ran with no attestation and quarantined on FIRST_PUBLIC_TIME_UNVERIFIED with every session present and none at zero volume; none lists a corporate action; "
                                                            "the twenty-nine pins of batches 1 to 3 matched again."})
        self.assertEqual(self.packet["dry_run"]["commit"], COMMIT)
        for phrase in ("nine events built from the next ten releases that stand (reports/m5-phase1b-batch4-permission-2026-10-14.json; the tenth, ASMB's, was released at the bell and has no spec)",
                       "Two things carry a call for the owner (decisions_needed): ACHV, whose history has an Item 5.03 8-K 36 days before the release, and ASMB's release at the bell.",
                       "The packet proposes label caveats for three filings inside windows and one for ACHV's earlier filing, and records no corporate action for any of the nine.",
                       "Nothing here is an acceptance: every event stays quarantined, and no label is computed, until the owner's attestations are added."):
            self.assertIn(phrase, self.packet["purpose"])
        self.assertEqual(self.packet["what_a_sign_off_would_look_like"], "For example: 'attest the nine' (keeping ACHV with its caveat, and ASMB's release quarantined), or 'attest the eight and hold ACHV', or a list of event_ids, with a word on ASMB. "
                                                                          "Then the attestations are added for those events, the sealed workflow runs for real (the push of the events file), and each event's commitment is pinned.")
        for phrase in ("Not an attestation of any event.", "Not Phase 1b acceptance.", "content was not opened for any in-window filing or for ACHV's earlier one", "No return, price or label was computed or viewed."):
            self.assertIn(phrase, " ".join(self.packet["not_a_claim"]))
        self.assertTrue((ROOT / "docs" / "SAME-DAY-COMPETING-CATALYST-POLICY.md").is_file())
        notes = {e["event_id"]: e["additional_note"] for e in self.packet["events"]}
        self.assertEqual(notes["aspn-m5b-2026-08-06"], "No other 8-K inside the window. EDGAR's acceptance of the 8-K (06:30 ET) is the same minute as the wire's, not earlier.")
        self.assertEqual(notes["coll-m5b-2026-08-06"], "1 other 8-K(s) sit inside the window (2026-08-13 Items 8.01); their content was not opened.")
        self.assertEqual(notes["pdfs-m5b-2026-08-06"], "No other 8-K inside the window. Released at 16:02 ET, two minutes after the close, and classed after_hours by the calendar: it is not at the bell.")
        self.assertEqual(notes["real-m5b-2026-08-06"], "No other 8-K inside the window. The second-quarter release is on PR Newswire (16:07 ET); the first-quarter release was on GlobeNewswire.")
        self.assertEqual(notes["tecx-m5b-2026-08-06"], "No other 8-K inside the window. Released at 16:01 ET, one minute after the close, and classed after_hours by the calendar: it is not at the bell.")
        self.assertEqual(notes["ttwo-m5b-2026-08-07"], "No other 8-K inside the window. The release is stamped 2026-08-07 07:30 ET by the page and its machine-readable time, a premarket release before the 8:00 a.m. call; "
                                                       "the page's address carries 2026-08-06. This issuer's two earlier events in the repository were after the close (2026-02-03 16:05 ET and 2026-05-21 16:05 ET), so a premarket release is a change of pattern; "
                                                       "the page's machine-readable time, the call 'today at 8:00 a.m.' on the issuer's own investor page and EDGAR's acceptance at 11:37 ET (not before the wire's minute) are consistent with it.")
        self.assertEqual(notes[ACHV], "1 other 8-K(s) sit inside the window (2026-08-14 Items 8.01,9.01); their content was not opened. The release came at 08:30 ET, later than this issuer's two earlier events in the repository "
                                      "(07:00 ET on 2026-03-24 and 2026-05-12); it is premarket either way and the page's machine-readable time agrees. An 8-K with Items 5.03, 5.07 and 9.01 filed 2026-07-06 20:06 ET, "
                                      "36 days before the release and before the window starts, is flagged by the identity check: see decisions_needed. "
                                      "The 8-K of 2026-08-14 (Items 8.01, 9.01) was accepted at 20:09 ET, after the close, so its first affected session is 2026-08-17.")
        # the usual minutes the two notes compare with are the earlier events' (Milestone 1's and batch 2's), and the wire pages' machine-readable times agree with the stamps
        m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}
        sources = {r["event_id"]: r for r in load(ROOT / "reports" / "m5-phase1b-batch4-sources-2026-10-14.json")["events"]}
        self.assertEqual([m1["TTWO"]["published_at"], self.by_id["ttwo-m5b-2026-05-21"]["published_at"]], ["2026-02-03T16:05:00-05:00", "2026-05-21T16:05:00-04:00"])
        self.assertEqual([m1["ACHV"]["published_at"], self.by_id["achv-m5b-2026-05-12"]["published_at"]], ["2026-03-24T07:00:00-04:00", "2026-05-12T07:00:00-04:00"])
        self.assertEqual(datetime.fromisoformat(sources["ttwo-m5b-2026-08-07"]["page_machine_readable_time"]), datetime.fromisoformat(self.by_id["ttwo-m5b-2026-08-07"]["published_at"]))
        self.assertEqual(datetime.fromisoformat(sources[ACHV]["page_machine_readable_time"].replace("Z", "+00:00")), datetime.fromisoformat(self.by_id[ACHV]["published_at"]))
        self.assertEqual(notes["klc-m5b-2026-08-13"], "1 other 8-K(s) sit inside the window (2026-08-14 Items 1.01,9.01); their content was not opened. The release came at 16:15 ET, so the reaction session is the next day (2026-08-14). "
                                                      "The 8-K inside the window carries Item 1.01 (entry into a material definitive agreement) and was filed at 17:00 ET on 2026-08-14, after that session's close, so it can first affect 2026-08-17, the second reaction session; "
                                                      "ALKT's, NBIX's and PARR's Item 1.01 filings in batch 1 were caveats too.")
        self.assertEqual(notes["lnsr-m5b-2026-08-13"], "No other 8-K inside the window. An Item 5.07 8-K was filed 2026-08-10 16:05 ET, three days before the release; its first affected session (2026-08-11) is on or before the anchor session, "
                                                       "so it falls inside no label's window.")
        # the near-the-bell notes are the calendar's: 16:02 and 16:01 are after the close, not at it
        for event_id in ("pdfs-m5b-2026-08-06", "tecx-m5b-2026-08-06"):
            self.assertEqual(self.calendar.classify(self.by_id[event_id]["published_at"])[1], "after_hours")


if __name__ == "__main__":
    unittest.main()
