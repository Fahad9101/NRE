import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nre import cli
from nre.core import DataError, canonical, digest
from nre.ingestion import SourceUnavailable, xbrl_company_concept


class FakeClient:
    """A fetch() double matching PublicClient's interface: url -> (body_bytes, metadata), no
    network. Mirrors tests/test_depth_cohort.py's own FakeClient exactly."""
    def __init__(self, documents=None, errors=None):
        self.documents, self.errors, self.calls = documents or {}, errors or {}, []

    def fetch(self, url, output):
        self.calls.append(url)
        if url in self.errors:
            raise self.errors[url]
        if url not in self.documents:
            raise AssertionError("unexpected fetch: " + url)
        body = canonical(self.documents[url])
        return body, {"url": url, "sha256": digest(body), "size": len(body),
                     "retrieved_at": "2026-09-30T12:00:00Z", "raw_file": digest(body) + ".raw"}


REAL_JBSS_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK0000880117/us-gaap/EarningsPerShareDiluted.json"
# A trimmed but real slice of JBSS's own response (the same accession already used throughout
# Milestone 3's other tests/worked examples), fetched directly on 2026-09-30.
REAL_JBSS_DOCUMENT = {
    "cik": 880117, "taxonomy": "us-gaap", "tag": "EarningsPerShareDiluted",
    "entityName": "SANFILIPPO JOHN B & SON INC",
    "units": {"USD/shares": [
        {"start": "2024-06-28", "end": "2024-09-26", "val": 1.00, "accn": "0001193125-25-256406",
         "fy": 2025, "fp": "Q1", "form": "10-Q", "filed": "2025-10-29"},
        {"start": "2025-06-27", "end": "2025-09-25", "val": 1.59, "accn": "0001193125-25-256406",
         "fy": 2025, "fp": "Q1", "form": "10-Q", "filed": "2025-10-29"},
    ]},
}


class XbrlCompanyConceptTests(unittest.TestCase):
    def test_real_response_shape_parses_cleanly(self):
        client = FakeClient({REAL_JBSS_URL: REAL_JBSS_DOCUMENT})
        facts, meta = xbrl_company_concept(client, "0000880117", "us-gaap", "EarningsPerShareDiluted",
                                           "USD/shares", "/tmp/out")
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[1]["val"], 1.59)
        self.assertEqual(client.calls, [REAL_JBSS_URL])
        self.assertEqual(meta["url"], REAL_JBSS_URL)

    def test_url_is_built_from_a_zero_padded_ten_digit_cik(self):
        client = FakeClient({REAL_JBSS_URL: REAL_JBSS_DOCUMENT})
        xbrl_company_concept(client, "880117", "us-gaap", "EarningsPerShareDiluted", "USD/shares", "/tmp/out")
        self.assertEqual(client.calls, [REAL_JBSS_URL])

    def test_missing_concept_surfaces_as_source_unavailable_not_a_crash(self):
        # The real behavior when a company has never reported a given tag (e.g. the wrong revenue
        # tag for its own ASC 606 adoption): SEC's API itself 404s.
        url = "https://data.sec.gov/api/xbrl/companyconcept/CIK0000880117/us-gaap/Revenues.json"
        client = FakeClient(errors={url: SourceUnavailable("HTTP_404")})
        with self.assertRaises(SourceUnavailable):
            xbrl_company_concept(client, "880117", "us-gaap", "Revenues", "USD", "/tmp/out")

    def test_response_cik_must_match_the_request(self):
        wrong_cik = dict(REAL_JBSS_DOCUMENT, cik=1)
        client = FakeClient({REAL_JBSS_URL: wrong_cik})
        with self.assertRaises(DataError):
            xbrl_company_concept(client, "880117", "us-gaap", "EarningsPerShareDiluted", "USD/shares", "/tmp/out")

    def test_missing_requested_unit_is_rejected_not_silently_empty(self):
        client = FakeClient({REAL_JBSS_URL: REAL_JBSS_DOCUMENT})
        with self.assertRaises(DataError):
            xbrl_company_concept(client, "880117", "us-gaap", "EarningsPerShareDiluted", "USD", "/tmp/out")

    def test_invalid_cik_rejected(self):
        with self.assertRaises(DataError):
            xbrl_company_concept(FakeClient(), "not-a-cik", "us-gaap", "EarningsPerShareDiluted", "USD/shares", "/tmp/out")

    def test_invalid_taxonomy_or_tag_rejected(self):
        with self.assertRaises(DataError):
            xbrl_company_concept(FakeClient(), "880117", "us-gaap; DROP TABLE", "EarningsPerShareDiluted", "USD/shares", "/tmp/out")
        with self.assertRaises(DataError):
            xbrl_company_concept(FakeClient(), "880117", "us-gaap", "../../etc/passwd", "USD/shares", "/tmp/out")


class CliEarningsSurpriseTests(unittest.TestCase):
    """cli.py's own "earnings-surprise" command, end to end, with a faked PublicClient standing in
    for the real network the same way test_consolidated_audit.py's MainTests fake Alpaca's opener."""

    def test_real_jbss_filing_computed_through_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("nre.ingestion.PublicClient", return_value=FakeClient({REAL_JBSS_URL: REAL_JBSS_DOCUMENT})), \
             patch("builtins.print") as output:
            code = cli.main(["earnings-surprise", "--cik", "880117", "--accession", "0001193125-25-256406",
                             "--output", tmp])
            self.assertEqual(code, 0)
            printed = json.loads(output.call_args_list[0].args[0])
            self.assertEqual(printed["state"], "COMPUTED")
            self.assertAlmostEqual(printed["surprise_pct"], 59.0, places=4)
            saved = json.loads((Path(tmp) / "earnings-surprise.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["cik"], "880117")
            self.assertEqual(saved["result"]["surprise_pct"], printed["surprise_pct"])


if __name__ == "__main__":
    unittest.main()
