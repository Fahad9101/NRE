"""The 128-event fingerprints/analogues run (Milestone 2 step 3 follow-up), reproduced offline from the committed inputs.

Nothing here touches the network: the machinery reads only committed, already-derived records.
"""
import json
import unittest
from pathlib import Path

from nre import analogues as an
from nre import fingerprints as fp
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
SPEC = "config/m2-step3-combined-events.json"
CALENDAR = "config/m2-merged-calendar-2024-2026.json"
TABLE = "reports/m2-step3-combined-fingerprint-table-2026-10-02.json"
POOL = "reports/m2-step3-combined-analogue-pool-report-2026-10-02.json"
RUN = "reports/m2-step3-combined-fingerprints-analogues-run-2026-10-02.json"
LABELS = ("day1_close_return", "session_2_close_return", "session_5_close_return", "session_10_close_return", "session_20_close_return",
          "positive_gap_retained_half", "positive_gap_filled")


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def health(targets, label):
    sizes = [t["labels"][label]["eligible"] for t in targets]
    return {"targets": len(sizes), "with_5_or_more": sum(s >= 5 for s in sizes), "with_10_or_more": sum(s >= 10 for s in sizes),
            "with_20_or_more": sum(s >= 20 for s in sizes), "with_none": sum(s == 0 for s in sizes),
            "analogues_found": sum(t["labels"][label]["state"] == an.FOUND for t in targets)}


class CombinedRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = fp.load_inputs(spec_path=ROOT / SPEC, calendar_path=ROOT / CALENDAR)
        cls.report = load(RUN)
        cls.pool = load(POOL)

    def test_the_combined_file_is_exactly_the_pinned_events_of_its_three_sources(self):
        sources = [load(name)["events"] for name in ("config/m1-events.json", "config/m2-step2-events.json", "config/m2-step3-events.json")]
        pinned = [event for events in sources for event in events if "recorded_result" in event]
        self.assertEqual(len(pinned), 128)
        self.assertEqual(load(SPEC)["events"], pinned)

    def test_it_loads_all_128_events_for_all_23_issuers(self):
        events = self.inputs["events"]
        self.assertEqual((len(events), len({e["cik"] for e in events})), (128, 23))
        self.assertEqual(len({e["event_id"] for e in events}), 128)

    def test_the_merged_calendar_carries_the_2025_01_09_closure(self):
        calendar = load(CALENDAR)
        self.assertIn("2025-01-09", calendar["holidays"])
        self.assertEqual((calendar["start"], calendar["end"]), ("2024-01-01", "2026-12-31"))

    def test_the_committed_outputs_reproduce_from_the_inputs(self):
        table = load(TABLE)
        self.assertEqual(canonical(fp.fingerprint_table(self.inputs)), canonical(table))
        self.assertEqual(canonical(an.pool_report(self.inputs)), canonical(self.pool))
        self.assertEqual(digest(canonical(table)), self.report["outputs"]["reaction_fingerprint_table"]["report_sha256"])
        self.assertEqual(digest(canonical(self.pool)), self.report["outputs"]["analogue_pool_report"]["report_sha256"])

    def test_the_report_compares_the_same_68_targets_before_and_after(self):
        old_ids = {e["event_id"] for e in load("config/m2-combined-events.json")["events"] if "recorded_result" in e}
        self.assertEqual(len(old_ids), 68)
        old_targets = [t for t in self.pool["targets"] if t["event_id"] in old_ids]
        new_targets = [t for t in self.pool["targets"] if t["event_id"] not in old_ids]
        self.assertEqual((len(old_targets), len(new_targets)), (68, 60))
        section = self.report["what_step_3_added"]
        for label in LABELS:
            self.assertEqual(section["the_original_68_targets_before_and_after"]["after_pool_of_128"][label], health(old_targets, label))
            self.assertEqual(section["the_60_new_targets"]["pool_of_128"][label], health(new_targets, label))
            self.assertEqual(section["all_targets_for_reference"]["per_pool"]["all_128_events"][label], self.pool["summary"][label])

    def test_the_before_side_is_the_2026_09_29_record(self):
        recorded = load("reports/m2-combined-analogue-pool-report-2026-09-29.json")
        before = self.report["what_step_3_added"]["the_original_68_targets_before_and_after"]["before_pool_of_68"]
        for label in LABELS:
            self.assertEqual(before[label], health(recorded["targets"], label))

    def test_the_machinery_reads_no_caveats_as_the_report_discloses(self):
        for module in ("fingerprints.py", "analogues.py"):
            self.assertNotIn("caveat", (ROOT / "nre" / module).read_text(encoding="utf-8").lower())
        self.assertTrue(any("never reads event caveats" in line for line in self.report["limits_and_wording"]))


if __name__ == "__main__":
    unittest.main()
