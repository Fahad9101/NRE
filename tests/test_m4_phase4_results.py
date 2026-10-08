"""The committed Phase 4 results: consistent with the two logs and the predictions file, reproduced by REPLAYING the look through Harness.look against temporary logs (P4-11: the real
access log is never touched, and no other code path reads a block-5 outcome), recomputed independently from plain arithmetic, and the real holdout log showing exactly one access.

The replay re-reads the sealed block-5 outcomes twice, and on the owner's decision every such run is two counted accesses (reports/m4-phase4-replay-accesses-2026-10-07.json). So it is OPT-IN since the
owner's decision of 2026-10-08 ("make the replay tests opt-in"): ReplayTests are skipped unless M4_REPLAY_HOLDOUT=1 is set, and a run made on purpose is added to that record. Everything else in this
file reads only committed outputs and the two logs."""
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_independent as independent  # noqa: E402
import m4_support as S  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_metrics as m  # noqa: E402
from nre import m4_phase4 as p4  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402
from nre.core import canonical, digest, iso  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATE = "2026-10-07"
RESULTS = ROOT / "reports" / ("m4-phase4-holdout-results-%s.json" % DATE)
DESCRIPTIVE = ROOT / "reports" / ("m4-phase4-descriptive-%s.json" % DATE)
PREDICTIONS = ROOT / "reports" / ("m4-phase4-holdout-predictions-%s.jsonl" % DATE)
DEVELOPMENT_FILES = ("m4-phase2-results-2026-10-07.json", "m4-phase2-completion-2026-10-07.json", "m4-phase3-results-2026-10-07.json", "m4-phase3-completion-2026-10-07.json")
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
TARGETS = d.targets(PROTOCOL)
HOLDOUT_FOLD = "holdout_test_block_5"
REPLAY_SWITCH = "M4_REPLAY_HOLDOUT"
REPLAY_SKIP_REASON = ("the replay re-reads the sealed block-5 outcomes twice (two counted accesses per run); set %s=1 to run it on purpose, then add the run to "
                      "reports/m4-phase4-replay-accesses-2026-10-07.json" % REPLAY_SWITCH)


def close(a, b, tolerance=1e-9):
    """Equal in structure, and equal to `tolerance` in every number (the C libraries behind exp and log can differ in the last bit between platforms)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], tolerance) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tolerance * max(1.0, abs(a), abs(b))
    return a == b


def quantile(ordered, p):
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def pre_look_logs(owner):
    """Temporary copies of the two real logs cut back to what they held before the look: the experiment log's first 175 records and the holdout log's genesis."""
    directory = tempfile.TemporaryDirectory()
    owner.addClassCleanup(directory.cleanup)
    root = Path(directory.name)
    out = []
    for source, keep, name in ((reg.EXPERIMENT_LOG, p4.EXPERIMENTS_BEFORE, "experiments.jsonl"), (reg.HOLDOUT_LOG, 1, "holdout.jsonl")):
        lines = [line for line in source.read_bytes().split(b"\n") if line.strip()]
        (root / name).write_bytes(b"\n".join(lines[:keep]) + b"\n")
        out.append(root / name)
    return out


class RecordTests(unittest.TestCase):
    """What the real logs and the committed files say, without replaying anything."""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(RESULTS.read_text(encoding="utf-8"))
        cls.by_key = {}
        for line in PREDICTIONS.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            cls.by_key.setdefault((record["target_id"], record["version"], record["predictor_id"]), []).append(record)

    def test_the_real_holdout_log_holds_its_genesis_and_exactly_one_access_and_the_tripwire_is_off_again(self):
        records = [r for r, _ in reg.read(reg.HOLDOUT_LOG)]
        self.assertEqual(reg.verify_chain(reg.HOLDOUT_LOG, "holdout_access", PROTOCOL)["records"], 2)
        genesis, access = records
        self.assertEqual(genesis["kind"], "genesis")
        self.assertEqual((access["access_number"], access["reason"], access["protocol_sha256"]), (1, p4.LOOK_REASON, pr.protocol_sha256(PROTOCOL)))
        self.assertRegex(access["harness_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(access["events_read"]), 23)
        self.assertFalse(h.ALLOW_HOLDOUT_LOOK)

    def test_the_access_names_exactly_the_23_holdout_events(self):
        inputs = d.load_inputs(PROTOCOL)  # the holdout stays sealed: only the identities of the sealed events are used
        sealed = sorted(e["event_id"] for e in inputs["events"] if d.is_sealed(e))
        self.assertEqual(reg.read(reg.HOLDOUT_LOG)[1][0]["events_read"], sealed)
        self.assertEqual((inputs["gate"].denied, inputs["gate"].unsealed), ([], 0))

    def test_the_experiment_log_holds_the_58_holdout_records_after_phase_3s_and_all_name_the_commit_of_the_access(self):
        records = [r for r, _ in reg.read(reg.EXPERIMENT_LOG)]
        self.assertEqual(reg.verify_chain(reg.EXPERIMENT_LOG, "experiments", PROTOCOL)["records"], len(records))
        added = records[p4.EXPERIMENTS_BEFORE:p4.EXPERIMENTS_BEFORE + p4.EXPECTED_RECORDS]
        self.assertEqual(len(added), p4.EXPECTED_RECORDS)
        self.assertEqual([r["experiment_id"] for r in added], ["m4-experiment-%05d" % n for n in range(p4.EXPERIMENTS_BEFORE, p4.EXPERIMENTS_BEFORE + p4.EXPECTED_RECORDS)])
        self.assertEqual({r["fold"] for r in added}, {HOLDOUT_FOLD})
        self.assertEqual({r["harness_commit"] for r in added}, {reg.read(reg.HOLDOUT_LOG)[1][0]["harness_commit"]})  # the commit the access names
        self.assertEqual({r["protocol_sha256"] for r in added}, {pr.protocol_sha256(PROTOCOL)})
        self.assertEqual(sorted({r["target_id"] for r in added}), sorted(p4.TARGETS))
        earlier = records[1:p4.EXPERIMENTS_BEFORE]
        self.assertFalse(any(r["fold"] == HOLDOUT_FOLD for r in earlier))  # nothing on the holdout before the look

    def test_every_holdout_experiment_names_the_hash_of_the_predictions_in_the_file_and_every_scored_cell_has_one(self):
        by_cell = {}
        for (target, version, predictor), records in self.by_key.items():
            by_cell[(target, version, predictor)] = [[r["event_id"], tuple(r["prediction"]) if isinstance(r["prediction"], list) else r["prediction"]] for r in records]
        scored = 0
        for record, _ in reg.read(reg.EXPERIMENT_LOG)[p4.EXPERIMENTS_BEFORE:p4.EXPERIMENTS_BEFORE + p4.EXPECTED_RECORDS]:
            key = (record["target_id"], record["version"], record["predictor_id"])
            if record["state"] != "EVALUATED":
                self.assertNotIn(key, by_cell)  # a cell that was not scored made no predictions...
                self.assertEqual(record["predictions_sha256"], digest(canonical([])))  # ...and its record says so
                continue
            self.assertEqual(record["predictions_sha256"], digest(canonical(by_cell[key])))
            self.assertEqual(record["test_event_ids_sha256"], reg.hash_list(sorted(e for e, _ in by_cell[key])))
            scored += 1
        self.assertEqual(scored, len(by_cell))

    def test_what_the_look_found_as_the_protocol_said_in_advance_and_as_it_turned_out(self):
        states = self.report["states"]
        counts_only = ("gap_ge_3pct", "gap_ge_5pct", "loses_half_of_gap")  # the protocol's disclosure: 3 to 5 positives in the holdout, in both versions
        for target_id in counts_only:
            self.assertEqual(states[target_id], {"all_event": "COUNTS_ONLY", "clean_window": "COUNTS_ONLY"}, target_id)
            for version in d.VERSIONS:
                self.assertTrue(3 <= self.report["evaluations"][target_id][version]["test_counts"]["positives"] <= 5)
        for target_id in ("extension_after_open_ge_5pct", "day1_close_return"):  # the protocol: these two meet their thresholds
            self.assertEqual(states[target_id], {"all_event": "EVALUATED", "clean_window": "EVALUATED"}, target_id)
        evaluated = self.report["evaluations"]
        self.assertEqual({v: evaluated["extension_after_open_ge_5pct"][v]["test_counts"]["positives"] for v in d.VERSIONS}, {"all_event": 11, "clean_window": 10})
        self.assertEqual({v: evaluated["day1_close_return"][v]["test_counts"]["events"] for v in d.VERSIONS}, {"all_event": 23, "clean_window": 21})
        for versions in evaluated.values():  # 23 events from 23 issuers (21 from 21 in the clean-window version): no issuer has two events in the holdout
            for result in versions.values():
                self.assertEqual(result["test_counts"]["issuers"], result["test_counts"]["events"])

    def test_the_confirmatory_models_direction_did_not_repeat_and_nothing_is_distinguishable_from_the_base_rate(self):
        contrasts = 0
        for target_id, model in (("extension_after_open_ge_5pct", "M2_logistic"), ("day1_close_return", "M3_ridge_linear")):
            for version in d.VERSIONS:
                contrast = self.report["evaluations"][target_id][version]["contrasts"][model]
                check = contrast["against_the_development_result"]
                self.assertEqual((check["comparable"], check["holdout_sign"], check["development_sign"], check["same_sign"]), (True, -1, 1, False), (target_id, version))
                self.assertTrue(contrast["headline"]["0.95"]["low"] < 0 < contrast["headline"]["0.95"]["high"], (target_id, version))  # the 95% interval includes zero
                contrasts += 1
        self.assertEqual(contrasts, 4)
        every = [c for versions in self.report["evaluations"].values() for result in versions.values() for section in ("contrasts", "other_contrasts") for c in result[section].values()]
        self.assertEqual(len(every), 32)
        excluding = [c for c in every if c["headline"]["0.95"]["low"] > 0 or c["headline"]["0.95"]["high"] < 0]
        self.assertEqual(len(excluding), 1)  # about 1.6 of 32 would be expected by chance alone; it is exploratory and its 99% interval includes zero
        self.assertEqual((excluding[0]["role"], excluding[0]["baseline"], excluding[0]["headline"]["0.99"]["low"] < 0 < excluding[0]["headline"]["0.99"]["high"]), ("exploratory", "C1_pooled_quantiles", True))
        self.assertFalse(any(c["headline"]["0.99"]["low"] > 0 or c["headline"]["0.99"]["high"] < 0 for c in every))

    def test_every_prediction_is_a_protocol_prediction_record_timed_by_its_clock_with_no_other_state(self):
        inputs = d.load_inputs(PROTOCOL)
        by_id = {e["event_id"]: e for e in inputs["events"]}
        for records in self.by_key.values():
            for record in records:
                self.assertEqual({k: record[k] for k in ("response_state", "opportunity_state", "confidence_tier")},
                                 {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"})
                for field in PROTOCOL["experiment_log"]["prediction_record_fields"]:
                    self.assertIn(field, record)
                event = by_id[record["event_id"]]
                expected = inputs["calendar"].bounds(event["reaction_session"])[0] if TARGETS[record["target_id"]].clock == "C0" else event["cutoff"]
                self.assertEqual(record["prediction_time"], iso(expected))
                self.assertEqual(record["fold"], HOLDOUT_FOLD)
        scored = sum(run["metrics"]["counts"]["events"] for target in self.report["evaluations"].values() for ev in target.values() for run in ev["predictors"].values()
                     if run["state"] == "EVALUATED")
        self.assertEqual(sum(len(v) for v in self.by_key.values()), scored)  # one record for every predictor and test event the report counts

    def test_the_report_says_one_look_no_claim_and_carries_the_selection_regime(self):
        report = self.report
        self.assertEqual(report["the_look"]["accesses"], 1)
        self.assertEqual(report["the_look"]["technical_reruns"], 0)
        self.assertEqual(report["holdout"], {"sealed_events": 23, "denied_reads": 0, "unsealed_loads": 46, "access_log_records_after_genesis": 1})
        self.assertEqual(report["selection_regime"], PROTOCOL["holdout"]["selection_regime"])
        self.assertIn("the holdout alone never creates one", " ".join(report["not_a_claim"]))
        self.assertTrue(report["determinism"]["identical"])
        for versions in report["evaluations"].values():
            for result in versions.values():
                self.assertEqual(result["selection_regime"], PROTOCOL["holdout"]["selection_regime"])
                for contrast in list(result["contrasts"].values()) + list(result["other_contrasts"].values()):
                    self.assertIn("never creates a claim", contrast["claim"])


@unittest.skipUnless(os.environ.get(REPLAY_SWITCH) == "1", REPLAY_SKIP_REASON)
class ReplayTests(unittest.TestCase):
    """The look replayed through Harness.look against temporary logs: the committed outputs must reproduce, and plain arithmetic must agree with them. Opt-in: see the module docstring."""

    @classmethod
    def setUpClass(cls):
        print("%s=1: this run re-reads the sealed block-5 outcomes twice (two counted accesses); add it to reports/m4-phase4-replay-accesses-2026-10-07.json" % REPLAY_SWITCH, file=sys.stderr)
        cls.report = json.loads(RESULTS.read_text(encoding="utf-8"))
        cls.descriptive = json.loads(DESCRIPTIVE.read_text(encoding="utf-8"))
        cls.by_key = {}
        for line in PREDICTIONS.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            cls.by_key.setdefault((record["target_id"], record["version"], record["predictor_id"]), []).append(record)
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.root = Path(directory.name)
        (cls.root / "reports").mkdir()
        for name in DEVELOPMENT_FILES:
            shutil.copy(ROOT / "reports" / name, cls.root / "reports" / name)
        experiments, holdout = pre_look_logs(cls)
        cls.harness = h.Harness.from_repository(experiment_log=experiments, holdout_log=holdout)
        commit = reg.read(reg.HOLDOUT_LOG)[1][0]["harness_commit"]
        with mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True):
            cls.summary = p4.run(cls.harness, DATE, root=cls.root, commit_state=(commit, True))
        with mock.patch.object(cls.harness, "holdout_log", S.genesis_only_holdout_log(cls)), mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True):
            cls.unsealed = cls.harness.look("a replay for verification")  # a second replayed look, to have the events in hand for the plain-arithmetic checks
        cls.replayed = json.loads((cls.root / "reports" / ("m4-phase4-holdout-results-%s.json" % DATE)).read_text(encoding="utf-8"))

    def test_the_real_logs_are_untouched_by_the_replay(self):
        self.assertEqual((len(reg.read(reg.EXPERIMENT_LOG)), len(reg.read(reg.HOLDOUT_LOG))), (p4.EXPERIMENTS_BEFORE + p4.EXPECTED_RECORDS, 2))
        self.assertEqual(self.summary["accesses"], 1)

    def test_the_replayed_look_reproduces_the_committed_results(self):
        committed = {k: v for k, v in self.report.items() if k != "determinism"}
        now = {k: v for k, v in self.replayed.items() if k != "determinism"}
        self.assertTrue(close(now, committed), "a replayed look differs from the committed results")
        self.assertEqual(self.summary["states"], self.report["states"])

    def test_the_replayed_look_reproduces_the_descriptive_report_and_the_predictions(self):
        replayed = json.loads((self.root / "reports" / ("m4-phase4-descriptive-%s.json" % DATE)).read_text(encoding="utf-8"))
        self.assertTrue(close(replayed, self.descriptive), "a replayed look differs from the committed descriptive report")
        lines = [json.loads(line) for line in (self.root / "reports" / ("m4-phase4-holdout-predictions-%s.jsonl" % DATE)).read_text(encoding="utf-8").splitlines()]
        committed = [json.loads(line) for line in PREDICTIONS.read_text(encoding="utf-8").splitlines()]
        strip = lambda records: [{k: v for k, v in r.items() if k != "generated_at"} for r in records]  # noqa: E731
        self.assertTrue(close(strip(lines), strip(committed)))

    def test_the_replayed_experiment_records_match_the_committed_ones_in_everything_but_time(self):
        mine = [r for r, _ in reg.read(self.harness.experiment_log)][p4.EXPERIMENTS_BEFORE:]
        real = [r for r, _ in reg.read(reg.EXPERIMENT_LOG)][p4.EXPERIMENTS_BEFORE:]
        keys = ("experiment_id", "target_id", "clock", "predictor_id", "version", "fold", "train_event_ids_sha256", "test_event_ids_sha256", "state", "harness_commit", "protocol_sha256")
        self.assertEqual([{k: r[k] for k in keys} for r in mine], [{k: r[k] for k in keys} for r in real])

    def test_the_states_follow_the_holdout_rule_from_the_replayed_counts(self):
        for version in d.VERSIONS:
            events = self.unsealed[version]
            for target_id in p4.TARGETS:
                target = TARGETS[target_id]
                values = [v for v in (target.function(e["labels"]) for e in events) if v is not None]
                if target.kind == "regression":
                    expected = d.EVALUABLE if len(values) >= pr.MIN_REGRESSION_TEST_EVENTS else d.COUNTS_ONLY
                else:
                    positives = sum(1 for v in values if v)
                    expected = d.EVALUABLE if positives >= pr.MIN_POSITIVES and len(values) - positives >= pr.MIN_NEGATIVES else d.COUNTS_ONLY
                result = self.report["evaluations"][target_id][version]
                self.assertEqual(result["state"], h.EVALUATED if expected == d.EVALUABLE else d.COUNTS_ONLY, (target_id, version))
                counts = result["test_counts"]
                self.assertEqual(counts["events"], len(values))
                if target.kind == "binary":
                    self.assertEqual((counts["positives"], counts["negatives"]), (sum(1 for v in values if v), sum(1 for v in values if not v)))

    def test_the_scores_contrasts_and_bootstrap_intervals_recompute_from_the_predictions_and_the_replayed_labels(self):
        losses = {}
        by_id = {version: {e["event_id"]: e for e in self.unsealed[version]} for version in d.VERSIONS}
        for (target_id, version, predictor), records in self.by_key.items():
            target = TARGETS[target_id]
            per_event = {}
            for record in records:
                y = target.function(by_id[version][record["event_id"]]["labels"])
                self.assertIsNotNone(y)
                per_event[record["event_id"]] = ((record["prediction"] - (1.0 if y else 0.0)) ** 2 if target.kind == "binary"
                                                 else math.fsum(m.pinball(y, f, q) for f, q in zip(record["prediction"], pr.QUANTILE_LEVELS)) / len(pr.QUANTILE_LEVELS))
            losses[(target_id, version, predictor)] = per_event
            metrics = self.report["evaluations"][target_id][version]["predictors"][predictor]["metrics"]
            self.assertAlmostEqual(math.fsum(per_event.values()) / len(per_event), metrics["brier" if target.kind == "binary" else "mean_pinball_loss"], places=9)
            self.assertEqual(len(per_event), metrics["counts"]["events"])
        checked = 0
        for target_id in p4.TARGETS:
            kind = TARGETS[target_id].kind
            comparator = h.COMPARATOR[kind]
            for version in d.VERSIONS:
                result = self.report["evaluations"][target_id][version]
                for predictor, contrast in result["contrasts"].items():
                    a, b = losses[(target_id, version, predictor)], losses[(target_id, version, comparator)]
                    self.assertEqual(list(a), list(b))
                    diffs = {e: a[e] - b[e] for e in a}
                    self.assertAlmostEqual(math.fsum(diffs.values()) / len(diffs), contrast["estimate"], places=9)
                    for name, field, seed_key in (("reaction_session", "reaction_session", "bootstrap_reaction_session"), ("issuer", "cik", "bootstrap_issuer")):
                        clusters = sorted({by_id[version][e][field] for e in diffs})
                        sums = {c: math.fsum(v for e, v in diffs.items() if by_id[version][e][field] == c) for c in clusters}
                        sizes = {c: sum(1 for e in diffs if by_id[version][e][field] == c) for c in clusters}
                        rng = random.Random(PROTOCOL["seeds"][seed_key])
                        replicates = []
                        for _ in range(pr.BOOTSTRAP_REPLICATES):
                            picks = [clusters[int(rng.random() * len(clusters))] for _ in clusters]
                            replicates.append(math.fsum(sums[c] for c in picks) / sum(sizes[c] for c in picks))
                        replicates.sort()
                        for level in (0.95, 0.99):
                            tail = (1 - level) / 2
                            got = contrast["by_clustering"][name]["intervals"]["%g" % level]
                            self.assertAlmostEqual(quantile(replicates, tail), got[0], places=9)
                            self.assertAlmostEqual(quantile(replicates, 1 - tail), got[1], places=9)
                    checked += 1
        self.assertGreater(checked, 0)

    def test_the_predictions_and_the_m2_fits_recompute_from_the_training_labels(self):
        problems, checked = independent.check(self.harness, self.report, self.by_key, holdout_events=self.unsealed)
        self.assertEqual(problems, [])
        self.assertGreater(checked, 0)

    def test_the_descriptive_counts_recompute_from_all_128_events(self):
        for version in d.VERSIONS:
            everything = sorted([e for e in self.harness.versions[version] if not d.is_sealed(e)] + list(self.unsealed[version]), key=fp.event_order)
            self.assertEqual(len(everything), 128)
            for target_id, target in TARGETS.items():
                if target.kind != "binary":
                    continue
                values = [v for v in (target.function(e["labels"]) for e in everything) if v is not None]
                row = self.descriptive["targets"][target_id][version]
                self.assertEqual((row["n_defined"], row["positives"], row["negatives"]), (len(values), sum(1 for v in values if v), sum(1 for v in values if not v)), (target_id, version))
                self.assertEqual(sum(row["defined_by_block"]), row["n_defined"])
                self.assertEqual(sum(row["positives_by_block"]), row["positives"])
                low, high = fp.wilson(row["positives"], row["n_defined"], pr.REPORTING_LEVEL)
                self.assertAlmostEqual(row["wilson_low"], round(low, 6), places=6)
                self.assertAlmostEqual(row["wilson_high"], round(high, 6), places=6)
        # the counts at freeze, which are part of the frozen protocol, are the all-event totals
        for role in ("primary", "descriptive_only", "insufficient_data_by_rule"):
            for item in PROTOCOL["targets"][role]:
                if item.get("kind") == "regression":
                    continue
                frozen = item["counts_at_freeze_all_event"]
                row = self.descriptive["targets"][item["id"]]["all_event"]
                self.assertEqual((row["n_defined"], row["positives"], row["negatives"]), (frozen["n_defined"], frozen["positives"], frozen["negatives"]), item["id"])

    def test_the_sign_checks_use_the_stated_convention_against_the_committed_development_results(self):
        development = p4.development_estimates()
        for target_id in p4.TARGETS:
            for version in d.VERSIONS:
                result = self.report["evaluations"][target_id][version]
                model = h.CONFIRMATORY[result["kind"]]
                contrast = result["contrasts"].get(model)
                if contrast is None:
                    continue
                check = contrast["against_the_development_result"]
                self.assertEqual(check, p4.sign_check(contrast["estimate"], development.get((target_id, version))))
                for pid, other in result["contrasts"].items():
                    if pid != model:
                        self.assertNotIn("against_the_development_result", other)


if __name__ == "__main__":
    unittest.main()
