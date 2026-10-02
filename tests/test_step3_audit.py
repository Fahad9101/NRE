"""Milestone 2 step 3's cohort audit, exercised offline.

Prices are synthetic and flat (no raw Alpaca data is ever committed or needed here); everything else -- the events spec, protocol,
merged calendar, reviewed ledger, acceptance review and the archived SEC-freeze payloads -- is the real, committed record. These tests
prove the records are mutually consistent and that the audit's structural gates behave as documented, before and after the real run.
"""
import glob
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nre import consolidated_audit as ca
from nre import event_acquire as ea
from nre.acceptance import audit_cohort
from nre.calendar import Calendar
from nre.core import canonical, digest, timestamp

ROOT = Path(__file__).resolve().parent.parent


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


SPEC = load("config/m2-step3-events.json")
PROTOCOL = load("config/m2-step3-protocol.json")
FROZEN = load("config/m2-step3-frozen-candidate-ledger.json")
LEDGER = load("reports/m2-step3-reviewed-candidate-ledger.json")
REVIEW = load("reports/m2-step3-acceptance-review.json")
CAL = Calendar(spec=load("config/m2-step3-merged-calendar.json"))
ARCHIVE = ROOT / "archive" / "m2-step3-sec-freeze"
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}
ACCEPTED = ca.accepted_events(SPEC)
# CXT's three real cash dividends (ex-dates), the only corporate actions among the 60 attested events.
DIVIDENDS = {"2024-11-29": "d1", "2025-02-28": "d2", "2025-05-30": "d3"}
BY_WINDOW = {(e["security"]["ticker"], ea.event_window(e, CAL)["start"], ea.event_window(e, CAL)["end"]): e for e in ACCEPTED}
assert len(BY_WINDOW) == len(ACCEPTED), "two events would share one fetch key"


def flat_bar(session):
    return {"t": session + "T00:00:00Z", "o": 123.45, "h": 130.5, "l": 120.25, "c": 125.75, "v": 1000}


def fetch(endpoint, params):
    event = BY_WINDOW[(params["symbols"], params["start"], params["end"])]
    window = ea.event_window(event, CAL)
    if endpoint == ea.ACTIONS_ENDPOINT:
        found = [{"ex_date": d, "id": i} for d, i in DIVIDENDS.items()
                 if event["security"]["ticker"] == "CXT" and window["required_sessions"][0] <= d <= window["required_sessions"][-1]]
        return json.dumps({"corporate_actions": {"cash_dividends": found} if found else {}, "next_page_token": None}).encode()
    rows = [flat_bar(s) for s in window["required_sessions"]]
    return json.dumps({"bars": {params["symbols"]: rows}, "next_page_token": None}).encode()


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
        return _Response(fetch(endpoint, {k: v[0] for k, v in parse_qs(parts.query).items()}))


class RecordsTests(unittest.TestCase):
    def test_every_attested_event_is_pinned_and_there_are_sixty(self):
        self.assertEqual(len(SPEC["events"]), 60)
        self.assertEqual(len(ACCEPTED), 60)
        for event in SPEC["events"]:
            self.assertEqual(set(event["attestations"]), ea.ATTESTATIONS, event["event_id"])

    def test_reviewed_ledger_is_the_frozen_ledger_plus_dispositions(self):
        for key in ("frozen_at", "membership_sha256", "protocol_sha256"):
            self.assertEqual(LEDGER[key], FROZEN[key])
        self.assertEqual(len(LEDGER["candidates"]), len(FROZEN["candidates"]), 66)
        for reviewed, frozen in zip(LEDGER["candidates"], FROZEN["candidates"]):
            self.assertEqual({k: v for k, v in reviewed.items() if k not in ("disposition", "event_id", "reason")}, frozen)

    def test_dispositions_account_for_every_candidate(self):
        included = {c["candidate_id"]: c["event_id"] for c in LEDGER["candidates"] if c["disposition"] == "included"}
        self.assertEqual(included, {e["candidate_id"]: e["event_id"] for e in SPEC["events"]})
        excluded = [c for c in LEDGER["candidates"] if c["disposition"] == "excluded"]
        self.assertEqual((len(included), len(excluded)), (60, 6))
        for c in excluded:
            self.assertIsNone(c["event_id"])
            self.assertTrue(c["reason"].strip(), c["candidate_id"])
        self.assertEqual({(c["ticker"], c["filing_date"]) for c in excluded},
                         {("CACI", "2025-04-24"), ("OKTA", "2025-02-04"), ("REAL", "2025-02-10"), ("ALKT", "2025-02-27"),
                          ("REKR", "2025-03-17"), ("SLSN", "2025-03-26")})

    def test_hashes_and_ordering_the_gates_read(self):
        self.assertEqual(LEDGER["protocol_sha256"], digest(canonical(PROTOCOL)))
        membership = sorted([{k: c.get(k) for k in ("candidate_id", "source_sha256")} for c in LEDGER["candidates"]],
                            key=lambda c: c["candidate_id"])
        self.assertEqual(REVIEW["frozen_membership_sha256"], digest(canonical(membership)))
        self.assertLess(timestamp(LEDGER["frozen_at"]), timestamp(REVIEW["prices_first_accessed_at"]))

    def test_archive_reproduces_every_candidate_source_hash(self):
        sources = ca.archive_sources(ARCHIVE)
        self.assertEqual(len(sources), 23)
        have = {digest(s["text"].encode("utf-8")) for s in sources}
        for c in LEDGER["candidates"]:
            self.assertIn(c["source_sha256"], have, c["candidate_id"])

    def test_spot_checks_are_complete_events_covering_both_timing_classes(self):
        labels = {}
        for path in sorted(glob.glob(str(ROOT / "reports" / "m2-step3-batch*-complete-events-2026-10-02.json"))):
            for event_id, record in json.loads(Path(path).read_text(encoding="utf-8"))["computed_events"].items():
                labels[event_id] = record["labels"]
        self.assertEqual(set(labels), {e["event_id"] for e in ACCEPTED})
        by_id = {e["event_id"]: e for e in ACCEPTED}
        timings = {}
        for check in REVIEW["spot_checks"]:
            self.assertIsNotNone(labels[check["event_id"]]["session_20_close_return"], check["event_id"])
            self.assertTrue(check["evidence"] and check["reviewers"])
            timings.setdefault(by_id[check["event_id"]]["expected_release_timing"], set()).add(check["event_id"])
        self.assertEqual(set(timings), {"premarket", "after_hours"})
        self.assertTrue(all(len(v) >= 2 for v in timings.values()))

    def test_independent_timing_report_covers_every_spot_check(self):
        report = load("reports/m2-step3-independent-timing-spot-checks-2026-10-02.json")
        self.assertEqual({c["event_id"] for c in report["checks"]}, {c["event_id"] for c in REVIEW["spot_checks"]})
        for check in report["checks"]:
            self.assertTrue(check["result"].startswith("AGREES"), check["event_id"])

    def test_workflow_audits_the_step3_files(self):
        text = (ROOT / ".github" / "workflows" / "depth3-consolidated-audit.yml").read_text(encoding="utf-8")
        for fragment in ("python -m nre.consolidated_audit", "--spec config/m2-step3-events.json",
                         "--protocol config/m2-step3-protocol.json", "--ledger reports/m2-step3-reviewed-candidate-ledger.json",
                         "--review reports/m2-step3-acceptance-review.json", "--calendar config/m2-step3-merged-calendar.json",
                         "--archive-dir archive/m2-step3-sec-freeze", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
            self.assertIn(fragment, text)


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archived = ca.archive_sources(ARCHIVE)
        cls.bundle = ca.assemble(SPEC, ACCEPTED, fetch, CAL, NOW, cls.archived)
        cls.with_archive = audit_cohort(cls.bundle, PROTOCOL, LEDGER, REVIEW, CAL)
        bare = dict(cls.bundle, sources=[s for s in cls.bundle["sources"] if not s["source_id"].startswith("sec-freeze-")])
        cls.without_archive = audit_cohort(bare, PROTOCOL, LEDGER, REVIEW, CAL)

    def test_every_attested_event_is_in_the_merged_bundle(self):
        self.assertEqual({e["event_id"] for e in self.bundle["events"]}, {e["event_id"] for e in ACCEPTED})

    def test_every_gate_passes_with_the_archive(self):
        self.assertEqual(self.with_archive["failed_gates"], [])
        self.assertEqual(self.with_archive["status"], "STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED")
        self.assertEqual(len(self.with_archive["gates"]), 16)

    def test_only_the_archive_gate_fails_without_the_archive(self):
        self.assertEqual(self.without_archive["failed_gates"], ["candidate_source_hashes"])

    def test_counts_follow_the_non_null_session_20_rule(self):
        counts = self.with_archive["counts"]
        self.assertEqual(counts["candidates"], 66)
        self.assertEqual(counts["events"], 60)
        self.assertEqual(counts["eligible_complete_events"], 57)  # CXT's three dividend-suppressed events drop out
        self.assertEqual(counts["unique_issuers"], 22)
        self.assertEqual(counts["dispositions"], {"included": 60, "excluded": 6})

    def test_spot_checks_land_in_both_timing_classes(self):
        checked = self.with_archive["details"]["spot_checked_events_by_timing"]
        self.assertEqual(set(checked), {"premarket", "after_hours"})
        self.assertTrue(all(len(v) >= 2 for v in checked.values()))

    def test_milestone_is_never_accepted_by_the_engine(self):
        self.assertIs(self.with_archive["milestone_accepted"], False)

    def test_summary_fits_one_annotation(self):
        line = ca._annotation("notice", ca.summarize(self.with_archive, len(self.archived)))
        self.assertLess(len(line), 4000)
        self.assertNotIn("\n", line)


class MainTests(unittest.TestCase):
    ARGS = ["--spec", "config/m2-step3-events.json", "--protocol", "config/m2-step3-protocol.json",
            "--ledger", "reports/m2-step3-reviewed-candidate-ledger.json", "--review", "reports/m2-step3-acceptance-review.json",
            "--calendar", "config/m2-step3-merged-calendar.json", "--archive-dir", "archive/m2-step3-sec-freeze"]

    def test_the_workflow_command_runs_end_to_end_offline(self):
        absolute = [str(ROOT / a) if a.startswith(("config/", "reports/", "archive/")) else a for a in self.ARGS]
        with patch.dict("os.environ", ENV, clear=True), patch("nre.consolidated_audit.build_opener", return_value=_Opener()), \
             patch("builtins.print") as output:
            code = ca.main(absolute)
        body = json.loads(output.call_args_list[0].args[0])
        self.assertEqual(code, 0)
        self.assertTrue(body["audit_ran"])
        self.assertEqual((body["accepted_events"], body["archive_observations"]), (60, 23))
        self.assertEqual(body["result"]["failed_gates"], [])
        text = json.dumps(body)
        for secret in ("AKTESTKEY123", "SECRETVALUE456", "123.45", "130.5", "120.25", "125.75"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
