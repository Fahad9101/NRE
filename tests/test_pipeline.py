import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from nre.calendar import Calendar
from nre.core import DataError, asof, canonical, timestamp
from nre.dataset import build, verify_snapshot, write_snapshot
from nre.ingestion import nasdaq_directory, release_evidence, sec_candidates
from nre.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((FIXTURES / "synthetic_bundle.json").read_text())

    def row(self):
        return build(self.bundle)[0][0]

    def reason(self, reason):
        row = self.row()
        self.assertEqual(row["state"], "QUARANTINED")
        self.assertIn(reason, row["reasons"])
        self.assertEqual(row["labels"], {})

    def test_known_returns_and_fill(self):
        row = self.row()
        self.assertEqual(row["state"], "MAPPED")
        self.assertAlmostEqual(row["labels"]["day1_open_return"]["value"], .10)
        self.assertAlmostEqual(row["labels"]["session_20_close_return"]["value"], .12)
        self.assertTrue(row["labels"]["positive_gap_filled"]["value"])
        self.assertTrue(row["labels"]["positive_gap_retained_half"]["value"])

    def test_synthetic_never_counts_as_historical_acceptance(self):
        self.assertEqual(build(self.bundle)[1]["historical_acceptance"], "NOT_APPLICABLE_SYNTHETIC")

    def test_exact_threshold_is_inclusive(self):
        self.assertTrue(self.row()["labels"]["gap_ge_10pct"]["value"])
        self.assertFalse(self.row()["labels"]["gap_ge_15pct"]["value"])

    def test_fixture_cannot_be_relabeled_as_live(self):
        self.bundle["synthetic"] = False
        with self.assertRaises(DataError): self.row()

    def test_afterhours_uses_same_day_close_not_next_day(self):
        self.bundle["sources"][1]["text"] += " 2026-01-05T22:00:00Z"
        self.bundle["events"][0].update(published_at="2026-01-05T22:00:00Z", cutoff="2026-01-05T22:01:00Z", timestamp_evidence="2026-01-05T22:00:00Z")
        row = self.row()
        self.assertEqual(row["reaction_session"], "2026-01-06")
        self.assertEqual(row["anchor"]["session"], "2026-01-05")
        self.assertAlmostEqual(row["labels"]["day1_open_return"]["value"], 110 / 112 - 1)

    def test_date_only_quarantined(self):
        self.bundle["events"][0].update(precision="date", published_at="2026-01-05")
        self.reason("AMBIGUOUS_PUBLICATION_TIME")

    def test_sec_acceptance_not_release(self):
        self.bundle["events"][0]["first_public_verified"] = False
        self.reason("FIRST_PUBLIC_TIME_UNVERIFIED")

    def test_forged_timestamp_evidence_rejected(self):
        self.bundle["events"][0]["timestamp_evidence"] = "not in document"
        with self.assertRaises(DataError): self.row()

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(DataError): timestamp("2026-01-05T12:00:00")

    def test_news_after_cutoff(self):
        self.bundle["events"][0]["cutoff"] = "2026-01-05T11:59:00Z"
        self.reason("NEWS_NOT_AVAILABLE_AT_CUTOFF")

    def test_forward_delayed_news(self):
        self.bundle["availability_mode"] = "forward_observed"
        self.bundle["sources"][1]["first_seen_at"] = "2026-01-05T12:02:00Z"
        self.reason("NEWS_NOT_AVAILABLE_AT_CUTOFF")

    def test_forward_unobserved_anchor(self):
        self.bundle["availability_mode"] = "forward_observed"
        self.reason("ANCHOR_NOT_OBSERVED_AT_CUTOFF")

    def test_future_identity(self):
        self.bundle["securities"][0]["available_at"] = "2026-02-01T00:00:00Z"
        self.reason("IDENTITY_NOT_KNOWN_AT_RELEASE")

    def test_expired_ticker_identity(self):
        self.bundle["securities"][0]["valid_to"] = "2026-01-04T00:00:00Z"
        self.reason("IDENTITY_EXPIRED")

    def test_etf_excluded(self):
        self.bundle["securities"][0]["security_type"] = "etf"
        self.reason("INELIGIBLE_SECURITY")

    def test_intraday_high_not_used(self):
        self.bundle["sources"][1]["text"] += "2026-01-05T15:00:00Z"
        self.bundle["events"][0].update(published_at="2026-01-05T15:00:00Z", cutoff="2026-01-05T15:01:00Z", timestamp_evidence="2026-01-05T15:00:00Z")
        self.reason("INTRADAY_OR_BELL_REQUIRES_FINER_DATA")

    def test_prediction_after_open_rejected(self):
        self.bundle["events"][0]["cutoff"] = "2026-01-05T14:31:00Z"
        self.reason("CUTOFF_NOT_BEFORE_REACTION_OPEN")

    def test_missing_previous_bar(self):
        self.bundle["prices"].pop(0)
        self.reason("MISSING_PREVIOUS_SESSION")

    def test_missing_middle_session_does_not_shift_horizon(self):
        self.bundle["prices"].pop(3)
        row = self.row()
        self.assertEqual(row["state"], "MAPPED")
        self.assertIsNone(row["labels"]["session_5_close_return"]["value"])
        self.assertEqual(row["labels"]["session_5_close_return"]["reason"], "MISSING_SESSION")
        self.assertIsNotNone(row["labels"]["session_2_close_return"]["value"])

    def test_duplicate_price_rejected(self):
        bar = copy.deepcopy(self.bundle["prices"][0]); bar["price_id"] = "duplicate"
        self.bundle["prices"].append(bar)
        with self.assertRaises(DataError): self.row()

    def test_duplicate_economic_event_rejected(self):
        event = copy.deepcopy(self.bundle["events"][0]); event["event_id"] = "duplicate"
        self.bundle["events"].append(event)
        with self.assertRaises(DataError): self.row()

    def test_foreign_key_rejected(self):
        self.bundle["events"][0]["source_id"] = "absent"
        with self.assertRaises(DataError): self.row()

    def test_nonfinite_rejected(self):
        self.bundle["prices"][1]["high"] = float("nan")
        with self.assertRaises(DataError): self.row()

    def test_bad_ohlc_rejected(self):
        self.bundle["prices"][1]["high"] = 50
        with self.assertRaises(DataError): self.row()

    def test_daily_bar_cannot_exist_before_close(self):
        self.bundle["prices"][1]["available_at"] = "2026-01-05T12:00:00Z"
        with self.assertRaises(DataError): self.row()

    def test_incomplete_daily_bar(self):
        self.bundle["prices"][1]["complete"] = False
        self.reason("INCOMPLETE_OR_HALTED_SESSION")

    def test_halt_not_forward_filled(self):
        self.bundle["prices"][1]["halted"] = True
        self.reason("INCOMPLETE_OR_HALTED_SESSION")

    def test_unknown_corporate_actions(self):
        self.bundle["prices"][1]["corporate_actions_verified"] = False
        self.reason("CORPORATE_ACTION_AUDIT_MISSING")

    def test_split_not_treated_as_loss(self):
        self.bundle["corporate_actions"] = [{"security_id":"SYNTH-A", "source_id":"identity", "effective_date":"2026-01-05", "available_at":"2026-01-02T12:00:00Z", "type":"split"}]
        self.reason("CORPORATE_ACTION_IN_WINDOW")

    def test_mixed_feeds_quarantined(self):
        self.bundle["prices"][1]["feed"] = "IEX"
        self.reason("MIXED_PRICE_FEEDS")

    def test_unpermitted_provider(self):
        self.bundle["providers"][0]["research_permitted"] = False
        self.reason("PROVIDER_USE_UNVERIFIED")

    def test_extended_hours_bar_cannot_be_regular_open(self):
        self.bundle["providers"][0]["session_scope"] = "extended"
        self.reason("REGULAR_SESSION_COVERAGE_UNVERIFIED")

    def test_negative_gap_is_not_positive_gap_fill(self):
        self.bundle["prices"][1].update(open=90,low=85,close=95)
        label = self.row()["labels"]["positive_gap_filled"]
        self.assertIsNone(label["value"])
        self.assertIsNotNone(label["reason"])

    def test_delayed_future_label_is_unknown(self):
        self.bundle["prices"][20]["available_at"] = "2026-10-01T00:00:00Z"
        label = self.row()["labels"]["session_20_close_return"]
        self.assertIsNone(label["value"])
        self.assertEqual(label["reason"], "LABEL_NOT_MATURE")

    def test_future_features_cannot_change_earlier_snapshot(self):
        original = self.row()["features"]
        future = copy.deepcopy(self.bundle["features"][0])
        future.update(revision_id="v2", value=9000000, available_at="2026-02-01T00:00:00Z")
        self.bundle["features"].append(future)
        self.assertEqual(self.row()["features"], original)

    def test_future_analogue_outcome_rejected(self):
        self.bundle["features"][0]["label_available_at"] = "2026-01-06T00:00:00Z"
        self.assertEqual(self.row()["features"], {})

    def test_snapshot_idempotence_and_sqlite_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, _ = write_snapshot(self.bundle, tmp)
            second, _ = write_snapshot(self.bundle, tmp)
            self.assertEqual(first, second)
            verify_snapshot(first)
            with sqlite3.connect(first / "dataset.sqlite") as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0], 1)
            self.assertEqual(main(["replay",str(first)]), 0)

    def test_tampered_snapshot_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = write_snapshot(self.bundle, tmp)
            (path / "outcomes.json").write_text("[]")
            with self.assertRaises(DataError): verify_snapshot(path)

    def test_source_revision_creates_new_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, _ = write_snapshot(self.bundle, tmp)
            self.bundle["sources"][1]["text"] += " Correction."
            second, _ = write_snapshot(self.bundle, tmp)
            self.assertNotEqual(first, second)
            verify_snapshot(first)


class CalendarTests(unittest.TestCase):
    def setUp(self): self.cal = Calendar()

    def test_dst(self):
        self.assertEqual(self.cal.bounds("2026-03-06")[0].hour, 14)
        self.assertEqual(self.cal.bounds("2026-03-09")[0].hour, 13)

    def test_early_close(self):
        self.assertEqual(self.cal.bounds("2026-11-27")[1].hour, 18)
        self.assertEqual(self.cal.classify("2026-11-27T18:01:00Z"), ("2026-11-30", "after_hours"))

    def test_weekend_holiday_and_after_hours(self):
        for value, expected in [("2026-01-05T12:00:00Z",("2026-01-05","premarket")), ("2026-01-05T22:00:00Z",("2026-01-06","after_hours")), ("2026-01-17T12:00:00Z",("2026-01-20","closed")), ("2026-04-03T12:00:00Z",("2026-04-06","closed"))]:
            with self.subTest(value=value): self.assertEqual(self.cal.classify(value), expected)

    def test_exact_bells(self):
        for t in ("2026-01-05T14:30:00Z", "2026-01-05T21:00:00Z"):
            self.assertEqual(self.cal.classify(t)[1], "bell_ambiguous")

    def test_unsupported_year(self):
        with self.assertRaises(DataError): self.cal.classify("2025-01-05T12:00:00Z")


class IngestionTests(unittest.TestCase):
    def test_sec_item_normalization_and_continuation(self):
        doc = json.loads((FIXTURES / "sec_submissions.json").read_text())
        result = sec_candidates(doc, "0")
        self.assertEqual([r["state"] for r in result["candidates"]], ["EARNINGS_CANDIDATE", "NOT_ITEM_2_02", "AMENDMENT_REVIEW"])
        self.assertFalse(result["historical_coverage_complete"])
        self.assertTrue(all(not r["first_public_verified"] for r in result["candidates"]))

    def test_sec_column_drift_rejected(self):
        doc = json.loads((FIXTURES / "sec_submissions.json").read_text())
        doc["filings"]["recent"]["items"].pop()
        with self.assertRaises(DataError): sec_candidates(doc, "0")

    def test_missing_items_not_silently_negative(self):
        doc = json.loads((FIXTURES / "sec_submissions.json").read_text())
        del doc["filings"]["recent"]["items"]
        self.assertEqual(sec_candidates(doc, "0")["candidates"][0]["state"], "ITEMS_UNAVAILABLE")

    def test_nested_primary_path_is_safe(self):
        doc = json.loads((FIXTURES / "sec_submissions.json").read_text())
        doc["filings"]["recent"]["primaryDocument"][0] = "nested/earnings.htm"
        row = sec_candidates(doc, "0")["candidates"][0]
        self.assertEqual(row["primary_document_state"], "PARSED_SAFE")
        self.assertTrue(row["url"].endswith("/nested/earnings.htm"))

    def test_unusual_primary_path_falls_back_to_index(self):
        doc = json.loads((FIXTURES / "sec_submissions.json").read_text())
        doc["filings"]["recent"]["primaryDocument"][0] = "../unsafe.htm"
        row = sec_candidates(doc, "0")["candidates"][0]
        self.assertEqual(row["primary_document_state"], "REVIEW_REQUIRED")
        self.assertIsNone(row["primary_url"])
        self.assertTrue(row["url"].endswith("-index.html"))

    def test_directory_not_historical_universe(self):
        raw = "Symbol|Security Name|Market Category|Test Issue|ETF\nSYNTH|Synthetic Common Stock|Q|N|N\nETF|Synthetic Fund|Q|N|Y\nFile Creation Time: 0919202612:00||||\n"
        rows = nasdaq_directory(raw,"2026-09-19T12:00:00Z")
        self.assertEqual(rows[0]["state"], "REQUIRES_IDENTITY_REVIEW")
        self.assertEqual(rows[1]["state"], "EXCLUDED_ETF")
        self.assertFalse(rows[0]["historical_membership_established"])

    def test_directory_footer_required(self):
        with self.assertRaises(DataError): nasdaq_directory("Symbol|Security Name\nA|Example", "2026-09-19T12:00:00Z")

    def test_extraction_requires_evidence(self):
        with self.assertRaises(DataError): release_evidence({"text":"nothing", "source_id":"s"}, "2026-01-05T12:00:00Z", "timestamp")


if __name__ == "__main__": unittest.main()
