import copy
import unittest
from unittest.mock import patch

from nre.core import DataError
from nre.m5_phase1b_audit import load
from nre import m6_guidance_preparation_audit as audit


class GuidancePreparationAuditTests(unittest.TestCase):
    def test_published_receipts_preserve_membership_and_outcome_boundary(self):
        result = audit.verify_preparation()
        self.assertEqual((result["verified_training_openings"], result["clean_training_openings"], result["basis_events_passed"]), (52, 44, 107))
        self.assertEqual(result["decision"], "READY_FOR_REMAINING_SOURCE_AND_LABEL_PREPARATION")
        self.assertEqual((result["closing_outcome_requests"], result["model_runs"]), (0, 0))

    def verify_changed(self, mutate):
        record = copy.deepcopy(load(audit.ROOT / audit.RESULT))
        mutate(record)

        def controlled_load(path):
            return record if path == audit.ROOT / audit.RESULT else load(path)

        with patch.object(audit, "load", side_effect=controlled_load):
            return audit.verify_preparation()

    def test_duplicate_receipt_event_cannot_replace_a_missing_event(self):
        def mutate(record):
            record["warmup_openings"]["events"][-1] = record["warmup_openings"]["events"][0]
        with self.assertRaisesRegex(DataError, "event membership"):
            self.verify_changed(mutate)

    def test_missing_commitment_cannot_keep_a_verified_open_status(self):
        def mutate(record):
            record["warmup_openings"]["events"][0]["opening_commitment_sha256"] = None
        with self.assertRaisesRegex(DataError, "Opening commitment"):
            self.verify_changed(mutate)

    def test_basis_pass_cannot_hide_a_corporate_action(self):
        def mutate(record):
            record["price_basis"]["events"][0]["intersecting_action_sha256"] = ["0" * 64]
        with self.assertRaisesRegex(DataError, "bridge replay differs"):
            self.verify_changed(mutate)

    def test_reaction_close_request_cannot_be_presented_as_preparation_only(self):
        def mutate(record):
            record["price_basis"]["reaction_session_bar_requests"] = 1
        with self.assertRaisesRegex(DataError, "closing outcomes"):
            self.verify_changed(mutate)
