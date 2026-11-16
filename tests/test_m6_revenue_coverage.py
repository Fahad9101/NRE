import unittest
from datetime import datetime

from nre.m6_revenue_coverage import exhibit_growth, select_growth, wire_growth


CIK = "0000880117"
ACCESSION = "0001193125-25-256406"
PUBLISHED = datetime.fromisoformat("2025-10-29T16:10:00-04:00")
DEADLINE = datetime.fromisoformat("2025-10-30T09:30:00-04:00")


class RevenueCoverageTests(unittest.TestCase):
    def setUp(self):
        base = {"accn": ACCESSION, "filed": "2025-10-29", "form": "10-Q"}
        self.current = dict(base, start="2025-06-27", end="2025-09-25", val=120_000_000)
        self.prior = dict(base, start="2024-06-28", end="2024-09-26", val=100_000_000)
        self.facts = {
            "cik": int(CIK),
            "entityName": "Fixture Issuer",
            "facts": {
                "us-gaap": {"Revenues": {"units": {"USD": [self.current, self.prior]}}}
            },
        }
        self.recent = {
            "accessionNumber": [ACCESSION],
            "filingDate": ["2025-10-29"],
            "reportDate": [self.current["end"]],
            "acceptanceDateTime": ["2025-10-29T20:30:00Z"],
            "form": ["10-Q"],
            "primaryDocument": ["quarter.htm"],
        }
        self.submissions = {"cik": CIK, "filings": {"recent": self.recent, "files": []}}

    def select(self):
        return select_growth(self.facts, self.submissions, CIK, PUBLISHED, DEADLINE)

    def test_original_same_filing_quarters_are_usable(self):
        result = self.select()
        self.assertEqual(result["status"], "usable")
        self.assertAlmostEqual(result["growth_fraction"], 0.20)

    def test_identical_duplicate_facts_do_not_create_ambiguity(self):
        revenues = self.facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
        revenues.extend((dict(self.current), dict(self.prior)))
        self.assertEqual(self.select()["status"], "usable")

    def test_filing_before_release_or_after_deadline_is_ineligible(self):
        for accepted in ("2025-10-29T20:09:59Z", "2025-10-30T13:30:01Z"):
            with self.subTest(accepted=accepted):
                self.recent["acceptanceDateTime"][0] = accepted
                self.assertEqual(self.select()["status"], "no_eligible_filing")

    def test_amendment_cannot_supply_original_revenue(self):
        self.recent["form"][0] = self.current["form"] = self.prior["form"] = "10-Q/A"
        self.assertEqual(self.select()["status"], "no_eligible_filing")

    def test_prior_comparison_from_another_filing_is_unusable(self):
        self.prior["accn"] = "0001193125-24-250000"
        self.assertEqual(self.select()["status"], "unusable_revenue")

    def test_fact_period_must_match_filing_report_date(self):
        self.recent["reportDate"][0] = "2025-09-26"
        self.assertEqual(self.select()["status"], "unusable_revenue")

    def test_conflicting_same_quarter_numbers_are_unusable(self):
        revenues = self.facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
        revenues.append(dict(self.current, val=121_000_000))
        self.assertEqual(self.select()["status"], "unusable_revenue")

    def test_year_to_date_fact_cannot_supply_quarterly_revenue(self):
        self.current["start"] = "2025-01-01"
        self.assertEqual(self.select()["status"], "unusable_revenue")

    def test_zero_prior_is_unusable(self):
        self.prior["val"] = 0
        self.assertEqual(self.select()["status"], "unusable_revenue")


    def test_after_hours_filing_dissemination_uncertainty_is_excluded(self):
        self.recent["acceptanceDateTime"][0] = "2025-10-29T21:30:00Z"
        self.assertEqual(self.select()["status"], "no_eligible_filing")

    def test_wire_data_uses_one_minute_buffer_and_pinned_url(self):
        url = "https://www.globenewswire.com/fixture"
        event = {"published_at": PUBLISHED.isoformat(), "cutoff": DEADLINE.isoformat(),
                 "source": {"url": url}}
        row = {"published_at": PUBLISHED.isoformat(), "cutoff_at": DEADLINE.isoformat(),
               "source_url": url, "basis": "Quarterly consolidated statements",
               "period_end": self.current["end"], "prior_period_end": self.prior["end"],
               "current_revenue_usd": self.current["val"], "prior_revenue_usd": self.prior["val"]}
        self.assertAlmostEqual(wire_growth(row, event, DEADLINE)["growth_fraction"], 0.20)
        at_buffer = datetime.fromisoformat("2025-10-29T16:11:00-04:00")
        self.assertIsNone(wire_growth(row, event, at_buffer))
        with self.assertRaisesRegex(ValueError, "pinned event"):
            wire_growth(dict(row, source_url=url + "-wrong"), event, DEADLINE)

    def test_exhibit_reconciles_acceptance_and_excludes_unequal_quarters(self):
        self.recent["form"][0] = "8-K"
        url = f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{ACCESSION.replace('-', '')}/ex99.htm"
        event = {"published_at": PUBLISHED.isoformat(), "candidate_id": ACCESSION,
                 "security": {"cik": CIK}}
        row = {"accession": ACCESSION, "cik": CIK, "form": "8-K", "exhibit": "99.1",
               "currency": "USD", "release_url": url,
               "accepted_at": self.recent["acceptanceDateTime"][0],
               "filing_date": self.recent["filingDate"][0], "current_quarter_end": self.current["end"],
               "prior_quarter_end": self.prior["end"], "current_usd": self.current["val"],
               "prior_usd": self.prior["val"]}
        self.assertAlmostEqual(exhibit_growth(row, event, self.submissions, DEADLINE)["growth_fraction"], 0.20)
        self.assertIsNone(exhibit_growth(dict(row, comparison_caveat="14 vs 13 weeks"),
                                         event, self.submissions, DEADLINE))
        with self.assertRaisesRegex(ValueError, "disagrees"):
            exhibit_growth(dict(row, accepted_at=PUBLISHED.isoformat()), event, self.submissions, DEADLINE)
