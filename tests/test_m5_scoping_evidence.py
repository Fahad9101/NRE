"""The Milestone 5 scoping evidence (nre/m5_scoping_evidence.py, reports/m5-scoping-evidence-2026-10-08.json): a pure function of three committed artifacts, independent of every Milestone 4
holdout result, with its arithmetic checked by hand. It fits nothing and reads no event-level outcome."""
import copy
import json
import math
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from nre import m5_scoping_evidence as ev
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
COMMITTED = ROOT / ev.OUT_NAME


def load(relative, root=ROOT):
    return json.loads((Path(root) / relative).read_text(encoding="utf-8"))


def copy_inputs(root):
    for name in ev.INPUTS:
        (Path(root) / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, Path(root) / name)


class Spy(dict):
    """A dict that records every key read from it, and every call that would expose all its keys at once."""
    def __init__(self, data, log, label):
        super().__init__(data)
        self.log, self.label = log, label

    def __getitem__(self, key):
        self.log.add((self.label, key))
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.log.add((self.label, key))
        return super().get(key, default)

    def __contains__(self, key):
        self.log.add((self.label, key))
        return super().__contains__(key)


def _exposes_everything(name):
    original = getattr(dict, name)

    def method(self, *args, **kwargs):
        self.log.add((self.label, "*" + name))
        return original(self, *args, **kwargs)
    return method


for _name in ("keys", "values", "items", "__iter__", "copy"):
    setattr(Spy, _name, _exposes_everything(_name))


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
        cls.built = ev.build()

    def test_the_committed_evidence_is_what_the_code_builds_from_the_committed_artifacts(self):
        self.assertEqual(digest(canonical(self.built)), digest(canonical(self.committed)))
        self.assertEqual(digest(canonical(ev.build())), digest(canonical(self.built)))        # and it is deterministic

    def test_it_opens_exactly_its_three_inputs_and_no_event_level_file(self):
        opened = []
        real_read_text = Path.read_text

        def recording_read_text(path, *args, **kwargs):
            opened.append(Path(path).resolve())
            return real_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", recording_read_text), mock.patch("builtins.open", side_effect=AssertionError("the evidence must not open files other than through read_text")):
            ev.build()
        self.assertEqual(sorted(p.relative_to(ROOT.resolve()).as_posix() for p in set(opened)), sorted(ev.INPUTS))
        self.assertFalse([p for p in opened if "m2-step3-combined-events" in p.name or p.parts[-2] == "data"])

    def test_it_touches_no_field_of_a_holdout_fold_but_the_sizes_of_the_training_and_test_sets(self):
        """A result read and then not used, or used only on a branch the garbage below does not reach, would pass the next test; reading it at all fails this one."""
        log = set()
        real_load = ev.load

        def spying_load(root, relative):
            data = real_load(root, relative)
            if relative == ev.REPORT:
                for entry in data["primary_targets"].values():
                    for version in ev.VERSIONS:
                        holdout = entry["holdout"][version]
                        if "test_counts" in holdout:
                            holdout["test_counts"] = Spy(holdout["test_counts"], log, "test_counts")
                        entry["holdout"][version] = Spy(holdout, log, "holdout")
            return data

        with mock.patch.object(ev, "load", spying_load):
            ev.build()
        read = {}
        for label, key in log:
            read.setdefault(label, set()).add(key)
        self.assertEqual(read, {"holdout": {"train", "test_counts"}, "test_counts": {"events"}})

    def test_it_uses_no_result_of_the_milestone_4_holdout(self):
        """Every holdout field except the size of the training set and of the test set is replaced by garbage: the output, apart from the hash of that input, does not move."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_inputs(root)
            report = load(ev.REPORT)
            for entry in report["primary_targets"].values():
                for version in ev.VERSIONS:
                    holdout = entry["holdout"][version]
                    kept = {"train": holdout.get("train"), "test_counts": {"events": holdout["test_counts"]["events"]}}
                    for key in list(holdout):
                        holdout[key] = kept[key] if key in kept else "GARBAGE"
                    entry["holdout"][version] = holdout
            (root / ev.REPORT).write_text(json.dumps(report), encoding="utf-8")
            doctored = ev.build(root)
        self.assertEqual(canonical(doctored), canonical(self.built))          # not even the provenance hashes move: they cover only the part of each input that is read

    def test_the_provenance_hashes_cover_exactly_the_parts_read_and_a_change_elsewhere_moves_nothing(self):
        report, protocol, table = load(ev.REPORT), load(ev.PROTOCOL), load(ev.TABLE)
        cells = {}
        for target, entry in report["primary_targets"].items():
            cells[target] = {"comparator": entry["comparator"]}
            for version in ev.VERSIONS:
                development, holdout = entry["development"][version], entry["holdout"][version]
                cells[target][version] = {"development": {key: development.get(key) for key in ("folds", "scores", "confirmatory_model_against_c1")},
                                          "holdout_sizes": {"train": holdout.get("train"), "test_events": holdout["test_counts"]["events"]}}
        expected = {ev.REPORT: digest(canonical(cells)), ev.PROTOCOL: digest(canonical(protocol["blocks_and_folds"]["expected_blocks"])), ev.TABLE: digest(canonical(table["scope_note"]))}
        self.assertEqual({name: item["canonical_sha256_of_the_part_read"] for name, item in self.built["inputs"].items()}, expected)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_inputs(root)
            report["holdout_accesses_counted_since"] = 999                    # the report is regenerated when the replay accounting grows; none of this is read
            report["primary_targets"]["loses_half_of_gap"]["development"]["all_event"]["counts"] = {"events": 0}          # nor is this development field
            protocol["amendments"] = ["an unrelated amendment"]
            table["a_new_key"] = 1
            for name, content in ((ev.REPORT, report), (ev.PROTOCOL, protocol), (ev.TABLE, table)):
                (root / name).write_text(json.dumps(content), encoding="utf-8")
            self.assertEqual(canonical(ev.build(root)), canonical(self.built))

    def test_a_cell_is_evidenced_only_if_its_development_contrast_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_inputs(root)
            report = load(ev.REPORT)
            development = report["primary_targets"]["day1_close_return"]["development"]["all_event"]
            self.assertTrue(development["scores"] and development["confirmatory_model_against_c1"])        # the committed report has both
            development["confirmatory_model_against_c1"] = None                                             # a contrast that was never computed
            (root / ev.REPORT).write_text(json.dumps(report), encoding="utf-8")
            cells = ev.build(root)["detectability"]
        self.assertEqual(set(cells), set(self.built["detectability"]) - {"day1_close_return/all_event"})

    def test_the_detectability_arithmetic_checks_by_hand(self):
        report = load(ev.REPORT)
        development = report["primary_targets"]["extension_after_open_ge_5pct"]["development"]["clean_window"]
        contrast = development["confirmatory_model_against_c1"]
        half_width = (contrast["interval_99"]["high"] - contrast["interval_99"]["low"]) / 2
        score = development["scores"]["C1_pooled_rate"]
        cell = self.built["detectability"]["extension_after_open_ge_5pct/clean_window"]
        self.assertAlmostEqual(cell["half_width_99"], half_width, places=12)
        self.assertAlmostEqual(cell["half_width_as_share_of_comparator_score"], half_width / score, places=12)
        self.assertEqual(cell["events"], 43)
        self.assertEqual(cell["events_for_a_stated_improvement_to_equal_the_half_width"], {"5%": math.ceil(43 * (half_width / (0.05 * score)) ** 2), "10%": math.ceil(43 * (half_width / (0.10 * score)) ** 2)})
        self.assertEqual(cell["events_for_a_stated_improvement_to_equal_the_half_width"], {"5%": 1085, "10%": 272})
        self.assertAlmostEqual(cell["half_width_as_share_of_comparator_score_at_test_sizes"]["128"], (half_width / score) * math.sqrt(43 / 128), places=12)
        self.assertEqual(sorted(cell["half_width_as_share_of_comparator_score_at_test_sizes"], key=int), ["128", "256", "512", "1024"])
        # a larger test set always narrows the interval, and a smaller improvement always needs more events
        shares = [cell["half_width_as_share_of_comparator_score_at_test_sizes"][k] for k in ("128", "256", "512", "1024")]
        self.assertEqual(shares, sorted(shares, reverse=True))
        self.assertLess(cell["events_for_a_stated_improvement_to_equal_the_half_width"]["10%"], cell["events_for_a_stated_improvement_to_equal_the_half_width"]["5%"])

    def test_every_evaluated_development_cell_is_there_and_the_unevaluated_one_is_not(self):
        cells = self.built["detectability"]
        self.assertEqual(len(cells), 9)                                           # 9 of the 10 development cells were evaluated
        self.assertNotIn("loses_half_of_gap/clean_window", cells)                 # INSUFFICIENT_DATA in Milestone 4: no contrast exists
        for name, cell in cells.items():
            self.assertGreater(cell["half_width_99"], 0, name)
            self.assertGreater(cell["comparator_score"], 0, name)
            self.assertLessEqual(cell["strongest_simple_baseline_score"], cell["comparator_score"], name)
            self.assertLessEqual(cell["strongest_m4_predictor_score"], cell["strongest_simple_baseline_score"], name)

    def test_a_simple_baseline_had_the_best_development_score_in_every_evaluated_cell(self):
        """The proposal's 'the logistic and ridge models never led' rests on this."""
        leaders = {name: (cell["strongest_m4_predictor"], cell["strongest_simple_baseline"]) for name, cell in self.built["detectability"].items()}
        self.assertTrue(all(best == simple for best, simple in leaders.values()), leaders)
        self.assertFalse([name for name, (best, _) in leaders.items() if not best.startswith("C")])
        self.assertEqual({name: best for name, (best, _) in leaders.items()},
                         {"gap_ge_3pct/clean_window": "C4_issuer_history_rate", "gap_ge_3pct/all_event": "C4_issuer_history_rate", "gap_ge_5pct/clean_window": "C4_issuer_history_rate",
                          "gap_ge_5pct/all_event": "C4_issuer_history_rate", "day1_close_return/clean_window": "C3_sector_group_quantiles", "day1_close_return/all_event": "C3_sector_group_quantiles",
                          "extension_after_open_ge_5pct/clean_window": "C1_pooled_rate", "extension_after_open_ge_5pct/all_event": "C1_pooled_rate", "loses_half_of_gap/all_event": "C4_issuer_history_rate"})

    def test_the_fold_sizes_are_those_of_milestone_4_and_the_held_back_arithmetic_is_right(self):
        folds = self.built["fold_sizes"]["extension_after_open_ge_5pct/clean_window"]
        self.assertEqual({k: (v["train_events"], v["test_events"]) for k, v in folds.items()}, {"dev_test_block_3": (55, 20), "dev_test_block_4": (75, 23), "block_5_as_a_fold": (98, 21)})
        for fold in folds.values():
            split = fold["if_a_fifth_is_held_back_twice"]
            self.assertEqual(split["left_to_fit"], split["training_events"] - 2 * split["held_back_for_calibration"])
            self.assertEqual(split["held_back_for_hyperparameter_selection"], split["held_back_for_calibration"])
            self.assertEqual(fold["leaves_at_most"], {str(m): split["left_to_fit"] // m for m in ev.MIN_LEAF})
        self.assertEqual(folds["dev_test_block_3"]["if_a_fifth_is_held_back_twice"]["left_to_fit"], 33)
        self.assertIsNone(self.built["fold_sizes"]["day1_close_return/all_event"]["dev_test_block_3"]["train_positives"])      # a return has no positives

    def test_the_data_supply_figure_is_the_datasets_own_rate_and_says_it_is_an_estimate(self):
        supply = self.built["data_supply"]
        self.assertEqual((supply["events"], supply["issuers"], supply["block_sizes"]), (128, 23, [17, 44, 21, 23, 23]))
        self.assertEqual((supply["first_reaction_session"], supply["last_reaction_session"]), ("2024-11-05", "2026-04-01"))
        span = (date(2026, 4, 1) - date(2024, 11, 5)).days
        since = (date.fromisoformat(supply["as_of"]) - date(2026, 4, 1)).days
        self.assertEqual((supply["span_days"], supply["days_since_the_last_reaction_session"]), (span, since))
        self.assertEqual(supply["events_at_the_same_rate_since_then"], round(128 * since / span, 1))
        self.assertEqual(supply["events_per_issuer_in_the_fingerprint_table_note"]["fewest"], 4)
        self.assertEqual(supply["events_per_issuer_in_the_fingerprint_table_note"]["most"], 6)
        self.assertIn("an estimate, not a count", supply["reading"])

    def test_the_issuer_count_is_read_from_the_scope_note_and_a_note_that_disagrees_is_refused(self):
        note_before = load(ev.TABLE)["scope_note"]
        self.assertIn("describe the 128 accepted events", note_before)
        self.assertIn("for the same 23 issuers (4 to 6 events each, 2024-11-04 to 2026-03-31)", note_before)
        for old, new, refused in (("for the same 23 issuers", "for the same 24 issuers", False), ("4 to 6 events each", "3 to 7 events each", False),
                                  ("describe the 128 accepted events", "describe the 129 accepted events", True), ("for the same 23 issuers (", "for 23 issuers (", True)):
            with tempfile.TemporaryDirectory() as directory, self.subTest(change=new):
                root = Path(directory)
                for name in ev.INPUTS:
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(ROOT / name, root / name)
                table = load(ev.TABLE)
                table["scope_note"] = table["scope_note"].replace(old, new)
                (root / ev.TABLE).write_text(json.dumps(table), encoding="utf-8")
                if refused:
                    with self.assertRaises(ValueError):
                        ev.build(root)
                else:
                    supply = ev.build(root)["data_supply"]
                    self.assertEqual(supply["issuers"], 24 if "24" in new else 23)
                    self.assertEqual(supply["events_per_issuer_in_the_fingerprint_table_note"]["fewest"], 3 if "3 to 7" in new else 4)

    def test_the_assumptions_and_the_scope_are_stated(self):
        self.assertEqual(len(self.built["assumptions"]), 5)
        self.assertIn("square root", self.built["assumptions"][0])
        self.assertIn("fits nothing", self.built["scope_note"])
        self.assertIn("reads no event-level outcome", self.built["scope_note"])
        self.assertIn("uses no result of the Milestone 4 holdout", self.built["scope_note"])
        self.assertEqual(set(self.built["inputs"]), set(ev.INPUTS))
        self.assertTrue(all(len(v["canonical_sha256_of_the_part_read"]) == 64 for v in self.built["inputs"].values()))

    def test_the_figures_and_tables_the_proposal_quotes_come_from_the_evidence(self):
        figures, tables = ev.figures(self.built), ev.tables(self.built)
        self.assertEqual((figures["EV5_MIN"], figures["EV5_MAX"]), ("248", "1,349"))
        self.assertEqual((figures["SHARE_MIN"], figures["SHARE_MAX"], figures["LOSES_SHARE"]), ("12%", "28%", "44%"))
        self.assertEqual((figures["TRAIN_MIN"], figures["TRAIN_MAX"], figures["CAL_MIN"], figures["CAL_MAX"]), ("55", "105", "11", "21"))
        self.assertEqual(figures["SUPPLY"], "48")                                # 47.5 rounded half up: an estimate, said to be one
        self.assertEqual(len(tables["DETECTABILITY_TABLE"].splitlines()), 2 + 9)
        self.assertEqual(len(tables["FOLD_TABLE"].splitlines()), 2 + 3)
        self.assertIn("| `extension_after_open_ge_5pct` | clean-window | 43 | 0.2450 | 0.0615 | 25% | 1,085 / 272 |", tables["DETECTABILITY_TABLE"])
        self.assertIn("| tested on block 3 | 55 | 24 | 11 / 11 | 33 | 11 / 6 / 3 |", tables["FOLD_TABLE"])


if __name__ == "__main__":
    unittest.main()
