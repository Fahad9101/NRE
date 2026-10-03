"""An event spec may carry its own scope_note; without one the original note applies, so every earlier report still reproduces."""
import json
import tempfile
import unittest
from pathlib import Path

from nre import analogues as an
from nre import fingerprints as fp
from nre.core import DataError, canonical

ROOT = Path(__file__).resolve().parent.parent
COMBINED, CALENDAR = "config/m2-step3-combined-events.json", "config/m2-merged-calendar-2024-2026.json"
VALID = "A description of the sample. They are not market base rates, and nothing here predicts, scores or ranks."


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class SpecScopeNoteTests(unittest.TestCase):
    def test_absent_means_the_original_note_applies(self):
        self.assertIsNone(fp.spec_scope_note({"events": []}))

    def test_a_valid_note_is_returned_unchanged(self):
        self.assertEqual(fp.spec_scope_note({"scope_note": VALID}), VALID)

    def test_a_note_must_be_a_nonempty_string(self):
        for bad in ("", "   ", 5, ["a"], {}):
            with self.assertRaises(DataError, msg=repr(bad)):
                fp.spec_scope_note({"scope_note": bad})

    def test_a_note_must_keep_the_two_statements_it_exists_to_make(self):
        for bad in ("A description of the sample.", "They are not market base rates.", "Nothing here predicts, scores or ranks."):
            with self.assertRaises(DataError, msg=bad):
                fp.spec_scope_note({"scope_note": bad})

    def test_the_original_note_itself_satisfies_the_requirement(self):
        self.assertIsNotNone(fp.spec_scope_note({"scope_note": fp.SCOPE_NOTE}))


class FlowThroughTests(unittest.TestCase):
    def test_the_default_milestone_1_spec_still_carries_the_original_note(self):
        inputs = fp.load_inputs()
        self.assertIsNone(inputs["scope_note"])
        self.assertEqual(fp.provenance(inputs, "x")["scope_note"], fp.SCOPE_NOTE)

    def test_a_spec_note_reaches_both_reports(self):
        spec = load(COMBINED)
        spec["scope_note"] = VALID
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            inputs = fp.load_inputs(spec_path=path, calendar_path=ROOT / CALENDAR, root=ROOT)
        self.assertEqual(fp.fingerprint_table(inputs)["scope_note"], VALID)
        self.assertEqual(an.pool_report(inputs)["scope_note"], VALID)

    def test_the_committed_128_event_reports_carry_their_own_accurate_note(self):
        note = load(COMBINED)["scope_note"]
        self.assertTrue(note.startswith("These figures describe the 128 accepted events"))
        for rel in ("reports/m2-step3-combined-fingerprint-table-2026-10-02.json", "reports/m2-step3-combined-analogue-pool-report-2026-10-02.json"):
            self.assertEqual(load(rel)["scope_note"], note)
        self.assertNotIn("Milestone 1 events only", note)

    def test_earlier_reports_without_a_spec_note_still_reproduce_exactly(self):
        inputs = fp.load_inputs(spec_path=ROOT / "config/m2-combined-events.json", calendar_path=ROOT / "config/m2-step2-merged-calendar.json")
        self.assertIsNone(inputs["scope_note"])
        self.assertEqual(canonical(fp.fingerprint_table(inputs)), canonical(load("reports/m2-combined-fingerprint-table-2026-09-29.json")))
        self.assertEqual(canonical(an.pool_report(inputs)), canonical(load("reports/m2-combined-analogue-pool-report-2026-09-29.json")))


if __name__ == "__main__":
    unittest.main()
