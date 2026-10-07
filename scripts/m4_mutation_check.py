"""Does the Milestone 4 test suite notice when the harness is wrong?

Each entry below is one deliberate defect: a single exact piece of source text in the harness and what it is replaced by. For each, this script copies the
repository to a temporary directory, makes that one change in the copy, and runs the Milestone 4 tests there. A defect that leaves every test green is a
hole in the tests, and is reported NOT CAUGHT. The repository itself is never modified.

    python scripts/m4_mutation_check.py            # every defect (about ten minutes)
    python scripts/m4_mutation_check.py history    # only defects whose description contains "history"
    python scripts/m4_mutation_check.py --list     # the defects, without running anything
    python scripts/m4_mutation_check.py --check-patterns   # does each defect's source text still occur exactly once? (fast; run by the tests)

A defect whose source text has changed is reported SKIPPED, never CAUGHT, so a refactor cannot quietly turn this check into a pass.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ["tests.test_m4_harness", "tests.test_m4_data_features", "tests.test_m4_metrics", "tests.test_m4_registry", "tests.test_m4_models", "tests.test_m4_phase2",
         "tests.test_m4_phase3", "tests.test_m4_phase4"]
# a defect in one of these files can only be seen by the test modules that use it, so only those are run for it (any other file's defects get every module)
TESTS_FOR = {"nre/m4_models.py": ["tests.test_m4_models", "tests.test_m4_phase2", "tests.test_m4_phase3"],
             "nre/m4_phase2.py": ["tests.test_m4_phase2", "tests.test_m4_phase3", "tests.test_m4_phase3_record"],
             "nre/m4_phase3.py": ["tests.test_m4_phase3", "tests.test_m4_phase3_record"],
             "nre/m4_phase4.py": ["tests.test_m4_phase4", "tests.test_m4_phase4_rehearsal", "tests.test_m4_phase4_record"],
             "nre/m4_report.py": ["tests.test_m4_report"]}
COPIED = ("nre", "tests", "config", "reports")

MUTATIONS = [
    # leakage: what a prediction may learn from
    ("history ignores the earlier-session rule", "nre/m4_features.py", 'and e["reaction_session"] < event["reaction_session"]\n', "\n"),
    ("history ignores label maturity", "nre/m4_features.py", 'and all(e["available_at"][name] <= event["cutoff"] for name in target.source_labels)]', "]"),
    ("the group prior ignores the 10-event minimum", "nre/m4_features.py", "    if len(members) >= pr.GROUP_PRIOR_MINIMUM:", "    if len(members) >= 1:"),
    ("the issuer history uses all issuers", "nre/m4_features.py", '    own = [v for e, v in defined if e["cik"] == event["cik"]]\n    k, n = sum(1 for v in own if v), len(own)',
     "    own = [v for e, v in defined]\n    k, n = sum(1 for v in own if v), len(own)"),
    ("a fold trains on its test block too", "nre/m4_data.py", '    train = [e for e in events if blocks[e["event_id"]] in fold.train_blocks]',
     '    train = [e for e in events if blocks[e["event_id"]] in fold.train_blocks + (fold.test_block,)]'),
    ("the fit sees the test events", "nre/m4_harness.py", "                model = predictor.fit(train, target)", "                model = predictor.fit(train + [e for e, _ in tests], target)"),
    ("a predictor is shown the labels", "nre/m4_harness.py", '    view = {k: v for k, v in event.items() if k not in ("labels", "labels_sha256")}', "    view = dict(event)"),
    ("a predictor is shown the digest of the labels", "nre/m4_harness.py", '    view = {k: v for k, v in event.items() if k not in ("labels", "labels_sha256")}',
     '    view = {k: v for k, v in event.items() if k != "labels"}'),
    ("the C0 opening gap is the close", "nre/m4_harness.py", 'view["open_gap"] = event["labels"]["day1_open_return"]["value"]', 'view["open_gap"] = event["labels"]["day1_close_return"]["value"]'),
    ("the C0 prediction time is the cutoff", "nre/m4_harness.py", '\n        when = self.inputs["calendar"].bounds(event["reaction_session"])[0] if target.clock == "C0" else event["cutoff"]',
     '\n        when = event["cutoff"]'),
    ("the C0 prediction time is the cutoff in the bulk records", "nre/m4_harness.py",
     '                    when = self.inputs["calendar"].bounds(event["reaction_session"])[0] if target.clock == "C0" else event["cutoff"]',
     '                    when = event["cutoff"]'),
    # leakage: label maturity and clusters
    ("maturity assertion never raises", "nre/m4_data.py", "if slack < 0:", "if slack < -1e9:"),
    ("clusters check does nothing", "nre/m4_data.py", '    for key, label in (("reaction_session", "reaction session"), ("cluster_id", "cluster")):', "    for key, label in ():"),
    # the sealed holdout
    ("sealed labels return something instead of raising", "nre/m4_data.py", '    def __getitem__(self, key):\n        self._deny("read of " + repr(key))',
     '    def __getitem__(self, key):\n        return {"value": None, "reason": "x"}'),
    ("look unseals before logging", "nre/m4_harness.py",
     '        reg.append(self.holdout_log, "holdout_access", record, self.protocol)\n        return {version: self.gate.unseal(sealed, version) for version in d.VERSIONS}',
     '        out = {version: self.gate.unseal(sealed, version) for version in d.VERSIONS}\n        reg.append(self.holdout_log, "holdout_access", record, self.protocol)\n        return out'),
    ("look ignores the tripwire", "nre/m4_harness.py", "        if not ALLOW_HOLDOUT_LOOK:\n            raise d.HoldoutNotAuthorized", "        if False:\n            raise d.HoldoutNotAuthorized"),
    ("evaluation ignores the tripwire", "nre/m4_harness.py", "        if self.real and not ALLOW_REAL_EVALUATION:", "        if False:"),
    ("the loader reads the holdout records", "nre/m4_data.py", '            event = _event(entry, calendar, sectors, placeholder)\n            event["labels"] = SealedLabels(entry["event_id"], gate)',
     '            event = _event(entry, calendar, sectors, placeholder)\n            load_labels(entry["event_id"])\n            event["labels"] = SealedLabels(entry["event_id"], gate)'),
    ("the holdout block is the first block", "nre/m4_data.py", "    if holdout_block != max(blocks.values()):", "    if False:"),
    ("the holdout fold is evaluated", "nre/m4_harness.py", '            if fold.role == "development":\n                test_values = d.target_values(target, test)',
     "            if True:\n                test_values = d.target_values(target, test)"),
    # thresholds, versions and abstention
    ("the enough rule is 9 not 10", "nre/m4_protocol.py", "MIN_POSITIVES = MIN_NEGATIVES = 10", "MIN_POSITIVES = MIN_NEGATIVES = 9"),
    ("forty training events is not enough", "nre/m4_data.py", "    if len(train_events) < pr.MIN_TRAIN_EVENTS:", "    if len(train_events) <= pr.MIN_TRAIN_EVENTS:"),
    ("the fold-level rule is not applied", "nre/m4_data.py",
     '    c = counts(train_values)\n    reason = shortfall(c)\n    return {"state": EVALUABLE if reason is None else INSUFFICIENT_DATA, "reason": reason, "train": c}',
     '    c = counts(train_values)\n    return {"state": EVALUABLE, "reason": None, "train": c}'),
    ("pooled test includes folds that were excluded", "nre/m4_harness.py",
     """                if entry["state"] == d.EVALUABLE:
                    usable.append((fold, [e for e, v in zip(train, train_values) if v is not None], [(e, v) for e, v in zip(test, test_values) if v is not None]))
                    pooled_values += test_values""",
     """                pooled_values += test_values
                if entry["state"] == d.EVALUABLE:
                    usable.append((fold, [e for e, v in zip(train, train_values) if v is not None], [(e, v) for e, v in zip(test, test_values) if v is not None]))"""),
    ("clean window is the all-event version", "nre/m4_data.py",
     '        clean.append(event if not names or is_sealed(event) else {**event, "labels": mask_labels(event["labels"], names)})', "        clean.append(event)"),
    ("insufficient data still predicts", "nre/m4_harness.py", '        if pooled["state"] != d.EVALUABLE:\n            run["state"], run["reason"] = d.INSUFFICIENT_DATA, pooled["reason"]',
     '        if False:\n            run["state"], run["reason"] = d.INSUFFICIENT_DATA, pooled["reason"]'),
    ("a failed fit is replaced by the comparator", "nre/m4_harness.py", "                failure = failure or abstention\n                continue", "                failure = None\n                continue"),
    # metrics, intervals and the decision rule
    ("the decision rule's better is flipped", "nre/m4_metrics.py", "    if high < 0 and estimate is not None and estimate < 0:", "    if high > 0 and estimate is not None and estimate < 0:"),
    ("the contrast sign is reversed", "nre/m4_harness.py",
     'differences = [m.event_brier(a["p"], a["y"]) - m.event_brier(b["p"], b["y"]) for a, b in zip(model_rows, base_rows)]',
     'differences = [m.event_brier(b["p"], b["y"]) - m.event_brier(a["p"], a["y"]) for a, b in zip(model_rows, base_rows)]'),
    ("the headline is the narrower interval", "nre/m4_metrics.py", '            if best is None or high - low > best["high"] - best["low"]:',
     '            if best is None or high - low < best["high"] - best["low"]:'),
    ("the bootstrap resamples events not clusters", "nre/m4_metrics.py", "    ids = sorted(set(clusters))", "    clusters = list(range(len(clusters)))\n    ids = sorted(set(clusters))"),
    ("the bootstrap is not seeded", "nre/m4_metrics.py", "    rng = random.Random(seed)\n    m = len(ids)", "    rng = random.Random()\n    m = len(ids)"),
    ("the random ranking is not seeded", "nre/m4_metrics.py", "    rng = random.Random(seed)\n    values = []", "    rng = random.Random()\n    values = []"),
    ("reliability uses five bins", "nre/m4_protocol.py", "MAX_RELIABILITY_BINS, MIN_PER_BIN = 4, 10", "MAX_RELIABILITY_BINS, MIN_PER_BIN = 5, 10"),
    ("precision at k ranks ascending", "nre/m4_metrics.py", "    return sorted(range(len(scores)), key=lambda i: (-scores[i], keys[i]))", "    return sorted(range(len(scores)), key=lambda i: (scores[i], keys[i]))"),
    ("the confusion threshold is strict", "nre/m4_metrics.py", "        called = score >= threshold", "        called = score > threshold"),
    ("average precision breaks ties by order", "nre/m4_metrics.py", "        while j < len(order) and scores[order[j]] == scores[order[i]]:\n            j += 1", "        j = i + 1"),
    ("the pooled quantiles are not type 7", "nre/m4_harness.py", '"quantiles": [fp.quantile(values, q) for q in pr.QUANTILE_LEVELS]',
     '"quantiles": [values[int(q * len(values))] for q in pr.QUANTILE_LEVELS]'),
    # integrity and the logs
    ("the protocol hash is not checked", "nre/m4_protocol.py", '    check("protocol_hash", actual == recorded,', '    check("protocol_hash", True,'),
    ("a pinned file is not checked", "nre/m4_protocol.py", '        check("pinned_file:" + key, got == pins[key]["canonical_sha256"], pins[key]["path"])', '        check("pinned_file:" + key, True, pins[key]["path"])'),
    ("the derived-labels map is not checked", "nre/m4_protocol.py", '    check("derived_labels_map", {k: list(v) for k, v in cs.DERIVED.items()} == {k: list(v) for k, v in derived_map.items()},',
     '    check("derived_labels_map", True,'),
    ("the cross-check finds nothing", "nre/m4_harness.py", "        return problems\n\n    def holdout_status", "        return []\n\n    def holdout_status"),
    ("the registry does not chain", "nre/m4_registry.py", '    written = {**record, "previous_record_sha256": rows[-1][1] if rows else None}', '    written = {**record, "previous_record_sha256": None}'),
    ("the log reader keeps carriage returns", "nre/m4_registry.py", '        raw = raw.rstrip(b"\\r")', "        pass"),
    ("a second genesis is allowed", "nre/m4_registry.py", '    if is_genesis != (not rows):\n        raise DataError("a genesis record is written once, first, and only first")',
     '    if False:\n        raise DataError("x")'),
    ("a log may start without a genesis", "nre/m4_registry.py",
     """        if number == 0:
            if record.get("kind") != "genesis" or record.get("log") != kind:
                raise DataError("%s: the first record must be the %s log's genesis" % (path, kind))""", "        if number == 0:\n            pass"),
    # Phase 2: the baselines
    ("the logistic penalty is not applied", "nre/m4_models.py", "    penalty = [0.0] + [pr.RIDGE_LAMBDA] * (k - 1)", "    penalty = [0.0] * k"),
    ("the logistic intercept is penalized", "nre/m4_models.py", "    penalty = [0.0] + [pr.RIDGE_LAMBDA] * (k - 1)", "    penalty = [pr.RIDGE_LAMBDA] * k"),
    ("the ridge intercept is penalized", "nre/m4_models.py", "(pr.RIDGE_LAMBDA if i == j and i > 0 else 0.0)", "(pr.RIDGE_LAMBDA if i == j else 0.0)"),
    ("standardization uses the sample standard deviation", "nre/m4_models.py", "for x in column) / n)", "for x in column) / (n - 1))"),
    ("a constant feature is not dropped", "nre/m4_models.py", "        (dropped if sd <= ZERO_SD * max(1.0, abs(mean)) else kept).append(j)", "        kept.append(j)"),
    ("Newton stops after one step", "nre/m4_models.py", "        if max(abs(s) for s in step) < pr.NEWTON_TOLERANCE:", "        if True:"),
    ("a rate cell of exactly ten falls back", "nre/m4_models.py", '        if cell is None or cell["n"] < pr.CELL_MINIMUM:\n            model.diagnostics["fallbacks_to_the_pooled_rate"] += 1',
     '        if cell is None or cell["n"] <= pr.CELL_MINIMUM:\n            model.diagnostics["fallbacks_to_the_pooled_rate"] += 1'),
    ("a quantile cell of exactly ten falls back", "nre/m4_models.py", '        if cell is None or cell["n"] < pr.CELL_MINIMUM:\n            model.diagnostics["fallbacks_to_the_pooled_quantiles"] += 1',
     '        if cell is None or cell["n"] <= pr.CELL_MINIMUM:\n            model.diagnostics["fallbacks_to_the_pooled_quantiles"] += 1'),
    ("a fallback is not counted", "nre/m4_models.py", '            model.diagnostics["fallbacks_to_the_pooled_rate"] += 1', "            pass"),
    ("C3 uses the timing cell", "nre/m4_models.py", '    return CellRate("C3_sector_group_rate", sector_cell)', '    return CellRate("C3_sector_group_rate", timing_cell)'),
    ("the issuer rate is not clipped", "nre/m4_models.py", "    return min(max(rate, pr.RATE_CLIP[0]), pr.RATE_CLIP[1])", "    return rate"),
    ("C4 is the prior rather than the shrunk rate", "nre/m4_models.py", '        return result["rate"]', '        return result["prior"]'),
    ("the without-sector logistic keeps the sector indicators", "nre/m4_models.py",
     '        row = [indicators["after_hours"]] + ([indicators["is_I"], indicators["is_other"]] if self.with_sector else [])\n        row.append(logit(',
     '        row = [indicators["after_hours"]] + ([indicators["is_I"], indicators["is_other"]] if True else [])\n        row.append(logit('),
    ("the logistic fits events whose target is absent", "nre/m4_models.py", "        defined = [(e, v) for e, v in zip(train, d.target_values(target, train)) if v is not None]",
     "        defined = [(e, v) for e, v in zip(train, d.target_values(target, train))]"),
    ("the monotone repair is not applied", "nre/m4_models.py", '                p = self.cap[view["event_id"]]', "                p = p"),
    ("the monotone repair is not counted", "nre/m4_models.py", '                model.diagnostics["repairs_of_the_nested_threshold"] += 1', "                pass"),
    ("an empty cap goes uncapped", "nre/m4_models.py", "        if self.cap is not None and not self.cap:", "        if False:"),
    ("the ridge model does not leave out rows without history", "nre/m4_models.py", "            except ProtocolGap:\n                excluded.append", "            except KeyError:\n                excluded.append"),
    ("the ridge model fits on twenty rows", "nre/m4_models.py", "        if len(rows) < pr.MIN_TRAIN_EVENTS:", "        if len(rows) < 20:"),
    ("the ridge residual quantiles are at the wrong levels", "nre/m4_models.py", "        residual_quantiles = [fp.quantile(residuals, q) for q in pr.QUANTILE_LEVELS]",
     "        residual_quantiles = [fp.quantile(residuals, q) for q in (0.05, 0.5, 0.95)]"),
    ("the ridge forecast omits the fitted mean", "nre/m4_models.py", '        return tuple(mean + q for q in c["residual_quantiles"])', '        return tuple(q for q in c["residual_quantiles"])'),
    ("the logistic penalty constant is two", "nre/m4_protocol.py", "RIDGE_LAMBDA = 1.0", "RIDGE_LAMBDA = 2.0"),
    ("the Newton iteration limit is fifty", "nre/m4_protocol.py", "NEWTON_TOLERANCE, NEWTON_MAX_ITERATIONS = 1e-8, 100", "NEWTON_TOLERANCE, NEWTON_MAX_ITERATIONS = 1e-8, 50"),
    # Phase 2: the harness extensions and the runner
    ("predictions are not rounded", "nre/m4_harness.py",
     "            base = self._baseline_rate(target, train)\n            rows = [self._row(e, v, rounded(predictor.predict(model, view_of(e, target))), fold, base) for e, v in tests]",
     "            base = self._baseline_rate(target, train)\n            rows = [self._row(e, v, predictor.predict(model, view_of(e, target)), fold, base) for e, v in tests]"),
    ("diagnostics are not collected", "nre/m4_harness.py", '"diagnostics": dict(getattr(model, "diagnostics", None) or {}), "rows": rows}', '"diagnostics": {}, "rows": rows}'),
    ("the guard ignores the list of authorized targets", "nre/m4_harness.py", "        if self.real and target_id not in REAL_EVALUATION_TARGETS:", "        if False:"),
    ("every model's contrast against C1 is confirmatory", "nre/m4_harness.py",
     '                role, note = "exploratory", {}\n                if pid == CONFIRMATORY[target.kind]:', '                role, note = "confirmatory", {}\n                if pid == CONFIRMATORY[target.kind]:'),
    ("the all-event contrast is confirmatory too", "nre/m4_harness.py", '                    elif clean_evaluable:\n                        role = "companion_of_the_confirmatory_contrast"',
     '                    elif clean_evaluable:\n                        role = "confirmatory"'),
    ("the 5pct models are not capped", "nre/m4_phase2.py", "            if target_id in NESTED:", "            if False:"),
    ("a clean tree is not required", "nre/m4_phase2.py", "    if not clean:", "    if False:"),
    ("an earlier output is overwritten", "nre/m4_phase2.py", "        if path.exists():", "        if False:"),
    ("two differing evaluations are recorded", "nre/m4_phase2.py", "    if first_digest != digest(", "    if False and first_digest != digest("),
    ("the records name the harness's own commit", "nre/m4_phase2.py", "    harness.commit = lambda: commit\n", "    pass\n"),
    ("the structure audit reads an outcome", "nre/m4_phase2.py", '                train = [e for e in train if target.function(e["labels"]) is not None]', '                train = [e for e in train if target.function(e["labels"])]'),
    # Phase 3: the C0 clock, and the runner for a later phase
    ("the companion role ignores whether the clean-window version can be evaluated", "nre/m4_harness.py", "                    elif clean_evaluable:\n", "                    elif True:\n"),
    ("the companion role is given when the clean-window version cannot be evaluated", "nre/m4_harness.py",
     'self._prepare(target, "clean_window")[0]["pooled_development_test"]["state"] == d.EVALUABLE', 'self._prepare(target, "clean_window")[0]["pooled_development_test"]["state"] != d.EVALUABLE'),
    ("the clean-window check looks at the all-event version", "nre/m4_harness.py",
     'self._prepare(target, "clean_window")[0]["pooled_development_test"]["state"] == d.EVALUABLE', 'self._prepare(target, "all_event")[0]["pooled_development_test"]["state"] == d.EVALUABLE'),
    ("the all-event contrast is confirmatory when the clean-window one cannot be", "nre/m4_harness.py",
     '                    if version == "clean_window":\n                        role = "confirmatory"', '                    if version == "clean_window" or not clean_evaluable:\n                        role = "confirmatory"'),
    ("an exploratory contrast does not say why", "nre/m4_harness.py", '{"role": role, **note, "baseline": COMPARATOR[target.kind],', '{"role": role, "baseline": COMPARATOR[target.kind],'),
    ("an absent opening return is accepted", "nre/m4_models.py", '    if value is None:\n        raise ProtocolGap("event %s has no opening return', '    if False:\n        raise ProtocolGap("event %s has no opening return'),
    ("a label wins over the supplied opening gap", "nre/m4_models.py", '    value = event["open_gap"] if "open_gap" in event else event["labels"]["day1_open_return"]["value"]',
     '    value = event["labels"]["day1_open_return"]["value"] if "labels" in event else event["open_gap"]'),
    ("M2 leaves the opening gap out on the C0 clock", "nre/m4_models.py", '        if target.clock == "C0":\n            row.append(open_gap(event))', '        if False:\n            row.append(open_gap(event))'),
    ("M2 names the opening gap on the B clock too", "nre/m4_models.py", '+ (["open_gap"] if target.clock == "C0" else []))', '+ (["open_gap"]))'),
    ("a later phase starts from a log of any length", "nre/m4_phase2.py", "    if len(experiments) != phase.log_records_before or len(accesses) != 1:", "    if len(accesses) != 1:"),
    ("a later phase ignores experiments on other targets", "nre/m4_phase2.py", '    if {record["target_id"] for record, _ in experiments[1:]} - set(phase.earlier_targets):', "    if False:"),
    ("a later phase names its outputs as Phase 2's", "nre/m4_phase2.py", '("m4-phase%d-results-%s.json" % (phase.number, date))', '("m4-phase%d-results-%s.json" % (2, date))'),
    ("a later phase evaluates Phase 2's targets", "nre/m4_phase2.py", "    first = run_all(harness, phase.targets)", "    first = run_all(harness, TARGETS)"),
    ("the C0 audit facts are reported for the B clock too", "nre/m4_phase2.py", '                if target.clock == "C0":  # M2 takes the opening gap', '                if True:  # M2 takes the opening gap'),
    ("the audit counts training rows from the test block", "nre/m4_phase2.py",
     '"training_rows_with_an_undefined_opening_gap"] = sum(1 for e in train if', '"training_rows_with_an_undefined_opening_gap"] = sum(1 for e in test if'),
    ("the audit counts the events that have an opening gap", "nre/m4_phase2.py",
     '"test_events_with_an_undefined_opening_gap"] = sum(1 for e in test if e["labels"]["day1_open_return"]["value"] is None)',
     '"test_events_with_an_undefined_opening_gap"] = sum(1 for e in test if e["labels"]["day1_open_return"]["value"] is not None)'),
    ("Phase 3 evaluates one of its two targets", "nre/m4_phase3.py", 'TARGETS = ("extension_after_open_ge_5pct", "loses_half_of_gap")', 'TARGETS = ("extension_after_open_ge_5pct",)'),
    ("Phase 3 expects the wrong number of earlier records", "nre/m4_phase3.py", "3, TARGETS, 1 + 2 * (18 + 18 + 15), p2.TARGETS,", "3, TARGETS, 1 + 2 * (18 + 18), p2.TARGETS,"),
    ("Phase 3 expects no earlier targets", "nre/m4_phase3.py", "3, TARGETS, 1 + 2 * (18 + 18 + 15), p2.TARGETS,", "3, TARGETS, 1 + 2 * (18 + 18 + 15), (),"),
    ("Phase 3 is numbered Phase 2", "nre/m4_phase3.py", "3, TARGETS, 1 + 2 * (18 + 18 + 15), p2.TARGETS,", "2, TARGETS, 1 + 2 * (18 + 18 + 15), p2.TARGETS,"),
    ("Phase 3's command line runs Phase 2", "nre/m4_phase3.py", "    return p2.main(argv, phase=PHASE_3)", "    return p2.main(argv)"),
    # Phase 4: the holdout evaluation in the harness
    ("the holdout fold is the second development fold", "nre/m4_harness.py", "        fold = self.holdout_fold()\n        train, sealed_test = d.split(", "        fold = self.folds[1]\n        train, sealed_test = d.split("),
    ("the holdout rule is not applied", "nre/m4_harness.py", '        elif held["state"] != d.EVALUABLE:\n            result["state"] = d.COUNTS_ONLY', '        elif False:\n            result["state"] = d.COUNTS_ONLY'),
    ("the fold-level rule is not applied to the holdout fold", "nre/m4_harness.py", '        if entry["state"] != d.EVALUABLE:\n            result["state"], result["reason"] = d.INSUFFICIENT_DATA',
     '        if False:\n            result["state"], result["reason"] = d.INSUFFICIENT_DATA'),
    ("a counts-only target is still fitted", "nre/m4_harness.py", '        if result["state"] is not None:\n            for predictor in predictors:', '        if result["state"] is not None and False:\n            for predictor in predictors:'),
    ("any events are accepted as the holdout's", "nre/m4_harness.py", '        if [e["event_id"] for e in test] != [e["event_id"] for e in sealed_test] or any(d.is_sealed(e) for e in test):', "        if False:"),
    ("the confirmatory holdout contrast is not labelled", "nre/m4_harness.py", '                role = "holdout_replication_check" if pid == CONFIRMATORY[target.kind] else "exploratory"', '                role = "exploratory"'),
    ("a holdout contrast claims something", "nre/m4_harness.py", '        no_claim = "none: the holdout alone never creates a claim"', '        no_claim = "a claim"'),
    ("the holdout metrics use the pooled K values", "nre/m4_harness.py", '"rows": rows, "metrics": self._metrics(target, rows, pr.PRECISION_K_FOLD),', '"rows": rows, "metrics": self._metrics(target, rows, pr.PRECISION_K_POOLED),'),
    ("the Wilson interval of a counts-only target is reversed", "nre/m4_harness.py", "wilson_low=low, wilson_high=high, wilson_level=pr.REPORTING_LEVEL)", "wilson_low=high, wilson_high=low, wilson_level=pr.REPORTING_LEVEL)"),
    ("a holdout prediction on the C0 clock is timed at the cutoff", "nre/m4_harness.py",
     'event = by_id[row["event_id"]]\n                when = self.inputs["calendar"].bounds(event["reaction_session"])[0] if target.clock == "C0" else event["cutoff"]',
     'event = by_id[row["event_id"]]\n                when = event["cutoff"]'),
    ("holdout experiments are recorded on a development fold", "nre/m4_harness.py", 'result, fold.name, self._train_ids(result["version"], fold.name), run.get("rows", []),',
     'result, "dev_test_block_3", self._train_ids(result["version"], fold.name), run.get("rows", []),'),
    ("a holdout experiment record always says EVALUATED", "nre/m4_harness.py", 'metrics, method if run["state"] == EVALUATED else "none", run["state"]))', 'metrics, method if run["state"] == EVALUATED else "none", EVALUATED))'),
    # Phase 4: the one-look runner and what it computes
    ("a run starts from a log of any length", "nre/m4_phase4.py", "    if len(experiments) != EXPERIMENTS_BEFORE or len(accesses) != 1:", "    if len(accesses) != 1:"),
    ("a run starts from a holdout log that already holds an access", "nre/m4_phase4.py", "    if len(experiments) != EXPERIMENTS_BEFORE or len(accesses) != 1:", "    if len(experiments) != EXPERIMENTS_BEFORE:"),
    ("holdout experiments already in the log are ignored", "nre/m4_phase4.py", '    if {record["target_id"] for record, _ in experiments[1:]} - set(TARGETS) or any(record["fold"] == harness.holdout_fold().name for record, _ in experiments[1:]):',
     '    if {record["target_id"] for record, _ in experiments[1:]} - set(TARGETS):'),
    ("the development results are not checked against their hashes", "nre/m4_phase4.py", '        if digest(canonical(results)) != completion["evaluation"]["results_canonical_sha256"]:', "        if False:"),
    ("the sign check always agrees", "nre/m4_phase4.py", '"same_sign": holdout_sign == development_sign and holdout_sign != 0,', '"same_sign": True,'),
    ("zero has a sign", "nre/m4_phase4.py", "    return (value > 0) - (value < 0)", "    return (value >= 0) - (value < 0)"),
    ("the nested cap is not applied at the holdout", "nre/m4_phase4.py", "            if target_id in p2.NESTED:", "            if False:"),
    ("the descriptive report leaves out a holdout event", "nre/m4_phase4.py", "        events = sorted(visible + list(unsealed[version]), key=fp.event_order)", "        events = sorted(visible + list(unsealed[version])[:-1], key=fp.event_order)"),
    ("the runner covers four of the five primaries", "nre/m4_phase4.py", "TARGETS = p2.TARGETS + p3.TARGETS  # the five primaries", "TARGETS = p2.TARGETS + p3.TARGETS[:1]  # the five primaries"),
    ("the second evaluation takes a second look", "nre/m4_phase4.py", "    second = evaluate_all(harness, unsealed)", "    second = evaluate_all(harness, harness.look(LOOK_REASON))"),
    ("the audit reads the test events' labels", "nre/m4_phase4.py", '            defined = [e for e in train if target.function(e["labels"]) is not None]', '            defined = [e for e in train + test if target.function(e["labels"]) is not None]'),
    ("the results report omits the selection-regime statement", "nre/m4_phase4.py", '            "selection_regime": harness.protocol["holdout"]["selection_regime"], "what_it_is_for"', '            "what_it_is_for"'),
    ("the look does not name itself the one look", "nre/m4_phase4.py", 'LOOK_REASON = ("Milestone 4 Phase 4: the one look at the final holdout', 'LOOK_REASON = ("Milestone 4 Phase 4: a look at the final holdout'),
    ("a value that cannot be written is found only after the records are appended", "nre/m4_phase4.py", "    for document in (report, descriptive):\n        json.dumps(document, allow_nan=False)",
     "    for document in ():\n        json.dumps(document, allow_nan=False)"),
    # Phase 4: the Milestone 4 report
    ("the report accepts a development result that does not match its hash", "nre/m4_report.py", '        if digest(canonical(results)) != records[phase]["completion"]["evaluation"]["results_canonical_sha256"]:', "        if False:"),
    ("the report does not check the protocol against its freeze record", "nre/m4_report.py", '    if protocol_sha != freeze["protocol"]["canonical_sha256"]:', "    if False:"),
    ("the report counts the genesis as an access", "nre/m4_report.py", "    accesses = [record for record, _ in reg.read(holdout_log)][1:]", "    accesses = [record for record, _ in reg.read(holdout_log)][:1]"),
    ("the looked-at-once criterion is always met", "nre/m4_report.py", '         "met_by_the_evidence": len(accesses) == 1},', '         "met_by_the_evidence": True},'),
    ("an interval that excludes zero is miscounted", "nre/m4_report.py", '"excludes_zero_at_95": contrast["headline"]["0.95"]["low"] > 0 or contrast["headline"]["0.95"]["high"] < 0,',
     '"excludes_zero_at_95": contrast["headline"]["0.95"]["low"] > 0 or contrast["headline"]["0.95"]["high"] < -1,'),
]


def occurrences(mutation):
    name, relative, old, new = mutation
    return (ROOT / relative).read_text(encoding="utf-8").count(old)


def run(mutation):
    name, relative, old, new = mutation
    with tempfile.TemporaryDirectory() as directory:
        copy = Path(directory)
        for part in COPIED:
            shutil.copytree(ROOT / part, copy / part, ignore=shutil.ignore_patterns("__pycache__"))
        path = copy / relative
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            return "SKIPPED", "the source text occurs %d times, not once" % text.count(old)
        path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        proc = subprocess.run([sys.executable, "-m", "unittest"] + TESTS_FOR.get(relative, TESTS), cwd=copy, capture_output=True, text=True, timeout=900)
        failing = sorted({line.split(" (")[0].replace("FAIL: ", "").replace("ERROR: ", "").strip()
                          for line in proc.stderr.splitlines() if line.startswith(("FAIL:", "ERROR:"))})
        return ("CAUGHT" if proc.returncode != 0 else "NOT CAUGHT"), "; ".join(failing[:2])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("only", nargs="*", help="run only the defects whose description contains one of these words")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check-patterns", action="store_true")
    parser.add_argument("--from-number", type=int, default=1, help="start at this defect (1-based, as --list numbers them); for resuming or running only the later ones")
    parser.add_argument("--to-number", type=int, default=10 ** 6, help="stop after this defect, so that several runs can share the list")
    args = parser.parse_args(argv)
    chosen = [m for number, m in enumerate(MUTATIONS, 1) if args.from_number <= number <= args.to_number and (not args.only or any(word in m[0] for word in args.only))]
    if args.list:
        print("\n".join(m[0] for m in chosen))
        return 0
    if args.check_patterns:
        bad = [m[0] for m in MUTATIONS if occurrences(m) != 1]
        print("every defect's source text occurs exactly once" if not bad else "source text missing or repeated for: " + "; ".join(bad))
        return 1 if bad else 0
    verdicts = {}
    for mutation in chosen:
        verdict, detail = run(mutation)
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        print("%-11s %s%s" % (verdict, mutation[0], ("\n            first failing test: " + detail) if detail else ""), flush=True)
    print("\n" + ", ".join("%d %s" % (n, v) for v, n in sorted(verdicts.items())) + " of %d" % len(chosen))
    return 0 if set(verdicts) == {"CAUGHT"} else 1


if __name__ == "__main__":
    sys.exit(main())
