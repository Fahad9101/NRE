import copy
import unittest
from unittest.mock import patch

from nre.core import DataError
from nre.m5_phase1b_audit import load
from nre import m6_guidance_result_audit as audit


class GuidanceResultAuditTests(unittest.TestCase):
    def mutate_result(self, mutate):
        result = copy.deepcopy(load(audit.ROOT / audit.RESULT))
        mutate(result)

        def controlled(path):
            return result if path == audit.ROOT / audit.RESULT else load(path)

        with patch.object(audit, "load", side_effect=controlled):
            return audit.verify_result()

    def test_single_attempt_failed_result_reproduces_from_aggregate_evidence(self):
        result = audit.verify_result()
        self.assertEqual(result["decision"], "STOP_DEVELOPMENT_GATE_NOT_MET")
        self.assertEqual(result["scoring_attempts"], 1)
        self.assertEqual(result["clean_counts"]["paired_rows"], 51)
        self.assertEqual(result["aggregate_and_membership_audit"], "passed")

    def test_a_different_attempt_cannot_be_presented_as_the_logged_test(self):
        with self.assertRaisesRegex(DataError, "attempt binding"):
            self.mutate_result(lambda r: r.update(attempt_sha256="0" * 64))

    def test_a_pass_cannot_replace_the_failed_registered_gate(self):
        def mutate(r):
            r["comparison"]["decision"] = "ELIGIBLE_FOR_FRESH_STUDY_SCOPING"
        with self.assertRaisesRegex(DataError, "Registered decision"):
            self.mutate_result(mutate)

    def test_a_changed_pair_membership_cannot_preserve_the_reported_counts(self):
        def mutate(r):
            r["comparison"]["reports"]["clean_window"]["summary"]["pair_membership_sha256"] = "0" * 64
        with self.assertRaisesRegex(DataError, "Pooled membership"):
            self.mutate_result(mutate)

    def test_a_narrower_claim_interval_cannot_replace_the_outer_envelope(self):
        def mutate(r):
            r["comparison"]["reports"]["clean_window"]["summary"]["interval_99"] = [0.00001, 0.00002]
        with self.assertRaisesRegex(DataError, "Outer bootstrap"):
            self.mutate_result(mutate)
