"""The Milestone 4 harness: the eight leakage and integrity tests the frozen protocol requires, and the harness's behaviour on synthetic and on real inputs.

Nothing here evaluates a predictor on a real event or reads a holdout outcome: the real inputs are only verified, planned and dry-run.
"""
import contextlib
import copy
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_support as S  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_features as feat  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_metrics as m  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402
from nre import m4_scoping_evidence as ev  # noqa: E402
from nre.core import DataError, canonical, digest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
FREEZE = pr.load_json(pr.FREEZE_PATH)
PRIMARY = ("gap_ge_3pct", "gap_ge_5pct", "day1_close_return", "extension_after_open_ge_5pct", "loses_half_of_gap")
LATE = {"day1_open_return": 9.9}


def harness(events=None, spec=None, **options):
    if events is None:
        events, spec = S.dataset()
    return h.Harness.for_tests(events, spec, calendar=S.CAL, **options)


class Oracle(h.Predictor):
    """A test double that knows the answers and so beats the base rate: it is given the positives, never the harness's labels."""
    id, kind = "TEST_ORACLE", "binary"

    def __init__(self, positives, strength=0.4):
        self.positives, self.strength = positives, strength

    def fit(self, train, target):
        return {"strength": self.strength}

    def predict(self, model, view):
        return 0.5 + (model["strength"] if view["event_id"] in self.positives else -model["strength"])


class Spy(h.Predictor):
    """Records what it is shown: the training events (with labels) at fit, and the views at predict."""
    id, kind = "TEST_SPY", "binary"

    def __init__(self):
        self.trained, self.views = [], []

    def fit(self, train, target):
        self.trained.append([e["event_id"] for e in train])
        return {"n": len(train)}

    def predict(self, model, view):
        self.views.append(view)
        return 0.3


class Failing(h.Predictor):
    id, kind = "TEST_FAILING", "binary"

    def fit(self, train, target):
        raise h.Abstain("MODEL_FIT_FAILED", "did not converge in 100 iterations")

    def predict(self, model, view):
        raise AssertionError("a model that failed to fit must not predict")


def positives_of(events, target_id, blocks=(3, 4)):
    block = ev.assign_blocks(events)
    target = d.targets(PROTOCOL)[target_id]
    return {e["event_id"] for e in events if block[e["event_id"]] in blocks and target.function(e["labels"])}


def poison(events, from_block):
    """The events with the labels of every event in a block at or after `from_block` reversed within its block, so that each such event carries another's
    outcomes while every block's counts, and so every threshold, stay as they were."""
    blocks = ev.assign_blocks(events)
    out = copy.deepcopy(events)
    for block in sorted({b for b in blocks.values() if b >= from_block}):
        members = [e for e in out if blocks[e["event_id"]] == block]
        for event, labels in zip(members, [e["labels"] for e in reversed(members)]):
            event["labels"] = labels
    return out


def canonical_digest(value):
    return digest(canonical(value))


class RequiredTests(unittest.TestCase):
    """One test for each of the eight requirements in config/m4-protocol.json, required_leakage_and_integrity_tests."""

    def test_the_protocol_requires_exactly_these_eight_tests(self):
        names = [item.split(":")[0] for item in PROTOCOL["required_leakage_and_integrity_tests"]]
        self.assertEqual(names, ["Label maturity", "Injected future", "History features", "Holdout sealing", "Protocol integrity", "Determinism", "Clusters", "Abstention"])

    def test_1_label_maturity_is_asserted_for_every_fold_and_target_before_anything_is_fitted(self):
        events, spec = S.dataset()
        late = copy.deepcopy(events)
        block = ev.assign_blocks(late)
        victim = next(e for e in late if block[e["event_id"]] == 2)
        first_test = min(e["cutoff"] for e in late if block[e["event_id"]] == 3)
        victim["available_at"]["day1_close_return"] = first_test + timedelta(hours=1)
        spy = Spy()
        with self.assertRaises(d.MaturityViolation):
            harness(late, spec).evaluate("gap_ge_3pct", "all_event", [spy])
        self.assertEqual(spy.trained, [], "nothing may be fitted once a maturity check has failed")
        other = copy.deepcopy(events)
        next(e for e in other if block[e["event_id"]] == 2)["available_at"]["session_20_close_return"] = first_test + timedelta(days=2)  # not this target's label...
        with self.assertRaises(d.MaturityViolation):  # ...but the longest label is checked for every target
            harness(other, spec).evaluate("gap_ge_3pct", "all_event", [Spy()])
        ok = harness(events, spec)
        for target_id in PRIMARY:
            for version in d.VERSIONS:
                folds = ok.fold_report(target_id, version)["folds"]
                self.assertTrue(all(f["smallest_label_slack_days"]["all_sixteen_labels"] > 0 for f in folds.values()), (target_id, version))

    def test_1_label_maturity_holds_on_the_real_folds_with_the_slack_the_protocol_states(self):
        real = h.Harness.from_repository()
        plan = real.plan()
        slacks = [f["smallest_label_slack_days"]["all_sixteen_labels"] for t in plan["targets"].values() if t["role"] == "primary" for v in d.VERSIONS
                  for f in t[v]["folds"].values()]
        self.assertTrue(slacks and min(slacks) > 9)
        self.assertEqual([b["needs_purge_for_the_20_session_horizon"] for b in plan["blocks"]["boundaries"]], [False] * 4)

    def test_2_injected_future_changing_later_labels_changes_no_earlier_prediction(self):
        events, spec = S.dataset()
        for target_id in ("gap_ge_3pct", "extension_after_open_ge_5pct", "day1_close_return"):
            base = harness(events, spec).evaluate(target_id, "all_event")
            run = base["predictors"][h.COMPARATOR[base["kind"]]]
            for fold_name, from_block in (("dev_test_block_3", 3), ("dev_test_block_4", 4)):
                changed = harness(poison(events, from_block), spec).evaluate(target_id, "all_event")
                other = changed["predictors"][h.COMPARATOR[base["kind"]]]
                self.assertEqual(changed["pooled_development_test"]["state"], d.EVALUABLE, "the future was changed without changing any threshold")
                self.assertEqual([r["p"] for r in run["folds"][fold_name]["rows"]], [r["p"] for r in other["folds"][fold_name]["rows"]], (target_id, fold_name))
                self.assertEqual(run["folds"][fold_name]["model"], other["folds"][fold_name]["model"])
                self.assertNotEqual([r["y"] for r in run["folds"][fold_name]["rows"]], [r["y"] for r in other["folds"][fold_name]["rows"]],
                                    "the change must have altered the outcomes whose predictions are being compared")

    def test_2_injected_future_changing_later_labels_changes_no_earlier_history_feature(self):
        events, _ = S.dataset()
        target = d.targets(PROTOCOL)["gap_ge_3pct"]
        for event in events[::5]:
            before = feat.issuer_history_rate(event, [e for e in events if e["event_id"] != event["event_id"]], target)
            changed = S.with_labels_changed(events, lambda e: e["labels"].update({"gap_ge_3pct": {"value": not e["labels"]["gap_ge_3pct"]["value"], "reason": None}})
                                            if e["reaction_session"] >= event["reaction_session"] else None)
            after = feat.issuer_history_rate(event, [e for e in changed if e["event_id"] != event["event_id"]], target)
            self.assertEqual(before, after, event["event_id"])

    def test_3_history_features_use_only_training_events_whose_labels_were_available_at_the_cutoff(self):
        events, spec = S.dataset()
        run = harness(events, spec)
        for target in d.targets(PROTOCOL).values():
            for fold in run.folds:
                train, test = d.split(run.versions["all_event"], run.blocks, fold)
                train_ids, test_ids = {e["event_id"] for e in train}, {e["event_id"] for e in test}
                for event in train + test:
                    used = feat.history(event, train, target)
                    self.assertFalse({e["event_id"] for e in used} & test_ids, (target.id, fold.name, event["event_id"]))
                    for e in used:
                        self.assertIn(e["event_id"], train_ids)
                        self.assertLess(e["reaction_session"], event["reaction_session"])
                        self.assertTrue(all(e["available_at"][name] <= event["cutoff"] for name in target.source_labels))

    def test_3_history_features_of_the_real_events_use_no_test_block_event(self):
        inputs = d.load_inputs(PROTOCOL)
        events, blocks = inputs["events"], inputs["blocks"]
        for fold in d.folds(PROTOCOL):
            train, test = d.split(events, blocks, fold)
            for target in d.targets(PROTOCOL).values():
                for event in train + test:
                    for used in feat.history(event, train, target):
                        self.assertIn(blocks[used["event_id"]], fold.train_blocks)
                        self.assertLess(used["reaction_session"], event["reaction_session"])
                        self.assertTrue(all(used["available_at"][name] <= event["cutoff"] for name in target.source_labels))
        self.assertEqual(inputs["gate"].denied, [])  # only identities, times and training labels were touched

    def test_3_a_test_events_features_do_not_change_when_the_test_blocks_labels_do(self):
        events, spec = S.dataset()
        target = d.targets(PROTOCOL)["gap_ge_3pct"]
        run = harness(events, spec)
        changed = harness(poison(events, 3), spec)
        fold = run.folds[0]
        train, test = d.split(run.versions["all_event"], run.blocks, fold)
        train2, test2 = d.split(changed.versions["all_event"], changed.blocks, fold)
        for a, b in zip(test, test2):
            self.assertEqual(feat.issuer_history_rate(a, train, target), feat.issuer_history_rate(b, train2, target))

    def test_4_holdout_sealing_every_read_of_a_block_5_outcome_raises_and_none_happens_in_a_run(self):
        events, spec = S.dataset()
        run = harness(events, spec)
        for target_id in PRIMARY:
            for version in d.VERSIONS:
                run.evaluate(target_id, version)
        run.plan()
        run.dry_run()
        self.assertEqual((run.gate.denied, run.gate.unsealed), ([], 0))
        sealed = [e for e in run.events if d.is_sealed(e)]
        self.assertEqual(len(sealed), S.SIZES[4])
        with self.assertRaises(d.HoldoutSealed):
            sealed[0]["labels"]["gap_ge_3pct"]
        self.assertEqual(len(run.gate.denied), 1)

    def test_4_holdout_sealing_the_only_way_to_the_labels_is_a_logged_look_that_is_off(self):
        self.assertIs(h.ALLOW_HOLDOUT_LOOK, False)
        self.assertEqual(h.REAL_EVALUATION_TARGETS, ("gap_ge_3pct", "gap_ge_5pct", "day1_close_return", "extension_after_open_ge_5pct", "loses_half_of_gap"))  # the five primaries; the look is separate
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "holdout.jsonl"
            run = harness(holdout_log=log, commit=lambda: "c" * 40, clock=lambda: "2026-10-06T00:00:00Z")
            with self.assertRaises(d.HoldoutNotAuthorized):
                run.look("a trial")
            self.assertFalse(log.exists())
            self.assertEqual((run.gate.unsealed, run.gate.denied), (0, []))

    def test_4_holdout_sealing_a_look_is_logged_before_any_label_is_read_and_each_look_is_counted(self):
        events, spec = S.dataset()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "holdout.jsonl"
            reg.init_logs(PROTOCOL, "c" * 40, "2026-10-06T00:00:00Z", Path(directory) / "experiments.jsonl", log)
            run = harness(events, spec, holdout_log=log, commit=lambda: "c" * 40, clock=lambda: "2026-10-06T01:00:00Z")
            seen = []
            original = run.gate._loader

            def loader(event_id):
                seen.append((event_id, len(reg.read(log))))  # how many records the log held when this event's labels were read
                return original(event_id)
            run.gate._loader = loader
            with mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True):
                first = run.look("the one look")
                second = run.look("a technical rerun")
            self.assertTrue(seen and all(count >= 2 for _, count in seen), "the access record must already be in the log when labels are read")
            self.assertEqual({v for _, v in seen[:S.SIZES[4]]}, {2})
            records = [r for r, _ in reg.read(log)]
            self.assertEqual([r.get("access_number") for r in records], [0, 1, 2])
            self.assertEqual(records[1]["events_read"], sorted(e["event_id"] for e in events if ev.assign_blocks(events)[e["event_id"]] == 5))
            self.assertEqual((records[1]["reason"], records[2]["reason"]), ("the one look", "a technical rerun"))
            self.assertEqual(reg.verify_chain(log, "holdout_access", PROTOCOL)["records"], 3)
            self.assertEqual(set(first), set(d.VERSIONS))
            for version, unsealed in first.items():
                self.assertEqual(len(unsealed), S.SIZES[4])
                self.assertTrue(all(not d.is_sealed(e) for e in unsealed))
            self.assertEqual(second["all_event"][0]["labels"], first["all_event"][0]["labels"])

    def test_4_holdout_sealing_if_the_access_cannot_be_logged_nothing_is_read(self):
        events, spec = S.dataset()
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not_a_directory"
            blocker.write_text("x", encoding="utf-8")
            run = harness(events, spec, holdout_log=blocker / "holdout.jsonl", commit=lambda: "c" * 40)
            with mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True):
                with self.assertRaises(Exception):
                    run.look("cannot be logged")
            self.assertEqual(run.gate.unsealed, 0)

    def test_4_holdout_sealing_no_other_code_path_unseals(self):
        calls = []
        for path in sorted((ROOT / "nre").glob("m4_*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if ".unseal(" in line and "def unseal" not in line and not line.lstrip().startswith(("#", '"""')):
                    calls.append((path.name, number))
        self.assertEqual([name for name, _ in calls], ["m4_harness.py"])
        look = (ROOT / "nre" / "m4_harness.py").read_text(encoding="utf-8")
        body = look[look.index("    def look("):]
        self.assertIn(".unseal(", body[:body.index("\ndef write_report")])
        self.assertLess(body.index("reg.append("), body.index(".unseal("))

    def test_4_holdout_sealing_the_real_inputs_never_open_a_holdout_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("config", "reports"):
                shutil.copytree(ROOT / name, root / name)
            original = h.Harness.from_repository().dry_run()
            spec = pr.load_json(root / PROTOCOL["inputs"]["events_spec"]["path"])
            real = h.Harness.from_repository()
            held = {e["event_id"] for e in real.events if d.is_sealed(e)}
            for entry in spec["events"]:
                if entry["event_id"] in held:
                    (root / entry["recorded_result"]["recorded_in"]).write_text("destroyed", encoding="utf-8")
            destroyed = h.Harness.from_repository(root).dry_run()
        self.assertEqual(canonical_digest(destroyed), canonical_digest(original))
        self.assertEqual((original["holdout"]["denied_reads"], original["holdout"]["unsealed_loads"]), (0, 0))

    def test_5_protocol_integrity_every_run_refuses_on_any_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("config", "reports"):
                shutil.copytree(ROOT / name, root / name)
            h.Harness.from_repository(root)  # the untouched copy is accepted
            freeze = "reports/m4-protocol-freeze-2026-10-06.json"
            tampering = {  # each file the protocol hashes, changed by an extra key (it parses as before; only its hash differs)
                "protocol": ("config/m4-protocol.json", lambda data: data.update(tampered=True)),
                "events spec": (PROTOCOL["inputs"]["events_spec"]["path"], lambda data: data.update(tampered=True)),
                "calendar": (PROTOCOL["inputs"]["calendar"]["path"], lambda data: data.update(tampered=True)),
                "fingerprint policy": (PROTOCOL["inputs"]["fingerprint_policy"]["path"], lambda data: data.update(tampered=True)),
                "sector map": (PROTOCOL["inputs"]["sector_map"]["path"], lambda data: data.update(tampered=True)),
                "scoping evidence": (PROTOCOL["inputs"]["scoping_evidence"]["path"], lambda data: data.update(tampered=True)),
                "caveat check": (PROTOCOL["inputs"]["caveat_check"]["path"], lambda data: data.update(tampered=True)),
                # the freeze record is what holds the hashes, so it is tampered with by changing one of them
                "the protocol hash in the freeze record": (freeze, lambda data: data["protocol"].update(canonical_sha256="0" * 64)),
                "a pinned input hash in the freeze record": (freeze, lambda data: data["inputs_pinned"]["calendar"].update(canonical_sha256="0" * 64)),
            }
            for label, (rel, change) in tampering.items():
                path = root / rel
                original = path.read_text(encoding="utf-8")
                try:
                    data = json.loads(original)
                    change(data)
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(DataError, msg=label):
                        h.Harness.from_repository(root)
                finally:
                    path.write_text(original, encoding="utf-8")
            h.Harness.from_repository(root)

    def test_5_protocol_integrity_the_failing_check_is_named(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("config", "reports"):
                shutil.copytree(ROOT / name, root / name)
            path = root / "config" / "m4-protocol.json"
            text = path.read_text(encoding="utf-8")
            self.assertIn("5000 replicates", text)
            path.write_text(text.replace("5000 replicates", "4000 replicates"), encoding="utf-8")
            with self.assertRaises(pr.ProtocolMismatch) as caught:
                h.Harness.from_repository(root)
            self.assertIn("protocol_hash", str(caught.exception))
            self.assertIn("constants_match_the_protocol_text", str(caught.exception))

    def test_5_protocol_integrity_a_changed_constant_in_the_code_is_caught_against_the_protocol_text(self):
        self.assertEqual(pr.constants_check(PROTOCOL), [])
        for name, value in (("BOOTSTRAP_REPLICATES", 4000), ("MIN_POSITIVES", 9), ("MIN_NEGATIVES", 9), ("PRECISION_K_POOLED", (10, 25)), ("PRECISION_K_FOLD", (5, 11)),
                            ("RATE_CLIP", (0.02, 0.98)), ("LOG_LOSS_CLIP", 1e-5), ("MIN_TRAIN_EVENTS", 30), ("MIN_REGRESSION_TEST_EVENTS", 15), ("RANDOM_RANKINGS", 500),
                            ("PRIOR_STRENGTH", 5), ("GROUP_PRIOR_DEFAULT", 0.4), ("GROUP_PRIOR_MINIMUM", 8), ("CELL_MINIMUM", 5), ("MAX_RELIABILITY_BINS", 5),
                            ("MIN_PER_BIN", 8), ("QUANTILE_LEVELS", (0.05, 0.5, 0.95)), ("CLAIM_LEVEL", 0.95), ("REPORTING_LEVEL", 0.9)):
            with mock.patch.object(pr, name, value):
                self.assertTrue(pr.constants_check(PROTOCOL), name)
        self.assertEqual(pr.constants_check(PROTOCOL), [])  # and the patches are gone
        for name, path, pattern, expected in pr.constant_readings():  # every reading finds its numbers in the protocol's own words
            node = PROTOCOL
            for key in path:
                node = node[key]
            found = re.search(pattern, node if isinstance(node, str) else str(node), re.DOTALL)
            self.assertTrue(found, name)
            self.assertEqual(tuple(float(g) for g in found.groups()), tuple(float(x) for x in expected), name)

    def test_5_protocol_integrity_the_codes_caveat_derivation_map_must_be_the_protocols(self):
        from nre import caveat_sensitivity as cs
        self.assertTrue(all(c["ok"] for c in pr.verify_protocol(PROTOCOL, FREEZE)))
        narrower = {**cs.DERIVED, "day1_close_return": ()}
        with mock.patch.object(cs, "DERIVED", narrower):
            failed = [c["check"] for c in pr.verify_protocol(PROTOCOL, FREEZE) if not c["ok"]]
        self.assertEqual(failed, ["derived_labels_map"])

    def test_5_protocol_integrity_a_synthetic_harness_still_checks_the_protocol_against_its_freeze_record(self):
        run = harness()
        self.assertTrue(all(c["ok"] for c in run.verify()))
        altered = copy.deepcopy(PROTOCOL)
        altered["seeds"]["bootstrap_issuer"] = 1
        events, spec = S.dataset()
        checks = h.Harness.for_tests(events, spec, calendar=S.CAL, protocol=altered).verify()
        self.assertEqual([c["check"] for c in checks if not c["ok"]], ["protocol_hash", "freeze_record_pins_the_protocol_inputs"][:1])

    def test_6_determinism_the_same_inputs_and_seeds_give_identical_outputs_and_hashes(self):
        events, spec = S.dataset()
        positives = positives_of(events, "gap_ge_3pct")
        for target_id in ("gap_ge_3pct", "day1_close_return"):
            predictors = [h.PooledRate(), Oracle(positives)] if target_id == "gap_ge_3pct" else None
            first = harness(events, spec).evaluate(target_id, "clean_window", predictors)
            second = harness(*S.dataset()).evaluate(target_id, "clean_window", [h.PooledRate(), Oracle(positives)] if predictors else None)
            self.assertEqual(canonical_digest(first), canonical_digest(second), target_id)
        run = harness(events, spec)
        self.assertEqual(canonical_digest(run.dry_run()), canonical_digest(harness(*S.dataset()).dry_run()))

    def test_6_determinism_the_seeds_are_used(self):
        events, spec = S.dataset()
        positives = positives_of(events, "gap_ge_3pct")
        base = harness(events, spec).evaluate("gap_ge_3pct", "all_event", [h.PooledRate(), Oracle(positives, 0.05)])
        altered = copy.deepcopy(PROTOCOL)
        altered["seeds"]["bootstrap_reaction_session"] += 1
        other = h.Harness.for_tests(events, spec, calendar=S.CAL, protocol=altered).evaluate("gap_ge_3pct", "all_event", [h.PooledRate(), Oracle(positives, 0.05)])
        a, b = base["contrasts"]["TEST_ORACLE"], other["contrasts"]["TEST_ORACLE"]
        self.assertNotEqual(a["by_clustering"]["reaction_session"]["intervals"], b["by_clustering"]["reaction_session"]["intervals"])
        self.assertEqual(a["by_clustering"]["issuer"], b["by_clustering"]["issuer"])
        self.assertEqual(a["estimate"], b["estimate"])

    def test_6_determinism_the_real_dry_run_reproduces(self):
        self.assertEqual(canonical_digest(h.Harness.from_repository().dry_run()), canonical_digest(h.Harness.from_repository().dry_run()))

    def test_7_clusters_no_reaction_session_or_block_is_split_between_training_and_test(self):
        events, spec = S.dataset()
        run = harness(events, spec)
        for fold in run.folds:
            train, test = d.split(run.versions["all_event"], run.blocks, fold)
            d.assert_clusters_whole(train, test, run.blocks)
        shared = [e for e in events if sum(1 for o in events if o["reaction_session"] == e["reaction_session"]) > 1]
        self.assertTrue(shared, "the synthetic data must include a session with two events for this test to mean anything")
        broken = harness(events, spec)
        victim = next(e for e in broken.events if e["reaction_session"] == shared[0]["reaction_session"] and not d.is_sealed(e))
        broken.blocks[victim["event_id"]] = 3 if broken.blocks[victim["event_id"]] != 3 else 2
        with self.assertRaises(DataError):
            broken.evaluate("gap_ge_3pct", "all_event")

    def test_7_clusters_the_real_folds_split_nothing(self):
        plan = h.Harness.from_repository().plan()  # plan asserts it for every fold before reporting anything
        self.assertEqual(sorted(plan["targets"]["gap_ge_3pct"]["all_event"]["folds"]), ["dev_test_block_3", "dev_test_block_4", "holdout_test_block_5"])

    def test_8_abstention_a_failed_fit_gives_null_predictions_with_a_reason_and_nothing_is_substituted(self):
        events, spec = S.dataset()
        run = harness(events, spec)
        result = run.evaluate("gap_ge_3pct", "all_event", [h.PooledRate(), Failing()])
        failed = result["predictors"]["TEST_FAILING"]
        self.assertEqual((failed["state"], failed["rows"]), ("MODEL_FIT_FAILED", []))
        self.assertIn("did not converge", failed["reason"])
        for entry in failed["folds"].values():
            self.assertEqual((entry["state"], entry["predictions"]), ("MODEL_FIT_FAILED", None))
            self.assertNotIn("rows", entry)
        self.assertNotIn("metrics", failed)
        self.assertEqual(result["contrasts"], {})
        self.assertEqual(result["predictors"]["C1_pooled_rate"]["state"], h.EVALUATED)

    def test_8_abstention_thresholds_not_met_give_insufficient_data_for_every_predictor_and_no_metric(self):
        events, spec = S.dataset()
        run = harness(events, spec)
        result = run.evaluate("gap_ge_5pct", "all_event", [h.PooledRate(), Oracle(positives_of(events, "gap_ge_5pct"))])
        self.assertEqual(result["pooled_development_test"]["state"], d.INSUFFICIENT_DATA)
        for pid, predictor in result["predictors"].items():
            self.assertEqual(predictor["state"], d.INSUFFICIENT_DATA, pid)
            self.assertTrue(predictor["reason"])
            self.assertEqual(predictor["rows"], [])
            self.assertNotIn("metrics", predictor)
            for entry in predictor["folds"].values():
                self.assertEqual((entry["state"], entry["predictions"]), (d.INSUFFICIENT_DATA, None))
                self.assertTrue(entry["reason"])
        self.assertEqual(result["contrasts"], {})

    def test_8_abstention_a_fold_below_the_training_threshold_is_marked_and_left_out_of_the_pool(self):
        events, spec = S.dataset()
        result = harness(events, spec).evaluate("gap_ge_5pct", "all_event")
        fold3 = result["folds"]["dev_test_block_3"]
        self.assertEqual(fold3["state"], d.INSUFFICIENT_DATA)
        self.assertLess(fold3["train"]["positives"], pr.MIN_POSITIVES)
        self.assertNotIn("dev_test_block_3", result["pooled_development_test"]["folds_included"])
        self.assertEqual(result["predictors"]["C1_pooled_rate"]["folds"]["dev_test_block_3"]["predictions"], None)

    def test_8_abstention_a_pooled_rate_with_nothing_to_learn_from_stops(self):
        events, _ = S.dataset()
        with self.assertRaises(h.Abstain) as caught:
            h.PooledRate().fit([], d.targets(PROTOCOL)["gap_ge_3pct"])
        self.assertEqual(caught.exception.state, "INSUFFICIENT_DATA")
        with self.assertRaises(h.Abstain):
            h.PooledQuantiles().fit([], d.targets(PROTOCOL)["day1_close_return"])

    def test_8_abstention_a_status_is_never_filled_in(self):
        events, spec = S.dataset()
        run = harness(events, spec)
        results = {v: run.evaluate("loses_half_of_gap", v, [h.PooledRate(), Failing()]) for v in d.VERSIONS}
        self.assertEqual(results["clean_window"]["pooled_development_test"]["state"], d.INSUFFICIENT_DATA)
        self.assertEqual(run.status("TEST_FAILING", results), m.INSUFFICIENT_DATA)
        ok = {v: run.evaluate("gap_ge_3pct", v, [h.PooledRate(), Failing()]) for v in d.VERSIONS}
        self.assertEqual(run.status("TEST_FAILING", ok), "MODEL_FIT_FAILED")


class BehaviourTests(unittest.TestCase):
    def setUp(self):
        self.events, self.spec = S.dataset()
        self.run = harness(self.events, self.spec)

    def test_a_predictor_is_shown_the_training_events_and_never_a_test_events_labels(self):
        for target_id in ("gap_ge_3pct", "extension_after_open_ge_5pct", "loses_half_of_gap"):
            spy = Spy()
            self.run.evaluate(target_id, "all_event", [spy])
            self.assertTrue(spy.views)
            for view in spy.views:
                self.assertNotIn("labels", view)
                self.assertNotIn("labels_sha256", view)  # the digest of the outcomes is itself derived from them
                self.assertEqual("open_gap" in view, target_id != "gap_ge_3pct", target_id)
            self.assertEqual(len(spy.trained), 2)  # one fit per development fold
            blocks = self.run.blocks
            self.assertEqual({blocks[i] for i in spy.trained[0]}, {1, 2})
            self.assertEqual({blocks[i] for i in spy.trained[1]}, {1, 2, 3})

    def test_the_c0_opening_gap_is_the_events_own_opening_return_and_the_b_clock_has_none(self):
        spy = Spy()
        self.run.evaluate("extension_after_open_ge_5pct", "all_event", [spy])
        original = {e["event_id"]: e["labels"]["day1_open_return"]["value"] for e in self.events}
        for view in spy.views:
            self.assertEqual(view["open_gap"], original[view["event_id"]])

    def test_only_events_with_the_target_defined_are_fitted_and_scored(self):
        spy = Spy()
        result = self.run.evaluate("loses_half_of_gap", "all_event", [spy])
        target = d.targets(PROTOCOL)["loses_half_of_gap"]
        defined = {e["event_id"] for e in self.events if target.function(e["labels"]) is not None if not d.is_sealed(next(x for x in self.run.events if x["event_id"] == e["event_id"]))}
        self.assertTrue(set(sum(spy.trained, [])) <= defined)
        self.assertEqual(len(spy.views), result["pooled_development_test"]["test"]["defined"])

    def test_the_pooled_rate_is_the_training_rate_among_events_with_the_target_defined(self):
        result = self.run.evaluate("gap_ge_3pct", "all_event")
        run = result["predictors"]["C1_pooled_rate"]
        blocks = self.run.blocks
        for fold_name, train_blocks in (("dev_test_block_3", {1, 2}), ("dev_test_block_4", {1, 2, 3})):
            train = [e for e in self.events if blocks[e["event_id"]] in train_blocks]
            rate = sum(1 for e in train if e["labels"]["gap_ge_3pct"]["value"]) / len(train)
            self.assertAlmostEqual(run["folds"][fold_name]["model"]["rate"], rate)
            self.assertTrue(all(r["p"] == h.rounded(run["folds"][fold_name]["model"]["rate"]) for r in run["folds"][fold_name]["rows"]))  # as produced: rounded

    def test_the_pooled_quantiles_are_type_7_quantiles_of_the_training_values(self):
        result = self.run.evaluate("day1_close_return", "all_event")
        model = result["predictors"]["C1_pooled_quantiles"]["folds"]["dev_test_block_3"]["model"]
        values = sorted(e["labels"]["day1_close_return"]["value"] for e in self.events if self.run.blocks[e["event_id"]] in (1, 2))
        self.assertEqual(model["quantiles"], [fp.quantile(values, q) for q in (0.1, 0.5, 0.9)])
        self.assertEqual(model["n"], len(values))

    def test_clean_window_drops_caveated_events_from_the_fit_and_the_score(self):
        every, clean = self.run.evaluate("gap_ge_3pct", "all_event"), self.run.evaluate("gap_ge_3pct", "clean_window")
        self.assertLess(clean["pooled_development_test"]["test"]["defined"], every["pooled_development_test"]["test"]["defined"])
        self.assertLess(clean["folds"]["dev_test_block_3"]["train"]["defined"], every["folds"]["dev_test_block_3"]["train"]["defined"])
        absent = {e["event_id"] for e in self.events if "day1_open_return" in cs_pairs(self.spec).get(e["event_id"], ())}
        scored = {r["event_id"] for r in clean["predictors"]["C1_pooled_rate"]["rows"]}
        self.assertFalse(scored & absent)

    def test_every_metric_is_reported_with_its_counts_and_the_version(self):
        result = self.run.evaluate("gap_ge_3pct", "clean_window")
        metrics = result["predictors"]["C1_pooled_rate"]["metrics"]
        pooled = result["pooled_development_test"]["test"]
        self.assertEqual({k: metrics["counts"][k] for k in ("events", "positives", "negatives")}, {"events": pooled["defined"], "positives": pooled["positives"],
                                                                                                   "negatives": pooled["negatives"]})
        self.assertGreater(metrics["counts"]["reaction_sessions"], 1)
        self.assertGreater(metrics["counts"]["issuers"], 1)
        self.assertEqual(result["version"], "clean_window")

    def test_the_metrics_are_reported_pooled_by_fold_and_by_source(self):
        events, spec = S.dataset()
        blocks = ev.assign_blocks(events)
        sources = {e["event_id"]: ("milestone_2_step_2" if blocks[e["event_id"]] == 3 else "milestone_2_step_3") for e in events}
        result = harness(events, spec, source_of=sources).evaluate("gap_ge_3pct", "all_event")
        run = result["predictors"]["C1_pooled_rate"]
        self.assertEqual(sorted(run["metrics_by_fold"]), ["dev_test_block_3", "dev_test_block_4"])
        self.assertEqual(sorted(run["metrics_by_source"]), ["milestone_2_step_2", "milestone_2_step_3"])
        self.assertEqual(run["metrics_by_fold"]["dev_test_block_3"]["counts"]["events"], result["folds"]["dev_test_block_3"]["test"]["defined"])
        self.assertEqual(sum(s["counts"]["events"] for s in run["metrics_by_source"].values()), run["metrics"]["counts"]["events"])

    def test_metric_level_thresholds_apply_inside_a_fold_and_the_pool(self):
        result = self.run.evaluate("gap_ge_3pct", "all_event")
        run = result["predictors"]["C1_pooled_rate"]
        pooled = run["metrics"]
        self.assertEqual(sorted(pooled["precision_at_k"]), ["10", "20"])
        self.assertIsInstance(pooled["pr_auc"], float)
        by_fold = run["metrics_by_fold"]["dev_test_block_3"]
        self.assertEqual(sorted(by_fold["precision_at_k"]), ["10", "5"])
        n = by_fold["counts"]["events"]
        self.assertEqual(n >= 20, "precision" in by_fold["precision_at_k"]["10"])  # K = 10 needs 2K = 20 events
        thin = self.run.evaluate("extension_after_open_ge_5pct", "clean_window")  # 9 pooled positives in the synthetic clean-window set
        self.assertEqual(thin["pooled_development_test"]["state"], d.INSUFFICIENT_DATA)

    def test_precision_at_k_reports_its_lift_over_the_base_rate_and_over_random_rankings(self):
        run = self.run.evaluate("gap_ge_3pct", "all_event")["predictors"]["C1_pooled_rate"]
        entry = run["metrics"]["precision_at_k"]["10"]
        self.assertAlmostEqual(entry["lift_over_the_training_base_rate"], entry["precision"] / m.mean([r["base_rate"] for r in run["rows"]]))
        self.assertEqual(entry["random_ranking"]["rankings"], 1000)
        self.assertEqual(entry["random_ranking"]["seed"], PROTOCOL["seeds"]["random_ranking"])

    def test_a_primary_contrast_is_one_per_target_against_the_pooled_comparator_and_lower_is_better(self):
        events, spec = S.dataset()
        positives = positives_of(events, "gap_ge_3pct")
        result = harness(events, spec).evaluate("gap_ge_3pct", "all_event", [h.PooledRate(), Oracle(positives)])
        contrast = result["contrasts"]["TEST_ORACLE"]
        rows = result["predictors"]
        brier_model, brier_base = rows["TEST_ORACLE"]["metrics"]["brier"], rows["C1_pooled_rate"]["metrics"]["brier"]
        self.assertAlmostEqual(contrast["estimate"], brier_model - brier_base)
        self.assertLess(contrast["estimate"], 0)
        self.assertEqual(contrast["metric"], "brier_score")
        self.assertEqual(set(contrast["by_clustering"]), {"reaction_session", "issuer"})
        self.assertEqual({c["replicates"] for c in contrast["by_clustering"].values()}, {5000})
        self.assertEqual({k: c["seed"] for k, c in contrast["by_clustering"].items()}, {"reaction_session": 410001, "issuer": 410002})
        self.assertNotIn("C1_pooled_rate", result["contrasts"])

    def test_the_regression_contrast_uses_the_mean_pinball_loss(self):
        class Shifted(h.Predictor):
            id, kind = "TEST_SHIFTED", "regression"

            def fit(self, train, target):
                return {"shift": 0.05}

            def predict(self, model, view):
                return (-0.1 + model["shift"], model["shift"], 0.1 + model["shift"])
        result = self.run.evaluate("day1_close_return", "all_event", [h.PooledQuantiles(), Shifted()])
        contrast = result["contrasts"]["TEST_SHIFTED"]
        self.assertEqual(contrast["metric"], "mean_pinball_loss")
        models, base = result["predictors"]["TEST_SHIFTED"]["metrics"], result["predictors"]["C1_pooled_quantiles"]["metrics"]
        self.assertAlmostEqual(contrast["estimate"], models["mean_pinball_loss"] - base["mean_pinball_loss"])
        self.assertEqual(sorted(base["pinball_loss_by_level"]), ["0.1", "0.5", "0.9"])

    def test_statuses_follow_the_decision_rule_in_both_versions(self):
        events, spec = S.dataset(sizes=(24, 44, 36, 36, 20))
        run = harness(events, spec)
        for label, predictor, expected in (("oracle", Oracle(positives_of(events, "gap_ge_3pct")), m.DISTINGUISHABLE_BETTER),
                                           ("wrong way round", Oracle(positives_of(events, "gap_ge_3pct"), -0.4), m.DISTINGUISHABLE_WORSE),
                                           ("no information", Oracle(set(), 0.0), m.NOT_DISTINGUISHABLE)):
            results = {v: run.evaluate("gap_ge_3pct", v, [h.PooledRate(), predictor]) for v in d.VERSIONS}
            self.assertEqual(run.status(predictor.id, results), expected, label)

    def test_a_thin_clean_window_version_is_insufficient_data_even_when_the_all_event_version_wins(self):
        events, spec = S.dataset()
        run = harness(events, spec)
        oracle = Oracle(positives_of(events, "extension_after_open_ge_5pct"))
        results = {v: run.evaluate("extension_after_open_ge_5pct", v, [h.PooledRate(), oracle]) for v in d.VERSIONS}
        self.assertEqual(results["all_event"]["pooled_development_test"]["state"], d.EVALUABLE)
        self.assertEqual(results["clean_window"]["pooled_development_test"]["state"], d.INSUFFICIENT_DATA)
        self.assertEqual(run.status(oracle.id, results), m.INSUFFICIENT_DATA)

    def test_descriptive_and_insufficient_targets_are_not_modelled(self):
        for target_id in ("gap_ge_10pct", "gap_ge_15pct", "closes_below_open"):
            with self.assertRaises(DataError):
                self.run.evaluate(target_id, "all_event")

    def test_a_predictor_of_the_wrong_kind_for_the_target_is_refused(self):
        with self.assertRaises(DataError):
            self.run.evaluate("day1_close_return", "all_event", [h.PooledRate()])

    def test_two_predictors_are_compared_on_the_same_events(self):
        class Skipping(h.Predictor):
            id, kind = "TEST_SKIPPING", "binary"

            def fit(self, train, target):
                return {}

            def predict(self, model, view):
                return 0.4
        result = self.run.evaluate("gap_ge_3pct", "all_event", [h.PooledRate(), Skipping()])
        a, b = (result["predictors"][k]["rows"] for k in ("C1_pooled_rate", "TEST_SKIPPING"))
        self.assertEqual([r["event_id"] for r in a], [r["event_id"] for r in b])
        with self.assertRaises(DataError):
            self.run._contrast(self.run.targets["gap_ge_3pct"], b[:-1], a)

    def test_the_plan_reports_every_target_with_counts_by_version_and_the_fold_states_of_the_primaries(self):
        plan = self.run.plan()
        self.assertEqual(len(plan["targets"]), 19)
        row = plan["targets"]["gap_ge_3pct"]
        self.assertEqual(sorted(row), sorted(["role", "kind", "clock", "source_labels", "definition", "blocks_1_to_4_all_event", "blocks_1_to_4_clean_window",
                                              "all_event", "clean_window"]))
        self.assertNotIn("all_event", plan["targets"]["gap_ge_10pct"])  # descriptive targets get counts only
        self.assertEqual(plan["targets"]["gap_ge_3pct"]["all_event"]["folds"]["holdout_test_block_5"]["test"][:6], "SEALED")
        self.assertEqual(len(plan["blocks"]["blocks"]), 5)

    def test_experiment_records_cover_every_predictor_and_fold_and_the_pool_in_the_protocols_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "experiments.jsonl"
            reg.init_logs(PROTOCOL, "c" * 40, "2026-10-06T00:00:00Z", log, Path(directory) / "holdout.jsonl")
            run = harness(self.events, self.spec, experiment_log=log, commit=lambda: "c" * 40, clock=lambda: "2026-10-06T02:00:00Z")
            result = run.evaluate("gap_ge_3pct", "all_event", [h.PooledRate(), Oracle(positives_of(self.events, "gap_ge_3pct"))])
            written = run.record_experiments(result)
            self.assertEqual(len(written), 2 * 3)  # two predictors x (two development folds + the pool)
            self.assertEqual(reg.verify_chain(log, "experiments", PROTOCOL)["records"], 7)
            for record in written:
                self.assertEqual(set(record), set(PROTOCOL["experiment_log"]["experiment_record_fields"]))
                self.assertEqual((record["protocol_sha256"], record["harness_commit"], record["version"], record["target_id"], record["clock"]),
                                 (pr.protocol_sha256(PROTOCOL), "c" * 40, "all_event", "gap_ge_3pct", "B"))
                self.assertEqual(record["features_version"], feat.FEATURE_VERSION)
            by_fold = {(r["predictor_id"], r["fold"]): r for r in written}
            c1 = by_fold[("C1_pooled_rate", "dev_test_block_3")]
            rows = result["predictors"]["C1_pooled_rate"]["folds"]["dev_test_block_3"]["rows"]
            self.assertEqual(c1["predictions_sha256"], digest(canonical([[r["event_id"], r["p"]] for r in rows])))
            self.assertEqual(c1["test_event_ids_sha256"], reg.hash_list(sorted(r["event_id"] for r in rows)))
            self.assertEqual(c1["train_event_ids_sha256"], reg.hash_list(sorted(run._train_ids("all_event", "dev_test_block_3"))))
            self.assertEqual(c1["state"], "EVALUATED")
            pooled = by_fold[("TEST_ORACLE", "pooled_development")]
            self.assertIn("5000 replicates", pooled["interval_method"])
            self.assertIsNotNone(pooled["metrics_with_counts"]["contrasts"]["against_the_comparator"])
            self.assertEqual([r["experiment_id"] for r in written][:2], ["m4-experiment-00001", "m4-experiment-00002"])

    def test_a_fold_that_could_not_be_evaluated_is_recorded_with_its_state_and_no_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "experiments.jsonl"
            reg.init_logs(PROTOCOL, "c" * 40, "2026-10-06T00:00:00Z", log, Path(directory) / "holdout.jsonl")
            run = harness(self.events, self.spec, experiment_log=log, commit=lambda: "c" * 40)
            written = run.record_experiments(run.evaluate("gap_ge_5pct", "all_event"))
            self.assertEqual({r["state"] for r in written}, {"INSUFFICIENT_DATA"})
            for record in written:
                self.assertEqual(record["predictions_sha256"], digest(canonical([])))

    def test_every_prediction_record_is_model_not_validated_with_no_qualified_opportunity_and_the_lowest_confidence(self):
        event = next(e for e in self.run.events if not d.is_sealed(e) and self.run.blocks[e["event_id"]] == 3)
        predictor, target = h.PooledRate(), self.run.targets["gap_ge_3pct"]
        record = self.run.prediction_record(predictor, {"rate": 0.3}, target, "all_event", "dev_test_block_3", event, 0.3, "2026-10-06T03:00:00Z")
        self.assertEqual({k: record[k] for k in ("response_state", "opportunity_state", "confidence_tier")},
                         {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"})
        self.assertEqual(set(PROTOCOL["experiment_log"]["prediction_record_fields"]) - set(record), set())
        self.assertEqual(record["model_version"], "m4-C1_pooled_rate-v1")
        self.assertEqual(record["prediction_time"], fp.iso(event["cutoff"]))
        c0 = self.run.prediction_record(predictor, {"rate": 0.3}, self.run.targets["extension_after_open_ge_5pct"], "all_event", "dev_test_block_3", event, 0.3, "x")
        self.assertEqual(c0["prediction_time"], fp.iso(S.CAL.bounds(event["reaction_session"])[0]))  # the C0 clock is the regular open
        self.assertEqual(h.RESPONSE["confidence_tier"], "VERY_LOW")
        self.assertNotIn("QUALIFIED", set(h.RESPONSE.values()))
        self.assertEqual(record["training_window_dates"][0], min(e["reaction_session"] for e in self.run.events if self.run.blocks[e["event_id"]] in (1, 2)))


def cs_pairs(spec):
    from nre import caveat_sensitivity as cs
    return cs.caveated_pairs(spec, with_derived=True)


class RealHarnessTests(unittest.TestCase):
    """The harness on the real inputs: verified, planned, dry-run. Nothing is evaluated and the holdout is not touched."""

    @classmethod
    def setUpClass(cls):
        cls.harness = h.Harness.from_repository()
        cls.report = cls.harness.dry_run()

    def test_real_evaluation_is_limited_to_the_five_primaries_and_the_holdout_look_is_off(self):
        self.assertIs(h.ALLOW_REAL_EVALUATION, True)  # Phase 2 and Phase 3, authorized 2026-10-07 (reports/m4-phase2-authorization-2026-10-07.json, m4-phase3-authorization-2026-10-07.json)
        self.assertEqual(h.REAL_EVALUATION_TARGETS, ("gap_ge_3pct", "gap_ge_5pct", "day1_close_return", "extension_after_open_ge_5pct", "loses_half_of_gap"))
        primaries = [t.id for t in self.harness.targets.values() if t.role == "primary"]
        self.assertEqual(sorted(h.REAL_EVALUATION_TARGETS), sorted(primaries))  # exactly the protocol's five primaries
        self.assertIs(h.ALLOW_HOLDOUT_LOOK, False)
        others = [t.id for t in self.harness.targets.values() if t.role != "primary"]
        self.assertEqual(len(others), 9 + 5)  # the descriptive-only targets (full_gap_fill and the five-session returns among them) and the INSUFFICIENT_DATA ones
        for refused in others:
            with self.assertRaises(h.EvaluationNotAuthorized):
                self.harness.evaluate(refused, "all_event")
        for authorized in ("gap_ge_3pct", "loses_half_of_gap"):
            with mock.patch.object(h, "ALLOW_REAL_EVALUATION", False):
                with self.assertRaises(h.EvaluationNotAuthorized):
                    self.harness.evaluate(authorized, "all_event")  # refused before anything is fitted
        with self.assertRaises(d.HoldoutNotAuthorized):
            self.harness.look("a trial")
        self.assertEqual((self.harness.gate.unsealed, self.harness.gate.denied), (0, []))

    def test_the_dry_run_verifies_everything_and_agrees_with_the_freeze_record(self):
        self.assertTrue(self.report["integrity_ok"])
        self.assertEqual(len(self.report["integrity_checks"]), 18)
        self.assertEqual(self.report["agreement_with_the_freeze_record"]["disagreements"], [])
        self.assertEqual(self.report["protocol"]["canonical_sha256"], FREEZE["protocol"]["canonical_sha256"])

    def test_the_dry_run_evaluates_nothing_and_reads_no_holdout_outcome(self):
        self.assertEqual(self.report["evaluated"], {"predictors_fitted": 0, "predictions_made": 0, "metrics_computed": 0})
        self.assertEqual(self.report["holdout"], {"sealed_events": 23, "denied_reads": 0, "unsealed_loads": 0, "access_log_records_after_genesis": 0})
        text = json.dumps(self.report)
        self.assertNotIn("brier", text)
        self.assertNotIn("log_loss", text)

    def test_the_cross_check_does_report_a_disagreement_when_there_is_one(self):
        plan = copy.deepcopy(self.report["plan"])
        self.assertEqual(self.harness.cross_check(plan), [])
        plan["targets"]["gap_ge_3pct"]["all_event"]["folds"]["dev_test_block_3"]["train"]["positives"] += 1
        plan["targets"]["loses_half_of_gap"]["clean_window"]["pooled_development_test"]["state"] = "EVALUABLE"
        plan["targets"]["day1_close_return"]["clean_window"]["pooled_development_test"]["test"]["defined"] += 1
        problems = self.harness.cross_check(plan)
        self.assertEqual(len(problems), 3)
        self.assertTrue(any("gap_ge_3pct" in p and "train pos" in p for p in problems))
        self.assertTrue(any("loses_half_of_gap" in p and "development status" in p for p in problems))
        self.assertTrue(any("day1_close_return" in p and "pooled development test" in p for p in problems))

    def test_the_development_statuses_are_the_ones_the_freeze_record_stated_in_advance(self):
        targets = self.report["plan"]["targets"]
        for version in d.VERSIONS:
            for target_id in PRIMARY:
                expected = "INSUFFICIENT_DATA" if (version, target_id) == ("clean_window", "loses_half_of_gap") else "EVALUABLE"
                self.assertEqual(targets[target_id][version]["pooled_development_test"]["state"], expected, (version, target_id))
        fold3 = targets["loses_half_of_gap"]["clean_window"]["folds"]["dev_test_block_3"]
        self.assertEqual((fold3["state"], fold3["train"]["positives"]), ("INSUFFICIENT_DATA", 9))
        self.assertEqual(targets["loses_half_of_gap"]["clean_window"]["pooled_development_test"]["test"], {"defined": 10, "positives": 5, "negatives": 5})
        for version in d.VERSIONS:
            self.assertEqual(targets["gap_ge_5pct"][version]["pooled_development_test"]["test"]["positives"], 10)  # the minimum that passes

    def test_the_holdout_fold_shows_training_counts_and_a_seal_in_place_of_test_counts(self):
        for target_id in PRIMARY:
            fold = self.report["plan"]["targets"][target_id]["all_event"]["folds"]["holdout_test_block_5"]
            self.assertEqual(fold["role"], "holdout")
            self.assertTrue(fold["test"].startswith("SEALED"))
            self.assertEqual(fold["test_events"], 23)

    def test_the_plan_reports_counts_by_block_for_every_target_without_reading_block_5(self):
        targets = self.report["plan"]["targets"]
        self.assertEqual(len(targets), 19)
        self.assertEqual(targets["gap_ge_3pct"]["blocks_1_to_4_all_event"]["defined"], 105)
        self.assertEqual(self.report["plan"]["events_whose_labels_were_available"], 105)
        for blocks in self.report["plan"]["blocks"]["blocks"]:
            self.assertGreater(blocks["events"], 0)

    def test_the_command_line_offers_no_way_to_evaluate(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            h.main(["evaluate"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(h.main(["verify"]), 0)
        self.assertEqual(json.loads(out.getvalue()), {"state": "VERIFIED", "checks": 18, "failed": []})

    def test_the_command_line_writes_the_dry_run_report_and_prints_its_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dry-run.json"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(h.main(["dry-run", "--output", str(path)]), 0)
            summary = json.loads(out.getvalue())
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(summary["state"], "DRY_RUN")
        self.assertEqual(summary["report_sha256"], canonical_digest(written))
        self.assertEqual(canonical_digest(written), canonical_digest(self.report))


if __name__ == "__main__":
    unittest.main()
