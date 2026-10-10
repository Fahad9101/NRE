"""Milestone 5 Phase 1b batch 1 after the owner's signoff: config/m5-phase1b-events.json (nine sealed events; eight carry the owner's attestations and the packet's caveats, NBIX does not) validates with the project's own spec validation, agrees with the frozen
ledger, the eligibility review, the owner's decisions, the Milestone 1 events and the wire evidence in reports/m5-phase1b-batch1-sources-2026-10-09.json (each page's machine-readable time converts to the minute taken from it), its dry-run state is
recoverable byte for byte, and a sealed run of it with injected prices maps the eight, quarantines NBIX, prints no price and pins no commitment."""
import hashlib
import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "config" / "m5-phase1b-events.json"
SOURCES = ROOT / "reports" / "m5-phase1b-batch1-sources-2026-10-09.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")
BATCH_1 = [("CACI", "2026-04-22"), ("ALKT", "2026-04-29"), ("JBSS", "2026-04-29"), ("HURN", "2026-05-05"), ("NBIX", "2026-05-05"), ("PARR", "2026-05-05"), ("CXT", "2026-05-06"), ("ASPN", "2026-05-07"), ("COLL", "2026-05-07")]
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class EventsFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(EVENTS)
        cls.events = cls.spec["events"]
        cls.ledger = {(c["ticker"], c["filing_date"]): c for c in load(ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json")["candidates"]}
        cls.review = {(r["ticker"], r["filing_date"]): r for r in load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")["candidates"]}
        cls.decisions = load(ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json")
        cls.m1 = {e["security"]["ticker"]: e for e in load(ROOT / "config" / "m1-events.json")["events"]}

    def test_it_passes_the_projects_own_spec_validation_all_nine_events_are_attested_and_the_eight_the_sealed_run_mapped_are_pinned(self):
        ea.validate_spec(self.spec, Calendar())
        self.assertEqual(len(self.events), 9)
        for event in self.events:
            with self.subTest(event=event["event_id"]):
                self.assertEqual(event["seal"], "hash_only")
                self.assertIn("attestations", event)                          # the eight on 2026-10-09, NBIX on 2026-10-10 once the owner had seen the action its second dry run listed (tests/test_m5_phase1b_attestations.py)
                self.assertEqual("recorded_result" in event, event["security"]["ticker"] != "NBIX")    # a commitment is pinned for each event the attested sealed run mapped (tests/test_m5_phase1b_sealed_run.py); NBIX's is not printed yet
                self.assertEqual(event["event_id"], event["cluster_id"])
                self.assertRegex(event["event_id"], r"^[a-z]+-m5b-2026-\d\d-\d\d$")
        self.assertEqual(len({e["event_id"] for e in self.events}), 9)
        self.assertEqual(len({e["security"]["security_id"] for e in self.events}), 9)
        self.assertEqual(len({e["source"]["source_id"] for e in self.events}), 9)

    def test_the_provider_block_mirrors_step_3_and_names_the_owners_recorded_answer(self):
        provider = self.spec["provider"]
        step3 = load(ROOT / "config" / "m2-step3-events.json")["provider"]
        self.assertEqual({k: v for k, v in provider.items() if k != "attestation"}, {k: v for k, v in step3.items() if k != "attestation"})
        self.assertEqual(provider["attestation"], {"reviewer": "Fahad9101", "date": "2026-10-09", "record": "reports/m5-phase1b-provider-scope-authorization-2026-10-09.json"})
        record = load(ROOT / provider["attestation"]["record"])
        auth = load(ROOT / "reports" / "m5-phase1b-authorization-2026-10-09.json")
        rights = next(a for a in auth["owner_answers"] if a["header"] == "Rights")
        self.assertEqual(record["questions_and_answers"][0]["owner_selected"], "Yes, provider rights fine")
        self.assertEqual({k: record["questions_and_answers"][0][k] for k in ("question", "owner_selected", "asked_at", "answered_at", "source")}, {k: rights[k] for k in ("question", "owner_selected", "asked_at", "answered_at", "source")})
        self.assertIn("The question is put to the owner again before Phase 1c.", record["scope_of_this_authorization"])
        self.assertIn("it does not itself attest any event's first_public_time, historical_identity or corporate_actions", record["scope_of_this_authorization"])
        self.assertEqual(provider["research_permitted"], True)

    def test_the_events_are_the_frozen_candidates_the_decisions_name_minus_the_bell_ambiguous_one(self):
        batch = self.decisions["wire_permission_read_as"]["batch_1"]
        self.assertEqual([(b["ticker"], b["release_date"]) for b in batch if b["ticker"] != "ASMB"], BATCH_1)
        by_candidate = {e["candidate_id"]: e for e in self.events}
        self.assertEqual(set(by_candidate), {b["candidate_id"] for b in batch if b["ticker"] != "ASMB"})
        for ticker, day in BATCH_1:
            event = by_candidate[self.ledger[(ticker, day)]["candidate_id"]]
            with self.subTest(event=event["event_id"]):
                row = self.review[(ticker, day)]
                candidate = self.ledger[(ticker, day)]
                self.assertEqual((event["security"]["ticker"], event["security"]["cik"], event["security"]["company_id"]), (ticker, candidate["cik"], candidate["cik"]))
                self.assertEqual(event["published_at"][:10], row["release_date_in_the_filing"])
                self.assertEqual(event["security"]["exchange"], "NYSE" if row["exchange_on_cover_or_release"] == "New York Stock Exchange" else "NASDAQ")
                self.assertEqual(event["security"]["security_type"], "common_stock")
                self.assertEqual(event["security"]["security_id"], "%s-%d-%s" % (ticker, int(candidate["cik"]), event["published_at"][:10]))
                self.assertEqual(row["assessment"], "results_release_no_issue_found")
        self.assertNotIn("ASMB", {e["security"]["ticker"] for e in self.events})
        for gone in (("REKR", "2026-07-15"), ("PAYO", "2026-08-06")):
            self.assertNotIn(self.ledger[gone]["candidate_id"], by_candidate)

    def test_each_time_is_the_wire_pages_minute_and_the_calendar_agrees(self):
        calendar = Calendar()
        for event in self.events:
            with self.subTest(event=event["event_id"]):
                published = datetime.fromisoformat(event["published_at"])
                self.assertEqual(published.astimezone(ZONE).strftime("%H:%M"), event["timestamp_evidence"])
                self.assertIn("(%s ET)" % event["timestamp_evidence"], event["source"]["text"])
                self.assertIn(event["source"]["url"], event["source"]["text"])
                self.assertEqual(datetime.fromisoformat(event["cutoff"]) - published, timedelta(minutes=3))
                self.assertEqual(datetime.fromisoformat(event["source"]["first_seen_at"]) - published, timedelta(minutes=1))
                self.assertEqual(event["precision"], "minute")
                session, timing = calendar.classify(event["published_at"])
                self.assertEqual((timing, session), (event["expected_release_timing"], event["expected_reaction_session"]))
                self.assertEqual(timing, "premarket" if published.astimezone(ZONE).strftime("%H:%M") < "09:30" else "after_hours")
                host = event["source"]["url"].split("/")[2]
                self.assertIn(host, {"www.businesswire.com", "www.globenewswire.com", "www.prnewswire.com"})
                self.assertTrue(event["source"]["url"].startswith("https://"))

    def test_the_identity_start_is_the_previous_earnings_release_the_milestone_1_event(self):
        for event in self.events:
            with self.subTest(event=event["event_id"]):
                previous = self.m1[event["security"]["ticker"]]["published_at"][:10]
                self.assertLess(previous, event["published_at"][:10])
                self.assertTrue(event["security"]["valid_from"].startswith(previous + "T00:00:00-05:00"))
                self.assertEqual(event["security"]["available_at"], previous + "T20:00:00Z")

    def test_the_two_caveats_on_all_labels_are_the_ones_the_sources_record_names(self):
        caveated = {e["security"]["ticker"]: [c for c in e["caveats"] if c["labels"] == ["all"]] for e in self.events if any(c["labels"] == ["all"] for c in e.get("caveats", []))}
        self.assertEqual(set(caveated), {"ALKT", "NBIX"})
        self.assertIn("share repurchase program", caveated["ALKT"][0]["note"])
        self.assertIn("09:00 ET", caveated["NBIX"][0]["note"])
        for notes in caveated.values():
            self.assertEqual(len(notes), 1)
        for event in self.events:
            for caveat in event.get("caveats", []):
                self.assertLessEqual(set(caveat["labels"]), ea.LABEL_NAMES | {"all"})


class SourcesRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(SOURCES)
        cls.spec = load(EVENTS)
        cls.events = {e["event_id"]: e for e in cls.spec["events"]}
        cohort = load(ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json")["issuers"]
        metas = {meta["url"]: meta for meta in (load(path) for path in sorted(RAW.glob("*.json")))}
        cls.accepted = {}
        for issuer in cohort:
            recent = json.loads((RAW / metas[issuer["submissions_url"]]["raw_file"]).read_bytes())["filings"]["recent"]
            for i, accession in enumerate(recent["accessionNumber"]):
                cls.accepted[accession] = datetime.fromisoformat(recent["acceptanceDateTime"][i].replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")

    def test_its_rows_are_the_events_and_each_pages_machine_time_converts_to_the_minute_taken_from_it(self):
        rows = self.record["events"]
        self.assertEqual([r["event_id"] for r in rows], [e["event_id"] for e in self.spec["events"]])
        wires = {"www.businesswire.com": "Business Wire", "www.globenewswire.com": "GlobeNewswire", "www.prnewswire.com": "PR Newswire"}
        for row in rows:
            with self.subTest(event=row["event_id"]):
                event = self.events[row["event_id"]]
                self.assertEqual((row["candidate_id"], row["url"], row["minute_et"], row["published_at"], row["expected_release_timing"], row["expected_reaction_session"]),
                                 (event["candidate_id"], event["source"]["url"], event["timestamp_evidence"], event["published_at"], event["expected_release_timing"], event["expected_reaction_session"]))
                self.assertEqual(row["wire"], wires[row["url"].split("/")[2]])
                self.assertIn(row["displayed_stamp"], event["source"]["text"])
                machine = datetime.fromisoformat(row["page_machine_readable_time"].replace("Z", "+00:00"))
                self.assertEqual(machine.astimezone(ZONE).strftime("%H:%M"), row["minute_et"])
                self.assertEqual(machine.astimezone(ZONE).strftime("%Y-%m-%d"), row["release_date"])
                self.assertEqual(machine, datetime.fromisoformat(event["published_at"]))
                self.assertEqual(row["edgar_acceptance_et"], self.accepted[row["candidate_id"]])
                self.assertGreaterEqual(row["edgar_acceptance_et"][11:], row["minute_et"] if row["edgar_acceptance_et"][:10] == row["release_date"] else "")
                self.assertTrue(row["same_day_release_check"]["how"] and row["same_day_release_check"]["result"])
        nbix = next(r for r in rows if r["ticker"] == "NBIX")
        self.assertIn("2026-05-05 09:00 ET", nbix["same_day_release_check"]["result"])
        self.assertIn("a caveat, not an exclusion", nbix["same_day_release_check"]["result"])
        self.assertEqual([r["ticker"] for r in rows if "No other" not in r["same_day_release_check"]["result"]], ["NBIX"])

    def test_the_bell_ambiguous_candidate_is_recorded_with_its_precedents_and_left_for_the_owner(self):
        asmb = self.record["quarantined_before_the_spec"]
        decisions = load(ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json")
        batch = {b["ticker"]: b for b in decisions["wire_permission_read_as"]["batch_1"]}
        self.assertEqual((asmb["ticker"], asmb["candidate_id"], asmb["release_date"], asmb["displayed_stamp"]), ("ASMB", batch["ASMB"]["candidate_id"], "2026-05-07", "May 07, 2026 16:00 ET"))
        machine = datetime.fromisoformat(asmb["page_machine_readable_time"].replace("Z", "+00:00"))
        self.assertEqual(machine.astimezone(ZONE).strftime("%Y-%m-%d %H:%M"), "2026-05-07 16:00")
        self.assertEqual(asmb["edgar_acceptance_et"], self.accepted[asmb["candidate_id"]])
        calendar = Calendar()
        self.assertEqual(calendar.classify("2026-05-07T16:00:00-04:00"), ("2026-05-07", "bell_ambiguous"))                     # the instant of the close: the label engine's timing class
        self.assertNotIn(calendar.classify("2026-05-07T16:00:00-04:00")[1], ea.TIMINGS)
        self.assertIn("it needs the owner's word at the signoff", asmb["reason"])
        step2 = load(ROOT / "reports" / "m2-step2-reviewed-candidate-ledger.json")["candidates"]
        self.assertTrue(any(c["ticker"] == "PDFS" and c["filing_date"] == "2025-08-07" and c["disposition"] == "quarantined" and "bell_ambiguous" in c["reason"] for c in step2))
        self.assertTrue((ROOT / "docs" / "M1-READINESS-ASSESSMENT.md").is_file())

    def test_the_events_file_digest_is_the_dry_run_states(self):
        stripped = json.loads(EVENTS.read_text(encoding="utf-8"))
        for event in stripped["events"]:
            event.pop("attestations", None)
            event.pop("recorded_result", None)
            kept = [c for c in event.get("caveats", []) if c["labels"] == ["all"]]       # the signoff added only the caveats that name labels
            if kept:
                event["caveats"] = kept
            else:
                event.pop("caveats", None)
        text = json.dumps(stripped, indent=2, ensure_ascii=False) + "\n"
        info = self.record["events_file"]
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), info["sha256_in_the_dry_run_state"])
        self.assertEqual((info["path"], info["events"], info["attestations"]), ("config/m5-phase1b-events.json", 9, 0))
        self.assertEqual(self.record["state"], "BATCH_1_SPECS_BUILT_DRY_RUN_PENDING")

    def test_it_states_what_was_read_what_went_wrong_and_what_it_is_not(self):
        record = self.record
        reading = record["reading"]
        self.assertEqual((reading["page_loads_in_the_built_in_browser"], reading["web_searches"]), (42, 2))
        self.assertEqual(sum(reading["by_host"].values()), 42)
        self.assertEqual(reading["by_host"], {"investor.caci.com": 1, "jbssinc.com": 1, "www.businesswire.com": 14, "www.globenewswire.com": 19, "www.jbssinc.com": 1, "www.prnewswire.com": 5, "www.sec.gov": 1})
        self.assertIn("The first GlobeNewswire navigation was refused by the browser", reading["refused_or_missing"])
        exposure = record["disclosure_of_a_web_search_exposure"]
        for phrase in ("Its summary of the second contained Alkami's second-quarter share repurchases", "I computed it in passing (about $17)", "not an event's price, return or label", "The tool is not used again in Phase 1b"):
            self.assertIn(phrase, exposure)
        self.assertEqual(record["permission"]["answer"], "Yes, batch 1 only (Recommended)")
        self.assertIn("Batch 1 only", record["permission"]["read_as"])
        self.assertEqual(len(record["caveats_carried"]), 2)
        text = " ".join(record["what_this_is_not"])
        for phrase in ("Not an attestation", "Not a proof that nothing earlier was public",
                       "Not a price, a return or a label of any event: none was read (the one inadvertent exposure is disclosed above); the sealed run prints none."):
            self.assertIn(phrase, text)


class SealedRunSimulationTests(unittest.TestCase):
    """The shipped events file through the sealed run with a fake provider holding distinctive prices and no corporate actions. With the pins taken out the nine attested events map and no price reaches the output; with the pins in, the injected
    prices cannot reproduce a recorded commitment, so each of the eight pinned events reports the mismatch and nothing else, while NBIX, whose commitment is not pinned yet, maps and reports no match either way."""

    def run_sealed(self, pinned):
        calendar = Calendar()
        spec = load(EVENTS)
        if not pinned:
            for event in spec["events"]:
                event.pop("recorded_result", None)

        class Response:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, size=-1):
                return self.data

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

    def test_the_pins_catch_prices_that_are_not_the_recorded_ones_and_report_nothing_else(self):
        code, printed = self.run_sealed(pinned=True)
        out = json.loads(printed[0])
        self.assertEqual((code, out["all_ok"]), (2, False))
        recorded = {e["event_id"]: e["recorded_result"]["labels_sha256"] for e in load(EVENTS)["events"] if "recorded_result" in e}
        self.assertEqual(len(recorded), 8)
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                if event_id == "nbix-m5b-2026-05-05":
                    self.assertEqual((view["state"], view["labels_match_recorded"], "error" in view), ("MAPPED", None, False))
                else:
                    self.assertEqual((view["state"], view["labels_match_recorded"], view["error"]), ("MAPPED", False, "LABELS_DIFFER_FROM_RECORDED"))
                    self.assertNotEqual(view["labels_sha256"], recorded[event_id])
        self.assertIsNone(re.search(r"\d\.\d", "\n".join(printed)))
        self.assertTrue(printed[1].startswith("::error title=NRE sealed event acquisition::"))

    def test_the_attested_events_map_and_nothing_is_pinned_or_leaked(self):
        code, printed = self.run_sealed(pinned=False)
        self.assertEqual(code, 0)
        out = json.loads(printed[0])
        self.assertEqual((out["all_ok"], out["counts_by_state"]), (True, {"MAPPED": 9}))
        self.assertEqual(len(out["events"]), 9)
        for event_id, view in out["events"].items():
            with self.subTest(event=event_id):
                self.assertEqual((view["state"], view["reasons"]), ("MAPPED", []))
                self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")
                self.assertIsNone(view["labels_match_recorded"])                                  # the pins were taken out
                self.assertEqual((view["missing_sessions"], view["zero_volume_sessions"], view["corporate_actions"]), ([], [], []))
                self.assertEqual(view["window"]["required_sessions"], 21)
                self.assertTrue(view["access_check_passed"])
        everything = "\n".join(printed)
        self.assertIsNone(re.search(r"\d\.\d", everything))
        for fragment in ("7183.2941", "1000003", "AKTESTKEY123", "SECRETVALUE456"):
            self.assertNotIn(fragment, everything)
        self.assertTrue(printed[1].startswith("::notice title=NRE sealed event acquisition::"))


if __name__ == "__main__":
    unittest.main()
