"""Milestone 5 Phase 1b batch 2: the owner's permission to read the ten releases' wire pages (reports/m5-phase1b-batch2-permission-2026-10-10.json) is quoted as given and the ten are recomputed from the S2 records; the ten events appended to
config/m5-phase1b-events.json after batch 1's nine (sealed; attested on the owner's signoff, tests/test_m5_phase1b_batch2_attestations.py) validate with the project's own spec validation and agree with the frozen ledger, the eligibility review, the Milestone 1 events,
the calendar and the wire evidence in reports/m5-phase1b-batch2-sources-2026-10-10.json (each page's machine-readable time converts to the minute taken from it; EDGAR's acceptance time is recomputed from the archived SEC lists); their dry-run state is recoverable byte for
byte; and a sealed run of them with injected prices quarantines every one once the attestations are taken out, maps every one as shipped, and prints no price."""
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
SOURCES = ROOT / "reports" / "m5-phase1b-batch2-sources-2026-10-10.json"
PERMISSION = ROOT / "reports" / "m5-phase1b-batch2-permission-2026-10-10.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
BATCH_2 = [("PAYO", "2026-05-07"), ("PDFS", "2026-05-07"), ("REAL", "2026-05-07"), ("TECX", "2026-05-07"), ("LNSR", "2026-05-08"), ("REKR", "2026-05-11"), ("ACHV", "2026-05-12"), ("SLSN", "2026-05-12"), ("KLC", "2026-05-14"), ("TTWO", "2026-05-21")]
BATCH_2_IDS = ["%s-m5b-%s" % (ticker.lower(), day) for ticker, day in BATCH_2]
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}
ACHV = "achv-m5b-2026-05-12"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class PermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(PERMISSION)
        cls.review = load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]
        cls.decisions = load(ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json")

    def test_the_message_the_question_and_the_answer_are_quoted_as_given(self):
        record = self.record
        self.assertEqual(record["owner_message"], {"text": "authorize batch 2.", "at": "2026-10-10T10:53:36.037Z", "source": "session transcript, line 42589",
                                                   "read_as": "The go-ahead to ask the question about batch 2, as the report offered; it is not itself the permission to read pages."})
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-10T10:54:45.656Z", "session transcript, line 42614 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-10T11:00:12.497Z", "session transcript, line 42615 (the tool result of the question)"))
        self.assertLess(record["owner_message"]["at"], record["asked"]["at"])
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        qa = record["questions_and_answers"]
        self.assertEqual(len(qa), 1)
        self.assertEqual((qa[0]["header"], qa[0]["owner_selected"]), ("Wire pages 2", "Yes, batch 2 only (Recommended)"))
        self.assertEqual(qa[0]["question"], "May I read public wire-release pages and the issuers' own newsroom pages to take the first-public minute of the batch 2 releases (S4)?")
        self.assertEqual([o["label"] for o in qa[0]["options_offered"]], ["Yes, batch 2 only (Recommended)", "Yes, all 35 remaining candidates", "No downloads for now"])
        yes = qa[0]["options_offered"][0]["description"]
        self.assertIn("PAYO 05-07, PDFS 05-07, REAL 05-07, TECX 05-07, LNSR 05-08, REKR 05-11, ACHV 05-12, SLSN 05-12, KLC 05-14, TTWO 05-21", yes)
        for phrase in ("batch 1 took 42 page loads, so expect 40 to 50", "No web-search tool, no price or quote page, no filing.", "No push, no other download. Later batches ask again."):
            self.assertIn(phrase, yes)
        self.assertIn("quoted from the session transcript, not from a summary", record["context"])
        self.assertIn("Later batches ask again.", record["context"])
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch2_permission", "2026-10-10"))

    def test_the_ten_are_the_ten_earliest_standing_candidates_outside_batch_1_recomputed_from_the_s2_records(self):
        excluded = {("REKR", "2026-07-15"), ("PAYO", "2026-08-06")}
        batch1 = {(b["ticker"], b["filing_date"]) for b in self.decisions["wire_permission_read_as"]["batch_1"]}
        remaining = sorted((r for r in self.review if (r["ticker"], r["filing_date"]) not in excluded | batch1), key=lambda r: (r["release_date_in_the_filing"], r["ticker"]))
        self.assertEqual(len(remaining), 35)
        read_as = self.record["permission_read_as"]
        self.assertEqual(read_as["batch_2"], [{"ticker": r["ticker"], "filing_date": r["filing_date"], "release_date": r["release_date_in_the_filing"], "candidate_id": r["candidate_id"]} for r in remaining[:10]])
        self.assertEqual([(b["ticker"], b["release_date"]) for b in read_as["batch_2"]], BATCH_2)
        self.assertEqual(read_as["next_in_line"], ["OKTA 2026-05-28", "VSAT 2026-05-28", "LOVE 2026-06-11"])
        self.assertTrue(all(r["assessment"] == "results_release_no_issue_found" and r["filing_date"] == r["release_date_in_the_filing"] for r in remaining[:10]))
        for phrase in ("The ten earliest releases among the 35 candidates that stand and are not in batch 1", "ties broken alphabetically", "All ten were assessed results_release_no_issue_found there, and each release date equals its filing date."):
            self.assertIn(phrase, read_as["how_batch_2_was_chosen"])
        self.assertIn("Batch 2 only", read_as["scope"])
        self.assertIn("No web-search tool, no price or quote page, no filing.", read_as["scope"])
        self.assertIn("It carries no push and no other download; later batches ask again.", read_as["scope"])

    def test_it_says_what_the_answer_does_not_authorize(self):
        text = " ".join(self.record["not_authorized_by_this_answer"])
        for phrase in ("Reading the wire or newsroom pages of any candidate outside batch 2.", "Reading the nine near-date 8-Ks", "Using the web-search tool", "Any push, any other download, any price or label read, and attesting any event's first-public time, identity or corporate actions for the owner."):
            self.assertIn(phrase, text)
        self.assertIn("no page had been read when this was recorded", " ".join(self.record["not_a_claim"]))


class EventsAndSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(EVENTS)
        cls.all_events = cls.spec["events"]
        cls.events = cls.spec["events"][9:]
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

    def test_the_ten_events_follow_batch_1_sealed_attested_and_pinned_and_the_whole_file_validates(self):
        ea.validate_spec(self.spec, Calendar())
        self.assertEqual([e["event_id"] for e in self.events], BATCH_2_IDS)
        for event in self.events:
            with self.subTest(event=event["event_id"]):
                self.assertEqual(event["seal"], "hash_only")
                self.assertIn("attestations", event)                          # the owner attested the batch after its dry run and signoff packet
                self.assertIn("recorded_result", event)                       # and each commitment was pinned after the attested sealed run printed it (tests/test_m5_phase1b_batch2_sealed_run.py)
                self.assertEqual(event["event_id"], event["cluster_id"])
                self.assertRegex(event["event_id"], r"^[a-z]+-m5b-2026-\d\d-\d\d$")
        self.assertEqual(len(self.all_events), 19)
        for path in (("event_id",), ("security", "security_id"), ("source", "source_id"), ("candidate_id",)):
            values = [e[path[0]] if len(path) == 1 else e[path[0]][path[1]] for e in self.all_events]
            self.assertEqual(len(set(values)), 19, path)

    def test_each_event_agrees_with_the_ledger_the_review_the_milestone_1_events_and_the_calendar(self):
        calendar = Calendar()
        for ticker, day in BATCH_2:
            event = next(e for e in self.events if e["security"]["ticker"] == ticker)
            with self.subTest(event=event["event_id"]):
                candidate, row = self.ledger[(ticker, day)], self.review[(ticker, day)]
                self.assertEqual(event["candidate_id"], candidate["candidate_id"])
                self.assertEqual((event["security"]["cik"], event["security"]["company_id"]), (candidate["cik"], candidate["cik"]))
                self.assertEqual(event["published_at"][:10], row["release_date_in_the_filing"])
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

    def test_the_sources_rows_are_the_events_and_each_pages_machine_time_converts_to_the_minute_taken_from_it(self):
        rows = self.record["events"]
        self.assertEqual([r["event_id"] for r in rows], BATCH_2_IDS)
        wires = {"www.businesswire.com": "Business Wire", "www.globenewswire.com": "GlobeNewswire", "www.prnewswire.com": "PR Newswire"}
        by_event = {e["event_id"]: e for e in self.events}
        for row in rows:
            with self.subTest(event=row["event_id"]):
                event = by_event[row["event_id"]]
                self.assertEqual((row["candidate_id"], row["url"], row["minute_et"], row["published_at"], row["expected_release_timing"], row["expected_reaction_session"]),
                                 (event["candidate_id"], event["source"]["url"], event["timestamp_evidence"], event["published_at"], event["expected_release_timing"], event["expected_reaction_session"]))
                self.assertEqual(row["wire"], wires[row["url"].split("/")[2]])
                self.assertIn(row["displayed_stamp"], event["source"]["text"])
                machine = datetime.fromisoformat(row["page_machine_readable_time"].replace("Z", "+00:00"))
                self.assertEqual(machine.astimezone(ZONE).strftime("%H:%M"), row["minute_et"])
                self.assertEqual(machine.astimezone(ZONE).strftime("%Y-%m-%d"), row["release_date"])
                self.assertEqual(machine.replace(second=0), datetime.fromisoformat(event["published_at"]))      # the page may carry seconds; the spec keeps the minute
                self.assertEqual(row["edgar_acceptance_et"], self.accepted[row["candidate_id"]])
                self.assertGreaterEqual(row["edgar_acceptance_et"][11:], row["minute_et"] if row["edgar_acceptance_et"][:10] == row["release_date"] else "")
                self.assertTrue(row["same_day_release_check"]["how"] and row["same_day_release_check"]["result"])
        self.assertEqual([r["ticker"] for r in rows if not r["same_day_release_check"]["result"].startswith("No other")], ["ACHV"])
        said = {"PAYO": "PR Newswire lists this one release between 2026-05-04 and 2026-05-12", "PDFS": "GlobeNewswire lists this one", "REAL": "another company's (ThredUp, 2026-05-06 09:15 ET)", "TECX": "this is the only result", "LNSR": "this is the only result",
                "REKR": "this is the only result", "SLSN": "this is the only result", "KLC": "the neighbours are 2026-05-04 08:37 ET and 2026-06-05 08:25 ET",
                "TTWO": "the neighbours are 2026-05-11 08:00 ET (a conference presentation) and 2026-06-24 06:15 ET (a Rockstar Games release)"}
        for row in rows:
            if row["ticker"] in said:
                self.assertIn(said[row["ticker"]], row["same_day_release_check"]["result"], row["ticker"])      # observations of the wire's own listings: they cannot be recomputed here, so they are pinned as recorded
        achv = next(r for r in rows if r["ticker"] == "ACHV")["same_day_release_check"]["result"]
        for phrase in ("One other release the same day: 2026-05-12 07:05 ET (machine-readable 2026-05-12T11:05:00Z), five minutes after the results release", "three senior leadership appointments", "the policy's third condition fails",
                       "a caveat, not an exclusion; the owner decides at the signoff."):
            self.assertIn(phrase, achv)
        by_wire = {}
        for row in rows:
            by_wire.setdefault(row["wire"], []).append(row["ticker"])
        self.assertEqual(by_wire, {"PR Newswire": ["PAYO"], "GlobeNewswire": ["PDFS", "REAL", "TECX", "LNSR", "REKR", "ACHV", "SLSN"], "Business Wire": ["KLC", "TTWO"]})

    def test_the_one_caveat_carried_at_the_dry_run_is_achvs_and_the_signoff_added_only_filings(self):
        carried = {e["security"]["ticker"]: [c for c in e["caveats"] if not c["note"].startswith("8-K ")] for e in self.events if any(not c["note"].startswith("8-K ") for c in e.get("caveats", []))}
        self.assertEqual(list(carried), ["ACHV"])                                      # every caveat the signoff added names an 8-K (REKR's Item 3.01 filing or an in-window filing)
        caveat = carried["ACHV"]
        self.assertEqual([c["labels"] for c in caveat], [["all"]])
        self.assertIn("The results release itself also reports the close of a private placement of up to $354 million and leadership changes", caveat[0]["note"])
        self.assertIn("A separate GlobeNewswire release five minutes later (07:05 ET) announced three senior leadership appointments", caveat[0]["note"])
        self.assertIn("is a caveat, not an exclusion", caveat[0]["note"])
        self.assertLessEqual(set(caveat[0]["labels"]), ea.LABEL_NAMES | {"all"})
        self.assertEqual(len(self.record["caveats_carried"]), 1)

    def test_the_dry_run_state_of_the_ten_is_recoverable_byte_for_byte(self):
        events = json.loads(json.dumps(self.events))
        for event in events:
            event.pop("attestations", None)
            event.pop("recorded_result", None)
            kept = [c for c in event.get("caveats", []) if not c["note"].startswith("8-K ")]       # the signoff added only caveats that name a filing (REKR's has labels "all", so the labels cannot tell them apart)
            if kept:
                event["caveats"] = kept
            else:
                event.pop("caveats", None)
        text = json.dumps({"events": events}, indent=2, ensure_ascii=False) + "\n"
        info = self.record["events_file"]
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), info["batch_2_events_sha256_in_the_dry_run_state"])
        self.assertEqual((info["path"], info["events"], info["batch_2_events"], info["batch_2_attestations"]), ("config/m5-phase1b-events.json", 19, 10, 0))
        self.assertEqual(self.record["state"], "BATCH_2_SPECS_BUILT_DRY_RUN_PENDING")
        self.assertEqual((self.record["kind"], self.record["recorded_on"]), ("m5_phase1b_batch2_sources", "2026-10-10"))

    def test_it_states_what_was_read_what_went_wrong_and_what_it_is_not(self):
        record, reading = self.record, self.record["reading"]
        self.assertIn("holds the ten events built from it in the dry-run state after batch 1's nine: sealed, no attestations, so each quarantines on FIRST_PUBLIC_TIME_UNVERIFIED until the owner attests it. Nothing here is a price, a return or a label.", record["purpose"])
        self.assertEqual((reading["page_loads_in_the_built_in_browser"], reading["web_searches"]), (27, 0))
        self.assertEqual(reading["by_host"], {"www.businesswire.com": 9, "www.globenewswire.com": 16, "www.prnewswire.com": 2})
        self.assertEqual(sum(reading["by_host"].values()), 27)
        self.assertIn("No filing was opened: EDGAR's acceptance times come from the archived SEC lists already in the repository.", reading["what"])
        for phrase in ("company-reported business content (guidance, placements, revenue and bookings figures), not a price, a return or a label of any event", "the first 2,600 characters of its text"):
            self.assertIn(phrase, reading["what_was_seen_in_passing"])
        self.assertIn("Business Wire's search with the phrase inside quotation marks returned its unfiltered latest list", reading["refused_or_missing"])
        self.assertIn("Payoneer's release is on PR Newswire", reading["refused_or_missing"])
        permission = record["permission"]
        self.assertEqual((permission["record"], permission["answer"], permission["answered_at"], permission["read_as"]),
                         ("reports/m5-phase1b-batch2-permission-2026-10-10.json", "Yes, batch 2 only (Recommended)", self.permission["answered"]["at"], self.permission["permission_read_as"]["scope"]))
        text = " ".join(record["what_this_is_not"])
        for phrase in ("Not an attestation", "Not a proof that nothing earlier was public", "Not a price, a return or a label of any event: none was read; the sealed run prints none."):
            self.assertIn(phrase, text)
        self.assertIn("batch 1's nine pinned events are re-checked in the same run", record["next"])


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
    """Batch 2's ten events through the sealed run with a fake provider holding distinctive prices and no corporate actions: with the attestations taken out they quarantine, with the pins taken out they map, as shipped the pins catch the injected prices, and no price
    reaches the output."""

    def run_sealed(self, attested, pinned=False):
        calendar = Calendar()
        spec = load(EVENTS)
        spec["events"] = spec["events"][9:]
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

    def test_unattested_the_ten_quarantine_on_the_attestation_alone_and_nothing_leaks(self):
        code, printed = self.run_sealed(attested=False)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"QUARANTINED": 10}))
        self.assertEqual(sorted(out["events"]), sorted(BATCH_2_IDS))
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
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"MAPPED": 10}))
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"], view["labels_match_recorded"]), ("MAPPED", [], None))
                self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")

    def test_as_shipped_each_pin_catches_the_injected_prices_and_nothing_else_is_reported(self):
        code, printed = self.run_sealed(attested=True, pinned=True)
        out = json.loads(printed[0])
        self.assertEqual((code, out["all_ok"]), (2, False))
        recorded = {e["event_id"]: e["recorded_result"]["labels_sha256"] for e in load(EVENTS)["events"][9:]}
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["labels_match_recorded"], view["error"]), ("MAPPED", False, "LABELS_DIFFER_FROM_RECORDED"))
                self.assertNotEqual(view["labels_sha256"], recorded[event_id])
        self.assertIsNone(re.search(r"\d\.\d", "\n".join(printed)))


if __name__ == "__main__":
    unittest.main()
