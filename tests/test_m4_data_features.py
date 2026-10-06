"""The harness's data layer and features: the sealed holdout, the two caveat versions, targets, folds, thresholds, label maturity and the history features.

Logic on small hand-built cases, and the same checks on the real inputs where they need only identities and times (never a holdout outcome).
"""
import copy
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_support as S  # noqa: E402
from nre import caveat_sensitivity as cs  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_features as feat  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_scoping_evidence as ev  # noqa: E402
from nre.core import DataError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
TARGETS = d.targets(PROTOCOL)
FOLDS = {f.name: f for f in d.folds(PROTOCOL)}


def blank(**values):
    labels = {name: {"value": None, "reason": "TEST_ABSENT"} for name in fp.LABELS}
    for name, value in values.items():
        labels[name] = {"value": value, "reason": None}
    return labels


class Probe(dict):
    """Labels that raise when a label other than the allowed ones is read."""

    def __init__(self, allowed, values):
        super().__init__({name: {"value": values.get(name), "reason": None} for name in allowed})
        self.allowed = set(allowed)

    def __getitem__(self, name):
        if name not in self.allowed:
            raise AssertionError("read the label %s, which the target does not declare as a source" % name)
        return super().__getitem__(name)


class SealingTests(unittest.TestCase):
    def setUp(self):
        self.events, self.spec = S.dataset()
        self.blocks = ev.assign_blocks(self.events)
        self.sealed, self.gate = d.seal_events(self.events, self.blocks, 5, self.spec)

    def holdout(self):
        return [e for e in self.sealed if d.is_sealed(e)]

    def test_exactly_the_holdout_blocks_events_are_sealed(self):
        self.assertEqual({e["event_id"] for e in self.holdout()}, {e["event_id"] for e in self.events if self.blocks[e["event_id"]] == 5})
        self.assertEqual(len(self.holdout()), S.SIZES[4])

    def test_every_way_of_reading_a_sealed_event_raises_and_is_counted(self):
        labels = self.holdout()[0]["labels"]
        for attempt in (lambda: labels["gap_ge_3pct"], lambda: list(labels), lambda: len(labels), lambda: "gap_ge_3pct" in labels, lambda: labels.get("gap_ge_3pct"),
                        lambda: dict(labels), lambda: list(labels.items()), lambda: list(labels.values()), lambda: bool(labels), lambda: labels == {}):
            with self.assertRaises(d.HoldoutSealed):
                attempt()
        self.assertEqual(len(self.gate.denied), 10)
        self.assertEqual(self.gate.unsealed, 0)

    def test_a_sealed_event_still_shows_everything_but_its_labels(self):
        event = self.holdout()[0]
        original = next(e for e in self.events if e["event_id"] == event["event_id"])
        for key in ("cutoff", "reaction_session", "cik", "cluster_id", "release_timing", "sic_division", "available_at", "labels_sha256"):
            self.assertEqual(event[key], original[key])
        self.assertIn("sealed", repr(event["labels"]))  # printing one is safe and tells the reader why there is nothing to see
        self.assertEqual(len(self.gate.denied), 0)

    def test_the_target_functions_cannot_be_run_on_a_sealed_event(self):
        for target in TARGETS.values():
            with self.assertRaises(d.HoldoutSealed):
                target.function(self.holdout()[0]["labels"])

    def test_the_gate_loads_nothing_until_it_unseals_and_then_applies_the_versions_mask(self):
        calls = []
        held = {e["event_id"]: e["labels"] for e in self.events if self.blocks[e["event_id"]] == 5}
        gate = d.HoldoutGate(lambda event_id: calls.append(event_id) or held[event_id], cs.caveated_pairs(self.spec, with_derived=True))
        self.assertEqual(calls, [])
        events = [e for e in self.sealed if d.is_sealed(e)]
        every, clean = gate.unseal(events, "all_event"), gate.unseal(events, "clean_window")
        self.assertEqual(len(calls), 2 * len(events))
        pairs = cs.caveated_pairs(self.spec, with_derived=True)
        for a, c in zip(every, clean):
            self.assertEqual(a["labels"], held[a["event_id"]])
            for name in fp.LABELS:
                expected_absent = name in pairs.get(c["event_id"], ())
                self.assertEqual(c["labels"][name]["value"] is None and c["labels"][name]["reason"] == cs.CAVEAT_REASON, expected_absent, (c["event_id"], name))
        self.assertTrue(any(pairs.get(e["event_id"]) for e in events), "the test needs a caveated holdout event")
        with self.assertRaises(DataError):
            gate.unseal(events, "neither")


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.events, self.spec = S.dataset()
        self.blocks = ev.assign_blocks(self.events)
        sealed, self.gate = d.seal_events(self.events, self.blocks, 5, self.spec)
        self.inputs = {"events": sealed, "spec": self.spec}
        self.versions = d.versions(self.inputs)

    def test_all_event_is_the_events_as_recorded(self):
        self.assertIs(self.versions["all_event"], self.inputs["events"])

    def test_clean_window_treats_the_caveated_pairs_and_what_derives_from_them_as_absent(self):
        pairs = cs.caveated_pairs(self.spec, with_derived=True)
        for event in self.versions["clean_window"]:
            if d.is_sealed(event):
                continue
            original = next(e for e in self.events if e["event_id"] == event["event_id"])
            for name in fp.LABELS:
                if name in pairs.get(event["event_id"], ()):
                    self.assertEqual(event["labels"][name], {"value": None, "reason": cs.CAVEAT_REASON})
                else:
                    self.assertEqual(event["labels"][name], original["labels"][name])

    def test_a_caveat_on_the_open_removes_every_gap_flag_and_both_conditional_flags_but_not_the_other_returns(self):
        event = next(e for e in self.versions["clean_window"] if not d.is_sealed(e) and e["event_id"] == "s000")  # event 0 carries a day1_open_return caveat
        for name in ("day1_open_return",) + tuple("gap_ge_%dpct" % t for t in fp.GAP_THRESHOLDS) + fp.CONDITIONAL_LABELS:
            self.assertIsNone(event["labels"][name]["value"], name)
        for name in ("day1_high_return", "day1_low_return", "day1_close_return", "session_5_close_return"):
            self.assertIsNotNone(event["labels"][name]["value"], name)

    def test_the_clean_window_events_match_caveat_sensitivitys_own_with_derived_variant(self):
        raw = {"events": self.events, "policy": None, "spec": self.spec}
        theirs = cs.variant_inputs(raw, cs.caveated_pairs(self.spec, with_derived=True), "with_derived")["events"]
        ours = [e for e in self.versions["clean_window"] if not d.is_sealed(e)]
        by_id = {e["event_id"]: e for e in theirs}
        for event in ours:
            self.assertEqual(event["labels"], by_id[event["event_id"]]["labels"])

    def test_no_event_object_is_shared_with_a_changed_label_between_versions(self):
        before = copy.deepcopy([e["labels"] for e in self.inputs["events"] if not d.is_sealed(e)])
        d.versions(self.inputs)
        self.assertEqual(before, [e["labels"] for e in self.inputs["events"] if not d.is_sealed(e)])

    def test_a_composite_target_is_absent_when_any_of_its_source_labels_is_caveated(self):
        extension = TARGETS["extension_after_open_ge_5pct"]
        high_caveated = blank(day1_open_return=0.02, day1_high_return=0.2)
        self.assertTrue(extension.function(high_caveated))
        self.assertIsNone(extension.function(d.mask_labels(high_caveated, {"day1_high_return"})))
        self.assertIsNone(extension.function(d.mask_labels(high_caveated, {"day1_open_return"})))


class TargetTests(unittest.TestCase):
    def test_the_five_primaries_are_binary_except_the_day1_close_return(self):
        primary = [t for t in TARGETS.values() if t.role == "primary"]
        self.assertEqual([t.id for t in primary], ["gap_ge_3pct", "gap_ge_5pct", "day1_close_return", "extension_after_open_ge_5pct", "loses_half_of_gap"])
        self.assertEqual({t.id: t.kind for t in primary}["day1_close_return"], "regression")
        self.assertEqual({t.id: t.clock for t in primary}, {"gap_ge_3pct": "B", "gap_ge_5pct": "B", "day1_close_return": "B",
                                                              "extension_after_open_ge_5pct": "C0", "loses_half_of_gap": "C0"})

    def test_all_targets_are_the_scoping_evidences_plus_the_regression_primary(self):
        self.assertEqual(set(TARGETS), {t[0] for t in ev.TARGETS} | {"day1_close_return"})
        for t in TARGETS.values():
            if t.role != "primary":
                self.assertEqual(t.kind, "binary")

    def test_each_target_reads_only_the_labels_it_declares_and_is_absent_without_any_of_them(self):
        for target in TARGETS.values():
            values = {name: (True if fp.label_kind(name) == "boolean" else 0.1) for name in target.source_labels}
            if "day1_high_return" in values:
                values["day1_high_return"] = 0.3
            result = target.function(Probe(target.source_labels, values))
            self.assertIsNotNone(result, target.id)
            for removed in target.source_labels:
                partial = {k: v for k, v in values.items() if k != removed}
                self.assertIsNone(target.function(Probe(target.source_labels, partial)), (target.id, removed))

    def test_the_primaries_source_labels_are_the_protocols(self):
        for item in PROTOCOL["targets"]["primary"]:
            self.assertEqual(TARGETS[item["id"]].source_labels, tuple(item["source_labels"]))
        for t in TARGETS.values():
            self.assertEqual(t.source_labels, d.SOURCES.get(t.id, t.source_labels))

    def test_the_regression_target_is_the_label_itself(self):
        self.assertEqual(TARGETS["day1_close_return"].function(blank(day1_close_return=0.07)), 0.07)
        self.assertIsNone(TARGETS["day1_close_return"].function(blank()))


class ThresholdTests(unittest.TestCase):
    def test_counts_count_only_defined_events(self):
        self.assertEqual(d.counts([True, False, None, True, None]), {"defined": 3, "positives": 2, "negatives": 1})
        self.assertEqual(d.counts([]), {"defined": 0, "positives": 0, "negatives": 0})

    def test_ten_positives_and_ten_negatives_is_enough_and_nine_is_not(self):
        self.assertTrue(d.enough({"defined": 20, "positives": 10, "negatives": 10}))
        self.assertFalse(d.enough({"defined": 20, "positives": 9, "negatives": 11}))
        self.assertFalse(d.enough({"defined": 20, "positives": 11, "negatives": 9}))
        self.assertIn("9 positives", d.shortfall({"defined": 20, "positives": 9, "negatives": 11}))
        self.assertIn("9 negatives", d.shortfall({"defined": 20, "positives": 11, "negatives": 9}))
        self.assertIsNone(d.shortfall({"defined": 20, "positives": 10, "negatives": 10}))

    def test_the_fold_level_rule_uses_the_training_events_with_the_target_defined(self):
        target, events = TARGETS["gap_ge_3pct"], [None] * 45
        self.assertEqual(d.fold_state(target, events, [True] * 10 + [False] * 10 + [None] * 25)["state"], d.EVALUABLE)
        self.assertEqual(d.fold_state(target, events, [True] * 9 + [False] * 11 + [None] * 25)["state"], d.INSUFFICIENT_DATA)
        self.assertEqual(d.fold_state(target, events, [True] * 10 + [False] * 9 + [None] * 26)["state"], d.INSUFFICIENT_DATA)

    def test_a_fold_with_under_forty_training_events_cannot_fit_anything(self):
        state = d.fold_state(TARGETS["gap_ge_3pct"], [None] * 39, [True] * 20 + [False] * 19)
        self.assertEqual(state["state"], d.INSUFFICIENT_DATA)
        self.assertIn("39 training events", state["reason"])
        self.assertEqual(d.fold_state(TARGETS["gap_ge_3pct"], [None] * 40, [True] * 20 + [False] * 20)["state"], d.EVALUABLE)  # forty is enough
        self.assertEqual(d.fold_state(TARGETS["day1_close_return"], [None] * 40, [0.1] * 40)["state"], d.EVALUABLE)

    def test_the_regression_rule_needs_forty_training_events_with_the_target_defined(self):
        target = TARGETS["day1_close_return"]
        self.assertEqual(d.fold_state(target, [None] * 41, [0.1] * 40 + [None])["state"], d.EVALUABLE)
        self.assertEqual(d.fold_state(target, [None] * 41, [0.1] * 39 + [None] * 2)["state"], d.INSUFFICIENT_DATA)

    def test_the_pooled_test_rule_and_the_regression_rule_for_the_pooled_test(self):
        self.assertEqual(d.pooled_state(TARGETS["gap_ge_5pct"], [True] * 10 + [False] * 34)["state"], d.EVALUABLE)  # the real, exactly-at-threshold case
        self.assertEqual(d.pooled_state(TARGETS["gap_ge_5pct"], [True] * 9 + [False] * 35)["state"], d.INSUFFICIENT_DATA)
        self.assertEqual(d.pooled_state(TARGETS["day1_close_return"], [0.1] * 20)["state"], d.EVALUABLE)
        self.assertEqual(d.pooled_state(TARGETS["day1_close_return"], [0.1] * 19 + [None] * 5)["state"], d.INSUFFICIENT_DATA)

    def test_the_holdouts_own_rule_gives_counts_only(self):
        self.assertEqual(d.holdout_state(TARGETS["gap_ge_3pct"], [True] * 5 + [False] * 18)["state"], d.COUNTS_ONLY)
        self.assertEqual(d.holdout_state(TARGETS["gap_ge_3pct"], [True] * 10 + [False] * 13)["state"], d.EVALUABLE)
        self.assertEqual(d.holdout_state(TARGETS["day1_close_return"], [0.1] * 19)["state"], d.COUNTS_ONLY)
        self.assertEqual(d.holdout_state(TARGETS["day1_close_return"], [0.1] * 20)["state"], d.EVALUABLE)


class FoldTests(unittest.TestCase):
    def setUp(self):
        self.events, self.spec = S.dataset()
        self.blocks = ev.assign_blocks(self.events)

    def test_the_folds_are_the_protocols(self):
        self.assertEqual([(f.name, f.role, f.train_blocks, f.test_block) for f in d.folds(PROTOCOL)],
                         [("dev_test_block_3", "development", (1, 2), 3), ("dev_test_block_4", "development", (1, 2, 3), 4),
                          ("holdout_test_block_5", "holdout", (1, 2, 3, 4), 5)])

    def test_a_fold_is_whole_blocks_in_time_order(self):
        for fold in FOLDS.values():
            train, test = d.split(self.events, self.blocks, fold)
            self.assertEqual({self.blocks[e["event_id"]] for e in train}, set(fold.train_blocks))
            self.assertEqual({self.blocks[e["event_id"]] for e in test}, {fold.test_block})
            self.assertEqual(train, sorted(train, key=fp.event_order))
            d.assert_clusters_whole(train, test, self.blocks)

    def test_a_reaction_session_split_between_training_and_test_is_caught(self):
        train, test = d.split(self.events, self.blocks, FOLDS["dev_test_block_3"])
        moved = copy.deepcopy(test[0])
        moved["reaction_session"] = train[-1]["reaction_session"]
        with self.assertRaisesRegex(DataError, "reaction session split"):
            d.assert_clusters_whole(train, [moved] + test[1:], self.blocks)

    def test_a_cluster_split_between_training_and_test_is_caught(self):
        train, test = d.split(self.events, self.blocks, FOLDS["dev_test_block_3"])
        moved = copy.deepcopy(test[0])
        moved["cluster_id"] = train[0]["cluster_id"]
        with self.assertRaisesRegex(DataError, "cluster split"):
            d.assert_clusters_whole(train, [moved] + test[1:], self.blocks)

    def test_a_block_split_between_training_and_test_is_caught(self):
        train, test = d.split(self.events, self.blocks, FOLDS["dev_test_block_3"])
        blocks = dict(self.blocks)
        blocks[test[0]["event_id"]] = blocks[train[0]["event_id"]]
        with self.assertRaisesRegex(DataError, "block split"):
            d.assert_clusters_whole(train, test, blocks)

    def test_a_label_that_matures_after_the_first_test_cutoff_is_a_violation(self):
        train, test = d.split(self.events, self.blocks, FOLDS["dev_test_block_3"])
        slack = d.assert_label_maturity(train, test, fp.LABELS, "dev_test_block_3")
        self.assertGreater(slack, 0)
        late = copy.deepcopy(train)
        late[-1]["available_at"]["session_20_close_return"] = test[0]["cutoff"] + timedelta(seconds=1)
        with self.assertRaises(d.MaturityViolation):
            d.assert_label_maturity(late, test, fp.LABELS, "dev_test_block_3")
        late[-1]["available_at"]["session_20_close_return"] = min(e["cutoff"] for e in test)  # available exactly at the cutoff: known
        d.assert_label_maturity(late, test, fp.LABELS, "dev_test_block_3")
        with self.assertRaises(d.MaturityViolation):  # ...but only the labels asked about are checked
            late[-1]["available_at"]["day1_close_return"] = test[0]["cutoff"] + timedelta(hours=1)
            d.assert_label_maturity(late, test, ("day1_close_return",), "f")

    def test_the_synthetic_blocks_leave_slack_at_every_boundary(self):
        for fold in FOLDS.values():
            train, test = d.split(self.events, self.blocks, fold)
            self.assertGreater(d.assert_label_maturity(train, test, fp.LABELS, fold.name), 0)


class RealInputsTests(unittest.TestCase):
    """The real events, loaded with the holdout sealed. Everything asserted needs only identities, times and the labels of blocks 1 to 4."""

    @classmethod
    def setUpClass(cls):
        cls.inputs = d.load_inputs(PROTOCOL)
        cls.reference = fp.load_inputs(spec_path=ROOT / PROTOCOL["inputs"]["events_spec"]["path"], calendar_path=ROOT / PROTOCOL["inputs"]["calendar"]["path"])

    def test_the_sealed_events_are_the_23_milestone_1_events_of_block_5(self):
        sealed = [e for e in self.inputs["events"] if d.is_sealed(e)]
        self.assertEqual(len(sealed), 23)
        self.assertEqual({self.inputs["blocks"][e["event_id"]] for e in sealed}, {5})
        self.assertEqual({d.sources_of(self.inputs["events"])[e["event_id"]] for e in sealed}, {"milestone_1"})
        self.assertEqual((min(e["reaction_session"] for e in sealed), max(e["reaction_session"] for e in sealed)), ("2026-01-22", "2026-04-01"))
        self.assertEqual(self.inputs["gate"].denied, [])
        self.assertEqual(self.inputs["gate"].unsealed, 0)

    def test_every_event_matches_the_ordinary_loaders_except_that_holdout_labels_are_sealed(self):
        ours = {e["event_id"]: e for e in self.inputs["events"]}
        self.assertEqual(set(ours), {e["event_id"] for e in self.reference["events"]})
        for event in self.reference["events"]:
            mine = ours[event["event_id"]]
            for key in event:
                if key == "labels" and d.is_sealed(mine):
                    continue
                self.assertEqual(mine[key], event[key], (event["event_id"], key))
        self.assertEqual([e["event_id"] for e in self.inputs["events"]], [e["event_id"] for e in self.reference["events"]])

    def test_the_inputs_are_hashed_and_shaped_as_the_ordinary_loaders_are(self):
        for key in ("policy_sha256", "sector_map_sha256", "sector_read_on", "scope_note"):
            self.assertEqual(self.inputs[key], self.reference[key])
        self.assertEqual(self.inputs["blocks"], ev.assign_blocks(self.reference["events"]))

    def test_the_real_versions_have_the_caveat_counts_the_protocol_pins(self):
        versions = d.versions(self.inputs)
        clean = [e for e in versions["clean_window"] if not d.is_sealed(e)]
        absent = sum(1 for e in clean for label in e["labels"].values() if label["reason"] == cs.CAVEAT_REASON)
        pairs = cs.caveated_pairs(self.inputs["spec"], with_derived=True)
        held = {e["event_id"] for e in self.inputs["events"] if d.is_sealed(e)}
        self.assertEqual(absent, sum(len(v) for k, v in pairs.items() if k not in held))
        self.assertEqual(len(pairs), PROTOCOL["inputs"]["caveated_labels"]["events_with_caveats"])

    def test_the_holdout_must_be_the_last_block(self):
        altered = copy.deepcopy(PROTOCOL)
        altered["holdout"]["block"] = 4
        with self.assertRaisesRegex(DataError, "last block"):
            d.load_inputs(altered)

    def test_the_real_divisions_are_all_ones_the_protocol_names(self):
        self.assertLessEqual({e["sic_division"] for e in self.inputs["events"]}, {"D", "I", "B", "E", "F", "G"})
        for event in self.inputs["events"]:
            feat.sector_group(event)

    def test_a_destroyed_holdout_record_changes_nothing_because_none_is_read(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name in ("config", "reports"):
            shutil.copytree(ROOT / name, root / name)
        held = {e["event_id"] for e in self.inputs["events"] if d.is_sealed(e)}
        for entry in self.inputs["spec"]["events"]:
            if entry["event_id"] in held:
                (root / entry["recorded_result"]["recorded_in"]).write_text("destroyed", encoding="utf-8")
        inputs = d.load_inputs(PROTOCOL, root)
        self.assertEqual(sum(d.is_sealed(e) for e in inputs["events"]), 23)
        self.assertEqual(inputs["gate"].denied, [])
        with self.assertRaises(ValueError):  # the labels are read from the record only when they are unsealed
            inputs["gate"].unseal([e for e in inputs["events"] if d.is_sealed(e)][:1], "all_event")

    def test_a_non_holdout_record_that_no_longer_matches_its_pinned_digest_is_refused_at_load(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name in ("config", "reports"):
            shutil.copytree(ROOT / name, root / name)
        held = {e["event_id"] for e in self.inputs["events"] if d.is_sealed(e)}
        entry = next(e for e in self.inputs["spec"]["events"] if "recorded_result" in e and e["event_id"] not in held)
        path = root / entry["recorded_result"]["recorded_in"]
        text = path.read_text(encoding="utf-8")
        self.assertIn('"day1_close_return"', text)
        path.write_text(text.replace('"day1_close_return": ', '"day1_close_return": 9', 1), encoding="utf-8")
        with self.assertRaises(DataError):
            d.load_inputs(PROTOCOL, root)

    def test_every_fold_every_target_and_every_label_is_mature_before_the_first_test_cutoff(self):
        events, blocks = self.inputs["events"], self.inputs["blocks"]
        smallest = {}
        for fold in FOLDS.values():
            train, test = d.split(events, blocks, fold)
            smallest[fold.name] = d.assert_label_maturity(train, test, fp.LABELS, fold.name)
            for target in TARGETS.values():
                d.assert_label_maturity(train, test, target.source_labels, fold.name)
            d.assert_clusters_whole(train, test, blocks)
        for slack in smallest.values():
            self.assertGreater(slack, 9)  # the protocol states 9 to 19 days of slack at the block boundaries

    def test_the_real_events_in_a_block_share_no_reaction_session_with_another_block(self):
        sessions = {}
        for e in self.inputs["events"]:
            sessions.setdefault(e["reaction_session"], set()).add(self.inputs["blocks"][e["event_id"]])
        self.assertTrue(all(len(blocks) == 1 for blocks in sessions.values()))


class SectorFeatureTests(unittest.TestCase):
    def event(self, division):
        return {"event_id": "x", "sic_division": division, "release_timing": "premarket"}

    def test_the_protocols_sector_grouping(self):
        self.assertEqual([feat.sector_group(self.event(x)) for x in "DIBEFG"], ["D", "I", "other", "other", "other", "other"])

    def test_a_division_the_protocol_does_not_name_is_a_gap_not_a_guess(self):
        for division in "ACHJ":
            with self.assertRaises(d.ProtocolGap):
                feat.sector_group(self.event(division))

    def test_indicators_code_d_as_the_reference(self):
        self.assertEqual(feat.indicators({"event_id": "x", "sic_division": "D", "release_timing": "after_hours"}), {"after_hours": 1, "is_I": 0, "is_other": 0})
        self.assertEqual(feat.indicators({"event_id": "x", "sic_division": "I", "release_timing": "premarket"}), {"after_hours": 0, "is_I": 1, "is_other": 0})
        self.assertEqual(feat.indicators({"event_id": "x", "sic_division": "E", "release_timing": "premarket"}), {"after_hours": 0, "is_I": 0, "is_other": 1})


class HistoryFeatureTests(unittest.TestCase):
    """Hand-built events on the real 2026 calendar: each outcome of gap_ge_3pct is set directly."""
    TARGET = TARGETS["gap_ge_3pct"]

    def make(self, n, session, issuer, positive, sic="2834", timing="after_hours", cluster=None):
        return S.build_event(n, session, timing, "%010d" % issuer, sic, cluster or "k%d" % n, blank(gap_ge_3pct=positive))

    def days(self):
        return [x for x in S.CAL.days if "2026-02-02" <= x <= "2026-04-30"]

    def test_the_rate_shrinks_the_issuers_own_record_toward_the_pooled_prior(self):
        days = self.days()
        train = [self.make(1, days[0], 1, True), self.make(2, days[1], 1, False), self.make(3, days[2], 1, True), self.make(4, days[3], 2, False), self.make(5, days[4], 2, False)]
        event = self.make(9, days[10], 1, False)
        result = feat.issuer_history_rate(event, train, self.TARGET)
        self.assertEqual((result["k"], result["n"]), (2, 3))
        self.assertEqual((result["prior"], result["prior_source"], result["prior_n"]), (0.4, "all_earlier_events", 5))  # fewer than 10 in the group: all earlier events
        self.assertAlmostEqual(result["rate"], (2 + 10 * 0.4) / (3 + 10))
        self.assertEqual(result["history_event_ids"], sorted(e["event_id"] for e in train))

    def test_ten_earlier_events_in_the_same_major_group_make_the_group_the_prior(self):
        days = self.days()
        group = [self.make(n, days[n], 3 + n % 5, n < 3, sic="2834" if n % 2 else "2836") for n in range(10)]  # SIC 2834 and 2836: major group 28; 3 positives
        others = [self.make(20 + n, days[10 + n], 9, True, sic="7372") for n in range(5)]  # a different group, all positive
        event = self.make(99, days[20], 3, False)
        result = feat.issuer_history_rate(event, group + others, self.TARGET)
        self.assertEqual((result["prior_source"], result["prior_n"], result["prior"]), ("sic_major_group", 10, 0.3))
        nine = feat.issuer_history_rate(event, group[:9] + others, self.TARGET)
        self.assertEqual((nine["prior_source"], nine["prior_n"]), ("all_earlier_events", 14))  # one short of ten: the pool of everything earlier

    def test_with_no_earlier_event_the_prior_is_one_half_and_so_is_the_rate(self):
        result = feat.issuer_history_rate(self.make(1, self.days()[0], 1, True), [], self.TARGET)
        self.assertEqual((result["rate"], result["prior"], result["prior_source"], result["n"]), (0.5, 0.5, "none_available", 0))

    def test_only_events_that_reacted_on_an_earlier_session_count(self):
        days = self.days()
        event = self.make(9, days[5], 1, False)
        same_session = self.make(1, days[5], 1, True, timing="premarket")
        later = self.make(2, days[6], 1, True)
        earlier = self.make(3, days[2], 1, True)
        self.assertEqual(feat.history(event, [same_session, later, earlier, event], self.TARGET), [earlier])

    def test_the_earlier_session_rule_stands_on_its_own_even_if_a_later_labels_availability_were_recorded_early(self):
        days = self.days()
        event = self.make(9, days[5], 1, False)
        later, same = self.make(1, days[6], 1, True), self.make(2, days[5], 1, True, timing="premarket")
        for other in (later, same):
            other["available_at"]["gap_ge_3pct"] = event["cutoff"] - timedelta(days=1)  # a wrong timestamp must not let the future in
        self.assertEqual(feat.history(event, [later, same], self.TARGET), [])

    def test_an_earlier_event_whose_labels_are_not_yet_available_at_the_cutoff_is_excluded(self):
        days = self.days()
        event = self.make(9, days[5], 1, False)
        unmatured = self.make(1, days[4], 1, True)
        unmatured["available_at"]["gap_ge_3pct"] = event["cutoff"] + timedelta(minutes=1)
        exactly = self.make(2, days[3], 1, True)
        exactly["available_at"]["gap_ge_3pct"] = event["cutoff"]
        self.assertEqual(feat.history(event, [unmatured, exactly], self.TARGET), [exactly])
        other_label = self.make(3, days[2], 1, True)
        other_label["available_at"]["session_20_close_return"] = event["cutoff"] + timedelta(days=30)  # not a source of this target
        self.assertEqual(feat.history(event, [other_label], self.TARGET), [other_label])

    def test_events_with_the_target_absent_are_not_history_and_do_not_count(self):
        days = self.days()
        absent = S.build_event(1, days[0], "after_hours", "%010d" % 1, "2834", "k1", blank())
        present = self.make(2, days[1], 1, True)
        result = feat.issuer_history_rate(self.make(9, days[5], 1, False), [absent, present], self.TARGET)
        self.assertEqual((result["k"], result["n"], result["prior_n"], result["history_event_ids"]), (1, 1, 1, ["s002"]))

    def test_changing_the_label_of_an_event_that_is_not_history_changes_nothing(self):
        days = self.days()
        train = [self.make(n, days[n], 1 + n % 3, n % 2 == 0) for n in range(8)]
        event = self.make(99, days[9], 1, False)
        base = feat.issuer_history_rate(event, train, self.TARGET)
        flipped = copy.deepcopy(train)
        flipped.append(self.make(50, days[12], 1, True))  # a later event
        flipped.append(self.make(51, days[9], 1, True, timing="premarket"))  # the same session
        self.assertEqual(feat.issuer_history_rate(event, flipped, self.TARGET), base)
        changed = copy.deepcopy(train)
        changed[0]["labels"]["gap_ge_3pct"]["value"] = not changed[0]["labels"]["gap_ge_3pct"]["value"]  # an event that is history
        self.assertNotEqual(feat.issuer_history_rate(event, changed, self.TARGET)["rate"], base["rate"])

    def test_the_regression_history_mean_shrinks_toward_the_group_mean_used_as_is(self):
        days = self.days()
        target = TARGETS["day1_close_return"]
        train = [S.build_event(n, days[n], "after_hours", "%010d" % (1 + n % 2), "2834", "k%d" % n, blank(day1_close_return=0.01 * (n + 1))) for n in range(4)]
        event = S.build_event(9, days[9], "after_hours", "%010d" % 1, "2834", "k9", blank(day1_close_return=0.5))
        result = feat.issuer_history_mean(event, train, target)
        own = [0.01 * (n + 1) for n in range(4) if 1 + n % 2 == 1]  # the events of issuer 1: n = 0 and 2
        mu = sum(0.01 * (n + 1) for n in range(4)) / 4
        self.assertAlmostEqual(result["mean"], (sum(own) + 10 * mu) / (len(own) + 10))
        self.assertEqual((result["n"], result["prior_source"]), (2, "all_earlier_events"))

    def test_the_regression_history_mean_has_no_default_so_it_stops_rather_than_guess(self):
        with self.assertRaises(d.ProtocolGap):
            feat.issuer_history_mean(S.build_event(1, self.days()[0], "after_hours", "%010d" % 1, "2834", "k1", blank(day1_close_return=0.1)), [], TARGETS["day1_close_return"])


if __name__ == "__main__":
    unittest.main()
