import unittest

from nre.core import DataError
from nre.earnings_surprise import quarterly_actual, surprise_for_filing, year_over_year_surprise

# Real JBSS (John B. Sanfilippo & Son) us-gaap:EarningsPerShareDiluted facts, fetched directly from
# data.sec.gov/api/xbrl/companyconcept/CIK0000880117/us-gaap/EarningsPerShareDiluted.json on
# 2026-09-30. A small, real slice -- not synthetic -- covering the filing this project already used
# as a worked example (accession 0001193125-25-256406, filed 2025-10-29, alongside the earnings 8-K
# accession 0001193125-25-256336 from the same day).
JBSS_EPS_DILUTED = [
    {"start": "2024-06-28", "end": "2024-09-26", "val": 1.00, "accn": "0001193125-25-256406",
     "fy": 2025, "fp": "Q1", "form": "10-Q", "filed": "2025-10-29"},
    {"start": "2025-06-27", "end": "2025-09-25", "val": 1.59, "accn": "0001193125-25-256406",
     "fy": 2025, "fp": "Q1", "form": "10-Q", "filed": "2025-10-29"},
    {"start": "2024-06-28", "end": "2024-12-26", "val": 2.16, "accn": "0000950170-25-010565",
     "fy": 2024, "fp": "Q2", "form": "10-Q", "filed": "2025-01-29"},  # half-year (YTD), not quarterly
    {"start": "2024-09-27", "end": "2024-12-26", "val": 1.16, "accn": "0000950170-25-010565",
     "fy": 2024, "fp": "Q2", "form": "10-Q", "filed": "2025-01-29"},
    {"start": "2025-06-27", "end": "2025-12-25", "val": 3.12, "accn": "0001193125-26-029438",
     "fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2026-01-29"},  # half-year (YTD), not quarterly
    {"start": "2025-09-26", "end": "2025-12-25", "val": 1.53, "accn": "0001193125-26-029438",
     "fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2026-01-29"},
]


# Real JBSS us-gaap:Revenues facts, fetched directly from data.sec.gov/api/xbrl/companyconcept/
# CIK0000880117/us-gaap/Revenues.json on 2026-09-30 -- the same three real accessions the EPS
# fixture above already uses. Confirms year_over_year_surprise() et al. are tag-generic (nothing
# here is EPS-specific), which is what actually makes revenue surprise buildable: the fetch layer
# (nre.ingestion.xbrl_company_concept) and this module already support any --tag/--unit pair via
# nre.cli's own earnings-surprise command, unchanged.
#
# A real, load-bearing finding while fetching this: JBSS reports revenue under THREE different
# real XBRL tags over its own history, not one -- RevenueFromContractWithCustomerIncludingAssessedTax
# (2016-09-29..2018-06-28), then ...ExcludingAssessedTax (2017-09-28..2021-06-24, overlapping), then
# plain Revenues (2019-12-26..2026-03-26, overlapping, and the sole tag in current use). This is
# more fragmented than EPS ever was (always EarningsPerShareDiluted) -- confirming the M3 scope
# doc's own prediction. "Revenues" is the correct, currently-active tag for any of this project's
# real 2025-2026 events; a caller reaching further back than ~2021 would need to check which tag
# was actually in use for that period rather than assume "Revenues" always applies.
JBSS_REVENUES = [
    {"start": "2023-06-30", "end": "2023-12-28", "val": 525327000, "accn": "0000950170-25-010565",
     "fy": 2024, "fp": "Q2", "form": "10-Q", "filed": "2025-01-29"},  # half-year (YTD), not quarterly
    {"start": "2023-09-29", "end": "2023-12-28", "val": 291222000, "accn": "0000950170-25-010565",
     "fy": 2024, "fp": "Q2", "form": "10-Q", "filed": "2025-01-29"},
    {"start": "2024-06-28", "end": "2024-09-26", "val": 276196000, "accn": "0001193125-25-256406",
     "fy": 2025, "fp": "Q1", "form": "10-Q", "filed": "2025-10-29"},
    {"start": "2024-06-28", "end": "2024-12-26", "val": 577263000, "accn": "0001193125-26-029438",
     "fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2026-01-29"},  # half-year (YTD), not quarterly
    {"start": "2024-09-27", "end": "2024-12-26", "val": 301067000, "accn": "0001193125-26-029438",
     "fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2026-01-29"},
    {"start": "2025-06-27", "end": "2025-09-25", "val": 298683000, "accn": "0001193125-25-256406",
     "fy": 2025, "fp": "Q1", "form": "10-Q", "filed": "2025-10-29"},
    {"start": "2025-09-26", "end": "2025-12-25", "val": 314777000, "accn": "0001193125-26-029438",
     "fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2026-01-29"},
]


class RealRevenueDataTests(unittest.TestCase):
    """Ground truth: JBSS's own real accession 0001193125-25-256406 reports Q1 FY2026 revenue of
    $298,683,000 against $276,196,000 the same quarter a year earlier -- a real +8.14% year-over-
    year increase -- proving the same functions used for EPS above work correctly for a different
    real tag with no code changes, including the half-year-vs-quarterly distinction that
    JBSS_REVENUES also exercises."""

    def test_year_over_year_revenue_surprise_matches_the_real_filing(self):
        result = year_over_year_surprise(JBSS_REVENUES, "2025-09-25", "2025-10-29")
        self.assertEqual(result["state"], "COMPUTED")
        self.assertEqual(result["current"]["value"], 298683000)
        self.assertEqual(result["prior"]["value"], 276196000)
        self.assertAlmostEqual(result["surprise_pct"], 8.1417, places=4)

    def test_second_real_quarter_also_computes_correctly(self):
        result = surprise_for_filing(JBSS_REVENUES, "0001193125-26-029438")
        self.assertEqual(result["state"], "COMPUTED")
        self.assertEqual(result["current"]["value"], 314777000)
        self.assertEqual(result["prior"]["value"], 301067000)
        self.assertAlmostEqual(result["surprise_pct"], 4.5538, places=4)

    def test_half_year_ytd_revenue_fact_is_not_mistaken_for_quarterly(self):
        actual = quarterly_actual(JBSS_REVENUES, "2024-12-26", "2026-01-29")
        self.assertEqual(actual["value"], 301067000)


class RealDataTests(unittest.TestCase):
    """Ground truth: JBSS's own real accession 0001193125-25-256406 (the 10-Q filed the same day as
    the earnings 8-K reports/m3-worked-example-jbss-same-day-filings-2026-09-29.json already
    normalized) reports Q1 FY2026 diluted EPS of $1.59 against $1.00 the same quarter a year
    earlier -- a real, +59% year-over-year improvement, computed here from the same public facts,
    not asserted from memory."""

    def test_current_quarter_actual(self):
        actual = quarterly_actual(JBSS_EPS_DILUTED, "2025-09-25", "2025-10-29")
        self.assertEqual(actual["value"], 1.59)
        self.assertEqual(actual["accession"], "0001193125-25-256406")

    def test_surprise_for_filing_identifies_its_own_fresh_quarter(self):
        # Given only the accession -- not the period_end -- surprise_for_filing() must find that
        # this filing's own fresh quarter is the one ending 2025-09-25 (not the comparative
        # 2024-09-26 quarter the same accession also repeats), then compute the identical result
        # year_over_year_surprise() gives when told the period_end directly.
        result = surprise_for_filing(JBSS_EPS_DILUTED, "0001193125-25-256406")
        self.assertEqual(result["state"], "COMPUTED")
        self.assertEqual(result["current"]["value"], 1.59)
        self.assertEqual(result["prior"]["value"], 1.00)
        self.assertAlmostEqual(result["surprise_pct"], 59.0, places=4)

    def test_surprise_for_filing_with_no_quarterly_fact_reports_explicitly(self):
        result = surprise_for_filing(JBSS_EPS_DILUTED, "not-a-real-accession")
        self.assertEqual(result["state"], "NO_QUARTERLY_FACT_IN_THIS_FILING")
        self.assertIsNone(result["surprise_pct"])

    def test_year_over_year_surprise_matches_the_real_filing(self):
        result = year_over_year_surprise(JBSS_EPS_DILUTED, "2025-09-25", "2025-10-29")
        self.assertEqual(result["state"], "COMPUTED")
        self.assertEqual(result["current"]["value"], 1.59)
        self.assertEqual(result["prior"]["value"], 1.00)
        self.assertAlmostEqual(result["surprise_pct"], 59.0, places=4)

    def test_half_year_ytd_facts_are_not_mistaken_for_quarterly(self):
        # The 2024-06-28..2024-12-26 fact (a half-year/YTD figure) must never be picked as "the
        # quarter ending 2024-12-26" -- only the genuinely quarterly 2024-09-27..2024-12-26 fact may.
        actual = quarterly_actual(JBSS_EPS_DILUTED, "2024-12-26", "2025-01-29")
        self.assertEqual(actual["value"], 1.16)


class PointInTimeTests(unittest.TestCase):
    def test_a_fact_filed_after_known_by_is_invisible(self):
        self.assertIsNone(quarterly_actual(JBSS_EPS_DILUTED, "2025-09-25", "2025-10-28"))

    def test_known_by_on_the_filing_date_itself_is_visible(self):
        self.assertIsNotNone(quarterly_actual(JBSS_EPS_DILUTED, "2025-09-25", "2025-10-29"))

    def test_surprise_before_the_filing_reports_not_yet_known(self):
        result = year_over_year_surprise(JBSS_EPS_DILUTED, "2025-09-25", "2025-10-28")
        self.assertEqual(result["state"], "CURRENT_PERIOD_NOT_YET_KNOWN")
        self.assertIsNone(result["surprise_pct"])

    def test_a_later_restatement_of_an_earlier_quarter_does_not_leak_backward(self):
        # A later filing (accn ...29438, filed 2026-01-29) also happens to report a quarter ending
        # 2025-12-25; if quarterly_actual() picked the latest match instead of the first-disclosed
        # one, a fact filed months after the original event could silently override it.
        restated = dict(JBSS_EPS_DILUTED[0], val=0.50, accn="9999999999-99-999999", filed="2026-06-01")
        with_restatement = JBSS_EPS_DILUTED + [restated]
        actual = quarterly_actual(with_restatement, "2024-09-26", "2025-10-29")
        self.assertEqual(actual["value"], 1.00)
        self.assertEqual(actual["accession"], "0001193125-25-256406")


class EdgeCaseTests(unittest.TestCase):
    def test_missing_current_period(self):
        self.assertIsNone(quarterly_actual(JBSS_EPS_DILUTED, "2099-01-01", "2026-09-30"))

    def test_missing_prior_period_reported_explicitly(self):
        only_current = [JBSS_EPS_DILUTED[1]]
        result = year_over_year_surprise(only_current, "2025-09-25", "2025-10-29")
        self.assertEqual(result["state"], "PRIOR_PERIOD_NOT_FOUND")
        self.assertIsNotNone(result["current"])
        self.assertIsNone(result["surprise_pct"])

    def test_zero_prior_period_is_not_divided_by(self):
        zero_prior = [dict(JBSS_EPS_DILUTED[0], val=0.0), JBSS_EPS_DILUTED[1]]
        result = year_over_year_surprise(zero_prior, "2025-09-25", "2025-10-29")
        self.assertEqual(result["state"], "PRIOR_PERIOD_ZERO")
        self.assertIsNone(result["surprise_pct"])

    def test_non_list_facts_rejected(self):
        with self.assertRaises(DataError):
            quarterly_actual("not-a-list", "2025-09-25", "2025-10-29")

    def test_fact_missing_required_key_rejected(self):
        with self.assertRaises(DataError):
            quarterly_actual([{"start": "2025-06-27", "end": "2025-09-25", "val": 1.59}], "2025-09-25", "2025-10-29")

    def test_a_prior_quarter_just_outside_tolerance_is_not_matched(self):
        # 40 days off a year-earlier target should not be mistaken for the real comparable quarter.
        far = [dict(JBSS_EPS_DILUTED[1]), dict(JBSS_EPS_DILUTED[0], end="2024-08-17", start="2024-05-18")]
        result = year_over_year_surprise(far, "2025-09-25", "2025-10-29")
        self.assertEqual(result["state"], "PRIOR_PERIOD_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
