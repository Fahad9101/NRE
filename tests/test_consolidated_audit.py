import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nre import consolidated_audit as ca
from nre import event_acquire as ea
from nre.acceptance import audit_cohort
from nre.calendar import Calendar
from nre.core import DataError
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
