"""The Milestone 5 Phase 1b candidate pool as frozen on 2026-10-09 (config/m5-phase1b-frozen-*.json, reports/m5-phase1b-sec-cohort-freeze.json, archive/m5-phase1b-sec-freeze) and the record of how it was produced
(reports/m5-phase1b-sec-cohort-freeze-result-2026-10-09.json): the three files agree with each other and with the pre-registered protocol, every candidate is re-derived from the archived SEC data with the project's own
screening code, and the record's figures and claims are the files'."""
import json
import re
import unittest
from collections import Counter
from pathlib import Path

from nre.cohort import relevant_history_files, screen_item_202
from nre.core import canonical, digest
from nre.ingestion import sec_candidates

ROOT = Path(__file__).resolve().parent.parent
COHORT = ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json"
LEDGER = ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json"
REPORT = ROOT / "reports" / "m5-phase1b-sec-cohort-freeze.json"
RESULT = ROOT / "reports" / "m5-phase1b-sec-cohort-freeze-result-2026-10-09.json"
SPEC = ROOT / "config" / "m5-phase1b-cohort-spec.json"
PROTOCOL = ROOT / "config" / "m5-phase1b-protocol.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
TRANSPORT = "built_in_browser_8k_subset"
REPRESENTATION = "browser_fetched_8k_filtered_subset"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class FrozenPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cohort, cls.ledger, cls.report = load(COHORT), load(LEDGER), load(REPORT)
        cls.spec, cls.protocol = load(SPEC), load(PROTOCOL)
        cls.candidates = cls.ledger["candidates"]
        cls.metas = {path.name: load(path) for path in sorted(RAW.glob("*.json"))}

    def test_the_three_frozen_files_agree_with_each_other_and_with_the_pre_registered_protocol(self):
        cohort, ledger, report, spec, protocol = self.cohort, self.ledger, self.report, self.spec, self.protocol
        self.assertEqual(report["state"], "FROZEN_CANDIDATE_MEMBERSHIP")
        self.assertIs(report["price_data_accessed_by_this_workflow"], False)
        self.assertEqual(len({cohort["frozen_at"], ledger["frozen_at"], report["frozen_at"]}), 1)
        self.assertEqual(report["frozen_at"], "2026-10-09T08:49:17.983908Z")
        self.assertEqual(cohort["protocol_sha256"], digest(canonical(protocol)))
        self.assertEqual(ledger["protocol_sha256"], cohort["protocol_sha256"])
        self.assertEqual(spec["protocol_sha256"], cohort["protocol_sha256"])
        self.assertEqual((cohort["selection_mode"], report["selection_mode"]), ("fixed_issuer_set", "fixed_issuer_set"))
        self.assertEqual((report["filing_screen"], report["event_window"]), ([spec["filing_screen_start"], spec["filing_screen_end"]], [protocol["event_window_start"], protocol["event_window_end"]]))
        self.assertEqual(report["sec_transport"], TRANSPORT)
        self.assertEqual((cohort["processed_issuers"], len(cohort["issuers"]), report["processed_issuers"]), (23, 23, 23))
        self.assertEqual((report["candidate_count"], len(self.candidates), report["issuers_with_item_2_02_candidates"]), (47, 47, 23))
        membership = [{"candidate_id": c["candidate_id"], "source_sha256": c["source_sha256"]} for c in self.candidates]
        self.assertEqual(digest(canonical(membership)), ledger["membership_sha256"])
        self.assertEqual(ledger["membership_sha256"], report["membership_sha256"])
        self.assertEqual(report["membership_sha256"], "94312b6624bac9e742d94970454d4f045df62b986a5d3a90ab153964dc331d04")
        ids = [c["candidate_id"] for c in self.candidates]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), len(ids))
        self.assertIn("No clean-cohort market prices were accessed by this step.", report["limitations"])

    def test_every_candidate_is_an_earnings_item_filed_in_the_window_by_one_of_the_23_issuers(self):
        spec, cohort = self.spec, self.cohort
        issuers = {i["cik"]: i["ticker"] for i in spec["issuers"]}
        self.assertEqual({i["cik"] for i in cohort["issuers"]}, set(issuers))
        self.assertEqual([i["cik"] for i in cohort["issuers"]], sorted(issuers))                     # processed in CIK order
        self.assertEqual([i["selection_position"] for i in cohort["issuers"]], list(range(1, 24)))
        for candidate in self.candidates:
            with self.subTest(candidate=candidate["candidate_id"]):
                self.assertIn(candidate["cik"], issuers)
                self.assertEqual(candidate["ticker"], issuers[candidate["cik"]])
                self.assertTrue(spec["filing_screen_start"] <= candidate["filing_date"] <= spec["filing_screen_end"])
                self.assertIn(candidate["form"], spec["allowed_forms"])
                self.assertIn("2.02", candidate["items"])
                self.assertRegex(candidate["candidate_id"], r"^\d{10}-\d{2}-\d{6}$")
                self.assertEqual((candidate["primary_review_state"], candidate["primary_source_sha256"]), ("REQUIRED_POST_FREEZE", None))
                self.assertEqual(candidate["discovery_submission_representation"], REPRESENTATION)
                self.assertEqual(candidate["source_sha256"], candidate["discovery_submission_sha256"])
                self.assertTrue(candidate["primary_url"].startswith("https://www.sec.gov/Archives/edgar/data/"))
        for issuer in cohort["issuers"]:
            mine = [c for c in self.candidates if c["cik"] == issuer["cik"]]
            self.assertEqual(sorted(issuer["candidate_ids"]), sorted(c["candidate_id"] for c in mine))
            self.assertEqual((issuer["item_2_02_candidates"], issuer["observations"]), (len(mine), 1))
            self.assertEqual({c["source_sha256"] for c in mine}, {issuer["submissions_sha256"]})
            self.assertEqual(issuer["submissions_url"], "https://data.sec.gov/submissions/CIK%s.json" % issuer["cik"])

    def test_the_archive_holds_the_sec_data_the_freeze_hashed(self):
        self.assertEqual((len(list(RAW.glob("*.raw"))), len(self.metas)), (23, 23))
        spec_start = self.spec["filing_screen_start"]
        urls = set()
        for name, meta in self.metas.items():
            with self.subTest(meta=name):
                payload = (RAW / meta["raw_file"]).read_bytes()
                self.assertEqual((digest(payload), len(payload)), (meta["sha256"], meta["size"]))
                self.assertEqual(meta["raw_file"], meta["sha256"] + ".raw")
                self.assertEqual(name, digest(canonical(meta)) + ".json")                             # observations are named by the hash of their own record
                self.assertRegex(meta["url"], r"^https://data\.sec\.gov/submissions/CIK\d{10}\.json$")
                self.assertEqual(meta["source_representation"], REPRESENTATION)
                self.assertRegex(meta["real_source_full_sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(meta["real_source_full_size"], meta["size"])
                self.assertTrue("2026-10-09T08:12:26" <= meta["retrieved_at"] <= "2026-10-09T08:12:36")
                urls.add(meta["url"])
                document = json.loads(payload)
                recent = document["filings"]["recent"]
                self.assertTrue(set(recent["form"]) <= {"8-K", "8-K/A"})
                self.assertTrue(all(day >= "2026-03-01" for day in recent["filingDate"]))
        self.assertEqual(urls, {i["submissions_url"] for i in self.cohort["issuers"]})

    def test_every_candidate_is_re_derived_from_the_archived_data_with_the_projects_own_screen(self):
        by_issuer = {i["cik"]: i for i in self.cohort["issuers"]}
        metas = {meta["url"]: meta for meta in self.metas.values()}
        rederived = []
        for cik, issuer in by_issuer.items():
            meta = metas[issuer["submissions_url"]]
            document = json.loads((RAW / meta["raw_file"]).read_bytes())
            self.assertEqual(str(document["cik"]).zfill(10), cik)
            self.assertEqual(relevant_history_files(document, self.spec["filing_screen_start"], meta["retrieved_at"]), [])      # no continuation file was needed
            rows = screen_item_202(sec_candidates(document, cik)["candidates"], self.spec["filing_screen_start"], self.spec["filing_screen_end"])
            self.assertEqual(sorted(r["candidate_id"] for r in rows), sorted(issuer["candidate_ids"]), issuer["ticker"])
            rederived += [r["candidate_id"] for r in rows]
            for row in rows:
                frozen = next(c for c in self.candidates if c["candidate_id"] == row["candidate_id"])
                self.assertEqual((frozen["filing_date"], frozen["form"], frozen["items"], frozen["primary_url"]), (row["filing_date"], row["form"], row["items"], row["url"]))
        self.assertEqual(sorted(rederived), [c["candidate_id"] for c in self.candidates])

    def test_the_pool_does_not_overlap_the_earlier_ones_and_holds_no_price_or_label(self):
        mine = {c["candidate_id"] for c in self.candidates}
        for name in ("m1-frozen-candidate-ledger.json", "m2-step2-frozen-candidate-ledger.json", "m2-step3-frozen-candidate-ledger.json"):
            self.assertFalse(mine & {c["candidate_id"] for c in load(ROOT / "config" / name)["candidates"]}, name)
        forbidden = {"open", "high", "low", "close", "volume", "price", "return", "label", "labels", "o", "h", "l", "c", "v"}

        def keys(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from keys(value)
            elif isinstance(node, list):
                for item in node:
                    yield from keys(item)
        for data in (self.cohort, self.ledger, self.report):
            self.assertEqual(forbidden & set(keys(data)), set())

    def test_what_the_review_will_have_to_look_at_is_there(self):
        amendments = [(c["ticker"], c["filing_date"]) for c in self.candidates if c["form"] == "8-K/A"]
        self.assertEqual(amendments, [("ASMB", "2026-08-14")])
        rekr = sorted((c["filing_date"], tuple(c["items"])) for c in self.candidates if c["ticker"] == "REKR")
        self.assertEqual(rekr, [("2026-05-11", ("2.02", "9.01")), ("2026-07-15", ("2.02", "7.01", "9.01")), ("2026-08-13", ("2.02", "9.01"))])
        self.assertEqual(max(c["filing_date"] for c in self.candidates), self.spec["filing_screen_end"])
        self.assertEqual([c["ticker"] for c in self.candidates if c["filing_date"] == self.spec["filing_screen_end"]], ["LOVE"])
        self.assertEqual(Counter(Counter(c["ticker"] for c in self.candidates).values()), Counter({2: 22, 3: 1}))


class ResultRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RESULT)
        cls.ledger, cls.report, cls.cohort = load(LEDGER), load(REPORT), load(COHORT)

    def test_it_quotes_the_owners_permission_and_the_request_it_answers(self):
        record = self.record
        permission = record["owner_permission"]
        answer, request = permission["owner_answer"], permission["assistant_request"]
        self.assertEqual((answer["text"], answer["at"]), ("yes, use the browser route", "2026-10-09T08:45:35.879Z"))
        self.assertIn("line 38046", answer["source"])
        self.assertLess(request["at"], answer["at"])
        self.assertTrue(request["text"].startswith("`41bb2da` is pushed and the main CI run is green, but the SEC freeze failed and nothing was written."))
        for phrase in ("I need your permission before I download the SEC files by another route.", "`data.sec.gov/submissions/CIK##########.json` for the 23 issuers, public SEC filing lists.",
                       "20 to 163 KB each, about 3.0 MB in all, held in browser memory only.", "about 34 KB of 8-K rows plus each file's SHA-256, archived in the repo exactly as step 3 did.",
                       "**Recommended next step:** say yes to the browser download."):
            self.assertIn(phrase, request["text"])
        self.assertIn("It carries no push and no other download.", permission["read_as"])
        self.assertEqual((record["kind"], record["recorded_on"], record["state"], record["transport"]), ("m5_phase1b_sec_cohort_freeze_result", "2026-10-09", "FROZEN_CANDIDATE_MEMBERSHIP", TRANSPORT))

    def test_its_figures_are_the_frozen_files(self):
        record, ledger, report = self.record, self.ledger, self.report
        output = record["computed_output"]
        dates = sorted(c["filing_date"] for c in ledger["candidates"])
        self.assertEqual(output, {"processed_issuers": report["processed_issuers"], "candidate_count": report["candidate_count"], "issuers_with_item_2_02_candidates": report["issuers_with_item_2_02_candidates"],
                                  "membership_sha256": report["membership_sha256"], "frozen_at": report["frozen_at"], "filing_date_range": [dates[0], dates[-1]],
                                  "protocol_window": report["event_window"], "forms": dict(sorted(Counter(c["form"] for c in ledger["candidates"]).items())),
                                  "candidates_per_issuer": {i["ticker"]: i["item_2_02_candidates"] for i in self.cohort["issuers"]}})
        self.assertEqual((output["candidate_count"], output["filing_date_range"], output["forms"]), (47, ["2026-04-22", "2026-09-10"], {"8-K": 46, "8-K/A": 1}))
        self.assertEqual(record["commit_of_the_rules"], "41bb2da")
        self.assertEqual(record["files"]["frozen"], ["config/m5-phase1b-frozen-issuer-cohort.json", "config/m5-phase1b-frozen-candidate-ledger.json", "reports/m5-phase1b-sec-cohort-freeze.json"])
        for path in record["files"]["frozen"]:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_the_failed_ci_attempt_is_described_as_far_as_it_is_known(self):
        attempt = self.record["ci_attempt"]
        self.assertEqual((attempt["run_id"], attempt["job_id"], attempt["attempt"], attempt["conclusion"]), (37902514638, 113728118678, 1, "failure"))
        self.assertTrue(attempt["commit"].startswith("41bb2da") and len(attempt["commit"]) == 40)
        self.assertIn("within the same second (2026-10-09T08:05:17Z)", attempt["failed_step"])
        self.assertIn("so nothing was written and no frozen file existed on main", attempt["steps_after_it"])
        self.assertIn("not read", attempt["log"])
        evidence = " ".join(attempt["why_the_sec_is_the_cause"])
        for phrase in ("failed in under a second", "Your Request Originates from an Undeclared Automated Tool", "6 of 6 GitHub Actions attempts"):
            self.assertIn(phrase, evidence)
        blocked = " ".join(json.dumps(load(ROOT / "reports" / "m2-step3-sec-cohort-freeze-blocked-2026-09-30.json")).split())
        self.assertIn("HTTP_403", blocked)
        step3 = load(ROOT / "reports" / "m2-step3-sec-cohort-freeze-result-2026-10-01.json")
        self.assertEqual(step3["transport"], "built_in_browser_offline_reprocessed")
        self.assertIn("6/6 real dispatches", " ".join(step3["how_this_differs_from_every_other_real_freeze_in_this_project"].split()))
        workflow = (ROOT / ".github" / "workflows" / "m5-phase1b-sec-cohort-freeze.yml").read_text(encoding="utf-8")
        self.assertIn("run 37902514638", workflow)

    def test_the_integrity_claims_are_the_archives(self):
        integrity = self.record["real_data_integrity"]
        sizes = sorted(path.stat().st_size for path in RAW.glob("*.raw"))
        self.assertEqual((sizes[0], sizes[-1]), (976, 1874))
        self.assertIn("those subsets are 976 to 1,874 bytes", integrity["subset"])
        self.assertIn("c64357e9dbce19b882684a3cc40c7a51f6b04f02c695bd9576a390207ac3edc7", integrity["transfer"])
        self.assertIn("(23 lines, 21,660 characters,", integrity["transfer"])
        self.assertIn("The first copy failed that check on 4 of the 23 lines (copying errors by the assistant)", integrity["transfer"])
        self.assertIn("(2026-10-09T08:11:38Z to 08:11:51Z, then 08:12:26Z to 08:12:35Z) with byte-identical SHA-256 hashes both times", integrity["stability"])
        retrieved = sorted(json.loads(path.read_text(encoding="utf-8"))["retrieved_at"] for path in RAW.glob("*.json"))
        self.assertEqual((retrieved[0][:19], retrieved[-1][:19]), ("2026-10-09T08:12:26", "2026-10-09T08:12:35"))
        self.assertIn("retrieved between 2026-10-09T08:12:26Z and 08:12:35Z", integrity["recency"])
        self.assertIn("never a hash of SEC's complete response", integrity["subset"])

    def test_the_figures_the_owner_was_given_when_asked_were_true(self):
        metas = [json.loads(path.read_text(encoding="utf-8")) for path in RAW.glob("*.json")]
        full, kept = [m["real_source_full_size"] for m in metas], [m["size"] for m in metas]
        self.assertEqual((min(full), max(full), sum(full), sum(kept)), (19989, 163223, 3008412, 33836))
        self.assertEqual((round(min(full) / 1000), round(max(full) / 1000), round(sum(full) / 1000000, 1), round(sum(kept) / 1000)), (20, 163, 3.0, 34))
        text = self.record["owner_permission"]["assistant_request"]["text"]
        for phrase in ("20 to 163 KB each, about 3.0 MB in all", "about 34 KB of 8-K rows"):
            self.assertIn(phrase, text)
        self.assertIn("(HTTP 200 for all 23)", self.record["real_data_integrity"]["fetch"])
        self.assertIn("It enumerates filings by their metadata only; no price, return or label was read.", self.record["purpose"])

    def test_it_says_what_it_is_not(self):
        text = " ".join(self.record["what_this_is_not"])
        for phrase in ("Not a review", "Not an event set", "Not a claim that GitHub Actions can read data.sec.gov/submissions/: it cannot, today, with this project's User-Agent.", "Not evidence of anything about prices or returns"):
            self.assertIn(phrase, text)
        hints = " ".join(self.record["for_the_review_that_follows"])
        for phrase in ("(ASMB, filed 2026-08-14)", "REKR has three candidates", "(2026-07-15)", "(LOVE, 2026-09-10)"):
            self.assertIn(phrase, hints)
        self.assertIn("The assistant believed Milestone 2 step 3's freeze had eventually come through GitHub Actions; it had not.", self.record["how_this_differs_from_the_plan"])


if __name__ == "__main__":
    unittest.main()
