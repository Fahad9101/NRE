import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nre.core import DataError, canonical, digest
from nre.m5_phase1b_audit import load
from nre.m6_guidance_protocol import FREEZE, PROTOCOL, ROOT, check_registration, verify_evidence


class GuidanceProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = load(ROOT / PROTOCOL)
        self.frame = load(ROOT / self.protocol["frame"])
        self.evidence = load(ROOT / self.protocol["held_evidence"])
        self.raw = load(ROOT / self.protocol["raw_opening_result"])
        self.calendar = load(ROOT / self.protocol["calendar"])

    def verify(self, evidence=None, raw=None):
        return verify_evidence(self.protocol, self.frame, evidence or self.evidence, raw or self.raw, self.calendar)

    def test_registration_checks_metadata_and_reports_pending_execution(self):
        result = check_registration()
        support = result["raw_opening_support"]
        self.assertTrue(result["raw_opening_coverage_passed"])
        self.assertEqual((support["rows"], support["issuers"], support["sessions"]), (58, 20, 46))
        self.assertEqual(result["model_runs"], 0)
        self.assertEqual(result["stage"], "PRE_REGISTERED_PENDING_WARMUP_AND_LABEL_MANIFESTS")
        self.assertEqual(support["guidance_signs"], {"raise": 40, "unchanged": 14, "cut": 4})

    def test_mismatched_raw_open_membership_and_counts_are_rejected(self):
        for change in ("membership", "counts"):
            raw = copy.deepcopy(self.raw)
            if change == "membership":
                raw["output"]["events"][0]["reaction_session"] = "2025-07-25"
            else:
                raw["output"]["matched"] = 57
            with self.subTest(change=change), self.assertRaises(DataError):
                self.verify(raw=raw)

    def test_equal_feature_cutoff_and_invalid_guidance_are_rejected(self):
        for change in ("cutoff", "range", "revision", "block"):
            evidence = copy.deepcopy(self.evidence)
            row = evidence["guidance_candidates"][0]
            if change == "cutoff":
                row["current"]["availability_proxy"] = row["feature_cutoff_at"]
            elif change == "range":
                row["prior"]["range_usd_millions"] = [0, 0]
            elif change == "revision":
                row["revision_fraction"] += 0.01
            else:
                row["held_block"] = "2026-Q3"
            raw = copy.deepcopy(self.raw)
            raw["evidence_canonical_sha256"] = digest(canonical(evidence))
            raw["output"]["guidance_evidence_sha256"] = raw["evidence_canonical_sha256"]
            with self.subTest(change=change), self.assertRaises(DataError):
                self.verify(evidence=evidence, raw=raw)

    def test_protocol_edit_fails_before_any_other_inputs_are_read(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for path in (PROTOCOL, FREEZE):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / path).read_bytes())
            changed = load(root / PROTOCOL)
            changed["gates"]["relative_mse_reduction"] = 0
            (root / PROTOCOL).write_bytes(canonical(changed))
            with self.assertRaisesRegex(DataError, "protocol differs"):
                check_registration(root)
