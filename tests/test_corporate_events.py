import json
import unittest
from pathlib import Path

from nre.corporate_events import CATEGORIES, ITEM_TAXONOMY, classify_filing, classify_item, normalize_filing
from nre.core import DataError

ROOT = Path(__file__).resolve().parent.parent


class TaxonomyTableTests(unittest.TestCase):
    def test_every_entry_has_a_valid_category_and_nonempty_title_and_subtype(self):
        for item, entry in ITEM_TAXONOMY.items():
            self.assertIn(entry["category"], CATEGORIES, item)
            self.assertTrue(entry["title"], item)
            self.assertTrue(entry["subtype"], item)

    def test_item_numbers_are_well_formed(self):
        import re
        for item in ITEM_TAXONOMY:
            self.assertRegex(item, r"^[1-9]\.\d{2}$")

    def test_exactly_one_earnings_item(self):
        earnings = [item for item, e in ITEM_TAXONOMY.items() if e["category"] == "earnings"]
        self.assertEqual(earnings, ["2.02"])

    def test_9_01_is_administrative_not_an_event(self):
        self.assertEqual(ITEM_TAXONOMY["9.01"]["category"], "administrative")


class ClassifyItemTests(unittest.TestCase):
    def test_known_item(self):
        self.assertEqual(classify_item("2.02"), {"title": "Results of Operations and Financial Condition",
                                                   "category": "earnings", "subtype": "results"})

    def test_unknown_item_is_none_not_guessed(self):
        self.assertIsNone(classify_item("1.99"))

    def test_non_string_is_none(self):
        self.assertIsNone(classify_item(202))

    def test_returned_dict_is_a_copy(self):
        first = classify_item("8.01")
        first["title"] = "tampered"
        self.assertEqual(classify_item("8.01")["title"], "Other Events")


class ClassifyFilingTests(unittest.TestCase):
    def test_multiple_items_classify_independently(self):
        rows = classify_filing(["2.02", "9.01"])
        self.assertEqual([r["item"] for r in rows], ["2.02", "9.01"])
        self.assertEqual(rows[0]["category"], "earnings")
        self.assertEqual(rows[1]["category"], "administrative")

    def test_order_is_preserved_not_sorted(self):
        rows = classify_filing(["9.01", "2.02"])
        self.assertEqual([r["item"] for r in rows], ["9.01", "2.02"])

    def test_unclassified_item_is_explicit_not_fabricated(self):
        rows = classify_filing(["2.02", "1.99"])
        self.assertEqual(rows[1], {"item": "1.99", "title": None, "category": "unclassified", "subtype": None})

    def test_empty_list_rejected(self):
        with self.assertRaises(DataError):
            classify_filing([])

    def test_non_list_rejected(self):
        with self.assertRaises(DataError):
            classify_filing("2.02,9.01")


class NormalizeFilingTests(unittest.TestCase):
    def test_shares_source_identity_across_items(self):
        rows = normalize_filing("0001193125-25-999999", "1120914", "2025-11-06", ["2.02", "9.01"],
                                source_url="https://www.sec.gov/example")
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["candidate_id"], "0001193125-25-999999")
            self.assertEqual(row["cik"], "0001120914")
            self.assertEqual(row["filing_date"], "2025-11-06")
            self.assertEqual(row["source_url"], "https://www.sec.gov/example")
        self.assertEqual(rows[0]["category"], "earnings")
        self.assertEqual(rows[1]["category"], "administrative")

    def test_pads_cik_to_ten_digits(self):
        rows = normalize_filing("id", "25445", "2025-01-01", ["8.01"])
        self.assertEqual(rows[0]["cik"], "0000025445")

    def test_rejects_bad_identity_fields(self):
        with self.assertRaises(DataError):
            normalize_filing("", "25445", "2025-01-01", ["8.01"])
        with self.assertRaises(DataError):
            normalize_filing("id", "not-a-cik", "2025-01-01", ["8.01"])
        with self.assertRaises(DataError):
            normalize_filing("id", "25445", "", ["8.01"])


class RealDataTests(unittest.TestCase):
    """Every item number this project has actually fetched from real SEC filings, across both
    Milestone 1's 243-candidate ledger and Milestone 2 step 2's 48-candidate ledger, classifies
    without crashing. A real-world coverage check, not just the hand-picked cases above."""

    def real_items(self):
        m1 = json.loads((ROOT / "reports" / "m1-reviewed-candidate-ledger.json").read_text(encoding="utf-8"))
        m2 = json.loads((ROOT / "config" / "m2-step2-frozen-candidate-ledger.json").read_text(encoding="utf-8"))
        seen = set()
        for candidate in m1["candidates"] + m2["candidates"]:
            seen.update(candidate.get("items", []))
        return seen

    def test_every_real_item_number_this_project_has_seen_is_covered(self):
        seen = self.real_items()
        self.assertTrue(seen)
        uncovered = seen - set(ITEM_TAXONOMY)
        self.assertEqual(uncovered, set(), "real item numbers this table doesn't cover: %s" % uncovered)

    def test_every_real_candidates_items_classify_without_crashing(self):
        m1 = json.loads((ROOT / "reports" / "m1-reviewed-candidate-ledger.json").read_text(encoding="utf-8"))
        m2 = json.loads((ROOT / "config" / "m2-step2-frozen-candidate-ledger.json").read_text(encoding="utf-8"))
        checked = 0
        for candidate in m1["candidates"] + m2["candidates"]:
            items = candidate.get("items")
            if not items:
                continue
            rows = classify_filing(items)
            self.assertEqual(len(rows), len(items))
            self.assertNotIn("unclassified", {r["category"] for r in rows})
            checked += 1
        self.assertGreater(checked, 250)

    def test_every_real_candidate_normalizes_end_to_end(self):
        m1 = json.loads((ROOT / "reports" / "m1-reviewed-candidate-ledger.json").read_text(encoding="utf-8"))
        m2 = json.loads((ROOT / "config" / "m2-step2-frozen-candidate-ledger.json").read_text(encoding="utf-8"))
        checked = 0
        for candidate in m1["candidates"] + m2["candidates"]:
            items = candidate.get("items")
            if not items:
                continue
            rows = normalize_filing(candidate["candidate_id"], candidate["cik"], candidate["filing_date"],
                                    items, candidate.get("primary_url"))
            self.assertEqual(len(rows), len(items))
            self.assertTrue(all(r["cik"] == candidate["cik"].zfill(10) for r in rows))
            checked += 1
        self.assertGreater(checked, 250)


if __name__ == "__main__":
    unittest.main()
