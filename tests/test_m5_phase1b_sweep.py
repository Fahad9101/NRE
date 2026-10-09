"""The Milestone 5 Phase 1b same-day sweep (reports/m5-phase1b-same-day-sweep-2026-10-09.json) is repeated here from the archived SEC bytes: the search for another 8-K or 8-K/A on a candidate's filing date, the candidates
whose own filing lists more than Items 2.02 and 9.01, and the other filings within three days are all the archive's, and the record says what it does not cover."""
import json
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "reports" / "m5-phase1b-same-day-sweep-2026-10-09.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
ZONE = ZoneInfo("America/New_York")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def archived_rows():
    """Every archived 8-K and 8-K/A row of each issuer, as a list of dictionaries, keyed by CIK."""
    cohort = load(ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json")
    metas = {meta["url"]: meta for meta in (load(path) for path in sorted(RAW.glob("*.json")))}
    rows = {}
    for issuer in cohort["issuers"]:
        recent = json.loads((RAW / metas[issuer["submissions_url"]]["raw_file"]).read_bytes())["filings"]["recent"]
        rows[issuer["cik"]] = [{key: recent[key][i] for key in recent} for i in range(len(recent["accessionNumber"]))]
    return rows


def eastern(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ZONE).strftime("%Y-%m-%d %H:%M")


class SweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RECORD)
        cls.candidates = sorted(load(ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json")["candidates"], key=lambda c: (c["ticker"], c["filing_date"]))
        cls.rows = archived_rows()

    def test_no_candidate_has_another_8k_on_its_filing_date_and_the_record_says_so(self):
        found = []
        for c in self.candidates:
            others = [r for r in self.rows[c["cik"]] if r["filingDate"] == c["filing_date"] and r["accessionNumber"] != c["candidate_id"]]
            self.assertEqual(sum(1 for r in self.rows[c["cik"]] if r["accessionNumber"] == c["candidate_id"]), 1, c["candidate_id"])          # the candidate itself is among the archived rows
            found += [(c["ticker"], r["accessionNumber"]) for r in others]
        self.assertEqual(found, [])
        result = self.record["result"]
        self.assertEqual(result, {"candidates_swept": 47, "issuers": 23, "archived_8k_rows_examined": sum(len(rows) for rows in self.rows.values()),
                                  "candidates_with_another_8k_or_8ka_on_the_same_filing_date": 0, "such_candidates": []})
        self.assertEqual(result["archived_8k_rows_examined"], 150)
        self.assertEqual(self.record["net_effect_on_the_47_candidates"], {"excluded_by_this_sweep": [], "unaffected_by_this_sweep": 47})

    def test_the_candidates_with_more_than_the_earnings_items_are_the_ledgers(self):
        beyond = [{"ticker": c["ticker"], "filing_date": c["filing_date"], "candidate_id": c["candidate_id"], "form": c["form"], "items": c["items"]}
                  for c in self.candidates if set(c["items"]) - {"2.02", "9.01"}]
        self.assertEqual(self.record["pointers_for_the_content_review"]["candidates_whose_own_filing_lists_items_beyond_2_02_and_9_01"], beyond)
        self.assertEqual([(b["ticker"], b["filing_date"], b["items"]) for b in beyond],
                         [("ACHV", "2026-05-12", ["2.02", "5.02", "9.01"]), ("ALKT", "2026-04-29", ["2.02", "7.01", "8.01", "9.01"]), ("ALKT", "2026-07-29", ["2.02", "7.01", "9.01"]),
                          ("ASPN", "2026-05-07", ["2.02", "7.01", "9.01"]), ("ASPN", "2026-08-06", ["2.02", "7.01", "9.01"]), ("COLL", "2026-05-07", ["2.02", "7.01", "9.01"]),
                          ("COLL", "2026-08-06", ["2.02", "7.01"]), ("OKTA", "2026-05-28", ["2.02", "7.01", "9.01"]), ("REKR", "2026-07-15", ["2.02", "7.01", "9.01"])])

    def test_the_filings_within_three_days_are_the_archives(self):
        near = []
        for c in self.candidates:
            mine = next(r for r in self.rows[c["cik"]] if r["accessionNumber"] == c["candidate_id"])
            day = datetime.strptime(c["filing_date"], "%Y-%m-%d")
            for r in sorted(self.rows[c["cik"]], key=lambda r: (r["filingDate"], r["accessionNumber"])):
                gap = (datetime.strptime(r["filingDate"], "%Y-%m-%d") - day).days
                if r["accessionNumber"] != c["candidate_id"] and r["filingDate"] != c["filing_date"] and abs(gap) <= 3:
                    near.append({"ticker": c["ticker"], "candidate_date": c["filing_date"], "candidate_accepted_et": eastern(mine["acceptanceDateTime"]), "other_filing_date": r["filingDate"],
                                 "days_from_candidate": gap, "other_accession": r["accessionNumber"], "other_form": r["form"], "other_items": r["items"].split(","),
                                 "other_accepted_et": eastern(r["acceptanceDateTime"])})
        self.assertEqual(self.record["pointers_for_the_content_review"]["other_8k_or_8ka_filings_by_the_same_issuer_within_three_calendar_days"], near)
        self.assertEqual([(n["ticker"], n["other_filing_date"], n["other_form"], n["other_items"]) for n in near],
                         [("ACHV", "2026-08-14", "8-K", ["8.01", "9.01"]), ("ASMB", "2026-08-13", "8-K", ["2.01", "9.01"]), ("HURN", "2026-07-27", "8-K", ["5.02"]), ("KLC", "2026-08-14", "8-K", ["1.01", "9.01"]),
                          ("LNSR", "2026-08-10", "8-K", ["5.07"]), ("LOVE", "2026-06-09", "8-K", ["5.07", "9.01"]), ("NBIX", "2026-07-31", "8-K/A", ["9.01"]), ("PARR", "2026-05-04", "8-K", ["5.07"]),
                          ("SLSN", "2026-08-21", "8-K", ["4.02", "9.01"])])
        pool = {c["candidate_id"] for c in self.candidates}
        for entry in near:
            self.assertNotIn(entry["other_accession"], pool)                                       # a different filing, not one of the 47

    def test_the_record_says_how_it_was_done_and_what_it_does_not_cover(self):
        record = self.record
        self.assertEqual((record["kind"], record["recorded_on"], record["policy"]), ("m5_phase1b_same_day_sweep", "2026-10-09", "docs/SAME-DAY-COMPETING-CATALYST-POLICY.md"))
        self.assertTrue((ROOT / record["policy"]).is_file())
        self.assertIn("It reads no price and downloads nothing.", record["purpose"])
        self.assertIn("for each candidate, whether the same issuer filed any other 8-K or 8-K/A on the identical calendar filing date", record["purpose"])
        step3 = load(ROOT / "reports" / "m2-step3-same-day-catalyst-review-2026-10-01.json")
        self.assertIn("filed any OTHER real 8-K/8-K-A on the identical calendar filing_date", step3["sweep_method"])
        limits = " ".join(record["limits"])
        for phrase in ("A competing item bundled into the candidate's own filing (an extra Item beyond 2.02 and 9.01), or announced by a wire release with no 8-K, is invisible to it",
                       "It tests the filing date, not the reaction day", "the filings within three days are listed below so the content review can look at them",
                       "It says nothing about whether any candidate is an earnings-results release, its first-public timing, its identity or its corporate actions"):
            self.assertIn(phrase, limits)
        self.assertIn("Milestone 2 step 3's ALKT exclusion", limits)
        blocked = " ".join(item for item in record["not_a_claim"])
        for phrase in ("Not an eligibility review: no candidate's filing text was read", "Not a disposition of any candidate", "Not a claim that no competing catalyst exists"):
            self.assertIn(phrase, blocked)
        self.assertIn("The third list is outside the policy's test", record["pointers_for_the_content_review"]["note"])
        alkt = [e for e in load(ROOT / "reports" / "m2-step3-reviewed-candidate-ledger.json")["candidates"] if e["ticker"] == "ALKT" and e["disposition"] == "excluded"]
        self.assertEqual(len(alkt), 1)
        self.assertIn("a separate PRNewswire release for a $400 million acquisition of MANTL went out in the same displayed minute", alkt[0]["reason"])


if __name__ == "__main__":
    unittest.main()
