import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nre import consolidated_audit as ca
from nre import event_acquire as ea
from nre.acceptance import audit_cohort
from nre.calendar import Calendar
from nre.core import DataError, digest
from nre.dataset import build

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads(ea.DEFAULT_SPEC.read_text(encoding="utf-8"))
PROTOCOL = json.loads((ROOT / "config/pilot.json").read_text(encoding="utf-8"))
LEDGER = json.loads((ROOT / "reports/m1-reviewed-candidate-ledger.json").read_text(encoding="utf-8"))
REVIEW = json.loads((ROOT / "reports/m1-acceptance-review.json").read_text(encoding="utf-8"))
CAL = Calendar()
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}
ACCEPTED = ca.accepted_events(SPEC)
DIVIDENDS = {"CXT": {"cash_dividends": [{"ex_date": "2026-02-27", "id": "abc"}]}}


def flat_bar(session):
    return {"t": session + "T00:00:00Z", "o": 123.45, "h": 130.5, "l": 120.25, "c": 125.75, "v": 1000}


def fetch(endpoint, params):
    ticker = params["symbols"]
    event = next(e for e in ACCEPTED if e["security"]["ticker"] == ticker)
    if endpoint == ea.ACTIONS_ENDPOINT:
        return json.dumps({"corporate_actions": DIVIDENDS.get(ticker, {}), "next_page_token": None}).encode()
    rows = [flat_bar(s) for s in ea.event_window(event, CAL)["required_sessions"]]
    return json.dumps({"bars": {ticker: rows}, "next_page_token": None}).encode()


class _Response:
    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size=-1):
        return self._data


class _Opener:
    def open(self, req, timeout=None):
        from urllib.parse import parse_qs, urlsplit
        parts = urlsplit(req.full_url)
        endpoint = parts.scheme + "://" + parts.netloc + parts.path
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        return _Response(fetch(endpoint, params))


class MergeTests(unittest.TestCase):
    def one(self, event):
        window = ea.event_window(event, CAL)
        bars = {s: {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10} for s in window["required_sessions"]}
        return ea.build_bundle(event, SPEC["provider"], window, bars, [], NOW, CAL)

    def test_empty_input_rejected(self):
        with self.assertRaises(DataError):
            ca.merge_bundles([])

    def test_bundles_from_different_events_merge_without_id_collisions(self):
        bundles = [self.one(e) for e in ACCEPTED[:4]]
        merged = ca.merge_bundles(bundles)
        for key, expected in (("events", 4), ("securities", 4), ("providers", 1), ("sources", 12)):
            self.assertEqual(len(merged[key]), expected, key)
        results, report = build(merged)
        self.assertEqual((report["events"], report["mapped_day1"]), (4, 4))

    def test_disagreeing_provider_terms_rejected(self):
        first, second = self.one(ACCEPTED[0]), self.one(ACCEPTED[1])
        second["providers"][0]["research_permitted"] = False
        with self.assertRaises(DataError):
            ca.merge_bundles([first, second])

    def test_events_declare_the_category_the_acceptance_gate_reads(self):
        for event in self.one(ACCEPTED[0])["events"]:
            self.assertEqual((event["category"], event["subtype"]), ("earnings", "results"))


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = ca.assemble(SPEC, ACCEPTED, fetch, CAL, NOW)
        cls.result = audit_cohort(cls.bundle, PROTOCOL, LEDGER, REVIEW)

    def test_every_accepted_event_is_in_the_bundle(self):
        self.assertEqual({e["event_id"] for e in self.bundle["events"]}, {e["event_id"] for e in ACCEPTED})

    def test_event_dependent_gates_pass_on_the_repository_records(self):
        gates = self.result["gates"]
        for name in ("real_data", "availability_mode", "protocol_hash", "selection_frozen_before_prices", "frozen_membership_hash",
                     "all_events_in_window", "earnings_results_only", "issuer_identity", "minimum_events", "minimum_issuers",
                     "independent_timing_spot_checks"):
            self.assertTrue(gates[name], name)

    def test_owner_decision_gates_pass_on_the_repository_records(self):
        for name in ("candidate_accounting", "discovery_coverage_review", "identity_history_review", "provider_rights_review"):
            self.assertTrue(self.result["gates"][name], name)

    def test_only_the_archive_gate_fails_without_the_archive(self):
        self.assertEqual(self.result["failed_gates"], ["candidate_source_hashes"])

    def test_counts_follow_the_non_null_session_20_rule(self):
        counts = self.result["counts"]
        suppressed = sum(1 for e in ACCEPTED if e["security"]["ticker"] in DIVIDENDS)
        self.assertEqual(counts["events"], len(ACCEPTED))
        self.assertEqual(counts["eligible_complete_events"], len(ACCEPTED) - suppressed)
        self.assertEqual(counts["unique_issuers"], len(ACCEPTED) - suppressed)

    def test_milestone_is_never_accepted_by_the_engine(self):
        self.assertIs(self.result["milestone_accepted"], False)

    def test_summary_fits_one_annotation(self):
        line = ca._annotation("notice", ca.summarize(self.result))
        self.assertLess(len(line), 4000)
        self.assertNotIn("\n", line)
        body = json.loads(line[len("::notice title=NRE cohort audit::"):])
        self.assertEqual(body["counts"]["events"], len(ACCEPTED))
        self.assertIn("candidate_accounting", body["failed_gates"] + body["passed_gates"])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = self.root / "nre-sec-freeze" / "raw"
        self.raw.mkdir(parents=True)

    def observation(self, name, payload, sha=None, url="https://data.sec.gov/submissions/CIK0000000001.json"):
        (self.raw / (name + ".payload")).write_bytes(payload)
        meta = {"payload_file": name + ".payload", "raw_file": name + ".raw", "sha256": sha or digest(payload),
                "size": len(payload), "url": url, "retrieved_at": "2026-09-20T12:00:00Z"}
        (self.raw / (name + ".json")).write_text(json.dumps(meta), encoding="utf-8")

    def test_missing_directory_means_no_sources(self):
        self.assertEqual(ca.archive_sources(self.root / "absent"), [])

    def test_payloads_become_verified_sources(self):
        self.observation("a", b'{"filings": [1]}', url="https://data.sec.gov/submissions/CIK0000000001.json")
        self.observation("b", b'{"filings": [2]}', url="https://data.sec.gov/submissions/CIK0000000002.json")
        sources = ca.archive_sources(self.root)
        self.assertEqual(len(sources), 2)
        self.assertEqual(len({s["source_id"] for s in sources}), 2)
        for source in sources:
            self.assertEqual(digest(source["text"].encode("utf-8")), source["sha256"])
            self.assertTrue(source["url"].startswith("https://"))

    def test_tampered_payload_rejected(self):
        self.observation("a", b'{"filings": [1]}', sha="0" * 64)
        with self.assertRaises(DataError):
            ca.archive_sources(self.root)

    def test_identical_payloads_collapse_to_one_source(self):
        self.observation("a", b'{"same": true}')
        self.observation("b", b'{"same": true}')
        self.assertEqual(len(ca.archive_sources(self.root)), 1)

    def test_files_that_are_not_observation_records_are_ignored(self):
        (self.raw / "noise.json").write_text(json.dumps({"unrelated": 1}), encoding="utf-8")
        (self.raw / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(ca.archive_sources(self.root), [])

    def test_archived_payloads_satisfy_the_source_hash_condition(self):
        self.observation("a", b'{"filings": [1]}')
        bundle = ca.assemble(SPEC, ACCEPTED[:2], fetch, CAL, NOW, ca.archive_sources(self.root))
        available = {digest(s["text"].encode("utf-8")) for s in bundle["sources"]}
        self.assertIn(digest(b'{"filings": [1]}'), available)
        build(bundle)

    def test_main_reports_the_archive_size(self):
        self.observation("a", b'{"filings": [1]}')
        with patch.dict("os.environ", ENV, clear=True), patch("nre.consolidated_audit.build_opener", return_value=_Opener()),              patch("builtins.print") as output:
            code = ca.main(["--archive-dir", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.call_args_list[0].args[0])["archive_observations"], 1)


class MainTests(unittest.TestCase):
    def run_main(self, argv, env=ENV):
        with patch.dict("os.environ", env, clear=True), patch("nre.consolidated_audit.build_opener", return_value=_Opener()), \
             patch("builtins.print") as output:
            code = ca.main(argv)
        return code, [call.args[0] for call in output.call_args_list]

    def test_no_credentials_no_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("nre.consolidated_audit.build_opener") as opener, \
             patch("builtins.print") as output:
            self.assertEqual(ca.main([]), 2)
        self.assertIn("MISSING_GITHUB_ACTIONS_SECRETS", output.call_args.args[0])
        opener.assert_not_called()

    def test_runs_and_prints_the_audit_result(self):
        code, printed = self.run_main([])
        body = json.loads(printed[0])
        self.assertEqual(code, 0)
        self.assertTrue(body["audit_ran"])
        self.assertEqual(body["accepted_events"], len(ACCEPTED))
        self.assertIs(body["result"]["milestone_accepted"], False)

    def test_strict_exits_nonzero_while_gates_fail(self):
        code, printed = self.run_main(["--strict"])
        self.assertEqual(code, 2 if json.loads(printed[0])["result"]["failed_gates"] else 0)

    def test_nothing_sensitive_is_printed(self):
        _, printed = self.run_main([])
        text = "\n".join(printed)
        for secret in ("AKTESTKEY123", "SECRETVALUE456", "123.45", "130.5", "120.25", "125.75"):
            self.assertNotIn(secret, text)

    def test_annotation_only_inside_actions(self):
        _, printed = self.run_main([])
        self.assertEqual(len(printed), 1)
        _, printed = self.run_main([], env=dict(ENV, GITHUB_ACTIONS="true"))
        self.assertTrue(printed[-1].startswith("::notice title=NRE cohort audit::"))

    def test_calendar_argument_is_optional_and_additive(self):
        # Explicitly passing a spec that covers the same (2026-only) dates as the default
        # must behave identically to omitting --calendar -- proves the new CLI argument
        # is wired through (main() -> audit_cohort() -> dataset.build()) without changing
        # anything when the calendar it points to covers the same ground as the default.
        code, printed = self.run_main(["--calendar", str(ROOT / "nre" / "calendar-2026.json")])
        default_code, default_printed = self.run_main([])
        self.assertEqual(code, default_code)
        self.assertEqual(json.loads(printed[0])["result"]["gates"], json.loads(default_printed[0])["result"]["gates"])

    def test_invalid_input_rejected(self):
        code, printed = self.run_main(["--ledger", str(ROOT / "config" / "does-not-exist.json")])
        self.assertEqual(code, 2)
        self.assertIn("INPUT_INVALID", printed[0])

    def test_a_failed_fetch_stops_the_audit(self):
        class Failing:
            def open(self, req, timeout=None):
                from urllib.error import URLError
                raise URLError("down")
        with patch.dict("os.environ", ENV, clear=True), patch("nre.consolidated_audit.build_opener", return_value=Failing()), \
             patch("builtins.print") as output:
            code = ca.main([])
        self.assertEqual(code, 2)
        self.assertIn("NETWORK_ERROR", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
