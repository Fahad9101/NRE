"""Phase 4 of Milestone 4: the one look at the final holdout (block 5), and everything computed inside it.

    python -m nre.m4_phase4 audit [--output PATH]     the structure of the holdout fold, taken before the look: reads which labels are defined for the TRAINING events and
                                                       the metadata of the 23 test events, never a block-5 outcome, and evaluates nothing
    python -m nre.m4_phase4 run --date YYYY-MM-DD      THE LOOK: needs ALLOW_HOLDOUT_LOOK, a clean committed tree, no earlier Phase 4 output, the experiment log exactly as
                                                       Phase 3 left it and the holdout log holding only its genesis. It calls Harness.look once.

The frozen protocol's rule (config/m4-protocol.json, holdout): every pre-registered predictor on every primary target, in both versions, trained on blocks 1 to 4, evaluated
once and together; nothing is selected; all of it is reported. Where the holdout's own thresholds are not met a target-version is COUNTS_ONLY. The holdout alone never creates a
claim. Everything after the look is a pure function of the events it returned: no code here unseals anything itself.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import fingerprints as fp
from . import m4_data as d
from . import m4_features as feat
from . import m4_harness as h
from . import m4_phase2 as p2
from . import m4_phase3 as p3
from . import m4_protocol as pr
from . import m4_registry as reg
from . import m4_scoping_evidence as ev
from .core import DataError, canonical, digest

TARGETS = p2.TARGETS + p3.TARGETS  # the five primaries, the looser gap threshold before the one it caps
LOOK_REASON = ("Milestone 4 Phase 4: the one look at the final holdout (block 5, the 23 Milestone 1 events) under protocol version 1: every pre-registered predictor on the five "
               "primary targets, in both versions, together")
EXPERIMENTS_BEFORE = p3.PHASE_3.log_records_before + 2 * (18 + 18)  # the genesis record, Phase 2's 102 experiments and Phase 3's 72
BINARY_TARGETS = 4  # gap_ge_3pct, gap_ge_5pct, extension_after_open_ge_5pct, loses_half_of_gap
EXPECTED_RECORDS = BINARY_TARGETS * 6 * 2 + 1 * 5 * 2  # six binary predictors and five regression ones, in two versions
DEVELOPMENT_RESULTS = {"phase2": ("reports/m4-phase2-results-2026-10-07.json", "reports/m4-phase2-completion-2026-10-07.json"),
                       "phase3": ("reports/m4-phase3-results-2026-10-07.json", "reports/m4-phase3-completion-2026-10-07.json")}
NOT_A_CLAIM = ["Not a claim: the holdout alone never creates one, and no status is assigned from it.",
               "Not evidence about any market: a convenience sample of 23 issuers, and block 5 is entirely Milestone 1 events (time and selection regime are confounded).",
               "Not Milestone 4 acceptance: that decision is the owner's."]


# ---- the audit taken before the look ---------------------------------------------------------------------------------------------------------

def holdout_structure_audit(harness, targets=TARGETS):
    """Facts about the holdout fold that need no block-5 outcome: the training events' cells and history, and the metadata of the 23 test events (release timing, sector, issuer,
    reaction session, cutoff), counted over all 23 whether or not a target is defined for them (that depends on outcomes). On the C0 clock the test events' opening gaps are
    outcomes too and are not read: they are read only in the look."""
    out = {}
    fold = harness.holdout_fold()
    for target_id in targets:
        target = harness.targets[target_id]
        out[target_id] = {}
        for version in d.VERSIONS:
            train, test = d.split(harness.versions[version], harness.blocks, fold)  # the test events are sealed: only their metadata is used below
            defined = [e for e in train if target.function(e["labels"]) is not None]
            cells = {"C2_timing": Counter(e["release_timing"] for e in defined), "C3_sector_group": Counter(feat.sector_group(e) for e in defined)}
            test_cells = {"C2_timing": Counter(e["release_timing"] for e in test), "C3_sector_group": Counter(feat.sector_group(e) for e in test)}
            small = {name: sorted(k for k, n in counter.items() if n < pr.CELL_MINIMUM) for name, counter in cells.items()}
            indicators = [feat.indicators(e) for e in defined]

            def own_history(event):
                return [x for x in feat.history(event, defined, target) if x["cik"] == event["cik"]]
            entry = {
                "training_events_with_the_target_defined": len(defined), "test_events": len(test),
                "training_cells": {name: dict(sorted(c.items())) for name, c in cells.items()},
                "test_events_by_cell": {name: dict(sorted(c.items())) for name, c in test_cells.items()},
                "cells_below_the_minimum_of_%d" % pr.CELL_MINIMUM: small,
                "test_events_that_would_fall_back_to_the_pooled_value": {
                    "C2_timing": sum(1 for e in test if e["release_timing"] in small["C2_timing"] or e["release_timing"] not in cells["C2_timing"]),
                    "C3_sector_group": sum(1 for e in test if feat.sector_group(e) in small["C3_sector_group"] or feat.sector_group(e) not in cells["C3_sector_group"])},
                "training_rows_with_no_earlier_matured_event": sum(1 for e in defined if not feat.history(e, defined, target)),
                "test_events_with_no_earlier_matured_event": sum(1 for e in test if not feat.history(e, defined, target)),
                "test_events_with_no_earlier_event_of_their_own_issuer": sum(1 for e in test if not own_history(e)),
                "test_events_by_issuer_count": dict(sorted(Counter(Counter(e["cik"] for e in test).values()).items())),
                "indicator_features_constant_in_training": sorted(name for name in ("after_hours", "is_I", "is_other") if len({row[name] for row in indicators}) < 2)}
            if target.kind == "regression":  # the ridge model needs a history mean for every test event: counted by trying, which reads only training labels
                gaps = 0
                for event in test:
                    try:
                        feat.issuer_history_mean(event, defined, target)
                    except d.ProtocolGap:
                        gaps += 1
                entry["test_events_whose_history_mean_would_stop_the_run"] = gaps
            out[target_id][version] = entry
    return out


def audit_report(harness):
    return {"schema_version": 1, "kind": "m4_phase4_holdout_structure_audit",
            "purpose": ("The structure of the holdout fold, taken before the look: the training cells the C2 and C3 baselines will use and which fall back to the pooled value, the "
                        "earlier matured history available to each of the 23 test events, and the test events' release timing and sector group, counted over all 23 whether or not "
                        "a target is defined for them (that depends on outcomes). It reads which labels are defined for the TRAINING events and the metadata of the test events, and "
                        "no block-5 outcome: not a target value, not a count of positives, and not the opening gap the C0 clock's M2 takes as a feature."),
            "protocol": {"id": harness.protocol["protocol_id"], "version": harness.protocol["protocol_version"], "canonical_sha256": pr.protocol_sha256(harness.protocol)},
            "targets": holdout_structure_audit(harness), "holdout": harness.holdout_status(),
            "not_a_claim": ["Not a result: nothing was fitted, scored or evaluated.", "Not Milestone 4 acceptance."]}


# ---- inside the look -------------------------------------------------------------------------------------------------------------------------

def evaluate_all(harness, unsealed, targets=TARGETS):
    """{(target_id, version): evaluate_holdout() result} for every primary target and version, from the events the one look returned. A target with a looser nested
    threshold has its M2 probabilities capped by that threshold's, as in the development folds; if the looser threshold has no predictions (COUNTS_ONLY, say) the capped
    model is MODEL_FIT_FAILED."""
    out = {}
    for version in d.VERSIONS:
        for target_id in targets:
            target = harness.targets[target_id]
            caps = None
            if target_id in p2.NESTED:
                looser = out[(p2.NESTED[target_id], version)]
                caps = {pid: ({r["event_id"]: r["p"] for r in looser["predictors"][pid]["rows"]} if looser["predictors"][pid]["state"] == h.EVALUATED else {})
                        for pid in p2.CAPPED}
            out[(target_id, version)] = harness.evaluate_holdout(target_id, version, unsealed[version], p2.predictors_for(target, caps))
    return out


def development_estimates(root=pr.ROOT):
    """{(target_id, version): {"estimate", "role", "from"} or None}: the pooled development out-of-fold contrast of the confirmatory model against C1, from the committed Phase 2 and
    Phase 3 results (each checked against the hash its completion record holds). None where the development result is INSUFFICIENT_DATA and there is no contrast."""
    root, out = Path(root), {}
    for phase, (results_name, completion_name) in DEVELOPMENT_RESULTS.items():
        results = json.loads((root / results_name).read_text(encoding="utf-8"))
        completion = json.loads((root / completion_name).read_text(encoding="utf-8"))
        if digest(canonical(results)) != completion["evaluation"]["results_canonical_sha256"]:
            raise DataError("%s does not match the hash its completion record holds" % results_name)
        for target_id, versions in results["evaluations"].items():
            model = h.CONFIRMATORY[versions["all_event"]["kind"]]
            for version, ev_ in versions.items():
                contrast = ev_["contrasts"].get(model)
                out[(target_id, version)] = ({"estimate": contrast["estimate"], "role": contrast["role"], "from": results_name} if contrast else None)
    return out


def sign_of(value):
    return (value > 0) - (value < 0)


def sign_check(holdout_estimate, development):
    """Whether the holdout estimate of the confirmatory contrast has the sign of the development estimate of the same version. An estimate of exactly zero has no sign."""
    if development is None:
        return {"comparable": False, "holdout_estimate": holdout_estimate, "holdout_sign": sign_of(holdout_estimate),
                "why": "the development result is INSUFFICIENT_DATA: there is no development contrast to compare with"}
    holdout_sign, development_sign = sign_of(holdout_estimate), sign_of(development["estimate"])
    return {"comparable": True, "holdout_estimate": holdout_estimate, "development_estimate": development["estimate"], "development_role": development["role"],
            "development_from": development["from"], "holdout_sign": holdout_sign, "development_sign": development_sign,
            "same_sign": holdout_sign == development_sign and holdout_sign != 0,
            "meaning": "a statement about direction only: -1 the model scored better than C1, +1 worse, 0 no sign"}


def holdout_without_rows(result):
    out = p2.plain(result)
    for run in out["predictors"].values():
        run.pop("rows", None)
    return out


def descriptive_report(harness, unsealed):
    """All 19 targets in both versions over the 105 visible events and the 23 the look returned: counts, base rates with Wilson intervals, buckets, per-block counts."""
    targets, regression = {}, {}
    for version in d.VERSIONS:
        visible = [e for e in harness.versions[version] if not d.is_sealed(e)]
        events = sorted(visible + list(unsealed[version]), key=fp.event_order)
        if len(events) != len(harness.events):
            raise DataError("the descriptive report must cover every event")
        for target_id, target in harness.targets.items():
            if target.kind == "binary":
                row = targets.setdefault(target_id, {"role": target.role, "definition": target.definition, "clock": target.clock, "sources": list(target.source_labels)})
                row[version] = ev.target_row(events, target.function, harness.blocks, pr.REPORTING_LEVEL)
        regression[version] = {label: ev.regression_row(events, label) for label in ev.REGRESSION_LABELS}
    return {"schema_version": 1, "kind": "m4_phase4_descriptive_report",
            "purpose": ("Counts, base rates with Wilson 95% intervals, the protocol's buckets and per-block counts for all 19 targets in both versions, over the 105 events whose labels were "
                        "visible and the 23 holdout events the one look returned; the five regression labels' summary statistics; and the block table by source. Descriptive only: no "
                        "predictor is fitted for the descriptive-only and INSUFFICIENT_DATA targets and no statement about skill is made."),
            "protocol": {"id": harness.protocol["protocol_id"], "version": harness.protocol["protocol_version"], "canonical_sha256": pr.protocol_sha256(harness.protocol)},
            "buckets": {"estimable_with_wide_uncertainty": "at least 30 positives and 30 negatives", "thin": "at least 10 and fewer than 30 of either", "insufficient": "fewer than 10 of either"},
            "targets": targets, "regression_labels": regression, "blocks": ev.time_structure(harness.events, harness.blocks, harness.source_of),
            "block_5_counts_note": harness.protocol["holdout"]["not_blind_to_counts"], "selection_regime": harness.protocol["holdout"]["selection_regime"],
            "holdout": harness.holdout_status(), "not_a_claim": NOT_A_CLAIM}


def results_report(harness, evaluations, development, digest_of_evaluations):
    runs = {t: {v: holdout_without_rows(evaluations[(t, v)]) for v in d.VERSIONS} for t in TARGETS}
    for target_id, version in evaluations:
        result = runs[target_id][version]
        model = h.CONFIRMATORY[result["kind"]]
        contrast = result["contrasts"].get(model)
        if contrast is not None:
            contrast["against_the_development_result"] = sign_check(contrast["estimate"], development.get((target_id, version)))
    accesses = max(len(reg.read(harness.holdout_log)) - 1, 0)
    return {"schema_version": 1, "kind": "m4_phase4_holdout_results",
            "purpose": ("The one look at the final holdout: every pre-registered predictor on the five primary targets, in both versions, trained on blocks 1 to 4 and scored on block 5 (the "
                        "23 Milestone 1 events), under protocol version 1. A target-version whose holdout thresholds are not met is COUNTS_ONLY. The holdout alone never creates a claim, "
                        "and no status is assigned from it; the contrast of the confirmatory model against C1 is compared with its development result for direction only."),
            "protocol": {"id": harness.protocol["protocol_id"], "version": harness.protocol["protocol_version"], "canonical_sha256": pr.protocol_sha256(harness.protocol)},
            "scope": {"targets": list(TARGETS), "versions": list(d.VERSIONS), "fold": harness.holdout_fold().name, "train_blocks": list(harness.holdout_fold().train_blocks),
                      "test_block": harness.holdout_fold().test_block, "confirmatory_models": h.CONFIRMATORY, "comparators": h.COMPARATOR,
                      "predictors": {"binary": [p.id for p in p2.models.binary_predictors()], "regression": [p.id for p in p2.models.regression_predictors()]}},
            "the_look": {"reason": LOOK_REASON, "accesses": accesses, "technical_reruns": max(accesses - 1, 0), "events_read": harness.holdout_status()["sealed_events"]},
            "determinism": {"evaluated_twice_from_the_same_events": True, "identical": True, "evaluations_canonical_sha256": digest_of_evaluations},
            "selection_regime": harness.protocol["holdout"]["selection_regime"], "what_it_is_for": harness.protocol["holdout"]["what_it_is_for"],
            "states": {t: {v: runs[t][v]["state"] for v in d.VERSIONS} for t in TARGETS},
            "evaluations": runs, "holdout": harness.holdout_status(), "not_a_claim": NOT_A_CLAIM}


def prediction_lines(harness, evaluations, generated_at):
    lines = []
    for target_id in TARGETS:
        for version in d.VERSIONS:
            lines += [canonical(r).decode("utf-8") for r in harness.holdout_prediction_records(evaluations[(target_id, version)], generated_at)]
    return lines


# ---- the run ---------------------------------------------------------------------------------------------------------------------------------

def run(harness, date, root=pr.ROOT, commit_state=None):
    """THE LOOK. Refuses unless it is authorized, the tree is clean, no Phase 4 output exists and the logs are exactly as Phase 3 left them; checks the development results it will
    compare with while the holdout is still sealed; then calls Harness.look once and does everything else on the events it returned.

    `commit_state` is (HEAD's hash, whether the tree is clean); it is read from git unless a test supplies it."""
    if not h.ALLOW_HOLDOUT_LOOK:
        raise d.HoldoutNotAuthorized("ALLOW_HOLDOUT_LOOK is False")
    if not h.ALLOW_REAL_EVALUATION:
        raise h.EvaluationNotAuthorized("ALLOW_REAL_EVALUATION is False")
    root = Path(root)
    commit, clean = commit_state or reg.harness_commit(root)
    if not clean:
        raise DataError("the working tree has uncommitted changes; commit first so that the access record and every experiment name the code that produced them")
    reports = root / "reports"
    results_path, descriptive_path = reports / ("m4-phase4-holdout-results-%s.json" % date), reports / ("m4-phase4-descriptive-%s.json" % date)
    predictions_path = reports / ("m4-phase4-holdout-predictions-%s.jsonl" % date)
    for path in (results_path, descriptive_path, predictions_path):
        if path.exists():
            raise DataError("%s exists; the holdout is looked at once" % path.name)
    reg.verify_chain(harness.experiment_log, "experiments", harness.protocol)
    reg.verify_chain(harness.holdout_log, "holdout_access", harness.protocol)
    experiments, accesses = reg.read(harness.experiment_log), reg.read(harness.holdout_log)
    if len(experiments) != EXPERIMENTS_BEFORE or len(accesses) != 1:
        raise DataError("the logs are not as Phase 4 expects: the experiment log holds %d records (expected %d: its genesis and Phases 2 and 3) and the holdout log %d "
                        "(expected 1: its genesis only; a technical rerun needs a code change of its own)" % (len(experiments), EXPERIMENTS_BEFORE, len(accesses)))
    if {record["target_id"] for record, _ in experiments[1:]} - set(TARGETS) or any(record["fold"] == harness.holdout_fold().name for record, _ in experiments[1:]):
        raise DataError("the experiment log already holds holdout experiments or experiments on targets that are not primaries")
    development = development_estimates(root)  # a missing or altered development result stops the run here, while the holdout is still sealed
    harness.commit = lambda: commit
    unsealed = harness.look(LOOK_REASON)  # THE ONE ACCESS: its record is written before any label is read
    first = evaluate_all(harness, unsealed)
    second = evaluate_all(harness, unsealed)
    first_digest = digest(canonical({"%s|%s" % k: p2.plain(v) for k, v in first.items()}))
    if first_digest != digest(canonical({"%s|%s" % k: p2.plain(v) for k, v in second.items()})):
        raise DataError("two evaluations of the same events differ; refusing to record either")
    descriptive = descriptive_report(harness, unsealed)
    report = results_report(harness, first, development, first_digest)
    generated_at = reg.now()
    lines = prediction_lines(harness, first, generated_at)
    planned = sum(len(result["predictors"]) for result in first.values())
    if planned != EXPECTED_RECORDS:
        raise DataError("the evaluation produced %d predictor cells where %d were expected" % (planned, EXPECTED_RECORDS))
    for document in (report, descriptive):
        json.dumps(document, allow_nan=False)  # a value that cannot be written stops the run here, before any experiment is recorded
    appended = 0
    for version in d.VERSIONS:
        for target_id in TARGETS:
            appended += len(harness.record_holdout_experiments(first[(target_id, version)]))
    h.write_report(results_path, report)
    h.write_report(descriptive_path, descriptive)
    predictions_path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8", newline="\n")
    return {"state": "LOOKED", "harness_commit": commit, "accesses": report["the_look"]["accesses"], "experiment_records": appended, "prediction_records": len(lines),
            "results": str(results_path), "descriptive": str(descriptive_path), "predictions": str(predictions_path),
            "results_canonical_sha256": digest(canonical(report)), "descriptive_canonical_sha256": digest(canonical(descriptive)), "states": report["states"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Milestone 4 Phase 4: the holdout structure audit, and the one look at the final holdout.")
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
