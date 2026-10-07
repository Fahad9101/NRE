"""The dress rehearsal (P4-7): the whole of Phase 4 on the REAL inputs, with the real block-5 record files destroyed and the block-5 labels replaced by seeded synthetic ones.

It runs the real runner against the real events' metadata, the real training labels, the real calendar and the real logs, all in a temporary copy of config/ and reports/ that is cut
back to what they held before the look (the Phase 4 outputs absent, the experiment log at 175 records, the holdout log at its genesis), so that the pipeline's plumbing (cells, history,
views, the opening gap, the nested cap, the descriptive report, the logging) is exercised before the one look and can be shown to work without reading a block-5 outcome. The real
logs and outputs are never touched, and the test stays valid after the real look.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_independent as independent  # noqa: E402
import m4_rehearsal as R  # noqa: E402
import m4_support as S  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_phase4 as p4  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402
from nre.core import canonical, digest, iso  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
HOLDOUT_FOLD = "holdout_test_block_5"


class BalancedRehearsal(unittest.TestCase):
    """A holdout that meets every threshold in the all-event version: every cell of the grid is scored."""

    @classmethod
    def setUpClass(cls):
        cls.before = R.real_log_counts()
        cls.summary, cls.root, cls.harness, cls.destroyed = R.rehearse(cls, S.holdout_balanced)
        cls.gate_after_the_run = (cls.harness.gate.unsealed, list(cls.harness.gate.denied))  # before any test replays a look through this harness
        cls.results = json.loads((cls.root / "reports" / "m4-phase4-holdout-results-2026-10-07.json").read_text(encoding="utf-8"))
        cls.descriptive = json.loads((cls.root / "reports" / "m4-phase4-descriptive-2026-10-07.json").read_text(encoding="utf-8"))

    def test_the_whole_pipeline_runs_on_the_real_inputs_with_one_access_and_58_records(self):
        self.assertEqual((self.summary["state"], self.summary["accesses"], self.summary["experiment_records"]), ("LOOKED", 1, 58))
        self.assertEqual(reg.verify_chain(self.harness.experiment_log, "experiments", PROTOCOL)["records"], p4.EXPERIMENTS_BEFORE + 58)
        accesses = reg.read(self.harness.holdout_log)
        self.assertEqual(len(accesses), 2)
        self.assertEqual((accesses[1][0]["reason"], len(accesses[1][0]["events_read"])), (p4.LOOK_REASON, 23))
        self.assertEqual(self.gate_after_the_run, (2 * 23, []))  # every event once per version
        self.assertEqual(self.results["the_look"], {"reason": p4.LOOK_REASON, "accesses": 1, "technical_reruns": 0, "events_read": 23})

    def test_it_never_touches_the_real_logs_the_real_outputs_or_the_real_record_files(self):
        self.assertEqual(R.real_log_counts(), self.before)
        self.assertTrue(self.destroyed and all(path.read_text(encoding="utf-8") == "destroyed" for path in self.destroyed))  # nothing opened them to read or write
        self.assertEqual(len(self.destroyed), 23)

    def test_every_all_event_cell_is_scored_and_the_nested_cap_holds(self):
        states = self.results["states"]
        self.assertEqual({states[t]["all_event"] for t in p4.TARGETS}, {h.EVALUATED})
        self.assertLessEqual({states[t]["clean_window"] for t in p4.TARGETS}, {h.EVALUATED, d.COUNTS_ONLY, d.INSUFFICIENT_DATA})
        lines = [json.loads(line) for line in (self.root / "reports" / "m4-phase4-holdout-predictions-2026-10-07.jsonl").read_text(encoding="utf-8").splitlines()]
        by = {}
        for record in lines:
            by.setdefault((record["target_id"], record["version"], record["predictor_id"]), {})[record["event_id"]] = record["prediction"]
        for pid in ("M2_logistic", "M2_without_sector"):
            for event_id, p in by[("gap_ge_5pct", "all_event", pid)].items():
                self.assertLessEqual(p, by[("gap_ge_3pct", "all_event", pid)][event_id])
        self.assertEqual(sum(1 for r in lines if r["version"] == "all_event"), 23 * (4 * 6 + 5))

    def test_the_predictions_are_timed_at_the_cutoff_or_the_regular_open_by_the_targets_clock(self):
        lines = [json.loads(line) for line in (self.root / "reports" / "m4-phase4-holdout-predictions-2026-10-07.jsonl").read_text(encoding="utf-8").splitlines()]
        by_id = {e["event_id"]: e for e in self.harness.events}
        calendar = self.harness.inputs["calendar"]
        for record in lines:
            event = by_id[record["event_id"]]
            clock = self.harness.targets[record["target_id"]].clock
            expected = calendar.bounds(event["reaction_session"])[0] if clock == "C0" else event["cutoff"]
            self.assertEqual(record["prediction_time"], iso(expected), record["target_id"])
            self.assertEqual(record["fold"], HOLDOUT_FOLD)

    def test_the_descriptive_report_counts_block_5_with_the_other_blocks_for_all_19_targets(self):
        report = self.descriptive
        self.assertEqual(len(report["targets"]), 18)  # 18 binary targets: the 19 less the regression target, which the regression labels below cover
        self.assertNotIn("day1_close_return", report["targets"])
        self.assertEqual({row["role"] for row in report["targets"].values()}, {"primary", "descriptive_only", "insufficient_data_by_rule"})
        row = report["targets"]["gap_ge_3pct"]["all_event"]
        self.assertEqual((row["defined_by_block"][4], row["positives_by_block"][4]), (23, 11))  # the synthetic block 5: 11 big gaps, 12 small
        self.assertEqual(sum(row["defined_by_block"]), 128)
        self.assertEqual(report["holdout"]["unsealed_loads"], 46)
        self.assertEqual(len(report["blocks"]["blocks"]), 5)
        self.assertEqual(sorted(report["regression_labels"]["all_event"]), sorted(["day1_open_return", "day1_high_return", "day1_close_return", "session_5_close_return", "session_20_close_return"]))

    def test_the_sign_check_compares_the_holdout_contrast_with_the_committed_development_result(self):
        for target_id in p4.TARGETS:
            result = self.results["evaluations"][target_id]["all_event"]
            model = h.CONFIRMATORY[result["kind"]]
            comparison = result["contrasts"][model]["against_the_development_result"]
            self.assertTrue(comparison["comparable"], target_id)
            self.assertIn(comparison["development_from"], ("reports/m4-phase2-results-2026-10-07.json", "reports/m4-phase3-results-2026-10-07.json"))
            self.assertEqual(comparison["holdout_sign"], p4.sign_of(comparison["holdout_estimate"]))
            self.assertEqual(comparison["development_sign"], p4.sign_of(comparison["development_estimate"]))

    def test_the_holdout_predictions_and_the_m2_fits_recompute_independently_from_a_replayed_look(self):
        # the post-look verification replays the look through Harness.look against a temporary log (never the real one) to get the events, then recomputes with plain arithmetic
        with mock.patch.object(self.harness, "holdout_log", S.genesis_only_holdout_log(self)), mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True):
            unsealed = self.harness.look("a replay for verification")
        by_key = {}
        for line in (self.root / "reports" / "m4-phase4-holdout-predictions-2026-10-07.jsonl").read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            by_key.setdefault((record["target_id"], record["version"], record["predictor_id"]), []).append(record)
        problems, checked = independent.check(self.harness, self.results, by_key, holdout_events=unsealed)
        self.assertEqual(problems, [])
        self.assertGreaterEqual(checked, 4 * 6 + 4 * 2)  # the all-event version: every binary predictor's predictions, and each M2 variant's fit as well
        with self.assertRaises(ValueError):
            independent.check(self.harness, self.results, by_key)  # without the replayed events the holdout fold cannot be checked

    def test_the_reports_the_run_wrote_are_the_ones_it_summarized(self):
        self.assertEqual(digest(canonical(self.results)), self.summary["results_canonical_sha256"])
        self.assertEqual(digest(canonical(self.descriptive)), self.summary["descriptive_canonical_sha256"])
        self.assertEqual(self.results["determinism"], {"evaluated_twice_from_the_same_events": True, "identical": True,
                                                       "evaluations_canonical_sha256": self.results["determinism"]["evaluations_canonical_sha256"]})


class SparseRehearsal(unittest.TestCase):
    """A holdout that meets almost none: every binary target is COUNTS_ONLY, the regression target is still scored, and every cell of the grid still has its record."""

    @classmethod
    def setUpClass(cls):
        cls.summary, cls.root, cls.harness, cls.destroyed = R.rehearse(cls, S.holdout_sparse)

    def test_every_binary_target_is_counts_only_and_the_regression_target_is_scored(self):
        states = self.summary["states"]
        for version in d.VERSIONS:
            self.assertEqual({states[t][version] for t in ("gap_ge_3pct", "gap_ge_5pct", "extension_after_open_ge_5pct", "loses_half_of_gap")}, {d.COUNTS_ONLY}, version)
        self.assertEqual(states["day1_close_return"]["all_event"], h.EVALUATED)
        self.assertEqual(self.summary["experiment_records"], 58)

    def test_no_predictor_is_fitted_for_a_counts_only_target_and_only_the_scored_cells_have_predictions(self):
        lines = [json.loads(line) for line in (self.root / "reports" / "m4-phase4-holdout-predictions-2026-10-07.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(lines and {r["target_id"] for r in lines} == {"day1_close_return"})
        log = [r for r, _ in reg.read(self.harness.experiment_log)][p4.EXPERIMENTS_BEFORE:]
        counts_only = [r for r in log if r["state"] == "COUNTS_ONLY"]
        self.assertGreaterEqual(len(counts_only), 4 * 6)
        self.assertEqual({r["predictions_sha256"] for r in counts_only}, {digest(canonical([]))})
        descriptive = json.loads((self.root / "reports" / "m4-phase4-descriptive-2026-10-07.json").read_text(encoding="utf-8"))
        self.assertEqual(descriptive["targets"]["gap_ge_3pct"]["all_event"]["positives_by_block"][4], 3)


if __name__ == "__main__":
    unittest.main()
