import json
import tempfile
import unittest
from pathlib import Path

from nre import depth_cohort as dc
from nre.calendar import Calendar
from nre.core import DataError, canonical, digest


def calendar_spec(version, start, end, holidays, early_closes=None):
    return {"version": version, "timezone": "America/New_York", "start": start, "end": end,
            "holidays": holidays, "early_closes": early_closes or {}}


def protocol(**overrides):
    base = {"event_window_start": "2025-06-01", "event_window_end": "2026-01-04", "price_window_end": "2026-02-28",
           "minimum_eligible_events": 1, "minimum_unique_issuers": 1}
    base.update(overrides)
    return base


def spec(protocol_dict, issuers=None, **overrides):
    # issuers uses an is-None check, not `issuers or DEFAULT`: an intentionally empty [] must stay empty for
    # test_rejects_a_missing_or_malformed_issuer_list to actually exercise that case.
    base = {"schema_version": 1, "selection_mode": "fixed_issuer_set", "protocol_sha256": digest(canonical(protocol_dict)),
           "filing_screen_start": "2025-06-01", "filing_screen_end": "2026-01-04",
           "event_window_start": "2025-06-01", "event_window_end": "2026-01-04", "allowed_forms": ["8-K", "8-K/A"],
           "issuers": issuers if issuers is not None else [{"ticker": "AAA", "cik": "0000000001"}, {"ticker": "BBB", "cik": "0000000002"}]}
    base.update(overrides)
    return base


def submissions(cik, accessions, files=None):
    """A minimal SEC submissions document: one 8-K per (accession, filing_date, items) triple."""
    return {"cik": cik, "filings": {"recent": {
        "accessionNumber": [a for a, _, _ in accessions], "form": ["8-K"] * len(accessions),
        "filingDate": [d for _, d, _ in accessions], "items": [i for _, _, i in accessions],
        "primaryDocument": ["ex99.htm"] * len(accessions),
        "acceptanceDateTime": ["%sT21:00:00.000Z" % d for _, d, _ in accessions],
    }, "files": files or []}}


class FakeClient:
    """A fetch() double matching PublicClient's interface: url -> (body_bytes, metadata), no network."""
    def __init__(self, documents, retrieved_at="2026-09-28T12:00:00Z"):
        self.documents, self.retrieved_at, self.calls = documents, retrieved_at, []

    def fetch(self, url, output):
        self.calls.append(url)
        if url not in self.documents:
            raise AssertionError("unexpected fetch: " + url)
        body = canonical(self.documents[url])
        return body, {"url": url, "sha256": digest(body), "size": len(body), "retrieved_at": self.retrieved_at, "raw_file": digest(body) + ".raw"}


class MergedCalendarTests(unittest.TestCase):
    def test_merges_holidays_and_spans_both_ranges(self):
        a = calendar_spec("a", "2025-01-01", "2025-12-31", ["2025-07-04"], {"2025-12-24": "13:00"})
        b = calendar_spec("b", "2026-01-01", "2026-12-31", ["2026-01-01"], {"2026-12-24": "13:00"})
        merged = dc.merged_calendar_spec(a, b)
        self.assertEqual((merged["start"], merged["end"]), ("2025-01-01", "2026-12-31"))
        self.assertEqual(merged["holidays"], ["2025-07-04", "2026-01-01"])
        self.assertEqual(merged["early_closes"], {"2025-12-24": "13:00", "2026-12-24": "13:00"})
        cal = Calendar(merged)
        self.assertIn("2025-07-03", cal.days)
        self.assertNotIn("2025-07-04", cal.days)
        self.assertIn("2026-06-01", cal.days)  # a date only 'b' would need is reachable, proving the ranges joined

    def test_the_real_2025_and_2026_files_merge_continuously_across_the_year_boundary(self):
        cal2025 = json.loads((Path(__file__).resolve().parent.parent / "nre" / "calendar-2025.json").read_text())
        cal2026 = json.loads((Path(__file__).resolve().parent.parent / "nre" / "calendar-2026.json").read_text())
        cal = Calendar(dc.merged_calendar_spec(cal2025, cal2026))
        boundary = cal.days.index("2025-12-31")
        self.assertEqual(cal.days[boundary:boundary + 2], ["2025-12-31", "2026-01-02"])  # 2026-01-01 is a holiday
        self.assertEqual(cal.offset("2026-01-02", 20), "2026-02-02")

    def test_the_real_2024_and_2025_files_merge_continuously_across_the_year_boundary(self):
        cal2024 = json.loads((Path(__file__).resolve().parent.parent / "nre" / "calendar-2024.json").read_text())
        cal2025 = json.loads((Path(__file__).resolve().parent.parent / "nre" / "calendar-2025.json").read_text())
        cal = Calendar(dc.merged_calendar_spec(cal2024, cal2025))
        boundary = cal.days.index("2024-12-31")
        self.assertEqual(cal.days[boundary:boundary + 2], ["2024-12-31", "2025-01-02"])  # 2025-01-01 is a holiday
        # A real step-3 candidate's own filing date (JBSS-style late-2024 Nov/Dec filing) can reach
        # a full 20-session forward window without falling off either end of the merged range.
        self.assertEqual(cal.offset("2024-11-04", 20), "2024-12-03")

    def test_the_real_step_3_merged_calendar_file_matches_a_fresh_merge(self):
        root = Path(__file__).resolve().parent.parent
        cal2024 = json.loads((root / "nre" / "calendar-2024.json").read_text())
        cal2025 = json.loads((root / "nre" / "calendar-2025.json").read_text())
        committed = json.loads((root / "config" / "m2-step3-merged-calendar.json").read_text())
        self.assertEqual(committed, dc.merged_calendar_spec(cal2024, cal2025))

    def test_rejects_mismatched_timezones_or_conflicting_early_closes_or_too_few_specs(self):
        a = calendar_spec("a", "2025-01-01", "2025-12-31", [])
        b = calendar_spec("b", "2026-01-01", "2026-12-31", [])
        with self.assertRaises(DataError):
            dc.merged_calendar_spec(a)
        with self.assertRaises(DataError):
            dc.merged_calendar_spec(a, dict(b, timezone="America/Chicago"))
        conflicting = dict(b, early_closes={"2025-12-24": "13:30"})
        with self.assertRaises(DataError):
            dc.merged_calendar_spec(dict(a, early_closes={"2025-12-24": "13:00"}), conflicting)


class ValidateSpecTests(unittest.TestCase):
    def test_the_real_step_2_files_validate(self):
        root = Path(__file__).resolve().parent.parent
        real_protocol = json.loads((root / "config" / "m2-step2-protocol.json").read_text())
        real_spec = json.loads((root / "config" / "m2-step2-cohort-spec.json").read_text())
        dc.validate_spec(real_spec, real_protocol)  # no exception
        self.assertEqual(len(real_spec["issuers"]), 23)
        self.assertEqual(len({i["cik"] for i in real_spec["issuers"]}), 23)

    def test_the_real_step_3_files_validate_and_precede_step_2_with_no_overlap(self):
        root = Path(__file__).resolve().parent.parent
        real_protocol = json.loads((root / "config" / "m2-step3-protocol.json").read_text())
        real_spec = json.loads((root / "config" / "m2-step3-cohort-spec.json").read_text())
        dc.validate_spec(real_spec, real_protocol)  # no exception
        self.assertEqual(len(real_spec["issuers"]), 23)
        self.assertEqual(len({i["cik"] for i in real_spec["issuers"]}), 23)
        step2_spec = json.loads((root / "config" / "m2-step2-cohort-spec.json").read_text())
        self.assertLessEqual(real_spec["filing_screen_end"], step2_spec["filing_screen_start"])
        # Same fixed issuer set as step 2, not a different sample.
        self.assertEqual({i["cik"] for i in real_spec["issuers"]}, {i["cik"] for i in step2_spec["issuers"]})

    def test_a_well_formed_spec_validates(self):
        p = protocol()
        dc.validate_spec(spec(p), p)  # no exception

    def test_rejects_the_wrong_schema_or_selection_mode(self):
        p = protocol()
        with self.assertRaises(DataError):
            dc.validate_spec(spec(p, schema_version=2), p)
        with self.assertRaises(DataError):
            dc.validate_spec(spec(p, selection_mode="historical_sec_master_mirror"), p)

    def test_rejects_a_protocol_hash_mismatch(self):
        p = protocol()
        with self.assertRaises(DataError):
            dc.validate_spec(spec(p, protocol_sha256="0" * 64), p)

    def test_rejects_an_event_window_that_disagrees_with_the_protocol(self):
        p = protocol()
        s = spec(p, event_window_end="2026-01-05")
        s["protocol_sha256"] = digest(canonical(p))  # keep the hash valid so only the window check can fire
        with self.assertRaises(DataError):
            dc.validate_spec(s, p)

    def test_rejects_an_inverted_filing_screen(self):
        p = protocol()
        with self.assertRaises(DataError):
            dc.validate_spec(spec(p, filing_screen_end="2025-01-01"), p)

    def test_rejects_a_filing_screen_that_would_overlap_milestone_1s_frozen_window(self):
        p = protocol(event_window_end="2026-01-05")
        with self.assertRaises(DataError):
            dc.validate_spec(spec(p, filing_screen_end="2026-01-05", event_window_end="2026-01-05"), p)

    def test_rejects_a_missing_or_malformed_issuer_list(self):
        p = protocol()
        for bad in ([], [{"ticker": "AAA"}], [{"ticker": "AAA", "cik": "1"}], [{"ticker": "", "cik": "0000000001"}]):
            with self.assertRaises(DataError):
                dc.validate_spec(spec(p, issuers=bad), p)

    def test_rejects_a_duplicate_cik(self):
        p = protocol()
        dupe = [{"ticker": "AAA", "cik": "0000000001"}, {"ticker": "AAB", "cik": "0000000001"}]
        with self.assertRaises(DataError):
            dc.validate_spec(spec(p, issuers=dupe), p)

    def test_rejects_missing_allowed_forms(self):
        p = protocol()
        with self.assertRaises(DataError):
            dc.validate_spec(spec(p, allowed_forms=[]), p)


class FreezeTargetedCandidatesTests(unittest.TestCase):
    def run_freeze(self, documents, issuers=None, protocol_overrides=None, spec_overrides=None, retrieved_at="2026-09-28T12:00:00Z"):
        p = protocol(**(protocol_overrides or {}))
        s = spec(p, issuers=issuers, **(spec_overrides or {}))
        client = FakeClient(documents, retrieved_at)
        with tempfile.TemporaryDirectory() as tmp:
            cohort, ledger, report = dc.freeze_targeted_candidates(s, p, tmp, "NRE test contact test@example.test", client=client)
            written = {name: json.loads((Path(tmp) / name).read_text()) for name in
                      ("issuer-cohort.json", "candidate-ledger.json", "discovery-report.json")}
        return cohort, ledger, report, written, client

    def test_one_matching_filing_per_issuer_is_frozen(self):
        docs = {
            "https://data.sec.gov/submissions/CIK0000000001.json": submissions("0000000001", [("0000000001-25-000010", "2025-07-15", "2.02")]),
            "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [("0000000002-25-000020", "2025-08-20", "2.02")]),
        }
        cohort, ledger, report, written, client = self.run_freeze(docs)
        self.assertEqual(sorted(c["candidate_id"] for c in ledger["candidates"]), ["0000000001-25-000010", "0000000002-25-000020"])
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["issuers_with_item_2_02_candidates"], 2)
        self.assertEqual(report["state"], "FROZEN_CANDIDATE_MEMBERSHIP")
        self.assertEqual(written["candidate-ledger.json"], ledger)  # what's on disk matches what's returned
        self.assertEqual(ledger["membership_sha256"],
                         digest(canonical(sorted([{"candidate_id": c["candidate_id"], "source_sha256": c["source_sha256"]}
                                                  for c in ledger["candidates"]], key=lambda x: x["candidate_id"]))))
        for candidate in ledger["candidates"]:
            self.assertEqual(candidate["primary_review_state"], "REQUIRED_POST_FREEZE")
            self.assertIsNone(candidate["primary_source_sha256"])

    def test_a_filing_outside_the_screen_window_is_excluded(self):
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": submissions("0000000001", [
            ("0000000001-25-000001", "2025-05-15", "2.02"),   # before the screen (starts 2025-06-01)
            ("0000000001-26-000002", "2026-01-10", "2.02"),   # after the screen (ends 2026-01-04)
            ("0000000001-25-000003", "2025-09-01", "2.02"),   # inside
        ]), "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        _, ledger, *_ = self.run_freeze(docs)
        self.assertEqual([c["candidate_id"] for c in ledger["candidates"]], ["0000000001-25-000003"])

    def test_a_non_item_2_02_8k_is_excluded(self):
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": submissions("0000000001", [
            ("0000000001-25-000001", "2025-07-01", "5.02"), ("0000000001-25-000002", "2025-07-02", "2.02"),
        ]), "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        _, ledger, *_ = self.run_freeze(docs)
        self.assertEqual([c["candidate_id"] for c in ledger["candidates"]], ["0000000001-25-000002"])

    def test_a_cik_mismatch_between_spec_and_submissions_is_rejected(self):
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": submissions("0000000099", []),
                "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        with self.assertRaises(DataError):
            self.run_freeze(docs)

    def test_a_conflicting_accession_between_source_files_is_rejected(self):
        recent = submissions("0000000001", [("0000000001-25-000001", "2025-07-01", "2.02")],
                             files=[{"name": "CIK0000000001-hist.json", "filingFrom": "2025-01-01", "filingTo": "2025-06-30"}])
        recent["filings"]["recent"]["filingDate"] = ["2025-09-01"]  # forces relevant_history_files to need the continuation
        continuation = {"cik": "0000000001", "filings": {"recent": {
            "accessionNumber": ["0000000001-25-000001"], "form": ["8-K"], "filingDate": ["2025-06-15"], "items": ["1.01"],
            "primaryDocument": ["other.htm"], "acceptanceDateTime": ["2025-06-15T21:00:00.000Z"]}}}  # same id, different row
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": recent,
                "https://data.sec.gov/submissions/CIK0000000001-hist.json": continuation,
                "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        with self.assertRaises(DataError):
            self.run_freeze(docs)

    def test_a_needed_continuation_file_is_fetched_and_its_candidate_included(self):
        recent = submissions("0000000001", [("0000000001-25-000099", "2025-10-15", "2.02")])  # earliest recent date: 2025-10-15
        recent["filings"]["files"] = [{"name": "CIK0000000001-hist.json", "filingFrom": "2025-01-01", "filingTo": "2025-09-30"}]
        continuation = submissions("0000000001", [("0000000001-25-000050", "2025-07-15", "2.02")])
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": recent,
                "https://data.sec.gov/submissions/CIK0000000001-hist.json": continuation,
                "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        cohort, ledger, report, written, client = self.run_freeze(docs)
        self.assertEqual(sorted(c["candidate_id"] for c in ledger["candidates"]), ["0000000001-25-000050", "0000000001-25-000099"])
        self.assertIn("https://data.sec.gov/submissions/CIK0000000001-hist.json", client.calls)
        issuer_1 = next(i for i in cohort["issuers"] if i["cik"] == "0000000001")
        self.assertEqual(issuer_1["observations"], 2)

    def test_an_unsafe_continuation_filename_is_rejected(self):
        recent = submissions("0000000001", [("0000000001-25-000099", "2025-10-15", "2.02")])
        recent["filings"]["files"] = [{"name": "../escape.json", "filingFrom": "2025-01-01", "filingTo": "2025-09-30"}]
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": recent,
                "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        with self.assertRaises(DataError):
            self.run_freeze(docs)

    def test_issuers_are_processed_in_cik_order_regardless_of_spec_order(self):
        issuers = [{"ticker": "BBB", "cik": "0000000002"}, {"ticker": "AAA", "cik": "0000000001"}]
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": submissions("0000000001", []),
                "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        cohort, *_ = self.run_freeze(docs, issuers=issuers)
        self.assertEqual([i["cik"] for i in cohort["issuers"]], ["0000000001", "0000000002"])
        self.assertEqual([i["selection_position"] for i in cohort["issuers"]], [1, 2])

    def test_membership_hash_is_reproducible_across_two_independent_runs(self):
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": submissions("0000000001", [("0000000001-25-000010", "2025-07-15", "2.02")]),
                "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [("0000000002-25-000020", "2025-08-20", "2.02")])}
        _, first, *_ = self.run_freeze(docs)
        _, second, *_ = self.run_freeze(docs)
        self.assertEqual(first["membership_sha256"], second["membership_sha256"])
        self.assertEqual({c["candidate_id"] for c in first["candidates"]}, {c["candidate_id"] for c in second["candidates"]})

    def test_a_bad_user_agent_is_rejected_before_any_network_call(self):
        p = protocol()
        s = spec(p)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(DataError):
            dc.freeze_targeted_candidates(s, p, tmp, "")  # client=None: constructs a real PublicClient, which validates first

    def test_no_prices_or_provider_terms_appear_in_any_output(self):
        docs = {"https://data.sec.gov/submissions/CIK0000000001.json": submissions("0000000001", [("0000000001-25-000010", "2025-07-15", "2.02")]),
                "https://data.sec.gov/submissions/CIK0000000002.json": submissions("0000000002", [])}
        cohort, ledger, report, *_ = self.run_freeze(docs)
        for blob in (cohort, ledger, report):
            text = json.dumps(blob)
            self.assertNotIn("close", text.lower())
            self.assertNotIn("open", text.lower())
        self.assertFalse(report["price_data_accessed_by_this_workflow"])


class CliFreezeTargetedCohortTests(unittest.TestCase):
    """cli.py's own "freeze-targeted-cohort" command, end to end. freeze_targeted_candidates()
    itself is already thoroughly covered above with a directly-injected FakeClient; this only
    proves the CLI's own new wiring (arg parsing, file reading, exit code) is correct, by patching
    the high-level function itself rather than digging into _client()'s own real-PublicClient
    construction path."""

    def test_spec_and_protocol_files_are_read_and_passed_through(self):
        from unittest.mock import patch
        from nre import cli
        p = protocol()
        s = spec(p)
        fake_result = {"state": "FROZEN_CANDIDATE_MEMBERSHIP", "candidate_count": 0}
        with tempfile.TemporaryDirectory() as tmp:
            spec_path, protocol_path = Path(tmp) / "spec.json", Path(tmp) / "protocol.json"
            spec_path.write_text(json.dumps(s), encoding="utf-8")
            protocol_path.write_text(json.dumps(p), encoding="utf-8")
            with patch("nre.depth_cohort.freeze_targeted_candidates", return_value=({}, {}, fake_result)) as mocked, \
                 patch("builtins.print") as output:
                code = cli.main(["freeze-targeted-cohort", "--spec", str(spec_path),
                                 "--protocol", str(protocol_path), "--output", tmp])
                self.assertEqual(code, 0)
                mocked.assert_called_once()
                called_spec, called_protocol = mocked.call_args.args[0], mocked.call_args.args[1]
                self.assertEqual(called_spec, s)
                self.assertEqual(called_protocol, p)
                printed = json.loads(output.call_args_list[0].args[0])
                self.assertEqual(printed["state"], "FROZEN_CANDIDATE_MEMBERSHIP")

    def test_a_non_frozen_state_exits_nonzero(self):
        from unittest.mock import patch
        from nre import cli
        p = protocol()
        s = spec(p)
        with tempfile.TemporaryDirectory() as tmp:
            spec_path, protocol_path = Path(tmp) / "spec.json", Path(tmp) / "protocol.json"
            spec_path.write_text(json.dumps(s), encoding="utf-8")
            protocol_path.write_text(json.dumps(p), encoding="utf-8")
            with patch("nre.depth_cohort.freeze_targeted_candidates",
                      return_value=({}, {}, {"state": "SOMETHING_ELSE"})), \
                 patch("builtins.print"):
                code = cli.main(["freeze-targeted-cohort", "--spec", str(spec_path),
                                 "--protocol", str(protocol_path), "--output", tmp])
                self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
