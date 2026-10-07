"""Phase 2 of Milestone 4: the baselines beyond the pooled rate, on the B-clock primary targets, on the development folds, in both versions.

    python -m nre.m4_phase2 audit [--output PATH]     the structure of the real development folds (cell sizes, events without history): reads which labels are
                                                       defined, never an outcome, and evaluates nothing
    python -m nre.m4_phase2 run --date YYYY-MM-DD      the evaluation itself: needs ALLOW_REAL_EVALUATION, a clean committed tree and no earlier Phase 2 output

The targets are gap_ge_3pct, gap_ge_5pct and day1_close_return (the C0-clock primaries are Phase 3). For each target and version every predictor is fitted
on each development fold's training blocks and scored on its test block; the results are pooled over the folds; every experiment is appended to the
hash-chained experiment log; and the statuses follow the protocol's decision rule. The holdout is not touched. A status is never a claim of an edge.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import m4_data as d
from . import m4_features as feat
from . import m4_harness as h
from . import m4_models as models
from . import m4_protocol as pr
from . import m4_registry as reg
from .core import DataError, canonical, digest

TARGETS = ("gap_ge_3pct", "gap_ge_5pct", "day1_close_return")
NESTED = {"gap_ge_5pct": "gap_ge_3pct"}  # the threshold whose probability caps this one's (M2's monotone repair)
CAPPED = ("M2_logistic", "M2_without_sector")


def predictors_for(target, caps=None):
    return models.binary_predictors(caps) if target.kind == "binary" else models.regression_predictors()


def run_all(harness, targets=TARGETS):
    """{(target_id, version): evaluate() result} for every target and version. A target with a looser nested threshold has its M2 probabilities capped
    by that threshold's (the monotone repair); if the looser threshold's model has no predictions, the capped model is MODEL_FIT_FAILED."""
    out = {}
    for version in d.VERSIONS:
        for target_id in targets:
            target = harness.targets[target_id]
            caps = None
            if target_id in NESTED:
                looser = out[(NESTED[target_id], version)]
                caps = {pid: ({r["event_id"]: r["p"] for r in looser["predictors"][pid]["rows"]} if looser["predictors"][pid]["state"] == h.EVALUATED else {})
                        for pid in CAPPED}
            out[(target_id, version)] = harness.evaluate(target_id, version, predictors_for(target, caps))
    return out


def statuses(harness, evaluations, targets=TARGETS):
    """The decision rule's status for each target's confirmatory model (M2_logistic for the binary targets, M3_ridge_linear for the regression one)."""
    return {t: {h.CONFIRMATORY[harness.targets[t].kind]: harness.status(h.CONFIRMATORY[harness.targets[t].kind],
                                                                       {v: evaluations[(t, v)] for v in d.VERSIONS})} for t in targets}


def plain(value):
    """A result as plain JSON data: models as dicts, tuples as lists."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def without_rows(result):
    """An evaluate() result without its per-event rows (they go to the predictions file)."""
    out = plain(result)
    for run in out["predictors"].values():
        run.pop("rows", None)
        for entry in run["folds"].values():
            entry.pop("rows", None)
    return out


# ---- the structure audit --------------------------------------------------------------------------------------------------------------------

def structure_audit(harness, targets=TARGETS):
    """Facts about the development folds that need only which labels are defined: the cells C2 and C3 will use, which of them fall back to the pooled value,
    which training rows and test events have no earlier event to learn from, and which indicator features are constant. No outcome value is looked at."""
    out = {}
    for target_id in targets:
        target = harness.targets[target_id]
        out[target_id] = {}
        for version in d.VERSIONS:
            folds = {}
            for fold in harness.folds:
                if fold.role != "development":
                    continue
                train, test = d.split(harness.versions[version], harness.blocks, fold)
                train = [e for e in train if target.function(e["labels"]) is not None]
                test = [e for e in test if target.function(e["labels"]) is not None]

                def own_history(event):
                    return [x for x in feat.history(event, train, target) if x["cik"] == event["cik"]]
                cells = {"C2_timing": Counter(e["release_timing"] for e in train), "C3_sector_group": Counter(feat.sector_group(e) for e in train)}
                test_cells = {"C2_timing": Counter(e["release_timing"] for e in test), "C3_sector_group": Counter(feat.sector_group(e) for e in test)}
                small = {name: sorted(k for k, n in counter.items() if n < pr.CELL_MINIMUM) for name, counter in cells.items()}
                indicators = [feat.indicators(e) for e in train]
                folds[fold.name] = {
                    "training_events_with_the_target_defined": len(train), "test_events_with_the_target_defined": len(test),
                    "training_cells": {name: dict(sorted(c.items())) for name, c in cells.items()},
                    "test_events_by_cell": {name: dict(sorted(c.items())) for name, c in test_cells.items()},
                    "cells_below_the_minimum_of_%d" % pr.CELL_MINIMUM: small,
                    "test_events_that_would_fall_back_to_the_pooled_value": {
                        "C2_timing": sum(1 for e in test if e["release_timing"] in small["C2_timing"] or e["release_timing"] not in cells["C2_timing"]),
                        "C3_sector_group": sum(1 for e in test if feat.sector_group(e) in small["C3_sector_group"] or feat.sector_group(e) not in cells["C3_sector_group"])},
                    "training_rows_with_no_earlier_matured_event": sum(1 for e in train if not feat.history(e, train, target)),
                    "test_events_with_no_earlier_matured_event": sum(1 for e in test if not feat.history(e, train, target)),
                    "test_events_with_no_earlier_event_of_their_own_issuer": sum(1 for e in test if not own_history(e)),
                    "indicator_features_constant_in_training": sorted(name for name in ("after_hours", "is_I", "is_other") if len({row[name] for row in indicators}) < 2)}
            out[target_id][version] = folds
    return out


def audit_report(harness):
    return {"schema_version": 1, "kind": "m4_phase2_structure_audit",
            "purpose": ("The structure of the real development folds, taken before any Phase 2 predictor is evaluated: how many training events fall in each cell the C2 and C3 baselines will use, "
                        "which cells have too few and so fall back to the pooled value, and how many training rows and test events have no earlier matured event to learn from (the ridge "
                        "model leaves those training rows out; a test event without one would stop the run). It counts which labels are defined and reads no outcome value: no rate, "
                        "no positive count, no return."),
            "protocol": {"id": harness.protocol["protocol_id"], "version": harness.protocol["protocol_version"], "canonical_sha256": pr.protocol_sha256(harness.protocol)},
            "targets": structure_audit(harness), "holdout": harness.holdout_status(),
            "not_a_claim": ["Not a result: nothing was fitted, scored or evaluated.", "Not Milestone 4 acceptance."]}


# ---- the run ---------------------------------------------------------------------------------------------------------------------------------

def results_report(harness, evaluations, status_by_target, digest_of_evaluations):
    runs = {t: {v: without_rows(evaluations[(t, v)]) for v in d.VERSIONS} for t in TARGETS}
    return {"schema_version": 1, "kind": "m4_phase2_results",
            "purpose": ("The Milestone 4 baselines beyond the pooled rate, fitted on each development fold's training blocks and scored on its test block, for the three B-clock "
                        "primary targets in both versions (all_event and clean_window). The holdout is sealed and the C0-clock targets are not run. Every contrast is model minus "
                        "comparator, lower is better. A status is never a claim of a tradable or production-ready edge."),
            "protocol": {"id": harness.protocol["protocol_id"], "version": harness.protocol["protocol_version"], "canonical_sha256": pr.protocol_sha256(harness.protocol)},
            "scope": {"targets": list(TARGETS), "versions": list(d.VERSIONS), "development_folds": [f.name for f in harness.folds if f.role == "development"],
                      "confirmatory_models": h.CONFIRMATORY, "comparators": h.COMPARATOR, "predictors": {
                          "binary": [p.id for p in models.binary_predictors()], "regression": [p.id for p in models.regression_predictors()]}},
            "determinism": {"evaluated_twice_from_scratch": True, "identical": True, "evaluations_canonical_sha256": digest_of_evaluations},
            "statuses": status_by_target, "evaluations": runs, "holdout": harness.holdout_status(),
            "not_a_claim": ["Not Milestone 4 acceptance.", "Not a claim of a predictive edge: a status says what the development folds can and cannot distinguish.",
                            "Not evidence about any market: the events are a convenience sample of 23 issuers."]}


def prediction_lines(harness, evaluations, generated_at):
    lines = []
    for target_id in TARGETS:
        for version in d.VERSIONS:
            lines += [canonical(r).decode("utf-8") for r in harness.prediction_records(evaluations[(target_id, version)], generated_at)]
    return lines


def run(harness, date, root=pr.ROOT, commit_state=None):
    """The real evaluation. Refuses unless it is authorized, the tree is clean, and neither the logs nor the outputs show an earlier Phase 2 run.

    `commit_state` is (HEAD's hash, whether the tree is clean); it is read from git unless a test supplies it."""
    if not h.ALLOW_REAL_EVALUATION:
        raise h.EvaluationNotAuthorized("ALLOW_REAL_EVALUATION is False")
    root = Path(root)
    commit, clean = commit_state or reg.harness_commit(root)
    if not clean:
        raise DataError("the working tree has uncommitted changes; commit first so that every record names the code that produced it")
    reports = root / "reports"
    results_path, predictions_path = reports / ("m4-phase2-results-%s.json" % date), reports / ("m4-phase2-predictions-%s.jsonl" % date)
    for path in (results_path, predictions_path):
        if path.exists():
            raise DataError("%s exists; Phase 2 is run once" % path.name)
    reg.verify_chain(harness.experiment_log, "experiments", harness.protocol)
    reg.verify_chain(harness.holdout_log, "holdout_access", harness.protocol)
    if len(reg.read(harness.experiment_log)) != 1 or len(reg.read(harness.holdout_log)) != 1:
        raise DataError("a log holds more than its genesis record: Phase 2 starts from empty logs")
    first = run_all(harness)
    second = run_all(harness)
    first_digest = digest(canonical({"%s|%s" % k: plain(v) for k, v in first.items()}))
    if first_digest != digest(canonical({"%s|%s" % k: plain(v) for k, v in second.items()})):
        raise DataError("two evaluations of the same inputs and seeds differ; refusing to record either")
    status_by_target = statuses(harness, first)
    report = results_report(harness, first, status_by_target, first_digest)
    generated_at = reg.now()
    lines = prediction_lines(harness, first, generated_at)
    harness.commit = lambda: commit
    appended = 0
    for target_id in TARGETS:
        for version in d.VERSIONS:
            appended += len(harness.record_experiments(first[(target_id, version)]))
    h.write_report(results_path, report)
    predictions_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"state": "EVALUATED", "harness_commit": commit, "experiment_records": appended, "prediction_records": len(lines), "results": str(results_path),
            "predictions": str(predictions_path), "results_canonical_sha256": digest(canonical(report)), "statuses": status_by_target}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Milestone 4 Phase 2: the structure audit and the development-fold evaluation of the B-clock baselines.")
    parser.add_argument("command", choices=("audit", "run"))
    parser.add_argument("--output", help="audit: write the report here")
    parser.add_argument("--date", help="run: the date to name the outputs (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    harness = h.Harness.from_repository()
    if args.command == "audit":
        report = audit_report(harness)
        summary = {"state": "AUDIT", "report_sha256": digest(canonical(report))}
        if args.output:
            summary["output"] = args.output
            h.write_report(args.output, report)
        print(json.dumps(summary, sort_keys=True))
        return 0
    if not args.date:
        parser.error("run needs --date")
    print(json.dumps(run(harness, args.date), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
