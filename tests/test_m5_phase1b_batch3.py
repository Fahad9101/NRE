"""Milestone 5 Phase 1b batch 3 in the dry-run state: the owner's permission to read the ten releases' wire pages (reports/m5-phase1b-batch3-permission-2026-10-10.json) is quoted as given and the ten are recomputed from the S2 records; the ten events appended to
config/m5-phase1b-events.json after the nineteen of batches 1 and 2 (sealed, no attestations) validate with the project's own spec validation and agree with the frozen ledger, the eligibility review, the Milestone 1 events, the calendar and the wire evidence in
reports/m5-phase1b-batch3-sources-2026-10-10.json (each page's machine-readable time converts to the minute taken from it; EDGAR's acceptance time is recomputed from the archived SEC lists); their dry-run state is recoverable byte for byte; and a sealed run of them
with injected prices quarantines every one for want of an attestation, maps every one once attested, and prints no price."""
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
SOURCES = ROOT / "reports" / "m5-phase1b-batch3-sources-2026-10-10.json"
PERMISSION = ROOT / "reports" / "m5-phase1b-batch3-permission-2026-10-10.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
# (ticker, the release's date, the 8-K's filing date): PARR's release came the day before its 8-K was filed
BATCH_3 = [("OKTA", "2026-05-28", "2026-05-28"), ("VSAT", "2026-05-28", "2026-05-28"), ("LOVE", "2026-06-11", "2026-06-11"), ("HURN", "2026-07-28", "2026-07-28"), ("ALKT", "2026-07-29", "2026-07-29"), ("NBIX", "2026-07-30", "2026-07-30"),
           ("PARR", "2026-08-04", "2026-08-05"), ("VSAT", "2026-08-04", "2026-08-04"), ("CACI", "2026-08-05", "2026-08-05"), ("CXT", "2026-08-05", "2026-08-05")]
BATCH_3_IDS = ["%s-m5b-%s" % (ticker.lower(), day) for ticker, day, _ in BATCH_3]
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

    def test_the_message_the_question_and_the_answer_are_quoted_as_given(self):
        record = self.record
        self.assertEqual(record["owner_message"], {"text": "authorize batch 3", "at": "2026-10-10T13:03:39.862Z", "source": "session transcript, line 44586",
                                                   "read_as": "The go-ahead to ask the question about batch 3, as the report offered; it is not itself the permission to read pages."})
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-10T13:04:03.894Z", "session transcript, line 44599 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-10T13:04:08.433Z", "session transcript, line 44600 (the tool result of the question)"))
        self.assertLess(record["owner_message"]["at"], record["asked"]["at"])
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        qa = record["questions_and_answers"]
        self.assertEqual(len(qa), 1)
        self.assertEqual((qa[0]["header"], qa[0]["owner_selected"]), ("Wire pages 3", "Yes, batch 3 only (Recommended)"))
        self.assertEqual(qa[0]["question"], "May I read public wire-release pages and the issuers' own newsroom pages to take the first-public minute of the batch 3 releases (S4)?")
        self.assertEqual([o["label"] for o in qa[0]["options_offered"]], ["Yes, batch 3 only (Recommended)", "Yes, all 25 remaining candidates", "No downloads for now"])
        yes = qa[0]["options_offered"][0]["description"]
        self.assertIn("OKTA 05-28, VSAT 05-28, LOVE 06-11, HURN 07-28, ALKT 07-29, NBIX 07-30, PARR 08-04, VSAT 08-04, CACI 08-05, CXT 08-05", yes)
        for phrase in ("batch 1 took 42 page loads and batch 2 took 27, so expect 25 to 45", "No web-search tool, no price or quote page, no filing.", "No push, no other download. Later batches ask again."):
            self.assertIn(phrase, yes)
        for phrase in ("Batches 1 and 2 are complete (nineteen events attested, pinned and verified on a re-run).", "The owner's answer on batch 2's wire pages was \"Yes, batch 2 only (Recommended)\", whose option text said \"Later batches ask again.\"",
                       "The assistant's report offered batch 3 and said it would ask the exact question, with names, sources and size, before opening any page.", "quoted from the session transcript, not from a summary"):
            self.assertIn(phrase, record["context"])
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch3_permission", "2026-10-10"))

    def test_the_ten_are_the_ten_earliest_standing_candidates_outside_batches_1_and_2_recomputed_from_the_s2_records(self):
        excluded = {("REKR", "2026-07-15"), ("PAYO", "2026-08-06")}
        batch1 = {(b["ticker"], b["filing_date"]) for b in self.decisions["wire_permission_read_as"]["batch_1"]}
        batch2 = {(b["ticker"], b["filing_date"]) for b in self.batch_2_permission["permission_read_as"]["batch_2"]}
        remaining = sorted((r for r in self.review if (r["ticker"], r["filing_date"]) not in excluded | batch1 | batch2), key=lambda r: (r["release_date_in_the_filing"], r["ticker"]))
        self.assertEqual(len(remaining), 25)
        read_as = self.record["permission_read_as"]
        self.assertEqual(read_as["batch_3"], [{"ticker": r["ticker"], "filing_date": r["filing_date"], "release_date": r["release_date_in_the_filing"], "candidate_id": r["candidate_id"]} for r in remaining[:10]])
        self.assertEqual([(b["ticker"], b["release_date"], b["filing_date"]) for b in read_as["batch_3"]], BATCH_3)
        self.assertEqual(read_as["next_in_line"], ["ASPN 2026-08-06", "COLL 2026-08-06", "PDFS 2026-08-06"])
        self.assertTrue(all(r["assessment"] == "results_release_no_issue_found" for r in remaining[:10]))
        self.assertEqual([r["ticker"] for r in remaining[:10] if r["filing_date"] != r["release_date_in_the_filing"]], ["PARR"])
        for phrase in ("The ten earliest releases among the 25 candidates that stand and are in neither batch 1 nor batch 2", "ties broken alphabetically",
                       "All ten were assessed results_release_no_issue_found there; nine have a release date equal to the filing date, and PARR's release (2026-08-04) preceded its 8-K filing (2026-08-05) by a day."):
            self.assertIn(phrase, read_as["how_batch_3_was_chosen"])
        self.assertIn("Batch 3 only", read_as["scope"])
        self.assertIn("No web-search tool, no price or quote page, no filing.", read_as["scope"])
        self.assertIn("It carries no push and no other download; later batches ask again.", read_as["scope"])

    def test_it_says_what_the_answer_does_not_authorize(self):
        text = " ".join(self.record["not_authorized_by_this_answer"])
        for phrase in ("Reading the wire or newsroom pages of any candidate outside batch 3.", "Reading the near-date 8-Ks", "Using the web-search tool", "Any push, any other download, any price or label read, and attesting any event's first-public time, identity or corporate actions for the owner."):
            self.assertIn(phrase, text)
        self.assertIn("no page had been read when this was recorded", " ".join(self.record["not_a_claim"]))


class EventsAndSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(EVENTS)
        cls.all_events = cls.spec["events"]
        cls.earlier = cls.spec["events"][:19]
        cls.events = cls.spec["events"][19:]
        cls.record = load(SOURCES)
        cls.permission = load(PERMISSION)
        cls.ledger = {(c["ticker"], c["filing_date"]): c for c in load(ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json")["candidates"]}
        cls.review = {(r["ticker"], r["filing_date"]): r for r in load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]}
        cls.m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}
        cohort = load(ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json")["issuers"]
        metas = {meta["url"]: meta for meta in (load(path) for path in sorted(RAW.glob("*.json")))}
        cls.accepted = {}
        for issuer in cohort:
            recent = json.loads((RAW / metas[issuer["submissions_url"]]["raw_file"]).read_bytes())["filings"]["recent"]
            for i, accession in enumerate(recent["accessionNumber"]):
                cls.accepted[accession] = datetime.fromisoformat(recent["acceptanceDateTime"][i].replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")

    def test_the_ten_events_follow_the_nineteen_sealed_and_unattested_and_the_whole_file_validates(self):
        ea.validate_spec(self.spec, Calendar())
        self.assertEqual([e["event_id"] for e in self.events], BATCH_3_IDS)
        for event in self.events:
            with self.subTest(event=event["event_id"]):
                self.assertEqual(event["seal"], "hash_only")
                self.assertNotIn("attestations", event)                       # the dry-run state: the owner attests the batch after the sealed dry run and the signoff packet
                self.assertNotIn("recorded_result", event)
                self.assertNotIn("caveats", event)
                self.assertEqual(event["event_id"], event["cluster_id"])
                self.assertRegex(event["event_id"], r"^[a-z]+-m5b-2026-\d\d-\d\d$")
        for event in self.earlier:
            self.assertIn("attestations", event)                              # batches 1 and 2 are attested and pinned, and untouched by this step
            self.assertIn("recorded_result", event)
        self.assertEqual(len(self.all_events), 29)
        for path in (("event_id",), ("security", "security_id"), ("source", "source_id"), ("candidate_id",)):
            values = [e[path[0]] if len(path) == 1 else e[path[0]][path[1]] for e in self.all_events]
            self.assertEqual(len(set(values)), 29, path)

    def test_each_event_agrees_with_the_ledger_the_review_the_milestone_1_events_and_the_calendar(self):
        calendar = Calendar()
        by_id = {e["event_id"]: e for e in self.events}
        for ticker, day, filed in BATCH_3:
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
        self.assertEqual(sorted(e["security"]["ticker"] for e in self.events), sorted(t for t, _, _ in BATCH_3))

    def test_the_sources_rows_are_the_events_and_each_pages_machine_time_converts_to_the_minute_taken_from_it(self):
        rows = self.record["events"]
        self.assertEqual([r["event_id"] for r in rows], BATCH_3_IDS)
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
        said = {"okta-m5b-2026-05-28": "the neighbours are 2026-05-21 08:30 ET (a Forrester Wave recognition) and 2026-05-29 08:00 ET (a notice of conference presentations)",
                "vsat-m5b-2026-05-28": "GlobeNewswire lists this one only, and Business Wire carries no Viasat-issued release", "love-m5b-2026-06-11": "this is the only result",
                "hurn-m5b-2026-07-28": "the neighbours are 2026-07-14 09:05 ET (the notice of the earnings release and webcast) and, in the broader search, 2026-05-05 16:05 ET (first-quarter results)",
                "alkt-m5b-2026-07-29": "there is none from 2026-07-24 to 2026-07-28, and the next is 2026-07-30 10:00 ET (a partnership announcement)",
                "nbix-m5b-2026-07-30": "the only other result in that range is another company's release (2026-08-03 08:00 ET) that mentions the name",
                "parr-m5b-2026-08-04": "this is the only result", "vsat-m5b-2026-08-04": "this is the only result",
                "caci-m5b-2026-08-05": "the neighbours are 2026-07-30 (a contract award) and 2026-08-17 (a selection to modernize technology architectures)",
                "cxt-m5b-2026-08-05": "the 2026-08-04 notice of its participation in the Oppenheimer technology conference, the day before"}
        self.assertEqual(sorted(said), sorted(BATCH_3_IDS))
        for row in rows:
            self.assertIn(said[row["event_id"]], row["same_day_release_check"]["result"], row["event_id"])      # observations of the wire's own listings: they cannot be recomputed here, so they are pinned as recorded
        by_wire = {}
        for row in rows:
            by_wire.setdefault(row["wire"], []).append(row["event_id"])
        self.assertEqual(by_wire, {"Business Wire": ["okta-m5b-2026-05-28", "hurn-m5b-2026-07-28", "caci-m5b-2026-08-05"],
                                   "GlobeNewswire": ["vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "cxt-m5b-2026-08-05"],
                                   "PR Newswire": ["alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30"]})
        self.assertEqual({r["event_id"]: r["minute_et"] for r in rows}, {"okta-m5b-2026-05-28": "16:01", "vsat-m5b-2026-05-28": "16:05", "love-m5b-2026-06-11": "07:00", "hurn-m5b-2026-07-28": "16:05", "alkt-m5b-2026-07-29": "16:05",
                                                                          "nbix-m5b-2026-07-30": "16:01", "parr-m5b-2026-08-04": "16:53", "vsat-m5b-2026-08-04": "16:05", "caci-m5b-2026-08-05": "16:15", "cxt-m5b-2026-08-05": "16:05"})

    def test_no_caveat_is_carried_at_the_dry_run_and_the_notes_say_what_is_unusual(self):
        self.assertEqual(self.record["caveats_carried"], [])
        self.assertFalse([e["event_id"] for e in self.events if "caveats" in e])
        notes = " ".join(self.record["notes"])
        for phrase in ("PARR: the wire minute (2026-08-04 16:53 ET) is on the day before the 8-K's filing date (2026-08-05); the archived SEC list gives the 8-K's acceptance as 2026-08-04 21:37 ET, so the event follows the wire minute and EDGAR's acceptance is later than it, not earlier.",
                       "VSAT has two events in this batch (2026-05-28 and 2026-08-04), the fiscal fourth-quarter and first-quarter releases; each has its own event, candidate and release page."):
            self.assertIn(phrase, notes)
        parr = next(r for r in self.record["events"] if r["ticker"] == "PARR")
        self.assertEqual((parr["minute_et"], parr["edgar_acceptance_et"]), ("16:53", "2026-08-04 21:37"))
        self.assertEqual(self.ledger[("PARR", "2026-08-05")]["candidate_id"], parr["candidate_id"])

    def test_the_dry_run_state_of_the_ten_is_recoverable_byte_for_byte(self):
        events = json.loads(json.dumps(self.events))
        text = json.dumps({"events": events}, indent=2, ensure_ascii=False) + "\n"
        info = self.record["events_file"]
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), info["batch_3_events_sha256_in_the_dry_run_state"])
        self.assertEqual((info["path"], info["events"], info["batch_3_events"], info["batch_3_attestations"]), ("config/m5-phase1b-events.json", 29, 10, 0))
        self.assertEqual(info["seal"], "every event carries seal: hash_only")
        self.assertEqual(info["provider_attestation"], "reports/m5-phase1b-provider-scope-authorization-2026-10-09.json (the owner's recorded 'Yes, provider rights fine')")
        self.assertTrue((ROOT / "reports" / "m5-phase1b-provider-scope-authorization-2026-10-09.json").is_file())
        self.assertEqual(self.record["state"], "BATCH_3_SPECS_BUILT_DRY_RUN_PENDING")
        self.assertEqual((self.record["kind"], self.record["recorded_on"]), ("m5_phase1b_batch3_sources", "2026-10-10"))

    def test_it_states_what_was_read_what_went_wrong_and_what_it_is_not(self):
        record, reading = self.record, self.record["reading"]
        self.assertIn("holds the ten events built from it in the dry-run state after the nineteen of batches 1 and 2: sealed, no attestations, so each quarantines on FIRST_PUBLIC_TIME_UNVERIFIED until the owner attests it. Nothing here is a price, a return or a label.", record["purpose"])
        self.assertEqual((reading["page_loads_in_the_built_in_browser"], reading["web_searches"]), (25, 0))
        self.assertEqual(reading["by_host"], {"www.businesswire.com": 11, "www.globenewswire.com": 10, "www.prnewswire.com": 4})
        self.assertEqual(sum(reading["by_host"].values()), 25)
        for phrase in ("each issuer's wire is the one its earlier events in the repository used", "No filing was opened: EDGAR's acceptance times come from the archived SEC lists already in the repository.",
                       "Listings were read through short extractions of the dates, times and titles wanted, so as to see as little else as possible."):
            self.assertIn(phrase, reading["what"])
        for phrase in ("showed the headline, the time (2026-08-26 16:01 ET) and the first sentences of Okta's 2026-08-26 release, which is a candidate of a later batch", "I did not open that release's page and did not use what I saw",
                       "one dateline sentence of Lovesac's release that gives its quarter's net sales", "These are company-reported business content, not a price, a return or a label of any event."):
            self.assertIn(phrase, reading["what_was_seen_in_passing"])
        for phrase in ("Nothing was refused. Two Business Wire searches returned nothing, one wasted page load each", "the first Okta search used a wrong title", "'Viasat Reports' found nothing because Viasat's releases are on GlobeNewswire",
                       "On one CACI listing the date lines did not render (a dash)"):
            self.assertIn(phrase, reading["refused_or_missing"])
        permission = record["permission"]
        self.assertEqual((permission["record"], permission["answer"], permission["answered_at"], permission["read_as"]),
                         ("reports/m5-phase1b-batch3-permission-2026-10-10.json", "Yes, batch 3 only (Recommended)", self.permission["answered"]["at"], self.permission["permission_read_as"]["scope"]))
        text = " ".join(record["what_this_is_not"])
        for phrase in ("Not an attestation", "Not a proof that nothing earlier was public", "Not a price, a return or a label of any event: none was read; the sealed run prints none."):
            self.assertIn(phrase, text)
        self.assertIn("the nineteen pinned events of batches 1 and 2 are re-checked in the same run", record["next"])


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
    """Batch 3's ten events through the sealed run with a fake provider holding distinctive prices and no corporate actions: unattested they quarantine, attested in memory they map, and no price reaches the output."""

    def run_sealed(self, attested):
        calendar = Calendar()
        spec = load(EVENTS)
        spec["events"] = spec["events"][19:]
        for event in spec["events"]:
            if attested:
                event["attestations"] = {name: {"reviewer": "test", "date": "2026-10-10", "record": "reports/m5-phase1b-batch3-permission-2026-10-10.json"} for name in sorted(ea.ATTESTATIONS)}

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

    def test_unattested_the_ten_quarantine_on_the_attestation_alone_and_nothing_leaks(self):
        code, printed = self.run_sealed(attested=False)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"QUARANTINED": 10}))
        self.assertEqual(sorted(out["events"]), sorted(BATCH_3_IDS))
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

    def test_attested_in_memory_they_would_all_map_so_nothing_but_the_attestation_blocks_them(self):
        code, printed = self.run_sealed(attested=True)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"MAPPED": 10}))
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"]), ("MAPPED", []))
                self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
