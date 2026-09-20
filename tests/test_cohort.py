import json
import unittest

from nre.cohort import (
    deterministic_issuer_sample,
    exchange_issuers,
    relevant_history_files,
    screen_item_202,
)
from nre.core import DataError
from nre.ingestion import SecRelayClient


class CohortSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [1, "Alpha Inc.", "AAA", "Nasdaq"],
                [1, "Alpha Inc.", "AAB", "Nasdaq"],
                [2, "Beta Corp.", "BBB", "NYSE"],
                [3, "Gamma Co.", "CCC", "NYSE American"],
                [4, "Other Co.", "DDD", "OTC"],
                [5, "Delta Co.", "EEE", "Nasdaq"],
            ],
        }

    def test_exchange_directory_deduplicates_issuer_classes(self):
        rows = exchange_issuers(self.directory, ["Nasdaq", "NYSE", "NYSE American"])
        self.assertEqual([r["cik"] for r in rows], ["0000000001", "0000000002", "0000000003", "0000000005"])
        alpha = rows[0]
        self.assertEqual(alpha["tickers"], ["AAA", "AAB"])
        self.assertEqual(alpha["exchanges"], ["Nasdaq"])

    def test_hash_sample_is_deterministic_and_excludes_preexplored(self):
        rows = exchange_issuers(self.directory, ["Nasdaq", "NYSE", "NYSE American"])
        first = deterministic_issuer_sample(rows, 2, "seed", ["0000000002"])
        second = deterministic_issuer_sample(rows, 2, "seed", ["2"])
        self.assertEqual(first, second)
        self.assertNotIn("0000000002", [r["cik"] for r in first])
        self.assertTrue(all(len(r["selection_key"]) == 64 for r in first))

    def test_sample_rejects_oversubscription(self):
        rows = exchange_issuers(self.directory, ["Nasdaq"])
        with self.assertRaises(DataError):
            deterministic_issuer_sample(rows, 20, "seed")


class FilingScreenTests(unittest.TestCase):
    def test_recent_coverage_avoids_unneeded_history(self):
        document = {
            "filings": {
                "recent": {"filingDate": ["2026-09-01", "2026-01-01"]},
                "files": [{"name": "old.json", "filingFrom": "2020-01-01", "filingTo": "2025-12-31"}],
            }
        }
        self.assertEqual(relevant_history_files(document, "2026-01-05"), [])

    def test_history_file_selected_when_recent_does_not_reach_screen(self):
        document = {
            "filings": {
                "recent": {"filingDate": ["2026-09-01", "2026-04-01"]},
                "files": [
                    {"name": "older.json", "filingFrom": "2025-01-01", "filingTo": "2026-03-31"},
                    {"name": "ancient.json", "filingFrom": "2020-01-01", "filingTo": "2024-12-31"},
                ],
            }
        }
        self.assertEqual(
            [x["name"] for x in relevant_history_files(document, "2026-01-05")],
            ["older.json"],
        )

    def test_item_202_screen_includes_amendments_and_buffer(self):
        rows = [
            {"candidate_id": "a", "filing_date": "2026-01-05", "items": ["2.02"], "form": "8-K"},
            {"candidate_id": "b", "filing_date": "2026-04-02", "items": ["2.02"], "form": "8-K/A"},
            {"candidate_id": "c", "filing_date": "2026-03-01", "items": ["5.02"], "form": "8-K"},
            {"candidate_id": "d", "filing_date": "2026-04-03", "items": ["2.02"], "form": "8-K"},
        ]
        result = screen_item_202(rows, "2026-01-05", "2026-04-02")
        self.assertEqual([r["candidate_id"] for r in result], ["a", "b"])


class SecRelayTests(unittest.TestCase):
    def test_json_relay_extracts_one_json_value(self):
        body = (
            b'Title: Example\n\nURL Source: http://data.sec.gov/submissions/CIK0000000001.json\n\n'
            b'Markdown Content:\n{"fields":["cik"],"data":[[1]]}\nrelay trailing prose'
        )
        payload, representation = SecRelayClient.payload(
            body, "https://data.sec.gov/submissions/CIK0000000001.json"
        )
        self.assertEqual(representation, "relay_json_extract")
        self.assertEqual(json.loads(payload), {"data": [[1]], "fields": ["cik"]})

    def test_html_relay_preserves_transformed_markdown(self):
        body = (
            b'Title: filing\n\nURL Source: http://www.sec.gov/Archives/example.htm\n\n'
            b'Markdown Content:\nAccepted 2026-01-05 16:01:00\nItem 2.02'
        )
        payload, representation = SecRelayClient.payload(
            body, "https://www.sec.gov/Archives/example.htm"
        )
        self.assertEqual(representation, "relay_markdown")
        self.assertIn(b"Item 2.02", payload)

    def test_relay_refuses_non_sec_source(self):
        with self.assertRaises(DataError):
            SecRelayClient.relay_url("https://example.com/file.json")


if __name__ == "__main__":
    unittest.main()
