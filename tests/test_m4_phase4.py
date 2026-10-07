"""Phase 4 on synthetic data: the holdout evaluation in every state a target-version can take, that its predictions depend on no block-5 outcome except the opening gap on the
C0 clock, the pre-look audit and that it reads no outcome, the descriptive report's counts, the sign check, and the one-look runner with all its refusals. No real event is
looked at: the real inputs are exercised with synthetic block-5 labels in tests/test_m4_phase4_rehearsal.py."""
import json
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_support as S  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_features as feat  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_phase2 as p2  # noqa: E402
from nre import m4_phase3 as p3  # noqa: E402
from nre import m4_phase4 as p4  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402
from nre import m4_scoping_evidence as ev  # noqa: E402
from nre.core import DataError, canonical, digest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
COMMIT, WHEN = "e" * 40, "2026-10-07T13:00:00Z"
SIZES = (24, 44, 36, 36, 30)  # a holdout of 30 events, so that thresholds of 10 and 10 can be met
HOLDOUT_FOLD = "holdout_test_block_5"
BINARY = ["C1_pooled_rate", "C2_timing_rate", "C3_sector_group_rate", "C4_issuer_history_rate", "M2_logistic", "M2_without_sector"]
REGRESSION = ["C1_pooled_quantiles", "C2_timing_quantiles", "C3_sector_group_quantiles", "M3_ridge_linear", "M3_without_sector"]


balanced, sparse = S.holdout_balanced, S.holdout_sparse  # the holdout labels that meet every threshold, and those that meet almost none


def dataset(choose=balanced, sizes=SIZES, close_missing=0):
    """Synthetic events and spec whose holdout block carries the labels `choose(position)` gives (the first `close_missing` have no day-1 close)."""
    events, spec = S.dataset(sizes=sizes)
    held = {e["event_id"]: i for i, e in enumerate(S.holdout_events(events))}

    def change(event):
        if event["event_id"] in held:
            event["labels"] = choose(held[event["event_id"]])
            if held[event["event_id"]] < close_missing:
                event["labels"]["day1_close_return"] = {"value": None, "reason": "TEST_ABSENT"}
    return S.with_labels_changed(events, change), spec


def absent_logs(owner):
    """Paths of logs that do not exist, so that a synthetic harness reads nothing from (and could write nothing to) the real logs."""
    directory = tempfile.TemporaryDirectory()
    (owner.addClassCleanup if isinstance(owner, type) else owner.addCleanup)(directory.cleanup)
    root = Path(directory.name)
    return {"experiment_log": root / "absent-experiments.jsonl", "holdout_log": root / "absent-holdout.jsonl"}


class Looked:
    """A synthetic harness with its own logs, and the events one look returned (the tripwire is patched on for that call only)."""

    def __init__(self, test, events, spec, look=True):
        directory = tempfile.TemporaryDirectory()
        (test.addClassCleanup if isinstance(test, type) else test.addCleanup)(directory.cleanup)  # `test` is a TestCase, or its class when built in setUpClass
        root = Path(directory.name)
        self.experiments, self.holdout = root / "experiments.jsonl", root / "holdout.jsonl"
        reg.init_logs(PROTOCOL, COMMIT, "2026-10-06T00:00:00Z", self.experiments, self.holdout)
        self.engine = h.Harness.for_tests(events, spec, calendar=S.CAL, experiment_log=self.experiments, holdout_log=self.holdout, commit=lambda: COMMIT, clock=lambda: WHEN)
        self.unsealed = None
        if look:
            with mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True):
                self.unsealed = self.engine.look("a test look")


def holdout_predictions(owner, events, spec):
    """{(target, predictor): {event: prediction}} for every cell of the five primaries (all_event), from one look. Every cell must be scored, or a missing prediction could hide a
    difference between two datasets."""
    looked = Looked(owner, events, spec)
    out = {}
    for target_id in p4.TARGETS:
        result = looked.engine.evaluate_holdout(target_id, "all_event", looked.unsealed["all_event"], p2.predictors_for(looked.engine.targets[target_id]))
        if result["state"] != h.EVALUATED:
            raise AssertionError("%s is %s: %s" % (target_id, result["state"], result["reason"]))
        for pid, run in result["predictors"].items():
            if run["state"] != h.EVALUATED:
                raise AssertionError("%s %s is %s" % (target_id, pid, run["state"]))
            out[(target_id, pid)] = {r["event_id"]: r["p"] for r in run["rows"]}
    return out


class Spy(h.Predictor):
    """Records the training events it is fitted on and what it is shown at predict."""
    id, kind = "TEST_SPY", "binary"

    def __init__(self):
        self.trained, self.views = [], []

    def fit(self, train, target):
        self.trained.append([e["event_id"] for e in train])
        return {"n": len(train)}

    def predict(self, model, view):
        self.views.append(view)
        return 0.3


class StateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = dataset(balanced)

    def look(self, events=None, spec=None):
        return Looked(self, events or self.events, spec or self.spec)

    def test_when_the_thresholds_are_met_every_predictor_is_scored_and_the_contrasts_are_holdout_contrasts(self):
        looked = self.look()
        target = looked.engine.targets["gap_ge_3pct"]
        result = looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], p2.predictors_for(target))
        self.assertEqual((result["state"], result["fold"]["test"], result["fold"]["state"]), (h.EVALUATED, {"defined": 30, "positives": 15, "negatives": 15}, d.EVALUABLE))
        self.assertEqual(sorted(result["predictors"]), sorted(BINARY))
        self.assertEqual({run["state"] for run in result["predictors"].values()}, {h.EVALUATED})
        self.assertEqual({run["predictions"] for run in result["predictors"].values()}, {30})
        self.assertEqual(sorted(result["contrasts"]), sorted(set(BINARY) - {"C1_pooled_rate"}))
        roles = {pid: c["role"] for pid, c in result["contrasts"].items()}
        self.assertEqual(roles.pop("M2_logistic"), "holdout_replication_check")
        self.assertEqual(set(roles.values()), {"exploratory"})
        for contrast in list(result["contrasts"].values()) + list(result["other_contrasts"].values()):
            self.assertIn("never creates a claim", contrast["claim"])
            self.assertEqual(set(contrast["headline"]), {"0.95", "0.99"})
            self.assertEqual(contrast["by_clustering"]["issuer"]["replicates"], pr.BOOTSTRAP_REPLICATES)
        self.assertNotIn("fold_contrasts", result)  # one fold: nothing to split
        self.assertEqual(result["selection_regime"], PROTOCOL["holdout"]["selection_regime"])  # every holdout result carries the protocol's statement
        self.assertIn("confounded", result["selection_regime"])

    def test_the_metrics_are_the_development_ones_on_the_one_fold_with_k_of_5_and_10(self):
        looked = self.look()
        target = looked.engine.targets["gap_ge_3pct"]
        result = looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], p2.predictors_for(target))
        metrics = result["predictors"]["M2_logistic"]["metrics"]
        self.assertEqual(set(metrics["precision_at_k"]), {"5", "10"})
        self.assertEqual(metrics["counts"], {"events": 30, "reaction_sessions": metrics["counts"]["reaction_sessions"], "issuers": metrics["counts"]["issuers"], "positives": 15, "negatives": 15})
        self.assertEqual(metrics["reliability"]["state"], "REPORTED")
        self.assertEqual(len(metrics["reliability"]["bins"]), min(pr.MAX_RELIABILITY_BINS, 30 // pr.MIN_PER_BIN))
        self.assertEqual(set(result["predictors"]["M2_logistic"]["metrics_by_source"]), {"test"})

    def test_too_few_positives_make_the_target_counts_only_and_nothing_is_fitted_or_scored(self):
        events, spec = dataset(sparse)
        looked = self.look(events, spec)
        spy = Spy()
        result = looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], [spy])
        self.assertEqual((result["state"], result["fold"]["test"]), (d.COUNTS_ONLY, {"defined": 30, "positives": 3, "negatives": 27}))
        self.assertIn("3 positives among 30 defined events (at least 10 needed)", result["reason"])
        self.assertEqual((spy.trained, spy.views), ([], []))  # no fit, no prediction
        self.assertEqual(result["predictors"]["TEST_SPY"], {"state": d.COUNTS_ONLY, "reason": result["reason"], "predictions": None})
        self.assertEqual((result["contrasts"], result["other_contrasts"]), ({}, {}))
        counts = result["test_counts"]
        self.assertEqual((counts["events"], counts["positives"], counts["negatives"]), (30, 3, 27))
        self.assertAlmostEqual(counts["base_rate"], 0.1)
        low, high = fp.wilson(3, 30, 0.95)
        self.assertEqual((counts["wilson_low"], counts["wilson_high"], counts["wilson_level"]), (low, high, 0.95))

    def test_too_few_negatives_are_counts_only_too_and_a_target_with_too_few_events_defined_is_counts_only(self):
        events, spec = dataset(lambda i: S.labels_from_returns(0.06, 0.13, 0.04, 0.02) if i < 28 else S.labels_from_returns(0.0, 0.01, -0.01, 0.0))
        looked = self.look(events, spec)
        result = looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], [Spy()])
        self.assertEqual((result["state"], result["fold"]["test"]["negatives"]), (d.COUNTS_ONLY, 2))
        self.assertIn("2 negatives among 30 defined events (at least 10 needed)", result["reason"])
        half = looked.engine.evaluate_holdout("loses_half_of_gap", "all_event", looked.unsealed["all_event"], [Spy()])  # only the 28 positive gaps are defined, and all lose half
        self.assertEqual((half["state"], half["fold"]["test"]), (d.COUNTS_ONLY, {"defined": 28, "positives": 28, "negatives": 0}))

    def test_the_regression_target_needs_twenty_test_events_not_a_class_balance(self):
        looked = self.look(*dataset(sparse))
        result = looked.engine.evaluate_holdout("day1_close_return", "all_event", looked.unsealed["all_event"], p2.predictors_for(looked.engine.targets["day1_close_return"]))
        self.assertEqual((result["state"], result["fold"]["test"]), (h.EVALUATED, {"defined": 30}))  # 30 events: scored although nearly all are flat
        self.assertEqual(sorted(result["predictors"]), sorted(REGRESSION))
        self.assertEqual(set(result["contrasts"]), set(REGRESSION) - {"C1_pooled_quantiles"})
        self.assertEqual(result["contrasts"]["M3_ridge_linear"]["role"], "holdout_replication_check")
        events, spec = dataset(balanced, close_missing=11)  # 19 events with a day-1 close
        short = self.look(events, spec)
        counts_only = short.engine.evaluate_holdout("day1_close_return", "all_event", short.unsealed["all_event"], [h.PooledQuantiles()])
        self.assertEqual((counts_only["state"], counts_only["fold"]["test"]), (d.COUNTS_ONLY, {"defined": 19}))
        self.assertIn("19 test events with the target defined (at least 20 needed)", counts_only["reason"])

    def test_a_fold_whose_training_events_are_too_few_is_insufficient_data_before_the_holdout_rule_is_applied(self):
        events, spec = dataset(balanced, sizes=(6, 8, 10, 10, 30))
        looked = self.look(events, spec)
        result = looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], [Spy()])
        self.assertEqual(result["state"], d.INSUFFICIENT_DATA)
        self.assertIn("34 training events, fewer than the 40 needed", result["reason"])
        self.assertEqual(result["predictors"]["TEST_SPY"]["predictions"], None)

    def test_the_clean_window_version_scores_what_that_version_sees_and_may_differ_from_the_all_event_one(self):
        looked = self.look()
        counts = {version: looked.engine.evaluate_holdout("gap_ge_3pct", version, looked.unsealed[version], [h.PooledRate()])["fold"]["test"] for version in d.VERSIONS}
        self.assertEqual(counts["all_event"]["defined"], 30)
        self.assertLessEqual(counts["clean_window"]["defined"], 30)

    def test_a_predictor_that_fails_to_fit_is_recorded_with_its_state_and_nothing_is_substituted(self):
        looked = self.look()

        class Failing(h.PooledRate):
            id = "TEST_FAILING"

            def fit(self, train, target):
                raise h.Abstain("MODEL_FIT_FAILED", "does not converge")
        result = looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], [h.PooledRate(), Failing()])
        self.assertEqual(result["predictors"]["TEST_FAILING"], {"state": "MODEL_FIT_FAILED", "reason": "does not converge", "predictions": None})
        self.assertEqual(result["predictors"]["C1_pooled_rate"]["state"], h.EVALUATED)
        self.assertNotIn("TEST_FAILING", result["contrasts"])

    def test_only_the_looks_events_are_accepted_and_the_sealed_ones_are_refused(self):
        looked = self.look()
        target = looked.engine.targets["gap_ge_3pct"]
        with self.assertRaisesRegex(DataError, "not the holdout fold's test events"):
            looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"][:-1], [h.PooledRate()])
        sealed = [e for e in looked.engine.versions["all_event"] if d.is_sealed(e)]
        with self.assertRaisesRegex(DataError, "not the holdout fold's test events"):
            looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", sealed, [h.PooledRate()])
        self.assertEqual(target.role, "primary")
        with self.assertRaisesRegex(DataError, "no predictor is fitted"):
            looked.engine.evaluate_holdout("full_gap_fill", "all_event", looked.unsealed["all_event"], [h.PooledRate()])

    def test_evaluating_the_holdout_unseals_nothing_itself(self):
        looked = self.look()
        before = looked.engine.gate.unsealed
        looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], p2.predictors_for(looked.engine.targets["gap_ge_3pct"]))
        self.assertEqual((looked.engine.gate.unsealed, looked.engine.gate.denied), (before, []))
        self.assertEqual(before, 2 * 30)  # the one look: every event once per version


class LeakageTests(unittest.TestCase):
    """The protocol: no predictor is fitted, scored or tuned on a block-5 outcome. A prediction for a holdout event may depend on its own opening gap on the C0 clock (known
    at the open) and on nothing else about block 5."""

    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = dataset(balanced)
        cls.base = holdout_predictions(cls, cls.events, cls.spec)

    def predictions(self, events):
        return holdout_predictions(self, events, self.spec)

    def test_swapping_every_block_5_outcome_but_not_the_opening_gap_changes_no_prediction(self):
        def swapped(position, n=30):
            lose, extend = position % 2 == 1, position % 2 == 0  # the opposite close pattern, and a different set of events that extend, with the same gaps
            if position < n // 2:
                return S.labels_from_returns(0.06, 0.13 if extend else 0.07, 0.04, 0.02 if lose else 0.05)
            return S.labels_from_returns(0.01, 0.09 if extend else 0.02, -0.01, 0.0 if lose else 0.015)
        other, _ = dataset(swapped)
        held = S.holdout_events(self.events)
        self.assertNotEqual([e["labels"] for e in held], [e["labels"] for e in S.holdout_events(other)])  # the outcomes really differ
        base, changed = self.base, self.predictions(other)
        self.assertEqual(set(base), set(changed))
        self.assertEqual(len(base), 4 * 6 + 5)  # six predictors on each of four binary targets, five on the regression one
        for key in base:
            self.assertEqual(base[key], changed[key], key)

    def test_changing_the_opening_gap_changes_only_the_c0_logistic_models(self):
        def shifted(position, n=30):  # every gap 0.2 points larger, with every outcome (every target's value) unchanged
            lose = position % 2 == 0
            if position < n // 2:
                return S.labels_from_returns(0.062, 0.13, 0.04, 0.02 if lose else 0.05)
            return S.labels_from_returns(0.012, 0.02, -0.01, 0.0 if lose else 0.015)
        other, _ = dataset(shifted)
        base, changed = self.base, self.predictions(other)
        differing = {key for key in base if base[key] != changed[key]}
        self.assertEqual({t for t, _ in differing}, {"extension_after_open_ge_5pct", "loses_half_of_gap"})  # the two C0 targets
        self.assertEqual({pid for _, pid in differing}, {"M2_logistic", "M2_without_sector"})
        self.assertEqual(len(differing), 4)

    def test_the_fit_sees_blocks_1_to_4_only_and_a_view_has_no_labels(self):
        looked = Looked(self, self.events, self.spec)
        spy = Spy()
        looked.engine.evaluate_holdout("gap_ge_3pct", "all_event", looked.unsealed["all_event"], [spy])
        blocks = looked.engine.blocks
        self.assertEqual({blocks[i] for i in spy.trained[0]}, {1, 2, 3, 4})
        self.assertEqual(len(spy.trained[0]), sum(1 for e in self.events if blocks[e["event_id"]] <= 4))
        self.assertEqual(len(spy.views), 30)
        for view in spy.views:
            self.assertNotIn("labels", view)
            self.assertNotIn("labels_sha256", view)
            self.assertNotIn("open_gap", view)  # a B-clock target
        c0 = Spy()
        looked.engine.evaluate_holdout("extension_after_open_ge_5pct", "all_event", looked.unsealed["all_event"], [c0])
        self.assertTrue(all("open_gap" in view and "labels" not in view for view in c0.views))


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = dataset(balanced)
        cls.engine = h.Harness.for_tests(cls.events, cls.spec, calendar=S.CAL, **absent_logs(cls))
        cls.audit = p4.holdout_structure_audit(cls.engine)

    def test_it_covers_the_five_primaries_in_both_versions_and_counts_all_the_test_events(self):
        self.assertEqual(sorted(self.audit), sorted(p4.TARGETS))
        for versions in self.audit.values():
            self.assertEqual(sorted(versions), sorted(d.VERSIONS))
            for entry in versions.values():
                self.assertEqual(entry["test_events"], 30)
                self.assertEqual(sum(entry["test_events_by_cell"]["C2_timing"].values()), 30)
                self.assertEqual(sum(entry["test_events_by_cell"]["C3_sector_group"].values()), 30)
        self.assertIn("test_events_whose_history_mean_would_stop_the_run", self.audit["day1_close_return"]["all_event"])
        self.assertNotIn("test_events_whose_history_mean_would_stop_the_run", self.audit["gap_ge_3pct"]["all_event"])

    def test_it_reads_no_outcome_changing_every_label_value_gives_the_identical_audit(self):
        def alter(event):
            for label in event["labels"].values():
                if label["value"] is not None:
                    label["value"] = (not label["value"]) if isinstance(label["value"], bool) else label["value"] + 0.123
        changed = h.Harness.for_tests(S.with_labels_changed(self.events, alter), self.spec, calendar=S.CAL, **absent_logs(self))
        # the training events' labels changed, so the facts that depend on which of them are defined may not: here every label stays defined, and nothing else is read
        self.assertEqual(digest(canonical(p4.holdout_structure_audit(changed))), digest(canonical(self.audit)))

    def test_it_never_touches_a_sealed_label(self):
        self.assertEqual((self.engine.gate.denied, self.engine.gate.unsealed), ([], 0))
        report = p4.audit_report(self.engine)
        self.assertEqual(report["kind"], "m4_phase4_holdout_structure_audit")
        self.assertEqual((report["holdout"]["denied_reads"], report["holdout"]["unsealed_loads"], report["holdout"]["access_log_records_after_genesis"]), (0, 0, 0))
        self.assertIn("no block-5 outcome", report["purpose"])
        self.assertIn("not the opening gap", report["purpose"])

    def test_it_counts_the_fallbacks_a_thin_training_cell_causes_as_the_baselines_will_make_them(self):
        events, spec = S.dataset(sizes=(10, 16, 14, 14, 30))  # 54 training events, of which loses_half_of_gap is defined for the positive gaps only: some cells hold fewer than 10
        engine = h.Harness.for_tests(events, spec, calendar=S.CAL, **absent_logs(self))
        entry = p4.holdout_structure_audit(engine, ("loses_half_of_gap",))["loses_half_of_gap"]["all_event"]
        train, test = d.split(engine.versions["all_event"], engine.blocks, engine.holdout_fold())
        defined = [e for e in train if engine.targets["loses_half_of_gap"].function(e["labels"]) is not None]
        timing, group = Counter(e["release_timing"] for e in defined), Counter(feat.sector_group(e) for e in defined)
        self.assertTrue(any(n < pr.CELL_MINIMUM for n in list(timing.values()) + list(group.values())))  # the case under test exists in this data
        falling = entry["test_events_that_would_fall_back_to_the_pooled_value"]
        self.assertEqual(falling["C2_timing"], sum(1 for e in test if timing.get(e["release_timing"], 0) < pr.CELL_MINIMUM))
        self.assertEqual(falling["C3_sector_group"], sum(1 for e in test if group.get(feat.sector_group(e), 0) < pr.CELL_MINIMUM))
        self.assertGreater(falling["C2_timing"] + falling["C3_sector_group"], 0)


class EvaluateAllTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = dataset(balanced)
        cls.looked = Looked(cls, cls.events, cls.spec)
        cls.first, cls.second = (p4.evaluate_all(cls.looked.engine, cls.looked.unsealed) for _ in range(2))  # twice, from the one look

    def test_it_covers_the_grid_and_caps_the_5pct_models_by_the_3pct_ones(self):
        out = self.first
        self.assertEqual(sorted(out), sorted((t, v) for t in p4.TARGETS for v in d.VERSIONS))
        self.assertEqual(sum(len(r["predictors"]) for r in out.values()), p4.EXPECTED_RECORDS)
        for version in d.VERSIONS:
            looser, tighter = out[("gap_ge_3pct", version)], out[("gap_ge_5pct", version)]
            if tighter["state"] == h.EVALUATED and looser["state"] == h.EVALUATED:
                for pid in p2.CAPPED:
                    cap = {r["event_id"]: r["p"] for r in looser["predictors"][pid]["rows"]}
                    for row in tighter["predictors"][pid]["rows"]:
                        self.assertLessEqual(row["p"], cap[row["event_id"]])

    def test_a_tighter_threshold_whose_looser_one_has_no_predictions_cannot_fit_its_capped_models(self):
        # 28 events have a gap of at least 3% (so the 3% target has only 2 negatives: COUNTS_ONLY) and 15 of them a gap of at least 5% (so the 5% target is scored)
        events, spec = dataset(lambda i: S.labels_from_returns(0.06, 0.13, 0.04, 0.02) if i < 15 else S.labels_from_returns(0.04, 0.05, 0.02, 0.03) if i < 28
                               else S.labels_from_returns(0.0, 0.01, -0.01, 0.0))
        looked = Looked(self, events, spec)
        out = p4.evaluate_all(looked.engine, looked.unsealed)
        looser, tighter = out[("gap_ge_3pct", "all_event")], out[("gap_ge_5pct", "all_event")]
        self.assertEqual((looser["state"], tighter["state"]), (d.COUNTS_ONLY, h.EVALUATED))
        for pid in p2.CAPPED:  # no 3% predictions to cap by: the capped models fail rather than going uncapped
            self.assertEqual(tighter["predictors"][pid]["state"], "MODEL_FIT_FAILED", pid)
            self.assertIn("monotone repair", tighter["predictors"][pid]["reason"])
            self.assertNotIn(pid, tighter["contrasts"])
        self.assertEqual({tighter["predictors"][pid]["state"] for pid in BINARY if pid not in p2.CAPPED}, {h.EVALUATED})

    def test_two_evaluations_of_the_same_events_are_identical(self):
        first, second = self.first, self.second
        self.assertEqual(digest(canonical({"%s|%s" % k: p2.plain(v) for k, v in first.items()})), digest(canonical({"%s|%s" % k: p2.plain(v) for k, v in second.items()})))
        self.assertEqual(self.looked.engine.gate.unsealed, 2 * 30)  # and no second access

    def test_the_c0_predictions_are_timed_at_the_regular_open_and_the_b_clock_ones_at_the_cutoff(self):
        looked, out = self.looked, self.first
        by_id = {e["event_id"]: e for e in looked.engine.events}
        for (target_id, version), result in out.items():
            records = looked.engine.holdout_prediction_records(result, WHEN)
            self.assertEqual(len(records), sum(run["predictions"] or 0 for run in result["predictors"].values()))
            for record in records:
                event = by_id[record["event_id"]]
                expected = S.CAL.bounds(event["reaction_session"])[0] if looked.engine.targets[target_id].clock == "C0" else event["cutoff"]
                self.assertEqual(record["prediction_time"], expected.strftime("%Y-%m-%dT%H:%M:%SZ"))
                self.assertEqual({k: record[k] for k in ("response_state", "opportunity_state", "confidence_tier")},
                                 {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"})
                self.assertEqual(record["fold"], HOLDOUT_FOLD)


class DescriptiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = dataset(balanced)
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        reg.init_logs(PROTOCOL, COMMIT, "2026-10-06T00:00:00Z", root / "e.jsonl", root / "h.jsonl")
        cls.engine = h.Harness.for_tests(cls.events, cls.spec, calendar=S.CAL, experiment_log=root / "e.jsonl", holdout_log=root / "h.jsonl", commit=lambda: COMMIT, clock=lambda: WHEN)
        with mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True):
            cls.unsealed = cls.engine.look("a test look")
        cls.report = p4.descriptive_report(cls.engine, cls.unsealed)

    def test_it_covers_all_19_targets_in_both_versions_and_the_five_regression_labels(self):
        report = self.report
        binary = [t for t in self.engine.targets.values() if t.kind == "binary"]
        self.assertEqual(len(self.engine.targets), 19)
        self.assertEqual(sorted(report["targets"]), sorted(t.id for t in binary))
        for row in report["targets"].values():
            self.assertEqual({"all_event", "clean_window"} <= set(row), True)
        self.assertEqual(sorted(report["regression_labels"]["all_event"]), sorted(ev.REGRESSION_LABELS))
        self.assertEqual(len(report["blocks"]["blocks"]), 5)

    def test_the_counts_are_the_counts_of_all_the_events_with_block_5_included(self):
        everything = sorted([e for e in self.engine.versions["all_event"] if not d.is_sealed(e)] + list(self.unsealed["all_event"]), key=fp.event_order)
        self.assertEqual(len(everything), len(self.events))
        for target_id in ("gap_ge_3pct", "extension_after_open_ge_5pct", "loses_half_of_gap", "full_gap_fill"):
            target = self.engine.targets[target_id]
            values = [v for v in (target.function(e["labels"]) for e in everything) if v is not None]
            row = self.report["targets"][target_id]["all_event"]
            self.assertEqual((row["n_defined"], row["positives"], row["negatives"]), (len(values), sum(values), len(values) - sum(values)))
            self.assertEqual(sum(row["defined_by_block"]), row["n_defined"])
            self.assertEqual(len(row["defined_by_block"]), 5)
            self.assertEqual(sum(row["positives_by_block"]), row["positives"])
            low, high = fp.wilson(row["positives"], row["n_defined"], 0.95)
            self.assertAlmostEqual(row["wilson_low"], round(low, 6), places=6)
            self.assertAlmostEqual(row["wilson_high"], round(high, 6), places=6)

    def test_block_5_is_in_the_counts_not_left_out(self):
        row = self.report["targets"]["gap_ge_3pct"]["all_event"]
        self.assertEqual(row["positives_by_block"][4], 15)  # the 15 big gaps of the holdout block
        self.assertEqual(row["defined_by_block"][4], 30)

    def test_the_report_says_what_the_protocol_says_about_block_5_and_is_json(self):
        json.dumps(self.report, allow_nan=False)
        self.assertEqual(self.report["kind"], "m4_phase4_descriptive_report")
        self.assertIn("visible in the scoping evidence", self.report["block_5_counts_note"])
        self.assertIn("confounded", self.report["selection_regime"])
        self.assertEqual(self.report["holdout"]["unsealed_loads"], 60)


class SignCheckTests(unittest.TestCase):
    def test_same_opposite_zero_and_missing(self):
        development = {"estimate": -0.01, "role": "confirmatory", "from": "reports/x.json"}
        self.assertTrue(p4.sign_check(-0.2, development)["same_sign"])
        self.assertFalse(p4.sign_check(0.2, development)["same_sign"])
        zero = p4.sign_check(0.0, development)
        self.assertEqual((zero["holdout_sign"], zero["same_sign"]), (0, False))
        self.assertFalse(p4.sign_check(0.0, {"estimate": 0.0, "role": "confirmatory", "from": "x"})["same_sign"])  # two zeros have no sign to share
        missing = p4.sign_check(0.2, None)
        self.assertEqual(missing["comparable"], False)
        self.assertIn("INSUFFICIENT_DATA", missing["why"])
        self.assertEqual(p4.sign_check(0.2, {"estimate": 0.05, "role": "companion_of_the_confirmatory_contrast", "from": "x"})["development_role"], "companion_of_the_confirmatory_contrast")

    def test_the_development_estimates_are_those_in_the_committed_results(self):
        estimates = p4.development_estimates()
        self.assertEqual(len(estimates), 10)
        self.assertIsNone(estimates[("loses_half_of_gap", "clean_window")])
        confirmatory = estimates[("extension_after_open_ge_5pct", "clean_window")]
        self.assertEqual(confirmatory["role"], "confirmatory")
        self.assertAlmostEqual(confirmatory["estimate"], 0.028344791358834873)
        self.assertEqual(estimates[("loses_half_of_gap", "all_event")]["role"], "exploratory")
        self.assertEqual(estimates[("gap_ge_3pct", "all_event")]["role"], "companion_of_the_confirmatory_contrast")

    def test_a_development_result_that_does_not_match_its_completion_record_stops_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "reports").mkdir()
            for name in ("m4-phase2-results-2026-10-07.json", "m4-phase2-completion-2026-10-07.json", "m4-phase3-results-2026-10-07.json", "m4-phase3-completion-2026-10-07.json"):
                shutil.copy(ROOT / "reports" / name, root / "reports" / name)
            self.assertEqual(len(p4.development_estimates(root)), 10)
            path = root / "reports" / "m4-phase3-results-2026-10-07.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["evaluations"]["loses_half_of_gap"]["all_event"]["contrasts"]["M2_logistic"]["estimate"] = -1.0
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "does not match the hash its completion record holds"):
                p4.development_estimates(root)


DEVELOPMENT_FILES = ("m4-phase2-results-2026-10-07.json", "m4-phase2-completion-2026-10-07.json", "m4-phase3-results-2026-10-07.json", "m4-phase3-completion-2026-10-07.json")


def add_experiments(path, count, fold="dev_test_block_3"):
    """`count` experiment records on the primary targets, standing in for the ones Phases 2 and 3 left in the log."""
    for n in range(count):
        reg.append(path, "experiments", reg.experiment_record(PROTOCOL, COMMIT, WHEN, n + 1, p4.TARGETS[n % len(p4.TARGETS)], "B", "C1_pooled_rate", "all_event", fold, [], [],
                                                               "m4-features-v1", {}, [], {}, "none", {}, "EVALUATED"), PROTOCOL)


def prepare(owner, events, spec, earlier=p4.EXPERIMENTS_BEFORE - 1):
    """A temporary root holding the development results Phase 4 compares with, logs shaped as Phase 3 leaves them (`earlier` experiment records after the genesis), and a
    synthetic harness over them. Returns (root, experiment log, holdout log, harness)."""
    directory = tempfile.TemporaryDirectory()
    (owner.addClassCleanup if isinstance(owner, type) else owner.addCleanup)(directory.cleanup)
    root = Path(directory.name)
    (root / "reports").mkdir()
    for name in DEVELOPMENT_FILES:
        shutil.copy(ROOT / "reports" / name, root / "reports" / name)
    experiments, holdout = root / "reports" / "e.jsonl", root / "reports" / "h.jsonl"
    reg.init_logs(PROTOCOL, COMMIT, "2026-10-06T00:00:00Z", experiments, holdout)
    add_experiments(experiments, earlier)
    engine = h.Harness.for_tests(events, spec, calendar=S.CAL, experiment_log=experiments, holdout_log=holdout, commit=lambda: COMMIT, clock=lambda: WHEN)
    return root, experiments, holdout, engine


def go(engine, root, tripwire=True, evaluation=True, commit_state=(COMMIT, True)):
    with mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", tripwire), mock.patch.object(h, "ALLOW_REAL_EVALUATION", evaluation):
        return p4.run(engine, "2026-10-07", root=root, commit_state=commit_state)


def outputs(root):
    return sorted(p.name for p in (root / "reports").glob("m4-phase4-*"))


class OneLookTests(unittest.TestCase):
    """One run of p4.run() on balanced synthetic data, shared by the tests that read what it wrote."""

    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = dataset(balanced)
        cls.root, cls.experiments, cls.holdout, cls.engine = prepare(cls, cls.events, cls.spec)
        cls.summary = go(cls.engine, cls.root)
        cls.results = json.loads((cls.root / "reports" / "m4-phase4-holdout-results-2026-10-07.json").read_text(encoding="utf-8"))

    def test_the_one_look_logs_one_access_evaluates_the_grid_and_writes_the_outputs(self):
        self.assertEqual((self.summary["state"], self.summary["accesses"], self.summary["experiment_records"]), ("LOOKED", 1, 58))
        accesses = [r for r, _ in reg.read(self.holdout)]
        self.assertEqual(len(accesses), 2)
        self.assertEqual((accesses[1]["access_number"], accesses[1]["reason"], accesses[1]["harness_commit"]), (1, p4.LOOK_REASON, COMMIT))
        self.assertEqual(accesses[1]["events_read"], sorted(e["event_id"] for e in S.holdout_events(self.events)))
        self.assertEqual(self.engine.gate.unsealed, 2 * 30)  # every event once per version: one look
        self.assertEqual(reg.verify_chain(self.holdout, "holdout_access", PROTOCOL)["records"], 2)
        log = [r for r, _ in reg.read(self.experiments)]
        self.assertEqual(reg.verify_chain(self.experiments, "experiments", PROTOCOL)["records"], p4.EXPERIMENTS_BEFORE + 58)
        added = log[p4.EXPERIMENTS_BEFORE:]
        self.assertEqual({r["fold"] for r in added}, {HOLDOUT_FOLD})
        self.assertEqual({r["harness_commit"] for r in added}, {COMMIT})
        self.assertEqual([r["experiment_id"] for r in added][:2], ["m4-experiment-%05d" % p4.EXPERIMENTS_BEFORE, "m4-experiment-%05d" % (p4.EXPERIMENTS_BEFORE + 1)])
        self.assertEqual({r["state"] for r in added if r["version"] == "all_event"}, {"EVALUATED"})  # the clean-window cells depend on how many events the caveats mask
        self.assertLessEqual({r["state"] for r in added}, {"EVALUATED", "COUNTS_ONLY"})
        self.assertEqual({r["version"] for r in added}, set(d.VERSIONS))
        self.assertEqual(sorted(Counter(r["target_id"] for r in added).items()), sorted([("gap_ge_3pct", 12), ("gap_ge_5pct", 12), ("extension_after_open_ge_5pct", 12),
                                                                                            ("loses_half_of_gap", 12), ("day1_close_return", 10)]))
        self.assertEqual(outputs(self.root), ["m4-phase4-descriptive-2026-10-07.json", "m4-phase4-holdout-predictions-2026-10-07.jsonl", "m4-phase4-holdout-results-2026-10-07.json"])
        results = self.results
        self.assertEqual((results["kind"], results["the_look"]["accesses"], results["the_look"]["technical_reruns"]), ("m4_phase4_holdout_results", 1, 0))
        self.assertEqual(sorted(results["evaluations"]), sorted(p4.TARGETS))
        self.assertEqual(results["scope"]["fold"], HOLDOUT_FOLD)
        self.assertIn("the holdout alone never creates one", " ".join(results["not_a_claim"]))
        self.assertEqual(results["holdout"]["unsealed_loads"], 60)
        self.assertEqual(results["states"]["gap_ge_3pct"]["all_event"], h.EVALUATED)
        self.assertEqual(results["selection_regime"], PROTOCOL["holdout"]["selection_regime"])  # every holdout result carries the protocol's statement
        self.assertEqual(results["what_it_is_for"], PROTOCOL["holdout"]["what_it_is_for"])

    def test_the_sign_check_is_attached_to_the_confirmatory_contrast_of_an_evaluated_target_and_to_no_other(self):
        checked = 0
        for target_id, versions in self.results["evaluations"].items():
            for version, result in versions.items():
                model = h.CONFIRMATORY[result["kind"]]
                contrast = result["contrasts"].get(model)
                if contrast is not None:
                    comparison = contrast["against_the_development_result"]
                    self.assertEqual(comparison["holdout_estimate"], contrast["estimate"])
                    self.assertIn(comparison["comparable"], (True, False))
                    checked += 1
                for pid, other in result["contrasts"].items():
                    if pid != model:
                        self.assertNotIn("against_the_development_result", other)
                for other in result["other_contrasts"].values():
                    self.assertNotIn("against_the_development_result", other)
        self.assertGreater(checked, 0)

    def test_a_second_run_is_refused_and_changes_nothing(self):
        before = (len(reg.read(self.holdout)), len(reg.read(self.experiments)), self.engine.gate.unsealed, outputs(self.root))
        with self.assertRaisesRegex(DataError, "the holdout is looked at once"):
            go(self.engine, self.root)
        self.assertEqual((len(reg.read(self.holdout)), len(reg.read(self.experiments)), self.engine.gate.unsealed, outputs(self.root)), before)


class RunTests(unittest.TestCase):
    """p4.run() in a temporary directory with its own logs shaped as Phase 3 leaves them: a counts-only grid, its refusals, and a failure after the look."""

    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = dataset(balanced)

    def fresh(self, events=None, spec=None, earlier=p4.EXPERIMENTS_BEFORE - 1):
        self.root, self.experiments, self.holdout, self.engine = prepare(self, events or self.events, spec or self.spec, earlier)

    def test_a_target_version_that_is_counts_only_still_has_a_record_for_every_predictor(self):
        self.fresh(*dataset(sparse))
        summary = go(self.engine, self.root)
        self.assertEqual(summary["experiment_records"], 58)
        states = summary["states"]
        self.assertEqual({states[t]["all_event"] for t in ("gap_ge_3pct", "gap_ge_5pct", "extension_after_open_ge_5pct", "loses_half_of_gap")}, {d.COUNTS_ONLY})
        self.assertEqual(states["day1_close_return"]["all_event"], h.EVALUATED)
        added = [r for r, _ in reg.read(self.experiments)][p4.EXPERIMENTS_BEFORE:]
        counts_only = [r for r in added if r["state"] == "COUNTS_ONLY"]
        self.assertGreaterEqual(len(counts_only), 4 * 6)
        for record in counts_only:
            self.assertEqual(record["predictions_sha256"], digest(canonical([])))
            self.assertEqual(record["metrics_with_counts"]["holdout_state"], "COUNTS_ONLY")
            self.assertIn("positives", record["metrics_with_counts"]["test_counts"])
        lines = (self.root / "reports" / "m4-phase4-holdout-predictions-2026-10-07.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines and all(json.loads(line)["target_id"] == "day1_close_return" for line in lines))  # only the evaluated cells predict

    def test_every_refusal_happens_before_any_block_5_outcome_is_read(self):
        self.fresh()
        for label, kwargs, message in (("the tripwire is off", {"tripwire": False}, "ALLOW_HOLDOUT_LOOK is False"),
                                       ("real evaluation is off", {"evaluation": False}, "ALLOW_REAL_EVALUATION is False"),
                                       ("the tree is dirty", {"commit_state": (COMMIT, False)}, "uncommitted changes")):
            with self.assertRaisesRegex(Exception, message, msg=label):
                go(self.engine, self.root, **kwargs)
            self.assertEqual((self.engine.gate.unsealed, len(reg.read(self.holdout)), outputs(self.root)), (0, 1, []), label)

    def test_it_refuses_logs_that_are_not_as_phase_3_left_them(self):
        self.fresh(earlier=p4.EXPERIMENTS_BEFORE - 2)  # one record short
        with self.assertRaisesRegex(DataError, "logs are not as Phase 4 expects"):
            go(self.engine, self.root)
        add_experiments(self.experiments, 1)  # now exactly right
        reg.append(self.holdout, "holdout_access", reg.holdout_access_record(PROTOCOL, COMMIT, WHEN, 1, "an earlier look", ["x"]), PROTOCOL)
        with self.assertRaisesRegex(DataError, "logs are not as Phase 4 expects"):  # a second access is refused: a technical rerun needs a code change of its own
            go(self.engine, self.root)
        self.assertEqual((self.engine.gate.unsealed, outputs(self.root)), (0, []))

    def test_it_refuses_a_log_that_already_holds_holdout_experiments(self):
        self.fresh(earlier=0)
        add_experiments(self.experiments, p4.EXPERIMENTS_BEFORE - 1, fold=HOLDOUT_FOLD)
        with self.assertRaisesRegex(DataError, "already holds holdout experiments"):
            go(self.engine, self.root)
        self.assertEqual(self.engine.gate.unsealed, 0)

    def test_it_refuses_when_the_development_result_it_compares_with_is_altered_while_the_holdout_is_still_sealed(self):
        self.fresh()
        path = self.root / "reports" / "m4-phase2-results-2026-10-07.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["statuses"]["gap_ge_3pct"]["M2_logistic"] = "DISTINGUISHABLE_BETTER"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(DataError, "does not match the hash its completion record holds"):
            go(self.engine, self.root)
        self.assertEqual((self.engine.gate.unsealed, len(reg.read(self.holdout)), outputs(self.root)), (0, 1, []))

    def test_a_failure_after_the_look_leaves_the_access_on_the_record_and_writes_nothing(self):
        self.fresh()
        with mock.patch.object(p4, "evaluate_all", side_effect=RuntimeError("a technical failure")):
            with self.assertRaisesRegex(RuntimeError, "a technical failure"):
                go(self.engine, self.root)
        self.assertEqual(len(reg.read(self.holdout)), 2)  # the access is logged: it cannot be undone
        self.assertEqual((len(reg.read(self.experiments)), outputs(self.root)), (p4.EXPERIMENTS_BEFORE, []))
        with self.assertRaisesRegex(DataError, "logs are not as Phase 4 expects"):  # and there is no automatic retry
            go(self.engine, self.root)

    def test_a_value_that_cannot_be_written_stops_the_run_before_any_experiment_is_recorded(self):
        self.fresh()
        real = p4.descriptive_report

        def with_a_nan(harness, unsealed):
            report = real(harness, unsealed)
            report["targets"]["gap_ge_3pct"]["all_event"]["base_rate"] = float("nan")
            return report
        with mock.patch.object(p4, "descriptive_report", with_a_nan):
            with self.assertRaises(ValueError):
                go(self.engine, self.root)
        self.assertEqual(len(reg.read(self.holdout)), 2)  # the look happened and stays on the record...
        self.assertEqual((len(reg.read(self.experiments)), outputs(self.root)), (p4.EXPERIMENTS_BEFORE, []))  # ...but nothing was recorded or written half-way


class ProtocolShapeTests(unittest.TestCase):
    def test_the_grid_the_runner_covers_is_the_protocols_five_primaries_and_the_58_cells_follow(self):
        primaries = [t["id"] for t in PROTOCOL["targets"]["primary"]]
        self.assertEqual(sorted(p4.TARGETS), sorted(primaries))
        self.assertEqual(p4.TARGETS, p2.TARGETS + p3.TARGETS)
        kinds = [t["kind"] for t in PROTOCOL["targets"]["primary"]]
        self.assertEqual((kinds.count("binary"), kinds.count("regression")), (4, 1))
        self.assertEqual(p4.EXPECTED_RECORDS, 4 * len(BINARY) * 2 + 1 * len(REGRESSION) * 2)
        self.assertEqual(p4.EXPERIMENTS_BEFORE, 1 + 2 * (18 + 18 + 15) + 2 * (18 + 18))

    def test_the_look_names_itself_as_the_one_look_in_the_words_the_older_safeguard_recognizes(self):
        self.assertTrue(p4.LOOK_REASON.startswith("Milestone 4 Phase 4: the one look at the final holdout"))
        self.assertIn("block 5", p4.LOOK_REASON)
        self.assertIn("protocol version 1", p4.LOOK_REASON)

    def test_no_code_but_the_harness_unseals_and_the_runner_looks_exactly_once(self):
        source = (ROOT / "nre" / "m4_phase4.py").read_text(encoding="utf-8")
        self.assertNotIn(".unseal(", source)
        self.assertEqual(source.count(".look("), 1)
        body = source[source.index("def run("):]
        self.assertLess(body.index("development_estimates(root)"), body.index(".look("))  # what can stop the run does so while the holdout is sealed
        self.assertLess(body.index("reg.verify_chain"), body.index(".look("))
        for path in sorted((ROOT / "nre").glob("m4_*.py")):
            if path.name not in ("m4_phase4.py", "m4_harness.py"):
                self.assertNotIn(".look(", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
