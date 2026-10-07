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
TESTS = ["tests.test_m4_harness", "tests.test_m4_data_features", "tests.test_m4_metrics", "tests.test_m4_registry", "tests.test_m4_models", "tests.test_m4_phase2"]
# a defect in one of these files can only be seen by the test modules that use it, so only those are run for it (any other file's defects get every module)
TESTS_FOR = {"nre/m4_models.py": ["tests.test_m4_models", "tests.test_m4_phase2"], "nre/m4_phase2.py": ["tests.test_m4_phase2"]}
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
    ("predictions are not rounded", "nre/m4_harness.py", "rounded(predictor.predict(model, view_of(e, target)))", "predictor.predict(model, view_of(e, target))"),
    ("diagnostics are not collected", "nre/m4_harness.py", '"diagnostics": dict(getattr(model, "diagnostics", None) or {}), "rows": rows}', '"diagnostics": {}, "rows": rows}'),
    ("the guard ignores the list of authorized targets", "nre/m4_harness.py", "        if self.real and target_id not in REAL_EVALUATION_TARGETS:", "        if False:"),
    ("every model's contrast against C1 is confirmatory", "nre/m4_harness.py",
     '                role = "exploratory"\n                if pid == CONFIRMATORY[target.kind]:', '                role = "confirmatory"\n                if pid == CONFIRMATORY[target.kind]:'),
    ("the all-event contrast is confirmatory too", "nre/m4_harness.py", 'role = "confirmatory" if version == "clean_window" else "companion_of_the_confirmatory_contrast"', 'role = "confirmatory"'),
    ("the 5pct models are not capped", "nre/m4_phase2.py", "            if target_id in NESTED:", "            if False:"),
    ("a clean tree is not required", "nre/m4_phase2.py", "    if not clean:", "    if False:"),
    ("an earlier output is overwritten", "nre/m4_phase2.py", "        if path.exists():", "        if False:"),
    ("two differing evaluations are recorded", "nre/m4_phase2.py", "    if first_digest != digest(", "    if False and first_digest != digest("),
    ("the records name the harness's own commit", "nre/m4_phase2.py", "    harness.commit = lambda: commit\n", "    pass\n"),
    ("the structure audit reads an outcome", "nre/m4_phase2.py", '                train = [e for e in train if target.function(e["labels"]) is not None]', '                train = [e for e in train if target.function(e["labels"])]'),
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
