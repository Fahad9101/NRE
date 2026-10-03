"""The descriptive evidence behind the Milestone 4 scope proposal: its logic on synthetic inputs, its consistency with the real inputs, and its
reproduction from them. No model, no prediction."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from nre import fingerprints as fp
from nre import m4_scoping_evidence as ev
from nre.core import canonical

ROOT = Path(__file__).resolve().parent.parent
SPEC, CALENDAR = "config/m2-step3-combined-events.json", "config/m2-merged-calendar-2024-2026.json"
REPORT = "reports/m4-scoping-evidence-2026-10-03.json"


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def labels(**values):
    base = {name: {"value": None, "reason": "X"} for name in fp.LABELS}
    for name, value in values.items():
        base[name] = {"value": value, "reason": None}
    return base


class LogicTests(unittest.TestCase):
    def test_a_gap_of_more_than_28_days_starts_a_new_block_and_exactly_28_does_not(self):
        events = [{"event_id": "a", "reaction_session": "2025-01-02"}, {"event_id": "b", "reaction_session": "2025-01-30"},
                  {"event_id": "c", "reaction_session": "2025-02-28"}, {"event_id": "d", "reaction_session": "2025-03-01"}]
        self.assertEqual(ev.assign_blocks(events), {"a": 1, "b": 1, "c": 2, "d": 2})  # 28 days stays, 29 cuts

    def test_extension_is_anchored_to_the_open(self):
        f = ev._extension(5)
        self.assertTrue(f(labels(day1_open_return=0.10, day1_high_return=0.155)))   # 1.155 / 1.10 - 1 = 5.0%
        self.assertFalse(f(labels(day1_open_return=0.10, day1_high_return=0.15)))   # 1.15 / 1.10 - 1 = 4.5%
        self.assertIsNone(f(labels(day1_high_return=0.2)))

    def test_fade_labels_are_conditional_on_a_positive_gap(self):
        self.assertIsNone(ev._loses_half(labels()))
        self.assertTrue(ev._loses_half(labels(positive_gap_retained_half=False)))
        self.assertFalse(ev._loses_half(labels(positive_gap_retained_half=True)))

    def test_closes_below_open_compares_the_close_with_the_open(self):
        self.assertTrue(ev._closes_below_open(labels(day1_open_return=0.05, day1_close_return=0.02)))
        self.assertFalse(ev._closes_below_open(labels(day1_open_return=0.02, day1_close_return=0.05)))
        self.assertIsNone(ev._closes_below_open(labels(day1_open_return=0.02)))

    def test_buckets_follow_the_declared_yardsticks(self):
        self.assertEqual(ev.bucket(30, 30), "estimable_with_wide_uncertainty")
        self.assertEqual(ev.bucket(29, 99), "thin")
        self.assertEqual(ev.bucket(10, 10), "thin")
        self.assertEqual(ev.bucket(9, 99), "insufficient")
        self.assertEqual(ev.bucket(0, 128), "insufficient")

    def test_the_hits_needed_are_the_smallest_whose_lower_bound_clears_the_base_rate(self):
        confidence = 0.95
        result = ev.uncertainty({"x": 0.25}, confidence)["smallest_precision_at_k_whose_lower_bound_clears_the_base_rate"]["x"]["if_the_top_k_events_are_selected"]
        for k_selected, row in result.items():
            k_selected, hits = int(k_selected), row["hits_needed"]
            self.assertGreater(fp.wilson(hits, k_selected, confidence)[0], 0.25)
            self.assertLessEqual(fp.wilson(hits - 1, k_selected, confidence)[0], 0.25)


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load(REPORT)
        cls.inputs = fp.load_inputs(spec_path=ROOT / SPEC, calendar_path=ROOT / CALENDAR)

    def test_every_target_row_adds_up(self):
        for row in self.report["targets"]:
            self.assertEqual(row["positives"] + row["negatives"], row["n_defined"], row["target"])
            self.assertEqual(sum(row["defined_by_block"]), row["n_defined"], row["target"])
            self.assertEqual(sum(row["positives_by_block"]), row["positives"], row["target"])
            self.assertEqual(sum(row["positives_by_timing"].values()), row["positives"], row["target"])
            self.assertLessEqual(row["wilson_low"], row["base_rate"])
            self.assertGreaterEqual(row["wilson_high"], row["base_rate"])

    def test_the_counts_agree_with_the_fingerprint_machinerys_own_table(self):
        cell = next(c for c in fp.fingerprint_table(self.inputs)["cells"] if c["level"] == "all")
        rows = {r["target"]: r for r in self.report["targets"]}
        for target, label in (("gap_ge_3pct", "gap_ge_3pct"), ("gap_ge_5pct", "gap_ge_5pct"), ("gap_ge_10pct", "gap_ge_10pct"),
                              ("full_gap_fill", "positive_gap_filled")):
            self.assertEqual((rows[target]["n_defined"], rows[target]["positives"]), (cell["labels"][label]["n"], cell["labels"][label]["k"]), target)
        mean = cell["labels"]["day1_close_return"]["mean"]["value"]
        self.assertAlmostEqual(self.report["regression_targets"]["day1_close_return"]["mean"], mean, places=5)

    def test_the_blocks_cover_every_event_once_and_no_boundary_needs_a_purge(self):
        structure = self.report["time_structure"]
        self.assertEqual(sum(b["events"] for b in structure["blocks"]), 128)
        self.assertEqual([b["events"] for b in structure["blocks"]], [17, 44, 21, 23, 23])
        self.assertTrue(structure["boundaries"])
        for boundary in structure["boundaries"]:
            self.assertFalse(boundary["needs_purge_for_the_20_session_horizon"], boundary)
            self.assertGreater(boundary["slack_days"], 0)

    def test_the_walk_forward_folds_partition_the_events(self):
        folds = self.report["walk_forward"]["expanding_window_folds"]
        sizes = [b["events"] for b in self.report["time_structure"]["blocks"]]
        for fold in folds:
            self.assertEqual(fold["train_events"], sum(sizes[:fold["test_block"] - 1]))
            self.assertEqual(fold["test_events"], sizes[fold["test_block"] - 1])
            self.assertEqual(fold["train_events_with_session_20_label_mature_at_the_first_test_cutoff"], fold["train_events"])
        plan = self.report["walk_forward"]["if_the_last_block_is_the_final_holdout"]
        self.assertEqual((plan["holdout_block"], plan["holdout_events"], plan["development_test_events"]), (5, 23, 44))

    def test_selection_totals_equal_the_reviewed_ledgers(self):
        for name, rel in ev.LEDGERS:
            ledger = load(rel)
            row = self.report["selection"][name]
            self.assertEqual(row["candidates"], len(ledger["candidates"]))
            self.assertEqual(row["included"] + row["excluded"] + row["quarantined"], row["candidates"])
        self.assertEqual(sum(r["included"] for r in self.report["selection"].values()), 128)

    def test_the_committed_report_reproduces_from_the_committed_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = ev.main(["--spec", str(ROOT / SPEC), "--calendar", str(ROOT / CALENDAR), "--output", str(out)])
            fresh = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        committed = load(REPORT)
        for key in ("spec", "calendar"):
            fresh["inputs"].pop(key)
            committed["inputs"].pop(key)
        self.assertEqual(canonical(fresh), canonical(committed))

    def test_the_scope_proposal_quotes_the_evidence_it_rests_on(self):
        # The proposal's figures are generated from the two evidence reports; this fails if either is regenerated without regenerating the proposal.
        doc = (ROOT / "docs" / "M4-BASELINE-PREDICTIVE-MODELS-SCOPE.md").read_text(encoding="utf-8")
        rows = {r["target"]: r for r in self.report["targets"]}
        for target in ("gap_ge_3pct", "gap_ge_5pct", "gap_ge_10pct", "gap_ge_15pct", "gap_ge_20pct", "gap_ge_30pct", "loses_half_of_gap", "full_gap_fill"):
            self.assertIn("| `%s` |" % target, doc)
            self.assertIn("| %d | %d | " % (rows[target]["n_defined"], rows[target]["positives"]), doc, target)
        plan = self.report["walk_forward"]["if_the_last_block_is_the_final_holdout"]
        self.assertIn("%d development test events" % plan["development_test_events"], doc)
        self.assertIn("a holdout of %d" % plan["holdout_events"], doc)
        for block in self.report["time_structure"]["blocks"]:
            self.assertIn("| %d | %s to %s | %d |" % (block["block"], block["first_reaction_session"], block["last_reaction_session"], block["events"]), doc)
        caveats = load("reports/m4-caveat-sensitivity-2026-10-03.json")
        self.assertIn("%d of the 128 events carry label-level caveats" % caveats["inventory"]["events_with_caveats"], doc)
        self.assertIn("no model code", doc)

    def test_the_decisions_record_matches_the_proposal_and_authorizes_nothing_further(self):
        record = load("reports/m4-scope-decisions-2026-10-03.json")
        self.assertEqual(sorted(d["proposal_section_6_decision"] for d in record["decisions"].values()), ["1", "3", "4", "5"])
        self.assertTrue(all(d["was_the_recommended_default"] for d in record["decisions"].values()))
        self.assertEqual(record["left_open"]["proposal_section_6_decision"], "2")
        self.assertTrue(any(line.startswith("Phase 0") for line in record["not_authorized_by_these_answers"]))
        doc = (ROOT / "docs" / "M4-BASELINE-PREDICTIVE-MODELS-SCOPE.md").read_text(encoding="utf-8")
        self.assertIn("reports/m4-scope-decisions-2026-10-03.json", doc)
        self.assertIn("Phase 0 is not yet authorized and nothing is built.", " ".join(doc.split()))  # the sentence wraps across lines in the document

    def test_the_report_claims_nothing_beyond_description(self):
        self.assertTrue(any("Not a model" in line for line in self.report["not_a_claim"]))


if __name__ == "__main__":
    unittest.main()
