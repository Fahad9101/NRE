"""S7 registry and fail-closed verification of sealed evidence."""
import copy
import json
import unittest
from pathlib import Path

from nre import m5_phase1b_audit as audit

ROOT = Path(__file__).resolve().parent.parent


class SealedAuditTests(unittest.TestCase):
    def setUp(self):
        self.registry = audit.load(ROOT / audit.REGISTRY)
        self.observed = {
            key: dict(view, labels_match_recorded=True)
            for key, view in audit.load(ROOT / audit.PRIOR)["sealed_view"]["events"].items()
        }

    def test_committed_registry_reconciles_pins_and_candidate_membership(self):
        self.assertEqual(self.registry["events"], audit.audit_events(self.observed, ROOT))
        self.assertEqual(self.registry["status"], "awaiting_owner_declaration")
        self.assertEqual(self.registry["seal"], "hash_only")
        self.assertEqual(self.registry["summary"]["commitments_verified"], 43)
        self.assertEqual(self.registry["summary"]["unavailable_session_labels"], 4)
        self.assertEqual(audit.input_hashes(ROOT), self.registry["input_sha256"])
        parts = self.registry["annotation_parts"]
        self.assertEqual([part["part"] for part in parts], [f"{i}/10" for i in range(1, 11)])
        self.assertCountEqual([event for part in parts for event in part["events"]], self.observed.keys())
        self.assertEqual(self.registry["run"]["run_id"], 43235690974)
        self.assertEqual(self.registry["run"]["head_sha"], "f53f05836f5b07c1a82ac0f7e228af19838aed5f")
        self.assertIsNone(audit.ea.SEALED_TRIPWIRE.search(json.dumps(self.registry)))

    def test_audit_refuses_wrong_pins_and_unexpected_fields(self):
        event_id = next(iter(self.observed))
        for mutation in ({"labels_sha256": "0" * 64}, {"labels_match_recorded": False},
                         {"raw_price": 123}, {"access_check_passed": 1}, {"missing_sessions": ["2026-05-05"]}):
            with self.subTest(fields=list(mutation)), self.assertRaises(ValueError):
                audit.audit_events(dict(self.observed, **{event_id: dict(self.observed[event_id], **mutation)}), ROOT)
        del self.observed[event_id]
        with self.assertRaises(ValueError):
            audit.audit_events(self.observed, ROOT)

    def test_annotation_reader_refuses_duplicates_and_decimal_payloads(self):
        event_id = next(iter(self.observed))
        message = {"part": "1/1", "all_ok": True, "events": {event_id: self.observed[event_id]}}
        annotation = {"title": audit.ANNOTATION_TITLE, "annotation_level": "notice",
                      "message": json.dumps(message)}
        observed, _ = audit.read_parts([annotation])
        self.assertEqual(observed, message["events"])
        first = dict(annotation, message=json.dumps(dict(message, part="1/2")))
        second = dict(annotation, message=json.dumps(dict(message, part="2/2")))
        unsafe = copy.deepcopy(message)
        unsafe["events"][event_id]["raw_price"] = 12.34
        for parts in ([first], [first, first], [first, second],
                      [dict(annotation, message=json.dumps(unsafe))]):
            with self.subTest(parts=len(parts)), self.assertRaises(ValueError):
                audit.read_parts(parts)
