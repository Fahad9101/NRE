"""Milestone 5 Phase 1b batch 4: the owner's permission to read the ten releases' wire pages (reports/m5-phase1b-batch4-permission-2026-10-14.json) is quoted as given and the ten are recomputed from the S2 records; nine events, appended to
config/m5-phase1b-events.json after the twenty-nine of batches 1 to 3 (sealed; attested on the owner's signoff, tests/test_m5_phase1b_batch4_attestations.py), validate with the project's own spec validation and agree with the frozen ledger, the eligibility review, the Milestone 1 events, the calendar and the wire evidence in
reports/m5-phase1b-batch4-sources-2026-10-14.json (each page's machine-readable time converts to the minute taken from it; EDGAR's acceptance time is recomputed from the archived SEC lists); the tenth release, ASMB's, was made at the bell and is put aside, which the calendar
confirms; their dry-run state is recoverable byte for byte; and a sealed run of the nine with injected prices quarantines every one once the attestations are taken out, maps every one as shipped, and prints no price."""
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
SOURCES = ROOT / "reports" / "m5-phase1b-batch4-sources-2026-10-14.json"
PERMISSION = ROOT / "reports" / "m5-phase1b-batch4-permission-2026-10-14.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
# (ticker, the release's date, the 8-K's filing date); ASMB's release is put aside, its candidate being the 8-K/A of the day after
BATCH_4 = [("ASPN", "2026-08-06", "2026-08-06"), ("COLL", "2026-08-06", "2026-08-06"), ("PDFS", "2026-08-06", "2026-08-06"), ("REAL", "2026-08-06", "2026-08-06"), ("TECX", "2026-08-06", "2026-08-06"),
           ("TTWO", "2026-08-07", "2026-08-07"), ("ACHV", "2026-08-11", "2026-08-11"), ("KLC", "2026-08-13", "2026-08-13"), ("LNSR", "2026-08-13", "2026-08-13")]
ASMB = ("ASMB", "2026-08-13", "2026-08-14")
BATCH_4_IDS = ["%s-m5b-%s" % (ticker.lower(), day) for ticker, day, _ in BATCH_4]
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class PermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(PERMISSION)
        cls.review = load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]
        cls.decisions = load(ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json")
        cls.batch_2_permission = load(ROOT / "reports" / "m5-phase1b-batch2-permission-2026-10-10.json")
        cls.batch_3_permission = load(ROOT / "reports" / "m5-phase1b-batch3-permission-2026-10-10.json")

    def test_the_message_the_question_and_the_answer_are_quoted_as_given(self):
        record = self.record
        self.assertEqual(record["owner_message"], {"text": "authorize batch 4", "at": "2026-10-14T05:18:34.377Z", "source": "session transcript, line 46626",
                                                   "read_as": "The go-ahead to ask the question about batch 4, as the report offered; it is not itself the permission to read pages."})
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-14T05:18:58.350Z", "session transcript, line 46639 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-14T05:19:24.899Z", "session transcript, line 46640 (the tool result of the question)"))
        self.assertLess(record["owner_message"]["at"], record["asked"]["at"])
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        qa = record["questions_and_answers"]
        self.assertEqual(len(qa), 1)
        self.assertEqual((qa[0]["header"], qa[0]["owner_selected"]), ("Wire pages 4", "Yes, batch 4 only (Recommended)"))
        self.assertEqual(qa[0]["question"], "May I read public wire-release pages and the issuers' own newsroom pages to take the first-public minute of the batch 4 releases (S4)?")
        self.assertEqual([o["label"] for o in qa[0]["options_offered"]], ["Yes, batch 4 only (Recommended)", "Yes, all 15 remaining candidates", "No downloads for now"])
        yes = qa[0]["options_offered"][0]["description"]
        self.assertIn("ASPN 08-06, COLL 08-06, PDFS 08-06, REAL 08-06, TECX 08-06, TTWO 08-07, ACHV 08-11, ASMB 08-13, KLC 08-13, LNSR 08-13", yes)
        for phrase in ("batches 1, 2 and 3 took 42, 27 and 25 page loads, so expect 25 to 45", "No web-search tool, no price or quote page, no filing.", "No push, no other download. Later batches ask again.",
                       "ASMB's release, whose 8-K/A of 08-14 you kept with a caveat"):
            self.assertIn(phrase, yes)
        for phrase in ("Batches 1 to 3 are complete (twenty-nine events attested, pinned and verified on a re-run).", "The owner's answer on batch 3's wire pages was \"Yes, batch 3 only (Recommended)\", whose option text said \"Later batches ask again.\"",
                       "The assistant's report offered batch 4 and said it would ask the exact question, with names, sources and size, before opening any page.", "quoted from the session transcript, not from a summary"):
            self.assertIn(phrase, record["context"])
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch4_permission", "2026-10-14"))

    def test_the_ten_are_the_ten_earliest_standing_candidates_outside_batches_1_to_3_recomputed_from_the_s2_records(self):
        excluded = {("REKR", "2026-07-15"), ("PAYO", "2026-08-06")}
        batch1 = {(b["ticker"], b["filing_date"]) for b in self.decisions["wire_permission_read_as"]["batch_1"]}
        batch2 = {(b["ticker"], b["filing_date"]) for b in self.batch_2_permission["permission_read_as"]["batch_2"]}
        batch3 = {(b["ticker"], b["filing_date"]) for b in self.batch_3_permission["permission_read_as"]["batch_3"]}
        remaining = sorted((r for r in self.review if (r["ticker"], r["filing_date"]) not in excluded | batch1 | batch2 | batch3), key=lambda r: (r["release_date_in_the_filing"], r["ticker"]))
        self.assertEqual(len(remaining), 15)
        read_as = self.record["permission_read_as"]
        self.assertEqual(read_as["batch_4"], [{"ticker": r["ticker"], "filing_date": r["filing_date"], "release_date": r["release_date_in_the_filing"], "candidate_id": r["candidate_id"]} for r in remaining[:10]])
        self.assertEqual([(b["ticker"], b["release_date"], b["filing_date"]) for b in read_as["batch_4"]], BATCH_4[:7] + [ASMB] + BATCH_4[7:])
        self.assertEqual(read_as["next_in_line"], ["REKR 2026-08-13", "JBSS 2026-08-19", "SLSN 2026-08-19"])
        self.assertEqual([r["ticker"] for r in remaining[:10] if r["assessment"] != "results_release_no_issue_found"], ["ASMB"])
        self.assertEqual(next(r for r in remaining[:10] if r["ticker"] == "ASMB")["assessment"], "owner_decision_header_only_amendment")
        self.assertEqual([r["ticker"] for r in remaining[:10] if r["filing_date"] != r["release_date_in_the_filing"]], ["ASMB"])
        self.assertEqual(self.decisions["effects"]["ASMB 2026-08-14"]["disposition"], "kept_with_caveat")
        for phrase in ("The ten earliest releases among the 15 candidates that stand and are in none of batches 1 to 3", "ties broken alphabetically",
                       "Nine were assessed results_release_no_issue_found there, with a release date equal to the filing date; the tenth, ASMB, is the 2026-08-14 8-K/A that the owner kept with a caveat as standing for its 2026-08-13 release"):
            self.assertIn(phrase, read_as["how_batch_4_was_chosen"])
        self.assertIn("Batch 4 only", read_as["scope"])
        self.assertIn("No web-search tool, no price or quote page, no filing.", read_as["scope"])
        self.assertIn("It carries no push and no other download; later batches ask again.", read_as["scope"])

    def test_it_says_what_the_answer_does_not_authorize(self):
        text = " ".join(self.record["not_authorized_by_this_answer"])
        for phrase in ("Reading the wire or newsroom pages of any candidate outside batch 4.", "Reading the near-date 8-Ks", "Using the web-search tool", "Any push, any other download, any price or label read, and attesting any event's first-public time, identity or corporate actions for the owner."):
            self.assertIn(phrase, text)
        self.assertIn("no page had been read when this was recorded", " ".join(self.record["not_a_claim"]))


class EventsAndSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(EVENTS)
        cls.all_events = cls.spec["events"][:38]
        cls.earlier = cls.spec["events"][:29]
        cls.events = cls.spec["events"][29:38]
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

    def test_the_nine_events_follow_the_twenty_nine_sealed_and_attested_and_the_whole_file_validates(self):
        ea.validate_spec(self.spec, Calendar())
        self.assertEqual([e["event_id"] for e in self.events], BATCH_4_IDS)
        for event in self.events:
            with self.subTest(event=event["event_id"]):
                self.assertEqual(event["seal"], "hash_only")
                self.assertIn("attestations", event)                          # the owner attested the batch after the sealed dry run and the signoff packet (tests/test_m5_phase1b_batch4_attestations.py)
                self.assertNotIn("recorded_result", event)                    # and nothing is pinned until the attested sealed run has printed the commitments
                self.assertEqual(event["event_id"], event["cluster_id"])
                self.assertRegex(event["event_id"], r"^[a-z]+-m5b-2026-\d\d-\d\d$")
        for event in self.earlier:
            self.assertIn("attestations", event)                              # batches 1 to 3 are attested and pinned, and untouched by this step
            self.assertIn("recorded_result", event)
        self.assertEqual(len(self.all_events), 38)
        for path in (("event_id",), ("security", "security_id"), ("source", "source_id"), ("candidate_id",)):
            values = [e[path[0]] if len(path) == 1 else e[path[0]][path[1]] for e in self.all_events]
            self.assertEqual(len(set(values)), 38, path)

    def test_each_event_agrees_with_the_ledger_the_review_the_milestone_1_events_and_the_calendar(self):
        calendar = Calendar()
        by_id = {e["event_id"]: e for e in self.events}
        for ticker, day, filed in BATCH_4:
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
                self.assertEqual(timing, "premarket" if event["timestamp_evidence"] < "09:30" else "after_hours")
                self.assertIn(event["source"]["url"].split("/")[2], {"www.businesswire.com", "www.globenewswire.com", "www.prnewswire.com"})
                self.assertTrue(event["source"]["url"].startswith("https://"))
        self.assertEqual(sorted(e["security"]["ticker"] for e in self.events), sorted(t for t, _, _ in BATCH_4))

    def test_the_sources_rows_are_the_events_and_each_pages_machine_time_converts_to_the_minute_taken_from_it(self):
        rows = self.record["events"]
        self.assertEqual([r["event_id"] for r in rows], BATCH_4_IDS)
        wires = {"www.businesswire.com": "Business Wire", "www.globenewswire.com": "GlobeNewswire", "www.prnewswire.com": "PR Newswire"}
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
        said = {"aspn-m5b-2026-08-06": "this is the only result", "coll-m5b-2026-08-06": "this is the only result", "pdfs-m5b-2026-08-06": "this is the only result",
                "real-m5b-2026-08-06": "the neighbour on PR Newswire is 2026-08-03 10:00 ET (a store opening), and GlobeNewswire has none in the window",
                "tecx-m5b-2026-08-06": "this is the only result",
                "ttwo-m5b-2026-08-07": "the neighbours in the results are 2026-07-22 10:00 ET (a game announcement) and 2026-09-01 08:00 ET (a game announcement). The page's address carries the date 2026-08-06 although the release is stamped 2026-08-07 07:30 ET.",
                "achv-m5b-2026-08-11": "this is the only result",
                "klc-m5b-2026-08-13": "the neighbours in the results are 2026-08-06 08:45 ET (a scholarship announcement) and 2026-09-28 08:24 ET (an awards announcement)",
                "lnsr-m5b-2026-08-13": "this is the only result"}
        self.assertEqual(sorted(said), sorted(BATCH_4_IDS))
        for row in rows:
            self.assertIn(said[row["event_id"]], row["same_day_release_check"]["result"], row["event_id"])      # observations of the wire's own listings: they cannot be recomputed here, so they are pinned as recorded
        by_wire = {}
        for row in rows:
            by_wire.setdefault(row["wire"], []).append(row["event_id"])
        self.assertEqual(by_wire, {"GlobeNewswire": ["aspn-m5b-2026-08-06", "coll-m5b-2026-08-06", "pdfs-m5b-2026-08-06", "tecx-m5b-2026-08-06", "achv-m5b-2026-08-11", "lnsr-m5b-2026-08-13"],
                                   "PR Newswire": ["real-m5b-2026-08-06"], "Business Wire": ["ttwo-m5b-2026-08-07", "klc-m5b-2026-08-13"]})
        self.assertEqual({r["event_id"]: r["minute_et"] for r in rows}, {"aspn-m5b-2026-08-06": "06:30", "coll-m5b-2026-08-06": "07:30", "pdfs-m5b-2026-08-06": "16:02", "real-m5b-2026-08-06": "16:07", "tecx-m5b-2026-08-06": "16:01",
                                                                          "ttwo-m5b-2026-08-07": "07:30", "achv-m5b-2026-08-11": "08:30", "klc-m5b-2026-08-13": "16:15", "lnsr-m5b-2026-08-13": "07:00"})

    def test_asmbs_release_at_the_bell_is_put_aside_and_the_calendar_and_the_archive_agree(self):
        block = self.record["quarantined_before_the_spec"]
        ticker, day, filed = ASMB
        candidate = self.ledger[(ticker, filed)]
        self.assertEqual((block["ticker"], block["candidate_id"], block["filing_date"], block["form"], block["release_date"]), (ticker, candidate["candidate_id"], filed, "8-K/A", day))
        self.assertEqual((block["wire"], block["displayed_stamp"], block["page_machine_readable_time"]), ("GlobeNewswire", "August 13, 2026 16:00 ET", "2026-08-13T20:00:00Z"))
        self.assertEqual(block["url"], "https://www.globenewswire.com/news-release/2026/08/13/3344875/16259/en/assembly-biosciences-reports-second-quarter-2026-financial-results-and-recent-updates.html")
        machine = datetime.fromisoformat(block["page_machine_readable_time"].replace("Z", "+00:00")).astimezone(ZONE)
        self.assertEqual(machine.strftime("%Y-%m-%d %H:%M:%S"), "2026-08-13 16:00:00")
        self.assertEqual(Calendar().classify(machine.isoformat())[1], "bell_ambiguous")                  # the instant of the close: no minute-precision spec can be built
        self.assertEqual(block["edgar_acceptance_et"], self.accepted[candidate["candidate_id"]])
        self.assertEqual(self.filings[candidate["candidate_id"]], {"filing_date": filed, "form": "8-K/A", "items": "2.02,9.01"})
        original = block["original_8k"]
        self.assertEqual(original["accession"], "0001193125-26-349198")
        self.assertEqual(self.filings[original["accession"]], {"filing_date": day, "form": "8-K", "items": "2.01,9.01"})
        self.assertEqual((original["items"], original["accepted_et"]), ("2.01,9.01", self.accepted[original["accession"]]))
        self.assertEqual(original["note"], "The 8-K the 8-K/A corrects (its Item 2.02 had been tagged as Item 2.01, per the owner's decision record); it is not one of the 47 candidates.")
        self.assertGreaterEqual(original["accepted_et"][11:], "16:00")                                    # the original 8-K was accepted after the release, as the wire minute requires
        self.assertEqual(self.review[(ticker, filed)]["assessment"], "owner_decision_header_only_amendment")
        self.assertFalse([e for e in self.spec["events"] if e["security"]["ticker"] == "ASMB" and e["published_at"][:10] == day])     # no spec was built for it
        self.assertFalse([e for e in self.spec["events"] if e["candidate_id"] == candidate["candidate_id"]])
        for phrase in ("Released at 16:00 ET, the regular-session close: nre/calendar.py's classify() returns bell_ambiguous for the instant of the close", "so no event spec can be built.",
                       "ASMB 2026-05-07 was left quarantined, not excluded, for the same reason on the owner's word (reports/m5-phase1b-batch1-signoff-2026-10-09.json)",
                       "The same disposition is proposed here; it needs the owner's word at the signoff.", "does not decide the timing question."):
            self.assertIn(phrase, block["reason"])
        self.assertEqual(block["same_day_release_check"], "GlobeNewswire date-filtered search ('Assembly Biosciences', 2026-08-12 to 2026-08-14): no other release in the window.")
        self.assertTrue((ROOT / "reports" / "m5-phase1b-batch1-signoff-2026-10-09.json").is_file())

    def test_no_caveat_is_carried_at_the_dry_run_and_the_notes_say_what_is_unusual(self):
        self.assertEqual(self.record["caveats_carried"], [])
        for event in self.events:
            self.assertTrue(all(c["note"].startswith("8-K ") for c in event.get("caveats", [])), event["event_id"])        # every caveat the signoff added names an 8-K; none was carried at the dry run
        notes = self.record["notes"]
        self.assertEqual(notes, ["ASPN: EDGAR's acceptance of the 8-K (2026-08-06 06:30 ET) is the same minute as the wire's, not earlier.",
                                 "TTWO: the release is stamped 2026-08-07 07:30 ET by the page and its machine-readable time, a premarket release before the 8:00 a.m. call; the page's address carries 2026-08-06.",
                                 "REAL: the second-quarter release is on PR Newswire (16:07 ET); the first-quarter release was on GlobeNewswire."])
        rows = {r["ticker"]: r for r in self.record["events"]}
        self.assertEqual((rows["ASPN"]["minute_et"], rows["ASPN"]["edgar_acceptance_et"]), ("06:30", "2026-08-06 06:30"))
        self.assertEqual(rows["REAL"]["wire"], "PR Newswire")

    def test_the_dry_run_state_of_the_nine_is_recoverable_byte_for_byte(self):
        events = json.loads(json.dumps(self.events))
        for event in events:
            event.pop("attestations")                                         # what the owner's signoff added: the attestations and the caveats that name a filing
            event.pop("caveats", None)
        text = json.dumps({"events": events}, indent=2, ensure_ascii=False) + "\n"
        info = self.record["events_file"]
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), info["batch_4_events_sha256_in_the_dry_run_state"])
        self.assertEqual((info["path"], info["events"], info["batch_4_events"], info["batch_4_attestations"]), ("config/m5-phase1b-events.json", 38, 9, 0))
        self.assertEqual(info["seal"], "every event carries seal: hash_only")
        self.assertEqual(info["provider_attestation"], "reports/m5-phase1b-provider-scope-authorization-2026-10-09.json (the owner's recorded 'Yes, provider rights fine')")
        self.assertTrue((ROOT / "reports" / "m5-phase1b-provider-scope-authorization-2026-10-09.json").is_file())
        self.assertEqual(self.record["state"], "BATCH_4_SPECS_BUILT_DRY_RUN_PENDING")
        self.assertEqual((self.record["kind"], self.record["recorded_on"]), ("m5_phase1b_batch4_sources", "2026-10-14"))

    def test_it_states_what_was_read_what_went_wrong_and_what_it_is_not(self):
        record, reading = self.record, self.record["reading"]
        self.assertIn("holds nine events built from it in the dry-run state after the twenty-nine of batches 1 to 3: sealed, no attestations, so each quarantines on FIRST_PUBLIC_TIME_UNVERIFIED until the owner attests it. "
                      "The tenth release, ASMB's, was made at the bell and is put aside for the owner's word. Nothing here is a price, a return or a label.", record["purpose"])
        self.assertEqual((reading["page_loads_in_the_built_in_browser"], reading["web_searches"]), (36, 0))
        self.assertEqual(reading["by_host"], {"take2games.com": 2, "www.businesswire.com": 15, "www.globenewswire.com": 17, "www.prnewswire.com": 2})
        self.assertEqual(sum(reading["by_host"].values()), 36)
        for phrase in ("except The RealReal, whose second-quarter release is on PR Newswire", "and Take-Two's own investor-relations press-release list and release page, which gave no release minute",
                       "No filing was opened: EDGAR's acceptance times come from the archived SEC lists already in the repository.", "Listings were read through short extractions of the dates, times and titles wanted, so as to see as little else as possible."):
            self.assertIn(phrase, reading["what"])
        for phrase in ("(the conference call 'today at 8:00 a.m. Eastern Time')", "a fragment of the company's net-bookings expectation", "one of them dated 2026-10-13 (a notice that it will report its next quarter's results)",
                       "These are company-reported business content, not a price, a return or a label of any event."):
            self.assertIn(phrase, reading["what_was_seen_in_passing"])
        for phrase in ("No site refused a page for permission.", "Business Wire's newsroom search answered 'Page Unavailable' (a reference id, no content) nine times, from three searches in quick succession onward, until about 45 minutes after my last attempt; its homepage loaded throughout.",
                       "I did not route around it: I waited, then asked for one search at a time", "Two GlobeNewswire searches for The RealReal found nothing, because its release is on PR Newswire.", "so Aspen's search was loaded twice."):
            self.assertIn(phrase, reading["refused_or_missing"])
        permission = record["permission"]
        self.assertEqual((permission["record"], permission["answer"], permission["answered_at"], permission["read_as"]),
                         ("reports/m5-phase1b-batch4-permission-2026-10-14.json", "Yes, batch 4 only (Recommended)", self.permission["answered"]["at"], self.permission["permission_read_as"]["scope"]))
        text = " ".join(record["what_this_is_not"])
        for phrase in ("Not an attestation", "Not a proof that nothing earlier was public", "Not a price, a return or a label of any event: none was read; the sealed run prints none."):
            self.assertIn(phrase, text)
        self.assertIn("the twenty-nine pinned events of batches 1 to 3 are re-checked in the same run", record["next"])
        self.assertIn("and the question about ASMB's release at the bell for the owner's word", record["next"])


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
    """Batch 4's nine events through the sealed run with a fake provider holding distinctive prices and no corporate actions: with the attestations taken out they quarantine, as shipped (attested, not pinned) they map, and no price reaches the output."""

    def run_sealed(self, attested):
        calendar = Calendar()
        spec = load(EVENTS)
        spec["events"] = spec["events"][29:38]
        for event in spec["events"]:
            if not attested:
                event.pop("attestations")

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

    def test_with_the_attestations_taken_out_the_nine_quarantine_on_the_attestation_alone_and_nothing_leaks(self):
        code, printed = self.run_sealed(attested=False)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"QUARANTINED": 9}))
        self.assertEqual(sorted(out["events"]), sorted(BATCH_4_IDS))
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

    def test_attested_and_unpinned_they_all_map_so_nothing_but_the_attestation_blocked_them(self):
        code, printed = self.run_sealed(attested=True)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"MAPPED": 9}))
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"]), ("MAPPED", []))
                self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
