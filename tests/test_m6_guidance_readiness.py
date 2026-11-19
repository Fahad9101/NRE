import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nre.core import DataError, canonical, digest
from nre.m5_phase1b_audit import load
from nre.m6_guidance_protocol import FREEZE as PROTOCOL_FREEZE, PROTOCOL, ROOT
from nre.m6_guidance_readiness import FREEZE, MASKS, WARMUP, check_preparation


class GuidanceReadinessTests(unittest.TestCase):
    def copy_inputs(self, root):
        protocol = load(ROOT / PROTOCOL)
        preparation = load(ROOT / FREEZE)
        paths = {PROTOCOL, PROTOCOL_FREEZE, FREEZE, WARMUP, MASKS,
                 *protocol["input_canonical_sha256"], *protocol["implementation_sha256_git_lf"],
                 *preparation["canonical_input_sha256"], *preparation["implementation_sha256_git_lf"]}
        for path in paths:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())

    def test_clean_training_gate_cannot_be_satisfied_by_the_sensitivity(self):
        result = check_preparation()
        minimum = load(ROOT / PROTOCOL)["warmup"]["minimum_common_fit_rows"]
        primary = result["source_support"]["clean_window"]
        sensitivity = result["source_support"]["all_defined"]
        self.assertLess(primary["warmup"]["rows"], minimum)
        self.assertGreaterEqual(sensitivity["warmup"]["rows"], minimum)
        self.assertFalse(primary["folds"][0]["fit_floor_possible"])
        self.assertEqual(result["decision"], "STOP_INSUFFICIENT_SOURCE_SUPPORT")
        self.assertEqual(result["closing_outcome_requests"], 0)
        self.assertEqual(result["model_runs"], 0)

    def test_a_source_mask_edit_cannot_silently_restore_training_support(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_inputs(root)
            masks = load(root / MASKS)
            for row in masks["events"]:
                row["hard_exclusions"] = []
                row["soft_caveats"] = []
            (root / MASKS).write_text(json.dumps(masks), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "Preparation source changed"):
                check_preparation(root)

    def test_repinning_a_source_mask_cannot_change_the_registered_clock(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_inputs(root)
            masks = load(root / MASKS)
            masks["events"][0]["observation_window"]["end_exclusive"] = "2025-02-05T15:00:00+00:00"
            (root / MASKS).write_text(json.dumps(masks), encoding="utf-8")
            freeze = load(root / FREEZE)
            freeze["canonical_input_sha256"][MASKS] = digest(canonical(masks))
            (root / FREEZE).write_text(json.dumps(freeze), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "Source observation window"):
                check_preparation(root)

    def test_published_source_gate_result_is_reproducible(self):
        expected = load(ROOT / "reports/m6-guidance-preparation-result-2026-11-19.json")
        self.assertEqual(check_preparation(), expected)
