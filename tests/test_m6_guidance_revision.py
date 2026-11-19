import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nre.core import DataError, canonical, digest
from nre.calendar import Calendar
from nre.m5_phase1b_audit import load
from nre.m6_guidance_protocol import PROTOCOL as PARENT_PROTOCOL, FREEZE as PARENT_FREEZE, ROOT
from nre.m6_guidance_readiness import check_preparation
from nre.m6_guidance_revision import (
    EARLIER, FREEZE, MASKS, PARENT_PREPARATION, PARENT_RESULT, PROTOCOL, RESULT, check_revision, verify_source,
)


class GuidanceRevisionTests(unittest.TestCase):
    def copy_inputs(self, root):
        protocol = load(ROOT / PROTOCOL)
        parent = load(ROOT / PARENT_PROTOCOL)
        preparation = load(ROOT / PARENT_PREPARATION)
        paths = {PROTOCOL, FREEZE, PARENT_PROTOCOL, PARENT_FREEZE, PARENT_PREPARATION, PARENT_RESULT,
                 *protocol["input_canonical_sha256"], *protocol["implementation_sha256_git_lf"],
                 *parent["input_canonical_sha256"], *parent["implementation_sha256_git_lf"],
                 *preparation["canonical_input_sha256"], *preparation["implementation_sha256_git_lf"]}
        for path in paths:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())

    def repin_protocol(self, root, protocol):
        (root / PROTOCOL).write_text(json.dumps(protocol), encoding="utf-8")
        freeze = load(root / FREEZE)
        freeze["canonical_sha256"] = digest(canonical(protocol))
        (root / FREEZE).write_text(json.dumps(freeze), encoding="utf-8")

    def repin_input(self, root, path, value):
        (root / path).write_text(json.dumps(value), encoding="utf-8")
        protocol = load(root / PROTOCOL)
        protocol["input_canonical_sha256"][path] = digest(canonical(value))
        self.repin_protocol(root, protocol)

    def test_larger_warmup_preserves_the_original_stopped_registration(self):
        parent_before = check_preparation()
        result = check_revision()
        self.assertEqual(parent_before, check_preparation())
        self.assertEqual(parent_before["decision"], "STOP_INSUFFICIENT_SOURCE_SUPPORT")
        self.assertEqual(result["decision"], "READY_FOR_RAW_WARMUP_OPENINGS")
        self.assertTrue(result["source_support"]["clean_window"]["folds"][0]["fit_floor_possible"])
        self.assertEqual(result["source_support"]["clean_window"]["held"], parent_before["source_support"]["clean_window"]["held"])
        self.assertEqual((result["closing_outcome_requests"], result["model_runs"]), (0, 0))
        self.assertEqual(result, load(ROOT / RESULT))

    def test_repinning_a_model_change_does_not_make_it_a_warmup_revision(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_inputs(root)
            protocol = load(root / PROTOCOL)
            protocol["models"]["ridge_penalty"] = 0.5
            self.repin_protocol(root, protocol)
            with self.assertRaisesRegex(DataError, "outside the allowed warmup adaptation"):
                check_revision(root)

    def test_earlier_input_digest_changes_fail_before_membership_use(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_inputs(root)
            earlier = load(root / EARLIER)
            earlier["candidate_events"][0]["revision_fraction"] += 0.01
            (root / EARLIER).write_text(json.dumps(earlier), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "revision input changed"):
                check_revision(root)

    def test_duplicate_earlier_event_cannot_inflate_fit_support_even_when_repinned(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_inputs(root)
            earlier = load(root / EARLIER)
            earlier["candidate_events"].append(copy.deepcopy(earlier["candidate_events"][0]))
            self.repin_input(root, EARLIER, earlier)
            with self.assertRaisesRegex(DataError, "Earlier source membership"):
                check_revision(root)

    def test_cutoff_equality_is_rejected_even_when_the_source_is_repinned(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_inputs(root)
            earlier = load(root / EARLIER)
            row = earlier["candidate_events"][0]
            row["current"]["availability_proxy"] = row["feature_cutoff_at"]
            self.repin_input(root, EARLIER, earlier)
            with self.assertRaisesRegex(DataError, "Earlier source clock"):
                check_revision(root)

    def test_renaming_a_cloned_economic_event_cannot_inflate_training_support(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_inputs(root)
            earlier, masks = load(root / EARLIER), load(root / MASKS)
            clone = copy.deepcopy(earlier["candidate_events"][0])
            original_id = clone["event_id"]
            clone["event_id"] += "-clone"
            earlier["candidate_events"].append(clone)
            cloned_mask = copy.deepcopy(next(r for r in masks["events"] if r["event_id"] == original_id))
            cloned_mask["event_id"] = clone["event_id"]
            masks["events"].append(cloned_mask)
            self.repin_input(root, EARLIER, earlier)
            self.repin_input(root, MASKS, masks)
            with self.assertRaisesRegex(DataError, "Earlier economic event is duplicated"):
                check_revision(root)

    def test_new_masks_cannot_replace_an_inherited_disposition(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_inputs(root)
            masks = load(root / MASKS)
            parent_masks = load(root / "reports/m6-guidance-source-masks-2026-11-19.json")
            masks["events"].append(copy.deepcopy(parent_masks["events"][0]))
            self.repin_input(root, MASKS, masks)
            with self.assertRaisesRegex(DataError, "Earlier source membership"):
                check_revision(root)

    def test_date_only_original_prior_does_not_invent_a_sec_acceptance(self):
        row = {"symbol": "CTSH", "cik": "0001058290", "source_kind": "issuer_release",
               "release_url": "https://news.cognizant.com/synthetic-guidance-fixture",
               "archive_sha256": "0" * 64, "publication_date": "2024-08-27",
               "availability_proxy": "2024-08-28T04:00:00+00:00", "range_usd_millions": [19500, 19800]}
        calendar = Calendar(load(ROOT / "config/m2-merged-calendar-2024-2026.json"))
        _, available = verify_source(row, row["symbol"], row["cik"], calendar)
        self.assertEqual(available.isoformat(), "2024-08-28T04:00:00+00:00")
        row["availability_proxy"] = "2024-08-27T04:00:00+00:00"
        with self.assertRaisesRegex(DataError, "issuer availability bound"):
            verify_source(row, row["symbol"], row["cik"], calendar)
