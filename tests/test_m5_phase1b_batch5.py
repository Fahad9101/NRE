"""Milestone 5 Phase 1b batch 5, the last: the owner's permission to read the five releases' wire pages (reports/m5-phase1b-batch5-permission-2026-10-15.json) is quoted as given and the five are recomputed from the S2 records; five events, appended to
config/m5-phase1b-events.json after the thirty-eight of batches 1 to 4 (sealed; attested on the owner's signoff, tests/test_m5_phase1b_batch5_attestations.py; pinned from the attested sealed run, tests/test_m5_phase1b_batch5_sealed_run.py), validate with the project's own spec validation and agree with the frozen ledger, the eligibility review, the Milestone 1 events, the calendar and the wire evidence in
reports/m5-phase1b-batch5-sources-2026-10-15.json (each page's machine-readable time converts to the minute taken from it; EDGAR's acceptance time is recomputed from the archived SEC lists); none was made at the bell, which the calendar confirms; their dry-run state is recoverable
byte for byte; and a sealed run of the five with injected prices quarantines every one once the attestations are taken out, maps every one once the pins are taken out too, shows each pin catching the injected prices as shipped, and prints no price."""
import hashlib
import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "config" / "m5-phase1b-events.json"
SOURCES = ROOT / "reports" / "m5-phase1b-batch5-sources-2026-10-15.json"
PERMISSION = ROOT / "reports" / "m5-phase1b-batch5-permission-2026-10-15.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
# (ticker, the release's date, the 8-K's filing date); SLSN's 8-K was filed the day after its release
BATCH_5 = [("REKR", "2026-08-13", "2026-08-13"), ("JBSS", "2026-08-19", "2026-08-19"), ("SLSN", "2026-08-19", "2026-08-20"), ("OKTA", "2026-08-26", "2026-08-26"), ("LOVE", "2026-09-10", "2026-09-10")]
BATCH_5_IDS = ["%s-m5b-%s" % (ticker.lower(), day) for ticker, day, _ in BATCH_5]
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class PermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(PERMISSION)
        cls.review = load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]
        cls.decisions = load(ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json")
        cls.earlier = {n: load(ROOT / "reports" / name) for n, name in ((2, "m5-phase1b-batch2-permission-2026-10-10.json"), (3, "m5-phase1b-batch3-permission-2026-10-10.json"), (4, "m5-phase1b-batch4-permission-2026-10-14.json"))}

    def test_the_message_the_question_and_the_answer_are_quoted_as_given(self):
        record = self.record
        self.assertEqual(record["owner_message"], {"text": "authorize batch 5", "at": "2026-10-15T09:51:12.054Z", "source": "session transcript, line 48416",
                                                   "read_as": "The go-ahead to ask the question about batch 5, as the report offered; it is not itself the permission to read pages."})
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-15T09:52:11.681Z", "session transcript, line 48441 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-15T09:52:18.018Z", "session transcript, line 48442 (the tool result of the question)"))
        self.assertLess(record["owner_message"]["at"], record["asked"]["at"])
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        qa = record["questions_and_answers"]
        self.assertEqual(len(qa), 1)
        self.assertEqual((qa[0]["header"], qa[0]["owner_selected"]), ("Wire pages 5", "Yes, batch 5 only (Recommended)"))
        self.assertEqual(qa[0]["question"], "May I read public wire-release pages and the issuers' own newsroom pages to take the first-public minute of the batch 5 releases (S4)?")
        self.assertEqual([o["label"] for o in qa[0]["options_offered"]], ["Yes, batch 5 only (Recommended)", "No downloads for now"])
        yes = qa[0]["options_offered"][0]["description"]
        self.assertIn("REKR 08-13, JBSS 08-19, SLSN 08-19, OKTA 08-26, LOVE 09-10", yes)
        for phrase in ("batches 1 to 4 took 42, 27, 25 and 36 page loads for ten candidates each, so for five expect 12 to 25", "No web-search tool, no price or quote page, no filing.", "No push, no other download.",
                       "SLSN's 8-K was filed 08-20, the day after its release", "all assessed 'results release, no issue found' in the S2 review",
                       "during batch 3 a Business Wire listing showed me Okta's 08-26 headline and time (16:01 ET); I will read its own page rather than rely on that", "This is the last batch: the final audit (S7) needs no pages."):
            self.assertIn(phrase, yes)
        for phrase in ("Batches 1 to 4 are complete (thirty-eight events attested, pinned and verified on a re-run; ASMB's two releases at the bell left quarantined).", "The owner's answer on batch 4's wire pages was \"Yes, batch 4 only (Recommended)\", whose option text said \"Later batches ask again.\"",
                       "The assistant's report offered batch 5, the last, and said it would ask the exact question, with names, sources and size, before opening any page.", "quoted from the session transcript, not from a summary"):
            self.assertIn(phrase, record["context"])
        self.assertEqual(qa[0]["options_offered"][1]["description"], "I stop here on Phase 1b until you say otherwise.")
        self.assertEqual((record["schema_version"], record["kind"], record["recorded_on"]), (1, "m5_phase1b_batch5_permission", "2026-10-15"))

    def test_the_five_are_the_last_standing_candidates_outside_batches_1_to_4_recomputed_from_the_s2_records(self):
        excluded = {("REKR", "2026-07-15"), ("PAYO", "2026-08-06")}
        batch1 = {(b["ticker"], b["filing_date"]) for b in self.decisions["wire_permission_read_as"]["batch_1"]}
        others = [{(b["ticker"], b["filing_date"]) for b in self.earlier[n]["permission_read_as"]["batch_%d" % n]} for n in (2, 3, 4)]
        taken = batch1.union(*others)
        self.assertEqual(len(taken), 40)
        self.assertFalse(excluded & taken)
        remaining = sorted((r for r in self.review if (r["ticker"], r["filing_date"]) not in excluded | taken), key=lambda r: (r["release_date_in_the_filing"], r["ticker"]))
        self.assertEqual(len(self.review), 47)
        self.assertEqual(len(remaining), 5)
        read_as = self.record["permission_read_as"]
        self.assertEqual(read_as["batch_5"], [{"ticker": r["ticker"], "filing_date": r["filing_date"], "release_date": r["release_date_in_the_filing"], "candidate_id": r["candidate_id"]} for r in remaining])
        self.assertEqual([(b["ticker"], b["release_date"], b["filing_date"]) for b in read_as["batch_5"]], BATCH_5)
        self.assertTrue(all(r["assessment"] == "results_release_no_issue_found" for r in remaining))
        self.assertEqual([r["ticker"] for r in remaining if r["filing_date"] != r["release_date_in_the_filing"]], ["SLSN"])
        for phrase in ("The five releases that remain among the 47 candidates once the two the owner excluded in the S2 decisions (REKR 2026-07-15, PAYO 2026-08-06) and the forty of batches 1 to 4 are taken out",
                       "All five were assessed results_release_no_issue_found there. SLSN's 8-K was filed 2026-08-20, the day after its 2026-08-19 release."):
            self.assertIn(phrase, read_as["how_batch_5_was_chosen"])
        self.assertIn("Batch 5 only", read_as["scope"])
        self.assertIn("No web-search tool, no price or quote page, no filing.", read_as["scope"])
        self.assertIn("It carries no push and no other download. It is the last batch: the final audit (S7) needs no pages.", read_as["scope"])
        self.assertEqual(read_as["disclosed_in_the_question"], "During batch 3 a Business Wire listing showed the headline and time (2026-08-26 16:01 ET) of Okta's 2026-08-26 release (reports/m5-phase1b-batch3-sources-2026-10-10.json, reading.what_was_seen_in_passing); "
                                                               "the question told the owner that Okta's own page would be read rather than relying on it.")
        batch3_passing = load(ROOT / "reports" / "m5-phase1b-batch3-sources-2026-10-10.json")["reading"]["what_was_seen_in_passing"]
        self.assertIn("Okta's 2026-08-26 release, which is a candidate of a later batch", batch3_passing)
        self.assertIn("(2026-08-26 16:01 ET)", batch3_passing)

    def test_it_says_what_the_answer_does_not_authorize(self):
        text = " ".join(self.record["not_authorized_by_this_answer"])
        for phrase in ("Reading the wire or newsroom pages of any other issuer or release.", "Reading the near-date 8-Ks", "Using the web-search tool", "Any push, any other download, any price or label read, and attesting any event's first-public time, identity or corporate actions for the owner."):
            self.assertIn(phrase, text)
        self.assertIn("no page had been read when this was recorded", " ".join(self.record["not_a_claim"]))


class EventsAndSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(EVENTS)
        cls.all_events = cls.spec["events"][:43]
        cls.earlier = cls.spec["events"][:38]
        cls.events = cls.spec["events"][38:43]
        cls.record = load(SOURCES)
        cls.permission = load(PERMISSION)
        cls.ledger = {(c["ticker"], c["filing_date"]): c for c in load(ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json")["candidates"]}
        cls.review = {(r["ticker"], r["filing_date"]): r for r in load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]}
        cls.m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}
        cohort = load(ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json")["issuers"]
        metas = {meta["url"]: meta for meta in (load(path) for path in sorted(RAW.glob("*.json")))}
        cls.accepted, cls.filings = {}, {}
        for issuer in cohort:
            recent = json.loads((RAW / metas[issuer["submissions_url"]]["raw_file"]).read_bytes())["filings"]["recent"]
            for i, accession in enumerate(recent["accessionNumber"]):
                cls.accepted[accession] = datetime.fromisoformat(recent["acceptanceDateTime"][i].replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")
                cls.filings[accession] = {"filing_date": recent["filingDate"][i], "form": recent["form"][i], "items": recent["items"][i]}

    def test_the_five_events_follow_the_thirty_eight_sealed_and_attested_and_the_whole_file_validates(self):
        ea.validate_spec(self.spec, Calendar())
        self.assertEqual(len(self.spec["events"]), 43)
        self.assertEqual([e["event_id"] for e in self.events], BATCH_5_IDS)
        for event in self.events:
            with self.subTest(event=event["event_id"]):
                self.assertEqual(event["seal"], "hash_only")
                self.assertIn("attestations", event)                          # the owner attested the batch after the sealed dry run and the signoff packet (tests/test_m5_phase1b_batch5_attestations.py)
                self.assertIn("recorded_result", event)                       # and each commitment was pinned after the attested sealed run printed it (tests/test_m5_phase1b_batch5_sealed_run.py)
                self.assertEqual(event["event_id"], event["cluster_id"])
                self.assertRegex(event["event_id"], r"^[a-z]+-m5b-2026-\d\d-\d\d$")
        for event in self.earlier:
            self.assertIn("attestations", event)                              # batches 1 to 4 are attested and pinned, and untouched by this step
            self.assertIn("recorded_result", event)
        self.assertEqual(len(self.all_events), 43)
        for path in (("event_id",), ("security", "security_id"), ("source", "source_id"), ("candidate_id",)):
            values = [e[path[0]] if len(path) == 1 else e[path[0]][path[1]] for e in self.all_events]
            self.assertEqual(len(set(values)), 43, path)

    def test_no_issuers_events_share_a_session_across_the_forty_three(self):
        spans = {}
        for event in self.all_events:
            window = ea.event_window(event, Calendar())
            spans.setdefault(event["security"]["ticker"], []).append((window["required_sessions"][0], window["required_sessions"][-1], event["event_id"]))
        self.assertEqual(len(sum(spans.values(), [])), 43)
        for ticker, rows in spans.items():
            rows.sort()
            for earlier, later in zip(rows, rows[1:]):
                with self.subTest(issuer=ticker):
                    self.assertLess(earlier[1], later[0])

    def test_each_event_agrees_with_the_ledger_the_review_the_milestone_1_events_and_the_calendar(self):
        calendar = Calendar()
        by_id = {e["event_id"]: e for e in self.events}
        for ticker, day, filed in BATCH_5:
            event = by_id["%s-m5b-%s" % (ticker.lower(), day)]
            with self.subTest(event=event["event_id"]):
                candidate, row = self.ledger[(ticker, filed)], self.review[(ticker, filed)]
                self.assertEqual(event["candidate_id"], candidate["candidate_id"])
                self.assertEqual((event["security"]["cik"], event["security"]["company_id"]), (candidate["cik"], candidate["cik"]))
                self.assertEqual(event["published_at"][:10], row["release_date_in_the_filing"])
                self.assertEqual(row["release_date_in_the_filing"], day)
                self.assertEqual(event["security"]["exchange"], "NYSE" if row["exchange_on_cover_or_release"] == "New York Stock Exchange" else "NASDAQ")
                self.assertEqual(event["security"]["security_type"], "common_stock")
                self.assertEqual(event["security"]["security_id"], "%s-%d-%s" % (ticker, int(candidate["cik"]), day))
                self.assertEqual(row["assessment"], "results_release_no_issue_found")
                previous = self.m1[ticker]["published_at"][:10]                # the previous earnings release: the issuer's Milestone 1 event
                self.assertLess(previous, day)
                self.assertEqual(datetime.fromisoformat(event["security"]["valid_from"]), datetime.fromisoformat(previous + "T00:00:00").replace(tzinfo=ZONE))
                self.assertEqual(event["security"]["available_at"], previous + "T20:00:00Z")
                published = datetime.fromisoformat(event["published_at"])
                self.assertEqual(published.astimezone(ZONE).strftime("%H:%M"), event["timestamp_evidence"])
                self.assertIn("(%s ET)" % event["timestamp_evidence"], event["source"]["text"])
                self.assertIn(event["source"]["url"], event["source"]["text"])
                self.assertEqual(datetime.fromisoformat(event["cutoff"]) - published, timedelta(minutes=3))
                self.assertEqual(datetime.fromisoformat(event["source"]["first_seen_at"]) - published, timedelta(minutes=1))
                self.assertEqual(event["precision"], "minute")
                session, timing = calendar.classify(event["published_at"])
                self.assertEqual((timing, session), (event["expected_release_timing"], event["expected_reaction_session"]))
                self.assertNotEqual(timing, "bell_ambiguous")                  # none of the five was made at the bell
                self.assertEqual(timing, "premarket" if event["timestamp_evidence"] < "09:30" else "after_hours")
                self.assertIn(event["source"]["url"].split("/")[2], {"www.businesswire.com", "www.globenewswire.com"})
                self.assertTrue(event["source"]["url"].startswith("https://"))
        self.assertEqual(sorted(e["security"]["ticker"] for e in self.events), sorted(t for t, _, _ in BATCH_5))

    def test_the_sources_rows_are_the_events_and_each_pages_machine_time_converts_to_the_minute_taken_from_it(self):
        rows = self.record["events"]
        self.assertEqual([r["event_id"] for r in rows], BATCH_5_IDS)
        wires = {"www.businesswire.com": "Business Wire", "www.globenewswire.com": "GlobeNewswire"}
        by_event = {e["event_id"]: e for e in self.events}
        for row in rows:
            with self.subTest(event=row["event_id"]):
                event = by_event[row["event_id"]]
                self.assertEqual((row["candidate_id"], row["url"], row["minute_et"], row["published_at"], row["expected_release_timing"], row["expected_reaction_session"]),
                                 (event["candidate_id"], event["source"]["url"], event["timestamp_evidence"], event["published_at"], event["expected_release_timing"], event["expected_reaction_session"]))
                self.assertEqual(row["wire"], wires[row["url"].split("/")[2]])
                self.assertEqual(row["ticker"], event["security"]["ticker"])
                self.assertEqual(row["event_id"], "%s-m5b-%s" % (row["ticker"].lower(), row["release_date"]))
                self.assertEqual(event["source"]["text"], "Wire release, displayed dateline %s (%s ET). %s" % (row["displayed_stamp"], event["timestamp_evidence"], event["source"]["url"]))
                self.assertEqual(event["source"]["source_id"], "%s-wire-%s" % (row["ticker"].lower(), row["release_date"]))
                machine = datetime.fromisoformat(row["page_machine_readable_time"].replace("Z", "+00:00"))
                self.assertEqual(machine.astimezone(ZONE).strftime("%H:%M"), row["minute_et"])
                self.assertEqual(machine.astimezone(ZONE).strftime("%Y-%m-%d"), row["release_date"])
                self.assertEqual(machine.replace(second=0), datetime.fromisoformat(event["published_at"]))      # the page may carry seconds; the spec keeps the minute
                self.assertEqual(row["edgar_acceptance_et"], self.accepted[row["candidate_id"]])
                self.assertGreaterEqual(row["edgar_acceptance_et"][11:], row["minute_et"] if row["edgar_acceptance_et"][:10] == row["release_date"] else "")
                self.assertTrue(row["same_day_release_check"]["how"] and row["same_day_release_check"]["result"])
                self.assertTrue(row["same_day_release_check"]["result"].startswith("No other"))
        said = {"rekr-m5b-2026-08-13": "the one other result in the window is dated 2026-08-12 (a product announcement, 'Rekor Expands Patented Verification Technology into Voice, Opening New Market for GoSecure')",
                "jbss-m5b-2026-08-19": "this is the latest result, and the one before it is dated 2026-07-16 16:10 ET",
                "slsn-m5b-2026-08-19": "this is the only result",
                "okta-m5b-2026-08-26": "the neighbours in the results are 2026-08-01 08:00 ET (a notice of the results date) and 2026-08-27 08:00 ET (a notice of conference presentations)",
                "love-m5b-2026-09-10": "this is the only result"}
        self.assertEqual(sorted(said), sorted(BATCH_5_IDS))
        for row in rows:
            self.assertIn(said[row["event_id"]], row["same_day_release_check"]["result"], row["event_id"])      # observations of the wire's own listings: they cannot be recomputed here, so they are pinned as recorded
        hows = {row["event_id"]: row["same_day_release_check"]["how"] for row in rows}
        self.assertEqual(hows, {"rekr-m5b-2026-08-13": "GlobeNewswire date-filtered search ('Rekor Systems', 2026-08-12 to 2026-08-14)",
                                "jbss-m5b-2026-08-19": "Business Wire company search ('John B. Sanfilippo', 68 results sorted latest, page 1)",
                                "slsn-m5b-2026-08-19": "GlobeNewswire date-filtered search ('Solésence', 2026-08-18 to 2026-08-20)",
                                "okta-m5b-2026-08-26": "Business Wire phrase searches ('Okta Announces', 43 results sorted latest, page 1; 'Okta, Inc. (Nasdaq: OKTA)', 113 results sorted latest, page 1)",
                                "love-m5b-2026-09-10": "GlobeNewswire date-filtered search ('Lovesac', 2026-09-09 to 2026-09-11)"})
        by_wire = {}
        for row in rows:
            by_wire.setdefault(row["wire"], []).append(row["event_id"])
        self.assertEqual(by_wire, {"GlobeNewswire": ["rekr-m5b-2026-08-13", "slsn-m5b-2026-08-19", "love-m5b-2026-09-10"], "Business Wire": ["jbss-m5b-2026-08-19", "okta-m5b-2026-08-26"]})
        self.assertEqual({r["event_id"]: r["minute_et"] for r in rows}, {"rekr-m5b-2026-08-13": "08:00", "jbss-m5b-2026-08-19": "16:10", "slsn-m5b-2026-08-19": "17:05", "okta-m5b-2026-08-26": "16:01", "love-m5b-2026-09-10": "07:00"})
        self.assertEqual({r["event_id"]: r["displayed_stamp"] for r in rows}, {"rekr-m5b-2026-08-13": "August 13, 2026 08:00 ET", "jbss-m5b-2026-08-19": "Aug 19, 2026 4:10 PM Eastern Daylight Time", "slsn-m5b-2026-08-19": "August 19, 2026 17:05 ET",
                                                                              "okta-m5b-2026-08-26": "Aug 26, 2026 4:01 PM Eastern Daylight Time", "love-m5b-2026-09-10": "September 10, 2026 07:00 ET"})
        # the earlier events of the same issuers, which the notes compare with
        self.assertEqual([self.m1["REKR"]["published_at"], next(e for e in self.earlier if e["event_id"] == "rekr-m5b-2026-05-11")["published_at"]], ["2026-03-31T16:05:00-04:00", "2026-05-11T16:05:00-04:00"])
        self.assertEqual([self.m1["SLSN"]["published_at"], next(e for e in self.earlier if e["event_id"] == "slsn-m5b-2026-05-12")["published_at"]], ["2026-03-31T08:02:00-04:00", "2026-05-12T08:00:00-04:00"])

    def test_nothing_is_at_the_bell_and_slsns_8k_was_filed_the_day_after_its_release(self):
        self.assertIsNone(self.record["quarantined_before_the_spec"])
        calendar = Calendar()
        for event in self.events:
            self.assertNotEqual(calendar.classify(event["published_at"])[1], "bell_ambiguous", event["event_id"])
        slsn = next(e for e in self.events if e["security"]["ticker"] == "SLSN")
        self.assertEqual(self.filings[slsn["candidate_id"]], {"filing_date": "2026-08-20", "form": "8-K", "items": "2.02,9.01"})
        self.assertEqual((slsn["published_at"][:10], self.accepted[slsn["candidate_id"]]), ("2026-08-19", "2026-08-20 16:12"))
        self.assertEqual((slsn["expected_release_timing"], slsn["expected_reaction_session"]), ("after_hours", "2026-08-20"))        # reaction session 08-20: the 8-K's filing date is also the reaction session
        for ticker in ("REKR", "JBSS", "OKTA", "LOVE"):
            event = next(e for e in self.events if e["security"]["ticker"] == ticker)
            self.assertEqual(self.filings[event["candidate_id"]], {"filing_date": event["published_at"][:10], "form": "8-K", "items": "2.02,9.01"})

    def test_no_caveat_is_carried_at_the_dry_run_and_the_notes_say_what_is_unusual(self):
        self.assertEqual(self.record["caveats_carried"], [])
        for event in self.events:
            for caveat in event.get("caveats", []):
                self.assertTrue(caveat["note"].startswith("8-K ") or caveat["note"].startswith("The second-quarter results were preliminarily pre-announced on 2026-07-15"), event["event_id"])      # every caveat the signoff added names a filing; none was carried at the dry run
        notes = self.record["notes"]
        self.assertEqual(notes, ["REKR: the second-quarter release is premarket (08:00 ET); its earlier events in the repository were after the close (16:05 ET on 2026-03-31 and 2026-05-11). EDGAR accepted the 8-K at 12:00 ET.",
                                 "SLSN: the release is after the close (17:05 ET on 2026-08-19); the 8-K was filed and accepted the next day (2026-08-20 16:12 ET). Its earlier events in the repository were premarket releases (08:02 ET on 2026-03-31 and 08:00 ET on 2026-05-12).",
                                 "LOVE: EDGAR's acceptance of the 8-K (2026-09-10 07:00 ET) is the same minute as the wire's, not earlier."])
        rows = {r["ticker"]: r for r in self.record["events"]}
        self.assertEqual((rows["LOVE"]["minute_et"], rows["LOVE"]["edgar_acceptance_et"]), ("07:00", "2026-09-10 07:00"))
        self.assertEqual((rows["REKR"]["minute_et"], rows["REKR"]["edgar_acceptance_et"]), ("08:00", "2026-08-13 12:00"))

    def test_the_dry_run_state_of_the_five_is_recoverable_byte_for_byte(self):
        events = json.loads(json.dumps(self.events))
        for event in events:
            event.pop("attestations")                                         # what the owner's signoff added: the attestations and the caveats that name a filing
            event.pop("caveats", None)
            event.pop("recorded_result")                                      # and what the attested sealed run's commitments added
        text = json.dumps({"events": events}, indent=2, ensure_ascii=False) + "\n"
        info = self.record["events_file"]
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), info["batch_5_events_sha256_in_the_dry_run_state"])
        self.assertEqual((info["path"], info["events"], info["batch_5_events"], info["batch_5_attestations"]), ("config/m5-phase1b-events.json", 43, 5, 0))
        self.assertEqual(info["seal"], "every event carries seal: hash_only")
        self.assertEqual(info["provider_attestation"], "reports/m5-phase1b-provider-scope-authorization-2026-10-09.json (the owner's recorded 'Yes, provider rights fine')")
        self.assertTrue((ROOT / "reports" / "m5-phase1b-provider-scope-authorization-2026-10-09.json").is_file())
        self.assertEqual(self.record["state"], "BATCH_5_SPECS_BUILT_DRY_RUN_PENDING")
        self.assertEqual((self.record["schema_version"], self.record["kind"], self.record["recorded_on"]), (1, "m5_phase1b_batch5_sources", "2026-10-15"))

    def test_it_states_what_was_read_what_went_wrong_and_what_it_is_not(self):
        record, reading = self.record, self.record["reading"]
        self.assertIn("holds five events built from it in the dry-run state after the thirty-eight of batches 1 to 4: sealed, no attestations, so each quarantines on FIRST_PUBLIC_TIME_UNVERIFIED until the owner attests it. "
                      "None was made at the bell. Nothing here is a price, a return or a label.", record["purpose"])
        self.assertTrue(record["purpose"].startswith("S4 for batch 5, the last: the first-public minute of each release in the fifth batch"))
        self.assertEqual((reading["page_loads_in_the_built_in_browser"], reading["web_searches"]), (13, 0))
        self.assertEqual(reading["by_host"], {"www.businesswire.com": 7, "www.globenewswire.com": 6})
        self.assertEqual(sum(reading["by_host"].values()), 13)
        for phrase in ("company searches on GlobeNewswire and Business Wire (each issuer's wire is the one its earlier events in the repository used)", "Business Wire's two release pages were loaded a second time to read the date and time the page itself displays",
                       "No filing was opened: EDGAR's acceptance times come from the archived SEC lists already in the repository.", "Listings were read through short extractions of the dates, times and titles wanted, so as to see as little else as possible."):
            self.assertIn(phrase, reading["what"])
        for phrase in ("Business Wire's Sanfilippo listing returned the opening sentences of the 2026-08-19 release", "('... cash flow of $227 million')", "from 2026-05-21 to 2026-09-18, including two after its results (2026-09-14, a webcast notice, and 2026-09-18, a board appointment)",
                       "These are company-reported business content, not a price, a return or a label of any event."):
            self.assertIn(phrase, reading["what_was_seen_in_passing"])
        for phrase in ("No site refused a page for permission, and Business Wire answered every request: I made one search at a time, with release pages between them.", "The first Business Wire search page re-navigated by itself once while my first script ran",
                       "the first batch call (GlobeNewswire's Rekor search) stopped at its first action because the pane had to be opened, but that page had loaded and was read without a second load."):
            self.assertIn(phrase, reading["refused_or_missing"])
        permission = record["permission"]
        self.assertEqual((permission["record"], permission["answer"], permission["answered_at"], permission["read_as"]),
                         ("reports/m5-phase1b-batch5-permission-2026-10-15.json", "Yes, batch 5 only (Recommended)", self.permission["answered"]["at"], self.permission["permission_read_as"]["scope"]))
        text = " ".join(record["what_this_is_not"])
        for phrase in ("Not an attestation", "Not a proof that nothing earlier was public", "Not a price, a return or a label of any event: none was read; the sealed run prints none."):
            self.assertIn(phrase, text)
        self.assertEqual(record["next"], "A sealed dry run (the push of the events file starts it; the thirty-eight pinned events of batches 1 to 4 are re-checked in the same run), then the signoff packet for the owner: for each event the wire evidence above and the sealed run's facts "
                                         "(missing and zero-volume sessions, corporate actions); then the owner's attestations of first-public time, historical identity and corporate actions, and the attested sealed run that pins each event's commitment. Then the final audit (S7).")


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        return self.data


class SealedRunSimulationTests(unittest.TestCase):
    """Batch 5's five events through the sealed run with a fake provider holding distinctive prices and no corporate actions: with the attestations taken out they quarantine, as shipped (attested, not pinned) they map, and no price reaches the output."""

    def run_sealed(self, attested, pinned=False):
        calendar = Calendar()
        spec = load(EVENTS)
        spec["events"] = spec["events"][38:43]
        for event in spec["events"]:
            if not attested:
                event.pop("attestations")
            if not pinned:
                event.pop("recorded_result")

        class Opener:
            def open(self, req, timeout=None):
                url = req.full_url
                query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
                if "corporate-actions" in url:
                    return Response(json.dumps({"corporate_actions": {}, "next_page_token": None}).encode())
                ticker = query["symbols"]
                rows, base = [], 7183.2941
                for i, day in enumerate(d for d in calendar.days if query["start"] <= d <= query["end"]):
                    o = round(base * (1 + 0.0013 * i), 4)
                    c = round(o * 1.0173, 4)
                    rows.append({"t": day + "T00:00:00Z", "o": o, "h": round(c * 1.0111, 4), "l": round(o * 0.9877, 4), "c": c, "v": 1000003 + 7919 * i})
                return Response(json.dumps({"bars": {ticker: rows}, "next_page_token": None}).encode())

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            with patch.dict("os.environ", dict(ENV, GITHUB_ACTIONS="true"), clear=True), patch("nre.event_acquire.build_opener", return_value=Opener()), patch("builtins.print") as output:
                code = ea.main(["--sealed", "--spec", str(path)])
        return code, [call.args[0] for call in output.call_args_list]

    def test_with_the_attestations_taken_out_the_five_quarantine_on_the_attestation_alone_and_nothing_leaks(self):
        code, printed = self.run_sealed(attested=False)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"QUARANTINED": 5}))
        self.assertEqual(sorted(out["events"]), sorted(BATCH_5_IDS))
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["session_labels"], view["labels_sha256"], view["labels_match_recorded"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], None, None, None))
                self.assertEqual((view["missing_sessions"], view["zero_volume_sessions"], view["corporate_actions"]), ([], [], []))
                self.assertEqual(view["window"]["required_sessions"], 21)
                self.assertTrue(view["access_check_passed"])
        everything = "\n".join(printed)
        self.assertIsNone(re.search(r"\d\.\d", everything))
        for fragment in ("7183.2941", "1000003", "AKTESTKEY123", "SECRETVALUE456"):
            self.assertNotIn(fragment, everything)
        self.assertTrue(printed[1].startswith("::notice title=NRE sealed event acquisition::"))

    def test_the_whole_file_in_one_sealed_run_keeps_every_event_in_the_annotations(self):
        # GitHub keeps only the first ten annotations of a kind per step; the forty-three events once needed eleven parts and the last was dropped (batch 5's first dry run)
        calendar = Calendar()
        spec = load(EVENTS)
        for event in spec["events"]:
            event.pop("recorded_result", None)                                # the fake prices would (rightly) differ from the pins; the question here is only how the report is carried

        class Opener:
            def open(self, req, timeout=None):
                url = req.full_url
                query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
                if "corporate-actions" in url:
                    return Response(json.dumps({"corporate_actions": {}, "next_page_token": None}).encode())
                rows = [{"t": day + "T00:00:00Z", "o": 50.25 + i, "h": 51.5 + i, "l": 49.75 + i, "c": 50.75 + i, "v": 1000003 + 7919 * i} for i, day in enumerate(d for d in calendar.days if query["start"] <= d <= query["end"])]
                return Response(json.dumps({"bars": {query["symbols"]: rows}, "next_page_token": None}).encode())

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            with patch.dict("os.environ", dict(ENV, GITHUB_ACTIONS="true"), clear=True), patch("nre.event_acquire.build_opener", return_value=Opener()), patch("builtins.print") as output:
                code = ea.main(["--sealed", "--spec", str(path)])
        printed = [call.args[0] for call in output.call_args_list]
        self.assertEqual(code, 0)
        prefix = "::notice title=NRE sealed event acquisition::"
        lines = [line for line in printed[1:] if line.startswith(prefix)]
        self.assertLessEqual(len(lines), 10)
        seen = {}
        for number, line in enumerate(lines, 1):
            self.assertLess(len(line) - len(prefix), 4000)
            body = json.loads(line[len(prefix):])
            self.assertEqual(body["part"], "%d/%d" % (number, len(lines)))
            seen.update(body["events"])
        self.assertEqual(sorted(seen), sorted(e["event_id"] for e in spec["events"]))
        self.assertEqual(len(seen), 43)

    def test_as_shipped_each_pin_catches_the_injected_prices_and_nothing_else_is_reported(self):
        code, printed = self.run_sealed(attested=True, pinned=True)
        out = json.loads(printed[0])
        self.assertEqual((code, out["all_ok"]), (2, False))
        recorded = {e["event_id"]: e["recorded_result"]["labels_sha256"] for e in load(EVENTS)["events"][38:43]}
        self.assertEqual(sorted(out["events"]), sorted(BATCH_5_IDS))
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["labels_match_recorded"], view["error"]), ("MAPPED", False, "LABELS_DIFFER_FROM_RECORDED"))
                self.assertNotEqual(view["labels_sha256"], recorded[event_id])
        self.assertIsNone(re.search(r"\d\.\d", "\n".join(printed)))

    def test_attested_and_unpinned_they_all_map_so_nothing_but_the_attestation_blocked_them(self):
        code, printed = self.run_sealed(attested=True)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"MAPPED": 5}))
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"]), ("MAPPED", []))
                self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
