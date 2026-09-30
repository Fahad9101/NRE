import unittest

from nre.catalyst_features import catalyst_features
from nre.core import DataError
from nre.corporate_events import classify_filing

# Real JBSS 8-K item list for accession 0001193125-25-256336 (filed 2025-10-29, the same real
# earnings release already normalized in reports/m3-worked-example-jbss-same-day-filings-2026-09-29.json):
# item 2.02 (earnings) plus 9.01 (an exhibit-attachment marker, not a separate event).
JBSS_8K_ITEMS = ["2.02", "9.01"]
# Real, already-computed year_over_year_surprise() result for the same real event (JBSS Q1 FY2026,
# accession 0001193125-25-256406, +59% EPS -- tests/test_earnings_surprise.py's own ground truth).
JBSS_EPS_SURPRISE_COMPUTED = {
    "state": "COMPUTED",
    "current": {"value": 1.59, "accession": "0001193125-25-256406"},
    "prior": {"value": 1.00, "accession": "0001193125-25-256336"},
    "surprise_pct": 59.0,
}
JBSS_REVENUE_SURPRISE_NEGATIVE = {"state": "COMPUTED", "current": {"value": 90}, "prior": {"value": 100},
                                  "surprise_pct": -10.0}


class CatalystFeaturesRealDataTests(unittest.TestCase):
    """Ground truth: JBSS's own real, already-classified 8-K (Phase A) combined with its own real,
    already-computed EPS surprise (Phase B) for the identical real earnings event."""

    def test_real_jbss_event_combines_both_phases(self):
        rows = classify_filing(JBSS_8K_ITEMS)
        result = catalyst_features(rows, JBSS_EPS_SURPRISE_COMPUTED)
        self.assertEqual(result["corporate_event_category"], "earnings")
        self.assertEqual(result["corporate_event_subtype"], "results")
        self.assertEqual(result["co_filed_items"], ["9.01"])
        self.assertEqual(result["earnings_surprise_state"], "COMPUTED")
        self.assertEqual(result["earnings_surprise_pct"], 59.0)
        self.assertEqual(result["surprise_direction"], "positive")

    def test_missing_surprise_result_is_recorded_not_computed_never_guessed(self):
        rows = classify_filing(JBSS_8K_ITEMS)
        result = catalyst_features(rows)
        self.assertEqual(result["earnings_surprise_state"], "NOT_COMPUTED")
        self.assertIsNone(result["earnings_surprise_pct"])
        self.assertIsNone(result["surprise_direction"])

    def test_a_state_with_no_surprise_pct_carries_no_direction_either(self):
        rows = classify_filing(JBSS_8K_ITEMS)
        result = catalyst_features(rows, {"state": "PRIOR_PERIOD_NOT_FOUND", "surprise_pct": None})
        self.assertEqual(result["earnings_surprise_state"], "PRIOR_PERIOD_NOT_FOUND")
        self.assertIsNone(result["surprise_direction"])

    def test_negative_surprise_direction(self):
        rows = classify_filing(JBSS_8K_ITEMS)
        result = catalyst_features(rows, JBSS_REVENUE_SURPRISE_NEGATIVE)
        self.assertEqual(result["surprise_direction"], "negative")

    def test_flat_surprise_direction(self):
        rows = classify_filing(JBSS_8K_ITEMS)
        result = catalyst_features(rows, {"state": "COMPUTED", "surprise_pct": 0.0})
        self.assertEqual(result["surprise_direction"], "flat")

    def test_only_the_earnings_item_alone_has_no_co_filed_items(self):
        rows = classify_filing(["2.02"])
        result = catalyst_features(rows)
        self.assertEqual(result["co_filed_items"], [])


class EdgeCaseTests(unittest.TestCase):
    def test_empty_rows_rejected(self):
        with self.assertRaises(DataError):
            catalyst_features([])

    def test_non_list_rejected(self):
        with self.assertRaises(DataError):
            catalyst_features("not-a-list")

    def test_no_earnings_row_rejected(self):
        # A filing with no item 2.02 at all is not one of this project's own real earnings events --
        # a real, separate same-day filing (like JBSS's own dividend 8-K) must never be mistaken for one.
        rows = classify_filing(["8.01"])
        with self.assertRaises(DataError):
            catalyst_features(rows)

    def test_two_earnings_rows_rejected_not_silently_picked(self):
        # Should never occur for a real filing (an accession has at most one item 2.02) -- if it
        # somehow did, silently picking one would hide a real data anomaly.
        rows = classify_filing(["2.02"]) + classify_filing(["2.02"])
        with self.assertRaises(DataError):
            catalyst_features(rows)


if __name__ == "__main__":
    unittest.main()
