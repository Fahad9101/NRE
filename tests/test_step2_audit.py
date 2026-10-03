"""Milestone 2 step 2's cohort audit with its real raw SEC archive, exercised offline.

Prices are synthetic and flat (no raw Alpaca data is ever committed or needed here); the events spec, protocol, merged calendar, reviewed ledger,
acceptance review, recorded corporate actions and the archived SEC payloads are the real, committed record. The tests show that the audit
reproduces step 2's recorded 2026-09-29 result without the archive (BLOCKED on exactly candidate_source_hashes) and passes all 16 gates with it.
"""
import glob
import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nre import consolidated_audit as ca
from nre import event_acquire as ea
from nre.acceptance import audit_cohort
from nre.calendar import Calendar
from nre.core import digest

ROOT = Path(__file__).resolve().parent.parent


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


SPEC = load("config/m2-step2-events.json")
PROTOCOL = load("config/m2-step2-protocol.json")
FROZEN = load("config/m2-step2-frozen-candidate-ledger.json")
LEDGER = load("reports/m2-step2-reviewed-candidate-ledger.json")
REVIEW = load("reports/m2-step2-acceptance-review.json")
RECORDED = load("reports/m2-step2-label-engine-dry-run-result-2026-09-29.json")["result"]["result"]
CAL = Calendar(spec=load("config/m2-step2-merged-calendar.json"))
ARCHIVE = ROOT / "archive" / "m2-step2-sec-freeze"
NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)
ENV = {"APCA_API_KEY_ID": "AKTESTKEY123", "APCA_API_SECRET_KEY": "SECRETVALUE456"}
ACCEPTED = ca.accepted_events(SPEC)
BY_WINDOW = {(e["security"]["ticker"], ea.event_window(e, CAL)["start"], ea.event_window(e, CAL)["end"]): e for e in ACCEPTED}
assert len(BY_WINDOW) == len(ACCEPTED), "two events would share one fetch key"


def recorded_actions():
    """Every corporate action the real per-batch runs recorded, by event_id (CXT's two dividends and JBSS's, whose ex-date precedes its window)."""
    found = {}
    for path in sorted(glob.glob(str(ROOT / "reports" / "m2-step2-batch*-complete-events-2026-09-29.json"))):
        for event_id, record in json.loads(Path(path).read_text(encoding="utf-8"))["computed_events"].items():
            found[event_id] = record["corporate_actions"]
    return found


ACTIONS = recorded_actions()


def flat_bar(session):
    return {"t": session + "T00:00:00Z", "o": 123.45, "h": 130.5, "l": 120.25, "c": 125.75, "v": 1000}


def fetch(endpoint, params):
    event = BY_WINDOW[(params["symbols"], params["start"], params["end"])]
    window = ea.event_window(event, CAL)
    if endpoint == ea.ACTIONS_ENDPOINT:
        grouped = {}
        for action in ACTIONS[event["event_id"]]:
            grouped.setdefault(action["type"], []).append({"ex_date": action["ex_date"], "id": action["id"]})
        return json.dumps({"corporate_actions": grouped, "next_page_token": None}).encode()
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


class ArchiveTests(unittest.TestCase):
    def test_the_archive_is_the_real_raw_bytes_and_reproduces_every_candidate_source_hash(self):
        sources = ca.archive_sources(ARCHIVE)
        self.assertEqual(len(sources), 23)
        have = {digest(s["text"].encode("utf-8")) for s in sources}
        for candidate in LEDGER["candidates"]:
            self.assertIn(candidate["source_sha256"], have, candidate["candidate_id"])
        self.assertEqual({c["discovery_submission_representation"] for c in FROZEN["candidates"]}, {"raw"})

    def test_payloads_are_stored_byte_exact_with_nothing_git_could_normalize(self):
        raw = ARCHIVE / "nre-sec-freeze" / "raw"
        payloads = sorted(raw.glob("*.payload"))
        self.assertEqual(len(payloads), 23)
        for path in payloads:
            body = path.read_bytes()
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256(body).hexdigest(), meta["sha256"])
            self.assertEqual((len(body), meta["payload_file"], meta["source_representation"]), (meta["size"], path.name, "raw_sec_response"))
            self.assertNotIn(b"\r", body)
            self.assertNotIn(b"\n", body)

    def test_workflow_passes_the_archive_and_watches_it(self):
        text = (ROOT / ".github" / "workflows" / "depth-consolidated-audit.yml").read_text(encoding="utf-8")
        for fragment in ("--archive-dir archive/m2-step2-sec-freeze", "'archive/m2-step2-sec-freeze/**'", "--spec config/m2-step2-events.json",
                         "--calendar config/m2-step2-merged-calendar.json"):
            self.assertIn(fragment, text)


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archived = ca.archive_sources(ARCHIVE)
        cls.bundle = ca.assemble(SPEC, ACCEPTED, fetch, CAL, NOW, cls.archived)
        cls.with_archive = audit_cohort(cls.bundle, PROTOCOL, LEDGER, REVIEW, CAL)
        bare = dict(cls.bundle, sources=[s for s in cls.bundle["sources"] if not s["source_id"].startswith("sec-freeze-")])
        cls.without_archive = audit_cohort(bare, PROTOCOL, LEDGER, REVIEW, CAL)

    def test_without_the_archive_it_reproduces_the_recorded_blocked_result(self):
        self.assertEqual(self.without_archive["failed_gates"], RECORDED["failed_gates"])
        self.assertEqual(self.without_archive["failed_gates"], ["candidate_source_hashes"])
        self.assertEqual(self.without_archive["status"], RECORDED["status"])
        self.assertEqual(self.without_archive["counts"], RECORDED["counts"])
        self.assertEqual(self.without_archive["details"]["spot_checked_events_by_timing"], RECORDED["details"]["spot_checked_events_by_timing"])
        for key in ("protocol_sha256", "membership_sha256", "ledger_sha256", "review_sha256"):
            self.assertEqual(self.without_archive[key], RECORDED[key], key)

    def test_with_the_archive_every_gate_passes(self):
        self.assertEqual(self.with_archive["failed_gates"], [])
        self.assertEqual(self.with_archive["status"], "STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED")
        self.assertEqual(len(self.with_archive["gates"]), 16)
        self.assertEqual(self.with_archive["counts"], RECORDED["counts"])

    def test_only_candidate_source_hashes_differs_between_the_two(self):
        differing = [name for name in self.with_archive["gates"] if self.with_archive["gates"][name] != self.without_archive["gates"][name]]
        self.assertEqual(differing, ["candidate_source_hashes"])

    def test_counts_follow_the_non_null_session_20_rule(self):
        counts = self.with_archive["counts"]
        self.assertEqual((counts["candidates"], counts["events"], counts["eligible_complete_events"], counts["unique_issuers"]), (48, 45, 43, 22))
        self.assertEqual(counts["dispositions"], {"included": 45, "excluded": 2, "quarantined": 1})

    def test_milestone_is_never_accepted_by_the_engine(self):
        self.assertIs(self.with_archive["milestone_accepted"], False)


class MainTests(unittest.TestCase):
    ARGS = ["--spec", "config/m2-step2-events.json", "--protocol", "config/m2-step2-protocol.json",
            "--ledger", "reports/m2-step2-reviewed-candidate-ledger.json", "--review", "reports/m2-step2-acceptance-review.json",
            "--calendar", "config/m2-step2-merged-calendar.json", "--archive-dir", "archive/m2-step2-sec-freeze"]

    def test_the_workflow_command_runs_end_to_end_offline(self):
        absolute = [str(ROOT / a) if a.startswith(("config/", "reports/", "archive/")) else a for a in self.ARGS]
        with patch.dict("os.environ", ENV, clear=True), patch("nre.consolidated_audit.build_opener", return_value=_Opener()), \
             patch("builtins.print") as output:
            code = ca.main(absolute)
        body = json.loads(output.call_args_list[0].args[0])
        self.assertEqual(code, 0)
        self.assertTrue(body["audit_ran"])
        self.assertEqual((body["accepted_events"], body["archive_observations"]), (45, 23))
        self.assertEqual(body["result"]["failed_gates"], [])
        text = json.dumps(body)
        for secret in ("AKTESTKEY123", "SECRETVALUE456", "123.45", "130.5", "120.25", "125.75"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
