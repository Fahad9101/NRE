"""The Milestone 5 Phase 1b eligibility review (reports/m5-phase1b-eligibility-review-2026-10-09.json): its 47 rows are the frozen ledger's candidates, its extraction digest is recomputed from them, the three release dates that differ
from the filing dates are the archived SEC list's, every candidate with items beyond 2.02 and 9.01 carries a note, and the record states what was read, what was found, what it leaves to the owner and what it is not."""
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
EXCHANGES = {"Nasdaq Stock Market LLC", "NASDAQ Stock Market LLC", "Nasdaq Global Select Market", "NASDAQ Global Select Market", "Nasdaq Stock Market", "NASDAQ Capital Market", "New York Stock Exchange"}
FIELDS = ["ticker", "filing_date", "candidate_id", "form", "release_date_in_the_filing", "exchange_on_cover_or_release", "press_release_exhibit"]
QUESTION = "May I read the Phase 1b candidates' SEC filing pages in the built-in browser for the S2 content review (eligibility: results release or pre-announcement or amendment, exchange, bundled items)?"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class ReviewRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RECORD)
        cls.ledger = load(ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json")["candidates"]
        cls.sweep = load(ROOT / "reports" / "m5-phase1b-same-day-sweep-2026-10-09.json")
        cls.rows = cls.record["candidates"]

    def test_its_47_rows_are_the_frozen_ledgers_candidates(self):
        by_id = {c["candidate_id"]: c for c in self.ledger}
        self.assertEqual([(r["ticker"], r["filing_date"]) for r in self.rows], sorted((c["ticker"], c["filing_date"]) for c in self.ledger))
        self.assertEqual({r["candidate_id"] for r in self.rows}, set(by_id))
        for row in self.rows:
            with self.subTest(candidate=row["candidate_id"]):
                frozen = by_id[row["candidate_id"]]
                self.assertEqual((row["ticker"], row["filing_date"], row["form"], row["items"], row["primary_url"]), (frozen["ticker"], frozen["filing_date"], frozen["form"], frozen["items"], frozen["primary_url"]))
                self.assertTrue(row["primary_url"].startswith("https://www.sec.gov/Archives/edgar/data/"))
                self.assertEqual(row["primary_url"].rsplit("/", 1)[0].rsplit("/", 1)[1], row["candidate_id"].replace("-", ""))      # the accession folder
                self.assertIn(row["exchange_on_cover_or_release"], EXCHANGES)
                self.assertRegex(row["press_release_exhibit"], r"^[A-Za-z0-9_.\-]+\.htm$")
        self.assertEqual(self.record["counts"]["candidates"], 47)

    def test_the_extraction_digest_is_recomputed_from_the_rows(self):
        table = [[row[field] for field in FIELDS] for row in self.rows]
        compact = json.dumps(table, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(len(compact), 5362)
        self.assertEqual(hashlib.sha256(compact).hexdigest(), self.record["extraction_table_sha256"])
        self.assertEqual(self.record["extraction_table_sha256"], "961b9770a6c3b9d40b368dcb54f219f292cf2e4ae9b518747dc719b04289b672")
        self.assertEqual(self.record["extraction_table_fields"], FIELDS)

    def test_a_release_date_differs_from_the_filing_date_only_where_the_archived_list_agrees(self):
        cohort = load(ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json")["issuers"]
        metas = {meta["url"]: meta for meta in (load(path) for path in sorted(RAW.glob("*.json")))}
        report_dates = {}
        for issuer in cohort:
            recent = json.loads((RAW / metas[issuer["submissions_url"]]["raw_file"]).read_bytes())["filings"]["recent"]
            report_dates.update({accession: recent["reportDate"][i] for i, accession in enumerate(recent["accessionNumber"])})
        different = [(r["ticker"], r["filing_date"], r["release_date_in_the_filing"]) for r in self.rows if r["release_date_in_the_filing"] != r["filing_date"]]
        self.assertEqual(different, [("ASMB", "2026-08-14", "2026-08-13"), ("PARR", "2026-08-05", "2026-08-04"), ("SLSN", "2026-08-20", "2026-08-19")])
        for row in self.rows:
            if row["release_date_in_the_filing"] != row["filing_date"]:
                self.assertEqual(report_dates[row["candidate_id"]], row["release_date_in_the_filing"], row["candidate_id"])
            self.assertLessEqual(row["release_date_in_the_filing"], row["filing_date"])                   # a release is never dated after the filing that reports it

    def test_the_three_decisions_and_the_counts(self):
        record = self.record
        self.assertEqual(Counter(r["assessment"] for r in self.rows), Counter({"results_release_no_issue_found": 44, "recommend_exclude_preliminary_preannouncement": 1, "owner_decision_header_only_amendment": 1,
                                                                              "owner_decision_pending_cash_takeover": 1}))
        self.assertEqual(record["counts"]["by_assessment"], {"owner_decision_header_only_amendment": 1, "owner_decision_pending_cash_takeover": 1, "recommend_exclude_preliminary_preannouncement": 1,
                                                             "results_release_no_issue_found": 44})
        special = {(r["ticker"], r["filing_date"]): r["assessment"] for r in self.rows if r["assessment"] != "results_release_no_issue_found"}
        self.assertEqual(special, {("ASMB", "2026-08-14"): "owner_decision_header_only_amendment", ("PAYO", "2026-08-06"): "owner_decision_pending_cash_takeover",
                                   ("REKR", "2026-07-15"): "recommend_exclude_preliminary_preannouncement"})
        self.assertEqual([d["candidate"] for d in record["decisions_for_the_owner"]], ["REKR 2026-07-15", "ASMB 2026-08-14", "PAYO 2026-08-06"])
        decisions = {d["candidate"]: d for d in record["decisions_for_the_owner"]}
        self.assertIn("certain preliminary, unaudited financial results", decisions["REKR 2026-07-15"]["finding"])
        self.assertIn("Exclude, as steps 2 and 3 did", decisions["REKR 2026-07-15"]["recommendation"])
        self.assertIn("inadvertently", " ".join(r["note"] for r in self.rows if r["ticker"] == "ASMB" and "note" in r))
        self.assertIn("Keep it, with a caveat", decisions["ASMB 2026-08-14"]["recommendation"])
        self.assertIn("costs one event", decisions["ASMB 2026-08-14"]["recommendation"])
        self.assertIn("$7.40 per share in cash (about $2.75 billion), closing expected in mid-2027", decisions["PAYO 2026-08-06"]["finding"])
        self.assertIn("this is a new category that steps 2 and 3 did not meet, so it needs the owner's word", decisions["PAYO 2026-08-06"]["recommendation"])
        ledger2 = load(ROOT / "reports" / "m2-step3-reviewed-candidate-ledger.json")["candidates"]
        self.assertTrue(any(c["ticker"] == "REKR" and c["disposition"] == "excluded" and "preliminary and unaudited" in c["reason"] for c in ledger2))
        self.assertTrue(any(c["ticker"] == "CACI" and c["form"] == "8-K/A" and c["disposition"] == "excluded" for c in ledger2))

    def test_every_candidate_with_items_beyond_the_earnings_ones_has_a_note(self):
        beyond = {(b["ticker"], b["filing_date"]) for b in self.sweep["pointers_for_the_content_review"]["candidates_whose_own_filing_lists_items_beyond_2_02_and_9_01"]}
        self.assertEqual(len(beyond), 9)
        noted = {(r["ticker"], r["filing_date"]) for r in self.rows if "note" in r}
        self.assertLessEqual(beyond, noted)
        for row in self.rows:
            if (row["ticker"], row["filing_date"]) in beyond:
                self.assertTrue(set(row["items"]) - {"2.02", "9.01"})
        by_key = {(r["ticker"], r["filing_date"]): r for r in self.rows}
        self.assertIn("A $100 million share repurchase program is announced in the release's headline", by_key[("ALKT", "2026-04-29")]["note"])
        self.assertIn("previously reported", by_key[("ACHV", "2026-05-12")]["note"])
        self.assertIn("preliminary, unaudited second-quarter results", by_key[("REKR", "2026-07-15")]["note"])
        self.assertIn("a special dividend was declared", by_key[("JBSS", "2026-08-19")]["note"])
        self.assertIn("filed on 2026-08-21 at 16:30 ET, not read", by_key[("SLSN", "2026-08-20")]["note"])

    def test_it_quotes_the_owners_permission_and_reads_it_narrowly(self):
        permission = self.record["owner_permission"]
        request, answer = permission["assistant_request"], permission["owner_answer"]
        self.assertEqual(request["question"], QUESTION)
        self.assertEqual((request["at"], request["source"]), ("2026-10-09T12:23:48.642Z", "session transcript, line 39517 (AskUserQuestion)"))
        self.assertEqual(request["selected_option_as_offered"]["label"], "Yes, all 47 filings (Recommended)")
        offered = request["selected_option_as_offered"]["description"]
        for phrase in ("each filing's press-release exhibit", "the SEC's size field for the 47 whole filings sums to 47.0 MB, an upper bound", "Browser memory only; I keep short quoted excerpts in the review records. No push, no other download."):
            self.assertIn(phrase, offered)
        self.assertEqual((answer["selected"], answer["at"]), ("Yes, all 47 filings (Recommended)", "2026-10-09T14:03:40.842Z"))
        self.assertIn("line 39523", answer["source"])
        self.assertLess(request["at"], answer["at"])
        self.assertIn("It carries no push and no other download: the nine other 8-Ks within three days of a candidate", permission["read_as"])

    def test_it_says_what_was_read_and_how(self):
        method = self.record["method"]
        reading = method["reading"]
        self.assertEqual((reading["host"], reading["candidates"], reading["documents_read"], reading["primary_pages"], reading["press_release_exhibits"]), ("www.sec.gov", 47, 94, 47, 47))
        self.assertEqual((reading["requests"], reading["distinct_urls"], reading["mistaken_requests"], reading["documents_with_http_200"], reading["decoded_bytes"], reading["encoded_bytes"]), (191, 95, 1, 94, 31011709, 1895187))
        self.assertEqual(reading["documents_read"], reading["primary_pages"] + reading["press_release_exhibits"])
        self.assertIn("browser memory only", reading["held_in"])
        self.assertIn("The one mistaken request went to a path that does not exist in the CXT 2026-05-06 filing folder", method["requests_explained"])
        self.assertIn("returned HTTP 404; nothing was read from it", method["requests_explained"])
        self.assertEqual(len(method["checks_for_every_candidate"]), 5)
        self.assertIn("Only PAYO 2026-08-06 matched the merger terms.", method["keyword_scan_result"])
        for term in ("to be acquired", "merger agreement", "tender offer", "going concern", "non-reliance", "delist"):
            self.assertIn(term, method["keyword_scan_terms"])

    def test_it_says_what_it_leaves_open_and_what_it_is_not(self):
        text = " ".join(self.record["what_this_is_not"])
        for phrase in ("Not a clearance of any candidate", "Not a disposition: the three decisions above and every inclusion are the owner's", "Not a full read of 94 documents", "Not evidence of anything about prices or returns: none was read."):
            self.assertIn(phrase, text)
        later = " ".join(self.record["carried_to_later_stages"])
        for phrase in ("another set of sites and needs its own permission", "ASMB 2026-08-14 (release 2026-08-13), PARR 2026-08-05 (release 2026-08-04) and SLSN 2026-08-20 (release 2026-08-19)", "JBSS's special dividend",
                       "Reading any of them needs a separate permission."):
            self.assertIn(phrase, later)
        self.assertEqual((self.record["kind"], self.record["recorded_on"], self.record["state"]), ("m5_phase1b_eligibility_review", "2026-10-09", "REVIEW_DONE_THREE_DECISIONS_FOR_THE_OWNER"))
        self.assertIn("It recommends; every disposition is made later, at the owner's signoff.", self.record["purpose"])
        self.assertIn("outcome-blind: no price, return or label was read", self.record["purpose"])


if __name__ == "__main__":
    unittest.main()
