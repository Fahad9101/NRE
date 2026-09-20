import json
import unittest

from nre.cohort import (
    deterministic_issuer_sample,
    exchange_issuers,
    historical_issuer_pool,
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


class HistoricalFrameTests(unittest.TestCase):
    def spec(self):
        return {
            "filing_screen_start": "2026-01-05",
            "filing_screen_end": "2026-04-02",
            "issuer_pool_max": 2,
            "deterministic_seed": "historical-seed",
            "exclude_ciks": ["0000000002"],
            "historical_frame": {
                "dataset": "mirror",
                "parquet_filename": "0033.parquet",
                "parquet_url": "https://example.test/0033.parquet",
                "parquet_sha256": "a" * 64,
                "parquet_listing_sha256": "b" * 64,
                "allowed_forms": ["8-K", "8-K/A"],
                "allowed_canonical_sources": [
                    "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx",
                    "https://www.sec.gov/Archives/edgar/full-index/2026/QTR2/master.idx",
                ],
            },
        }

    def frame(self):
        source = {
            "dataset": "mirror",
            "parquet_filename": "0033.parquet",
            "parquet_url": "https://example.test/0033.parquet",
            "parquet_sha256": "a" * 64,
            "parquet_listing_sha256": "b" * 64,
        }
        rows = [
            {
                "cik": "1", "company_name": "Alpha", "form_type": "8-K",
                "date_filed": "2026-01-05",
                "filename": "edgar/data/1/0000000001-26-000001.txt",
                "src": "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx",
            },
            {
                "cik": "1", "company_name": "Alpha Corp", "form_type": "8-K/A",
                "date_filed": "2026-02-01",
                "filename": "edgar/data/1/0000000001-26-000002.txt",
                "src": "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx",
            },
            {
                "cik": "2", "company_name": "Excluded", "form_type": "8-K",
                "date_filed": "2026-02-02",
                "filename": "edgar/data/2/0000000002-26-000001.txt",
                "src": "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx",
            },
            {
                "cik": "3", "company_name": "Gamma", "form_type": "8-K",
                "date_filed": "2026-03-31",
                "filename": "edgar/data/3/0000000003-26-000001.txt",
                "src": "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx",
            },
            {
                "cik": "4", "company_name": "Delta", "form_type": "8-K",
                "date_filed": "2026-04-02",
                "filename": "edgar/data/4/0000000004-26-000001.txt",
                "src": "https://www.sec.gov/Archives/edgar/full-index/2026/QTR2/master.idx",
            },
        ]
        return {
            "schema_version": 1,
            "source": source,
            "filing_screen_start": "2026-01-05",
            "filing_screen_end": "2026-04-02",
            "rows": rows,
        }

    def test_historical_pool_is_deterministic_and_excludes_preexplored(self):
        first = historical_issuer_pool(self.frame(), self.spec())
        second = historical_issuer_pool(self.frame(), self.spec())
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertNotIn("0000000002", [x["cik"] for x in first])
        self.assertTrue(all(len(x["selection_key"]) == 64 for x in first))

    def test_historical_pool_groups_aliases_and_accessions(self):
        spec = self.spec()
        spec["issuer_pool_max"] = 3
        pool = historical_issuer_pool(self.frame(), spec)
        alpha = next(x for x in pool if x["cik"] == "0000000001")
        self.assertEqual(alpha["historical_names"], ["Alpha", "Alpha Corp"])
        self.assertEqual(
            alpha["historical_accessions"],
            ["0000000001-26-000001", "0000000001-26-000002"],
        )

    def test_historical_pool_rejects_wrong_pinned_source(self):
        frame = self.frame()
        frame["source"]["parquet_sha256"] = "c" * 64
        with self.assertRaises(DataError):
            historical_issuer_pool(frame, self.spec())

    def test_historical_pool_rejects_filename_cik_mismatch(self):
        frame = self.frame()
        frame["rows"][0]["filename"] = "edgar/data/99/0000000001-26-000001.txt"
        with self.assertRaises(DataError):
            historical_issuer_pool(frame, self.spec())

    def test_historical_pool_rejects_conflicting_duplicate_accession(self):
        frame = self.frame()
        duplicate = dict(frame["rows"][0])
        duplicate["company_name"] = "Different Name"
        frame["rows"].append(duplicate)
        with self.assertRaises(DataError):
            historical_issuer_pool(frame, self.spec())


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

    def test_one_year_sec_guarantee_covers_sparse_recent_history(self):
        document = {
            "filings": {
                "recent": {"filingDate": ["2026-09-01", "2026-04-01"]},
                "files": [
                    {"name": "older.json", "filingFrom": "2020-01-01", "filingTo": "2025-06-30"},
                ],
            }
        }
        self.assertEqual(
            relevant_history_files(
                document,
                "2026-01-05",
                "2026-09-20T18:50:00Z",
            ),
            [],
        )

    def test_no_continuations_means_recent_is_complete_history(self):
        document = {
            "filings": {
                "recent": {"filingDate": ["2026-09-01", "2026-04-01"]},
                "files": [],
            }
        }
        self.assertEqual(
            relevant_history_files(document, "2020-01-01"),
            [],
        )

    def test_old_screen_with_noncovering_continuations_fails_closed(self):
        document = {
            "filings": {
                "recent": {"filingDate": ["2026-09-01", "2026-04-01"]},
                "files": [
                    {"name": "old.json", "filingFrom": "2018-01-01", "filingTo": "2019-12-31"},
                ],
            }
        }
        with self.assertRaises(DataError):
            relevant_history_files(
                document,
                "2020-06-01",
                "2026-09-20T18:50:00Z",
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
