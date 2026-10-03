"""The caveat check: how much the pools move when caveated labels are treated as absent. Offline and read-only."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from nre import caveat_sensitivity as cs
from nre import fingerprints as fp
from nre.core import DataError, canonical

ROOT = Path(__file__).resolve().parent.parent
SPEC, CALENDAR = "config/m2-step3-combined-events.json", "config/m2-merged-calendar-2024-2026.json"
REPORT = "reports/m4-caveat-sensitivity-2026-10-03.json"


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class PairTests(unittest.TestCase):
    SPEC = {"events": [
        {"event_id": "a", "recorded_result": {}, "caveats": [{"labels": ["day1_open_return"], "note": "x"}]},
        {"event_id": "b", "recorded_result": {}, "caveats": [{"labels": ["all"], "note": "x"}]},
        {"event_id": "c", "recorded_result": {}, "caveats": [{"labels": ["session_5_close_return"], "note": "x"},
                                                              {"labels": ["session_20_close_return"], "note": "y"}]},
        {"event_id": "d", "recorded_result": {}},
        {"event_id": "e", "caveats": [{"labels": ["session_5_close_return"], "note": "x"}]},
    ]}

    def test_pairs_are_exactly_what_the_caveats_name_with_all_expanded(self):
        self.assertEqual(cs.caveated_pairs(self.SPEC), {"a": {"day1_open_return"}, "b": set(fp.LABELS),
                                                         "c": {"session_5_close_return", "session_20_close_return"}})

    def test_events_without_a_recorded_result_or_without_caveats_are_ignored(self):
        pairs = cs.caveated_pairs(self.SPEC)
        self.assertNotIn("d", pairs)
        self.assertNotIn("e", pairs)

    def test_a_caveat_on_the_open_touches_every_gap_flag_and_both_conditional_flags(self):
        derived = cs.caveated_pairs(self.SPEC, with_derived=True)["a"]
        self.assertEqual(derived, {"day1_open_return"} | {"gap_ge_%dpct" % t for t in fp.GAP_THRESHOLDS} | set(fp.CONDITIONAL_LABELS))

    def test_a_caveat_on_the_close_or_the_low_touches_only_its_own_conditional_flag(self):
        spec = {"events": [{"event_id": "x", "recorded_result": {}, "caveats": [{"labels": ["day1_close_return"], "note": "n"}]},
                           {"event_id": "y", "recorded_result": {}, "caveats": [{"labels": ["day1_low_return"], "note": "n"}]},
                           {"event_id": "z", "recorded_result": {}, "caveats": [{"labels": ["day1_high_return", "session_10_close_return"], "note": "n"}]}]}
        derived = cs.caveated_pairs(spec, with_derived=True)
        self.assertEqual(derived["x"], {"day1_close_return", "positive_gap_retained_half"})
        self.assertEqual(derived["y"], {"day1_low_return", "positive_gap_filled"})
        self.assertEqual(derived["z"], {"day1_high_return", "session_10_close_return"})

    def test_a_label_the_pipeline_never_computes_is_rejected(self):
        bad = {"events": [{"event_id": "q", "recorded_result": {}, "caveats": [{"labels": ["session_6_close_return"], "note": "n"}]}]}
        with self.assertRaises(DataError):
            cs.caveated_pairs(bad)


class VariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(SPEC)
        cls.inputs = fp.load_inputs(spec_path=ROOT / SPEC, calendar_path=ROOT / CALENDAR)
        cls.pairs = cs.caveated_pairs(cls.spec)

    def test_the_input_is_never_mutated(self):
        before = copy.deepcopy(self.inputs["events"])
        for variant in cs.VARIANTS:
            cs.variant_inputs(self.inputs, self.pairs, variant)
        self.assertEqual(self.inputs["events"], before)

    def test_caveated_labels_become_absent_with_the_caveat_reason_and_nothing_else_changes(self):
        changed = cs.variant_inputs(self.inputs, self.pairs, "as_recorded")
        originals = {e["event_id"]: e for e in self.inputs["events"]}
        for event in changed["events"]:
            for name, block in event["labels"].items():
                if name in self.pairs.get(event["event_id"], ()):
                    self.assertEqual(block, {"value": None, "reason": cs.CAVEAT_REASON})
                else:
                    self.assertEqual(block, originals[event["event_id"]]["labels"][name])

    def test_dropping_events_removes_exactly_the_caveated_ones(self):
        dropped = cs.variant_inputs(self.inputs, self.pairs, "events_dropped")
        self.assertEqual({e["event_id"] for e in self.inputs["events"]} - {e["event_id"] for e in dropped["events"]}, set(self.pairs))
        self.assertEqual((len(self.pairs), len(dropped["events"])), (38, 90))

    def test_the_direct_estimates_agree_with_the_fingerprint_machinerys_own_table(self):
        changed = cs.variant_inputs(self.inputs, self.pairs, "as_recorded")
        cell = next(c for c in fp.fingerprint_table(changed)["cells"] if c["level"] == "all")
        rows = cs.headline_pool(self.inputs["events"], changed["events"])
        for label, row in rows.items():
            block = cell["labels"][label]
            self.assertEqual(block["n"], row["n_without"], label)
            value = block["proportion"]["value"] if block["kind"] == "boolean" else block["mean"]["value"]
            self.assertAlmostEqual(value, row["estimate_without"], places=5, msg=label)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(SPEC)
        cls.inputs = fp.load_inputs(spec_path=ROOT / SPEC, calendar_path=ROOT / CALENDAR)

    def test_without_any_caveat_nothing_moves(self):
        spec = copy.deepcopy(self.spec)
        for event in spec["events"]:
            event.pop("caveats", None)
        report = cs.analyse(spec, self.inputs)
        self.assertEqual(report["inventory"]["events_with_caveats"], 0)
        for variant in cs.VARIANTS:
            data = report["variants"][variant]
            self.assertEqual(data["events_in_pool"], 128)
            self.assertEqual(data["shift_summary"]["notable"], 0)
            self.assertEqual(data["cell_states"]["pooled_cells"]["changed_count"], 0)
            self.assertEqual(data["cell_states"]["issuer_cells"]["changed"], 0)
            for health in data["pool_health"].values():
                self.assertEqual(health["before"], health["after"])
            for cell in data["headline_pools"].values():
                for row in cell.values():
                    self.assertIn(row["shift_in_standard_errors"], (0.0, None))

    def test_the_committed_report_reproduces_from_the_committed_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cs.main(["--spec", str(ROOT / SPEC), "--calendar", str(ROOT / CALENDAR), "--output", str(out)])
            fresh = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        committed = load(REPORT)
        # the paths recorded in the report are the ones given on the command line; compare everything else exactly
        for key in ("spec", "calendar"):
            fresh["inputs"].pop(key)
            committed["inputs"].pop(key)
        self.assertEqual(canonical(fresh), canonical(committed))

    def test_the_inventory_matches_what_the_run_report_disclosed(self):
        inventory = load(REPORT)["inventory"]
        run = load("reports/m2-step3-combined-fingerprints-analogues-run-2026-10-02.json")
        self.assertEqual(inventory["events_with_caveats"], 38)
        self.assertEqual(inventory["pairs_named_explicitly"], 105)
        self.assertTrue(any("38 of the 128 events carry caveats" in line and "105 distinct event-label pairs" in line
                            for line in run["limits_and_wording"]))
        self.assertEqual(inventory["events_using_the_all_sentinel"], ["lnsr-2026-03-31", "slsn-2026-03-31"])


if __name__ == "__main__":
    unittest.main()
