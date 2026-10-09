"""The owner's decisions after the Milestone 5 Phase 1b eligibility review (reports/m5-phase1b-s2-decisions-2026-10-09.json): the four answers as given, what each decides for the three candidates, and the first batch recomputed
from the review's table (the ten earliest releases among the candidates that stand, ties broken alphabetically)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "reports" / "m5-phase1b-s2-decisions-2026-10-09.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class DecisionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(RECORD)
        cls.review = load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")
        cls.rows = {(r["ticker"], r["filing_date"]): r for r in cls.review["candidates"]}

    def test_the_four_answers_are_quoted_as_given(self):
        record = self.record
        self.assertEqual((record["asked"]["at"], record["asked"]["source"]), ("2026-10-09T14:26:06.969Z", "session transcript, line 39906 (AskUserQuestion)"))
        self.assertEqual((record["answered"]["at"], record["answered"]["source"]), ("2026-10-09T17:00:54.499Z", "session transcript, line 39912 (the tool result of the questions)"))
        self.assertLess(record["asked"]["at"], record["answered"]["at"])
        qa = record["questions_and_answers"]
        self.assertEqual([(q["header"], q["owner_selected"]) for q in qa],
                         [("Wire pages", "Yes, batch 1 only (Recommended)"), ("REKR 07-15", "Exclude it (Recommended)"), ("ASMB 08-14", "Keep it, with a caveat (Recommended)"), ("PAYO 08-06", "Exclude it (Recommended)")])
        self.assertEqual(qa[0]["question"], "May I read public wire-release pages and the issuers' own newsroom pages to take the first-public minute of the releases (S4)?")
        self.assertEqual(qa[1]["question"], "REKR 2026-07-15 (a preliminary, unaudited pre-announcement; the full results followed on 2026-08-13): exclude it?")
        self.assertEqual(qa[2]["question"], "ASMB 2026-08-14 (an 8-K/A that only corrects the header of the 2026-08-13 8-K; the results release is dated 2026-08-13): keep it or exclude it?")
        self.assertEqual(qa[3]["question"], "PAYO 2026-08-06 (Q2 results while a $7.40-per-share cash take-private by Nuvei, agreed 2026-06-15, was pending; guidance withdrawn): exclude it?")
        for q in qa:
            labels = [o["label"] for o in q["options_offered"]]
            self.assertIn(q["owner_selected"], labels)
            self.assertTrue(labels[0].endswith("(Recommended)"))
        self.assertEqual([len(q["options_offered"]) for q in qa], [3, 2, 2, 2])
        self.assertIn("Later batches ask again.", qa[0]["options_offered"][0]["description"])

    def test_each_answer_decides_what_the_record_says_it_decides(self):
        effects = self.record["effects"]
        self.assertEqual(set(effects), {"REKR 2026-07-15", "ASMB 2026-08-14", "PAYO 2026-08-06"})
        for key, effect in effects.items():
            ticker, day = key.split()
            self.assertEqual(effect["candidate_id"], self.rows[(ticker, day)]["candidate_id"], key)
        self.assertEqual((effects["REKR 2026-07-15"]["disposition"], effects["ASMB 2026-08-14"]["disposition"], effects["PAYO 2026-08-06"]["disposition"]), ("excluded", "kept_with_caveat", "excluded"))
        self.assertIn("explicit preliminary, unaudited pre-announcement", effects["REKR 2026-07-15"]["reason"])
        self.assertIn("it stands for the 2026-08-13 results release, whose first-public time comes from the 2026-08-13 wire and 8-K, not from 2026-08-14", effects["ASMB 2026-08-14"]["caveat"])
        self.assertIn("a pending cash take-private (Nuvei, $7.40 per share, agreed 2026-06-15)", effects["PAYO 2026-08-06"]["reason"])
        self.assertIn("PAYO 2026-05-07 stays a candidate", effects["PAYO 2026-08-06"]["reason"])
        assessments = {"%s %s" % key: r["assessment"] for key, r in self.rows.items() if "%s %s" % key in effects}
        self.assertEqual(assessments, {"REKR 2026-07-15": "recommend_exclude_preliminary_preannouncement", "ASMB 2026-08-14": "owner_decision_header_only_amendment", "PAYO 2026-08-06": "owner_decision_pending_cash_takeover"})

    def test_batch_1_is_the_ten_earliest_releases_that_stand_and_the_permission_is_read_narrowly(self):
        excluded = {("REKR", "2026-07-15"), ("PAYO", "2026-08-06")}
        standing = sorted((r for key, r in self.rows.items() if key not in excluded), key=lambda r: (r["release_date_in_the_filing"], r["ticker"]))
        self.assertEqual(self.record["candidates_standing_after_the_decisions"], len(standing))
        self.assertEqual(len(standing), 45)
        permission = self.record["wire_permission_read_as"]
        batch = permission["batch_1"]
        self.assertEqual(batch, [{"ticker": r["ticker"], "filing_date": r["filing_date"], "release_date": r["release_date_in_the_filing"], "candidate_id": r["candidate_id"]} for r in standing[:10]])
        self.assertEqual([(b["ticker"], b["release_date"]) for b in batch], [("CACI", "2026-04-22"), ("ALKT", "2026-04-29"), ("JBSS", "2026-04-29"), ("HURN", "2026-05-05"), ("NBIX", "2026-05-05"),
                                                                              ("PARR", "2026-05-05"), ("CXT", "2026-05-06"), ("ASMB", "2026-05-07"), ("ASPN", "2026-05-07"), ("COLL", "2026-05-07")])
        self.assertEqual(len({b["candidate_id"] for b in batch}), 10)
        self.assertNotIn(("ASMB", "2026-08-14"), {(b["ticker"], b["filing_date"]) for b in batch})
        self.assertIn("Batch 1 only", permission["scope"])
        self.assertIn("It carries no push and no other download; later batches ask again.", permission["scope"])
        self.assertIn("the ties on 2026-05-07 (ASMB, ASPN, COLL, PAYO, PDFS, REAL, TECX) were broken alphabetically", permission["how_batch_1_was_chosen"])
        ties = sorted(r["ticker"] for r in standing + [self.rows[("PAYO", "2026-08-06")]] if r["release_date_in_the_filing"] == "2026-05-07")
        self.assertEqual(ties, ["ASMB", "ASPN", "COLL", "PAYO", "PDFS", "REAL", "TECX"])
        self.assertIn("Those were my typing errors: the candidates are PARR 2026-05-05 (release and filing date) and ASMB 2026-05-07", permission["disclosure"])

    def test_it_says_what_the_answers_do_not_authorize(self):
        text = " ".join(self.record["not_authorized_by_these_answers"])
        for phrase in ("Reading the wire or newsroom pages of any candidate outside batch 1.", "Reading the nine near-date 8-Ks", "Any push, any other download, any price or label read, and attesting any event's first-public time, identity or corporate actions for the owner."):
            self.assertIn(phrase, text)
        self.assertEqual((self.record["kind"], self.record["recorded_on"]), ("m5_phase1b_s2_decisions", "2026-10-09"))
        self.assertIn("quoted from the session transcript, not from a summary", self.record["context"])


if __name__ == "__main__":
    unittest.main()
