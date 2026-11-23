import copy
import json
import os
import unittest
from contextlib import contextmanager, redirect_stdout
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nre import m6_guidance_acquire as acquire
from nre import m6_guidance_compare as compare
from nre.calendar import Calendar
from nre.core import DataError, canonical, digest, timestamp
from nre.m5_phase1b_audit import load
from nre.m6_guidance_price_basis import ANCHOR_DOMAIN, anchor_params
from nre.m6_guidance_warmup_opening import opening_commitment

ROOT = acquire.ROOT
OPEN, ANCHOR, CLOSE = 110.125, 100.5, 105.75
TRADE_ID = 987654321001


class SyntheticAcquisition:
    """Synthetic request/receipt fixture; never constructs a network client."""
    def __init__(self):
        self.protocol = {"calendar": "config/m2-merged-calendar-2024-2026.json"}
        self.calendar = Calendar(load(ROOT / self.protocol["calendar"]))
        self.event = {"event_id": "synthetic-event", "symbol": "SYN", "cik": "synthetic-cik",
                      "reaction_session": "2025-01-08", "scheduled_open_at": "2025-01-08T14:30:00+00:00",
                      "feature_cutoff_at": "2025-01-08T14:15:00+00:00", "revision_fraction": 0.1}
        self.descriptor = {**self.event, "anchor_session": "2025-01-07", "subset": "warmup", "clean_window": True}
        self.quality = {self.event["event_id"]: {"hard_exclusions": [], "soft_caveats": []}}
        self.warmup = {"events": [self.descriptor], "protocol_sha256": "a" * 64, "cohort_sha256": "b" * 64}
        self.basis = {"events": [self.descriptor], "protocol_sha256": "a" * 64, "cohort_sha256": "c" * 64}
        self.config = {"request_budget": 30, "corporate_action_inventory_end": "2026-11-22",
                       "protocol_sha256": "a" * 64, "final_source_review": "synthetic-source-review.json",
                       "input_canonical_sha256": {"synthetic-source-review.json": "d" * 64}}
        self.anchor = {"t": "2025-01-07T05:00:00+00:00", "o": ANCHOR, "h": 112.75, "l": 90.25,
                       "c": ANCHOR, "v": 123456, "n": 1234}
        self.close = {"t": "2025-01-08T05:00:00+00:00", "o": OPEN, "h": 115.75, "l": 90.25,
                      "c": CLOSE, "v": 234567, "n": 2345}
        self.open = OPEN
        self.missing_close = False
        self.requests = []
        self.preparation = {"warmup_openings": {"events": []}, "price_basis": {
            "events": [], "anchor_commitment_scheme": ANCHOR_DOMAIN,
            "corporate_action_inventory": {"query": {"symbols": "SYN", "start": "2024-01-01", "end": "2026-11-21",
                                                       "limit": 1000, "sort": "asc", "data_quality": "all", "region": "all"}}}}
        self.repin()

    def official(self):
        return {"x": "Q", "z": "C", "c": ["Q"], "i": TRADE_ID, "p": self.open,
                "t": (timestamp(self.event["scheduled_open_at"]) + timedelta(seconds=1)).isoformat()}

    def repin(self):
        opening_sha = opening_commitment(self.descriptor, self.official(), self.warmup["protocol_sha256"], self.warmup["cohort_sha256"])
        params = anchor_params(self.descriptor, self.calendar)
        anchor_sha = digest(canonical({"domain": ANCHOR_DOMAIN, "protocol_sha256": self.basis["protocol_sha256"],
                                       "cohort_sha256": self.basis["cohort_sha256"], "event_id": self.event["event_id"],
                                       "symbol": self.event["symbol"], "anchor_session": self.descriptor["anchor_session"],
                                       "query": params, "raw_anchor_bar": self.anchor}))
        self.preparation["warmup_openings"]["events"] = [{"event_id": self.event["event_id"], "opening_commitment_sha256": opening_sha}]
        self.preparation["price_basis"]["events"] = [{"event_id": self.event["event_id"], "anchor_commitment_sha256": anchor_sha}]

    def locked(self):
        return self.config, self.protocol, [self.event], self.quality, self.warmup, self.basis

    def fetch(self, endpoint, params):
        self.requests.append((endpoint, dict(params)))
        if endpoint == acquire.ea.ACTIONS_ENDPOINT:
            self.assert_ca(params)
            return json.dumps({"corporate_actions": {"cash_dividends": [{
                "id": "synthetic-dividend", "symbol": "SYN", "ex_date": "2025-01-20",
                "process_date": "2025-01-19", "rate": 918273.125}]}, "next_page_token": None}).encode()
        if endpoint.endswith("/trades"):
            acquire.validate_trade_request(self.event, endpoint, params)
            return json.dumps({"symbol": "SYN", "trades": [self.official()], "next_page_token": None}).encode()
        if endpoint == acquire.ea.BARS_ENDPOINT:
            if params == anchor_params(self.descriptor, self.calendar):
                rows = [self.anchor]
            elif params == anchor_params(dict(self.descriptor, anchor_session=self.event["reaction_session"]), self.calendar):
                rows = [] if self.missing_close else [self.close]
            else:
                raise AssertionError("Unexpected bar request outside the two registered sessions")
            return json.dumps({"bars": {"SYN": rows}, "next_page_token": None}).encode()
        raise AssertionError("Unexpected provider endpoint")

    def assert_ca(self, params):
        expected = dict(self.preparation["price_basis"]["corporate_action_inventory"]["query"], end=self.config["corporate_action_inventory_end"])
        if params != expected:
            raise AssertionError("Unexpected corporate-action discovery request")

    @contextmanager
    def patched(self, acquisition=None):
        def controlled_load(path):
            if path == ROOT / acquire.PREPARATION:
                return self.preparation
            if path == ROOT / acquire.ACQUISITION and acquisition is not None:
                return acquisition
            return load(path)
        with patch.object(acquire, "locked_inputs", side_effect=lambda root: self.locked()), \
                patch.object(acquire, "load", side_effect=controlled_load):
            yield


class GuidanceAcquisitionTests(unittest.TestCase):
    def fixture(self):
        return SyntheticAcquisition()

    def test_acquisition_binds_exact_open_anchor_and_close_without_publishing_values(self):
        f = self.fixture()
        with f.patched():
            manifest, private, (_, events, quality) = acquire.acquire(ROOT, f.fetch)
        self.assertEqual((manifest["requests"], manifest["closing_outcome_requests"], manifest["labels_committed"], manifest["model_runs"]), (4, 1, 1, 0))
        self.assertEqual(len(f.requests), 4)
        self.assertEqual(len(manifest["corporate_action_receipts"]), 1)
        self.assertEqual(len(manifest["events"][0]["receipts"]), 3)
        self.assertRegex(manifest["events"][0]["label_commitment_sha256"], r"^[0-9a-f]{64}$")
        self.assertAlmostEqual(private[f.event["event_id"]]["gap"], OPEN / ANCHOR - 1)
        self.assertAlmostEqual(private[f.event["event_id"]]["close_return"], CLOSE / ANCHOR - 1)
        self.assertEqual(private[f.event["event_id"]]["mature_at"], "2025-01-08T21:05:00+00:00")
        self.assertEqual(events, [f.event])
        self.assertEqual(quality, f.quality)
        serialized = json.dumps(manifest)
        for forbidden in (str(OPEN), str(ANCHOR), str(CLOSE), str(TRADE_ID), "918273.125", '"gap"', '"close_return"', '"raw_anchor_bar"', '"price"', '"rate"'):
            self.assertNotIn(forbidden, serialized)

    def test_an_opening_commitment_change_withholds_before_anchor_or_close(self):
        f = self.fixture()
        f.preparation["warmup_openings"]["events"][0]["opening_commitment_sha256"] = "0" * 64
        with f.patched():
            manifest, private, _ = acquire.acquire(ROOT, f.fetch)
        self.assertEqual((manifest["requests"], manifest["closing_outcome_requests"]), (2, 0))
        self.assertFalse(private)
        self.assertEqual(manifest["aggregate_attrition"], {"opening_commitment_mismatch": 1})
        self.assertEqual(manifest["events"][0]["status"], "withheld")

    def test_an_anchor_commitment_change_withholds_before_reaction_close(self):
        f = self.fixture()
        f.preparation["price_basis"]["events"][0]["anchor_commitment_sha256"] = "0" * 64
        with f.patched():
            manifest, private, _ = acquire.acquire(ROOT, f.fetch)
        self.assertEqual((manifest["requests"], manifest["closing_outcome_requests"]), (3, 0))
        self.assertFalse(private)
        self.assertEqual(manifest["aggregate_attrition"], {"anchor_commitment_mismatch": 1})

    def test_source_hard_exclusion_requests_no_event_market_records(self):
        f = self.fixture()
        f.quality[f.event["event_id"]]["hard_exclusions"] = ["synthetic-source-hard"]
        with f.patched():
            manifest, private, _ = acquire.acquire(ROOT, f.fetch)
        self.assertEqual(len(f.requests), 1)  # Fixed-universe metadata inventory only.
        self.assertEqual(f.requests[0][0], acquire.ea.ACTIONS_ENDPOINT)
        self.assertEqual(manifest["closing_outcome_requests"], 0)
        self.assertFalse(private)
        self.assertEqual(manifest["events"][0]["quality_state"], "source_withheld")

    def test_zero_nonfinite_and_missing_price_labels_are_generic_event_withholds(self):
        for kind in ("zero_gap", "nonfinite_close", "missing_close"):
            with self.subTest(kind=kind):
                f = self.fixture()
                if kind == "zero_gap":
                    f.open = ANCHOR
                    f.repin()
                elif kind == "nonfinite_close":
                    f.close["c"] = float("nan")
                else:
                    f.missing_close = True
                with f.patched():
                    manifest, private, _ = acquire.acquire(ROOT, f.fetch)
                self.assertFalse(private)
                row = manifest["events"][0]
                self.assertEqual((row["status"], row["quality_state"], row["label_commitment_sha256"]), ("withheld", "price_quality_withheld", None))
                self.assertEqual(manifest["closing_outcome_requests"], 1)
                self.assertNotIn("zero_gap", json.dumps(row))
                self.assertNotIn("NaN", json.dumps(manifest))

    def test_transport_rejects_mutated_metadata_or_close_session_before_fetch(self):
        original_paginate = acquire.ea._paginate
        for kind in ("metadata_end", "close_window", "anchor_feed"):
            f, bar_calls = self.fixture(), 0

            def mutate_then_paginate(fetch, params, payload_key):
                nonlocal bar_calls
                modified = dict(params)
                if payload_key == "corporate_actions" and kind == "metadata_end":
                    modified["end"] = "2027-01-01"
                if payload_key == "bars":
                    bar_calls += 1
                    if kind == "anchor_feed" and bar_calls == 1:
                        modified["feed"] = "iex"
                    if kind == "close_window" and bar_calls == 2:
                        modified["end"] = "2025-01-09T23:59:59-05:00"
                return original_paginate(fetch, modified, payload_key)

            with self.subTest(kind=kind), f.patched(), patch.object(acquire.ea, "_paginate", side_effect=mutate_then_paginate):
                with self.assertRaises(DataError):
                    acquire.acquire(ROOT, f.fetch)
            # The fake transport asserts exact recipes independently; no mutated
            # request can reach it and turn this into an AssertionError instead.
            self.assertTrue(all(p.get("feed") != "iex" and p.get("end") not in
                                ("2027-01-01", "2025-01-09T23:59:59-05:00") for _, p in f.requests))

    def claim(self, f, manifest):
        return {"attempt_id": "guidance-v2-001", "protocol_sha256": f.config["protocol_sha256"],
                "acquisition_sha256": digest(canonical(manifest)),
                "execution_configuration_sha256": digest(canonical(f.config)),
                "workflow_run_id": "123456", "execution_commit": "synthetic-execution-commit"}

    def test_changed_request_or_label_commitment_cannot_reach_the_model(self):
        f = self.fixture()
        with f.patched():
            manifest, private, inputs = acquire.acquire(ROOT, f.fetch)
        claim = self.claim(f, manifest)
        for change in ("request", "label", "maturity"):
            changed = copy.deepcopy(manifest)
            if change == "request":
                changed["events"][0]["receipts"][0]["request_sha256"] = "0" * 64
            elif change == "label":
                changed["events"][0]["label_commitment_sha256"] = "0" * 64
            else:
                changed["events"][0]["close_mature_at"] = "2025-01-08T21:06:00+00:00"
            with self.subTest(change=change), f.patched(manifest), patch.dict(os.environ, {"GITHUB_RUN_ID": claim["workflow_run_id"], "GITHUB_SHA": claim["execution_commit"]}), \
                    patch.object(acquire, "acquire", return_value=(changed, private, inputs)), \
                    patch.object(compare, "compare", side_effect=AssertionError("Model fitted before acquisition replay matched")):
                with self.assertRaises(DataError):
                    acquire.score_once(ROOT, lambda endpoint, params: self.fail("Unexpected network"), claim)

    def test_wire_response_hash_change_preserves_semantic_pins_and_is_recorded(self):
        f = self.fixture()
        with f.patched():
            manifest, private, inputs = acquire.acquire(ROOT, f.fetch)
        changed = copy.deepcopy(manifest)
        changed["events"][0]["receipts"][0]["response_sha256"] = "0" * 64
        claim = self.claim(f, manifest)
        with f.patched(manifest), patch.dict(os.environ, {"GITHUB_RUN_ID": claim["workflow_run_id"], "GITHUB_SHA": claim["execution_commit"]}), \
                patch.object(acquire, "acquire", return_value=(changed, private, inputs)), \
                patch.object(compare, "compare", return_value={"decision": "synthetic-stop"}) as mocked:
            result = acquire.score_once(ROOT, lambda endpoint, params: self.fail("Unexpected network"), claim)
        mocked.assert_called_once()
        self.assertEqual(result["acquisition_sha256"], digest(canonical(manifest)))
        self.assertIn("0" * 64, json.dumps(result))
        self.assertNotIn('"gap"', json.dumps(result))

    def test_wrong_workflow_claim_fails_before_acquisition_and_fitting(self):
        f = self.fixture()
        with f.patched():
            manifest, _, _ = acquire.acquire(ROOT, f.fetch)
        claim = self.claim(f, manifest)
        for change in ({"workflow_run_id": "another-run"}, {"execution_commit": "another-commit"}, {"acquisition_sha256": "0" * 64}):
            with self.subTest(change=change), f.patched(manifest), \
                    patch.dict(os.environ, {"GITHUB_RUN_ID": "123456", "GITHUB_SHA": "synthetic-execution-commit"}), \
                    patch.object(acquire, "acquire", side_effect=AssertionError("Acquisition called with wrong claim")), \
                    patch.object(compare, "compare", side_effect=AssertionError("Model fitted with wrong claim")):
                with self.assertRaises(DataError):
                    acquire.score_once(ROOT, lambda endpoint, params: self.fail("Unexpected network"), claim | change)

    def test_exact_replay_hands_only_private_labels_to_one_comparison_call(self):
        f = self.fixture()
        with f.patched():
            manifest, private, inputs = acquire.acquire(ROOT, f.fetch)
        claim = self.claim(f, manifest)
        with f.patched(manifest), patch.dict(os.environ, {"GITHUB_RUN_ID": claim["workflow_run_id"], "GITHUB_SHA": claim["execution_commit"]}), \
                patch.object(acquire, "acquire", return_value=(manifest, private, inputs)), \
                patch.object(compare, "compare", return_value={"decision": "synthetic-stop"}) as mocked:
            result = acquire.score_once(ROOT, lambda endpoint, params: self.fail("Unexpected network"), claim)
        mocked.assert_called_once_with(inputs[0], inputs[1], private, inputs[2])
        self.assertEqual(result["scoring_attempts"], 1)
        self.assertEqual(result["comparison"], {"decision": "synthetic-stop"})
        self.assertNotIn('"gap"', json.dumps(result))

    def test_cli_redacts_untrusted_error_payload_and_credentials(self):
        output = StringIO()
        with TemporaryDirectory() as directory, patch.object(acquire, "ROOT", Path(directory)), \
                patch.object(acquire.subprocess, "check_output", return_value=""), \
                patch("sys.argv", ["guidance", "acquire"]), \
                patch.dict(os.environ, {"APCA_API_KEY_ID": "synthetic-key", "APCA_API_SECRET_KEY": "synthetic-secret"}), \
                patch.object(acquire.ea, "make_fetch", return_value=lambda endpoint, params: None), \
                patch.object(acquire, "acquire", side_effect=RuntimeError("synthetic-secret price918273.125")), redirect_stdout(output):
            self.assertEqual(acquire.main(), 2)
        self.assertEqual(json.loads(output.getvalue()), {"status": "guidance_execution_failed", "reason": "RuntimeError"})

    def test_existing_attempt_blocks_another_acquisition_before_provider_creation(self):
        output = StringIO()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / acquire.ATTEMPT
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            with patch.object(acquire, "ROOT", root), patch.object(acquire.subprocess, "check_output", return_value=""), \
                    patch("sys.argv", ["guidance", "acquire"]), \
                    patch.object(acquire.ea, "make_fetch", side_effect=AssertionError("Provider created after existing attempt")), redirect_stdout(output):
                self.assertEqual(acquire.main(), 2)
        self.assertEqual(json.loads(output.getvalue()), {"status": "guidance_execution_failed", "reason": "DataError"})
