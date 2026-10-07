"""The Milestone 4 evaluation harness: the machinery the frozen protocol requires, and the one place a predictor is evaluated.

It verifies the protocol and every input the protocol pins, builds the folds, asserts that no fold leaks, keeps the holdout sealed, and evaluates predictors
on the development folds (nre/m4_models.py holds the baselines beyond the pooled rate C1, nre/m4_phase2.py runs them). What may be evaluated on the real
events is set by two constants, ALLOW_REAL_EVALUATION and REAL_EVALUATION_TARGETS; ALLOW_HOLDOUT_LOOK stays False until the one look at block 5. Each is
changed in a commit of its own, with the owner's go-ahead on record.

    python -m nre.m4_harness verify | plan | dry-run [--output PATH] | verify-logs | init-logs
"""
import argparse
import json
import sys
from pathlib import Path

from . import fingerprints as fp
from . import m4_data as d
from . import m4_features as feat
from . import m4_metrics as m
from . import m4_protocol as pr
from . import m4_registry as reg
from . import m4_scoping_evidence as ev
from .core import DataError, canonical, digest, iso

ALLOW_REAL_EVALUATION = True  # fitting and scoring predictors on the real development folds, only with the owner's go-ahead: Phase 2 and Phase 3, 2026-10-07
REAL_EVALUATION_TARGETS = ("gap_ge_3pct", "gap_ge_5pct", "day1_close_return",  # Phase 2's go-ahead: the B clock
                           "extension_after_open_ge_5pct", "loses_half_of_gap")  # Phase 3's: the C0 clock; any other target is refused
ALLOW_HOLDOUT_LOOK = True  # ON for the one look at block 5 only (Phase 4, "authorize phase 4", 2026-10-07; reports/m4-phase4-authorization-2026-10-07.json); off again in the commit after it
COMPARATOR = {"binary": "C1_pooled_rate", "regression": "C1_pooled_quantiles"}
CONFIRMATORY = {"binary": "M2_logistic", "regression": "M3_ridge_linear"}  # the one model per primary target whose contrast against C1 can support a status
# the exploratory contrasts reported besides each predictor's against C1: (model, the predictor it is set against)
OTHER_CONTRASTS = {"binary": (("M2_logistic", "C2_timing_rate"), ("M2_logistic", "C3_sector_group_rate"), ("M2_logistic", "C4_issuer_history_rate"),
                              ("M2_logistic", "M2_without_sector")),
                   "regression": (("M3_ridge_linear", "C2_timing_quantiles"), ("M3_ridge_linear", "C3_sector_group_quantiles"),
                                  ("M3_ridge_linear", "M3_without_sector"))}
PREDICTION_DIGITS = 12  # predictions are rounded when produced so that results reproduce across platforms (exp and log can differ in the last bit)
RESPONSE = {"response_state": "MODEL_NOT_VALIDATED", "opportunity_state": "NO_QUALIFIED_OPPORTUNITY", "confidence_tier": "VERY_LOW"}
RESPONSE_REASONS = ["no calibration has been shown", "the sample is small and clustered", "no confidence threshold has been validated"]
EVALUATED = "EVALUATED"


class EvaluationNotAuthorized(DataError):
    """Evaluating on the real events has not been authorized in this version of the harness."""


class Abstain(Exception):
    """A predictor cannot be fitted: its state (INSUFFICIENT_DATA or MODEL_FIT_FAILED) and why. Nothing is substituted for the missing prediction."""

    def __init__(self, state, reason):
        super().__init__("%s: %s" % (state, reason))
        self.state, self.reason = state, reason


class FittedModel(dict):
    """A fitted model: its parameters (what is hashed and logged) as the dict, and, outside it, whatever the model needs to predict (`context`) and what it
    counts while predicting (`diagnostics`, for instance each use of a fallback)."""
    context = None

    def __init__(self, parameters=(), context=None, diagnostics=None):
        super().__init__(parameters)
        self.context = context
        self.diagnostics = diagnostics if diagnostics is not None else {}


def rounded(value):
    """A prediction as produced: rounded to PREDICTION_DIGITS decimals (a tuple elementwise), and never -0.0."""
    if isinstance(value, (tuple, list)):
        return tuple(rounded(v) for v in value)
    return round(value, PREDICTION_DIGITS) + 0.0


class Predictor:
    """fit(train_events, target) -> a JSON-serializable model (a FittedModel); predict(model, view) -> a probability or (q10, q50, q90). A `view` has no labels."""
    id = kind = None

    def fit(self, train, target):
        raise NotImplementedError

    def predict(self, model, view):
        raise NotImplementedError


class PooledRate(Predictor):
    """C1 for a binary target: the rate among the training events with the target defined."""
    id, kind = "C1_pooled_rate", "binary"

    def fit(self, train, target):
        values = [v for v in d.target_values(target, train) if v is not None]
        if not values:
            raise Abstain("INSUFFICIENT_DATA", "no training event has the target defined")
        positives = sum(1 for v in values if v)
        return {"rate": positives / len(values), "n": len(values), "positives": positives}

    def predict(self, model, view):
        return model["rate"]


class PooledQuantiles(Predictor):
    """C1 for the regression target: the 10th, 50th and 90th percentiles (type 7) of the target among the training events."""
    id, kind = "C1_pooled_quantiles", "regression"

    def fit(self, train, target):
        values = sorted(v for v in d.target_values(target, train) if v is not None)
        if not values:
            raise Abstain("INSUFFICIENT_DATA", "no training event has the target defined")
        return {"quantiles": [fp.quantile(values, q) for q in pr.QUANTILE_LEVELS], "n": len(values)}

    def predict(self, model, view):
        return tuple(model["quantiles"])


def view_of(event, target):
    """What a predictor may know about a test event: everything but its labels and their digest (which is derived from the outcomes), plus, for the C0
    clock, the opening gap (known at the open)."""
    view = {k: v for k, v in event.items() if k not in ("labels", "labels_sha256")}
    if target.clock == "C0":
        view["open_gap"] = event["labels"]["day1_open_return"]["value"]
    return view


def _fold_counts(target, values):
    return d.counts(values) if target.kind == "binary" else {"defined": sum(v is not None for v in values)}


class Harness:
    def __init__(self, protocol, freeze, inputs, root=pr.ROOT, real=False, source_of=None, clock=reg.now, commit=None,
                 experiment_log=reg.EXPERIMENT_LOG, holdout_log=reg.HOLDOUT_LOG):
        self.protocol, self.freeze, self.inputs, self.root, self.real = protocol, freeze, inputs, Path(root), real
        self.events, self.blocks, self.gate, self.spec = inputs["events"], inputs["blocks"], inputs["gate"], inputs["spec"]
        self.versions, self.targets, self.folds = d.versions(inputs), d.targets(protocol), d.folds(protocol)
        self.source_of = source_of or {e["event_id"]: "test" for e in self.events}
        self.clock, self.commit = clock, commit or (lambda: reg.harness_commit(self.root)[0])
        self.experiment_log, self.holdout_log = Path(experiment_log), Path(holdout_log)
        self.seeds = {name: protocol["seeds"][key] for key, name in pr.SEED_KEYS.items()}
        self.seeds[pr.SEED_RANDOM_RANKING] = protocol["seeds"][pr.SEED_RANDOM_RANKING]

    @classmethod
    def from_repository(cls, root=pr.ROOT, **options):
        """The real protocol and inputs, with the holdout sealed. Raises ProtocolMismatch unless every integrity check passes."""
        root = Path(root)
        protocol = pr.load_json(root / "config" / "m4-protocol.json")
        freeze = pr.load_json(root / "reports" / "m4-protocol-freeze-2026-10-06.json")
        inputs = d.load_inputs(protocol, root)
        options.setdefault("experiment_log", root / "reports" / "m4-experiment-log.jsonl")
        options.setdefault("holdout_log", root / "reports" / "m4-holdout-access-log.jsonl")
        harness = cls(protocol, freeze, inputs, root, real=True, source_of=d.sources_of(inputs["events"], root), **options)
        pr.require_verified(harness.verify())
        return harness

    @classmethod
    def for_tests(cls, events, spec, calendar=None, protocol=None, **options):
        """A harness over synthetic events, built the way the real one is: the events of the last block are sealed behind the gate."""
        protocol = protocol or pr.load_json(pr.PROTOCOL_PATH)
        freeze = pr.load_json(pr.FREEZE_PATH)
        blocks = ev.assign_blocks(events)
        sealed, gate = d.seal_events(events, blocks, max(blocks.values()), spec)
        inputs = {"events": sorted(sealed, key=fp.event_order), "policy": None, "spec": spec, "blocks": blocks, "gate": gate, "calendar": calendar}
        return cls(protocol, freeze, inputs, real=False, **options)

    def verify(self):
        checks = pr.verify_protocol(self.protocol, self.freeze, self.inputs.get("policy"))
        return checks + (pr.verify_inputs(self.protocol, self.inputs, self.spec, self.root) if self.real else [])

    def _guard(self, target_id):
        """On the real inputs only the targets the owner's go-ahead covers may be evaluated, and only while the tripwire is on."""
        if self.real and not ALLOW_REAL_EVALUATION:
            raise EvaluationNotAuthorized("evaluating on the real events is not authorized in this version of the harness; verify, plan and dry-run are")
        if self.real and target_id not in REAL_EVALUATION_TARGETS:
            raise EvaluationNotAuthorized("%s is not among the targets authorized for evaluation on the real events (%s)" % (target_id, ", ".join(REAL_EVALUATION_TARGETS)))

    # ---- folds -----------------------------------------------------------------------------------------------------------------------------

    def _prepare(self, target, version):
        """Fold by fold: the split, the leakage assertions, the fold-level rule; and the events of the development folds that may be evaluated."""
        events = self.versions[version]
        folds, usable, pooled_values = {}, [], []
        for fold in self.folds:
            train, test = d.split(events, self.blocks, fold)
            d.assert_clusters_whole(train, test, self.blocks)
            slack_all = d.assert_label_maturity(train, test, fp.LABELS, fold.name)
            slack_target = d.assert_label_maturity(train, test, target.source_labels, fold.name)
            train_values = d.target_values(target, train)
            entry = {"role": fold.role, "train_blocks": list(fold.train_blocks), "test_block": fold.test_block, "train_events": len(train),
                     "test_events": len(test), "smallest_label_slack_days": {"all_sixteen_labels": round(slack_all, 2), "this_target": round(slack_target, 2)},
                     **d.fold_state(target, train, train_values)}
            if fold.role == "development":
                test_values = d.target_values(target, test)
                entry["test"] = _fold_counts(target, test_values)
                if entry["state"] == d.EVALUABLE:
                    usable.append((fold, [e for e, v in zip(train, train_values) if v is not None], [(e, v) for e, v in zip(test, test_values) if v is not None]))
                    pooled_values += test_values
            else:
                entry["test"] = "SEALED: the holdout's own counts are read only at the logged look"
            folds[fold.name] = entry
        pooled = {**d.pooled_state(target, pooled_values), "folds_included": [f.name for f, _, _ in usable]}
        return {"folds": folds, "pooled_development_test": pooled}, usable

    def fold_report(self, target_id, version):
        return self._prepare(self.targets[target_id], version)[0]

    # ---- plan and dry run ------------------------------------------------------------------------------------------------------------------

    def plan(self):
        """What a run would do, and every assertion that makes it sound. Scores nothing and reads no holdout outcome."""
        out = {"blocks": ev.time_structure(self.events, self.blocks, self.source_of), "targets": {}}
        for target in self.targets.values():
            row = {"role": target.role, "kind": target.kind, "clock": target.clock, "source_labels": list(target.source_labels), "definition": target.definition}
            for version in d.VERSIONS:
                visible = [e for e in self.versions[version] if not d.is_sealed(e)]
                row["blocks_1_to_4_" + version] = _fold_counts(target, d.target_values(target, visible))
                if target.role == "primary":
                    row[version] = self.fold_report(target.id, version)
            out["targets"][target.id] = row
        out["events_whose_labels_were_available"] = sum(1 for e in self.events if not d.is_sealed(e))
        return out

    def cross_check(self, plan):
        """The fold counts and development statuses this harness computes against those frozen in the freeze record. Returns the disagreements."""
        recorded, problems = self.freeze["pre_freeze_count_check"]["counts"], []
        for version in d.VERSIONS:
            for target_id, want in recorded[version].items():
                got = plan["targets"][target_id][version]
                for fold_name, entry in got["folds"].items():
                    if target_id == "day1_close_return":
                        pairs = [("train defined", entry["train"]["defined"], want["train_defined"][fold_name])]
                        if entry["role"] == "development":
                            pairs.append(("test defined", entry["test"]["defined"], want["test_defined"][fold_name]))
                    else:
                        saved = want["folds"][fold_name]
                        names = (("defined", "defined"), ("pos", "positives"), ("neg", "negatives"))
                        pairs = [("train " + a, entry["train"][b], saved["train"][a]) for a, b in names]
                        if entry["role"] == "development":
                            pairs += [("test " + a, entry["test"][b], saved["test"][a]) for a, b in names]
                        pairs.append(("train meets threshold", entry["state"] == d.EVALUABLE, saved["train_meets_fit_threshold"]))
                    problems += ["%s %s %s %s: harness %s, freeze record %s" % (version, target_id, fold_name, label, a, b) for label, a, b in pairs if a != b]
                pooled = got["pooled_development_test"]
                frozen_pool = want.get("pooled_development_test_over_fitted_folds") or {"defined": want["pooled_development_test"]}
                if pooled["test"]["defined"] != frozen_pool["defined"]:
                    problems.append("%s %s pooled development test: harness %s events, freeze record %s" % (version, target_id, pooled["test"]["defined"], frozen_pool["defined"]))
                status = self.freeze["pre_freeze_count_check"]["resulting_status"][version][target_id]["development"]
                if pooled["state"] != (d.EVALUABLE if status == "EVALUABLE" else status):
                    problems.append("%s %s development status: harness %s, freeze record %s" % (version, target_id, pooled["state"], status))
        return problems

    def holdout_status(self):
        return {"sealed_events": sum(1 for e in self.events if d.is_sealed(e)), "denied_reads": len(self.gate.denied), "unsealed_loads": self.gate.unsealed,
                "access_log_records_after_genesis": max(len(reg.read(self.holdout_log)) - 1, 0)}

    def dry_run(self):
        """verify + plan + cross-check as one report. Evaluates no predictor and reads no holdout outcome. It carries no clock or commit, so it reproduces."""
        checks = self.verify()
        plan = self.plan()
        return {"schema_version": 1, "kind": "m4_harness_dry_run",
                "purpose": ("Run the Milestone 4 harness on the real inputs without evaluating anything: verify the frozen protocol and every pinned input, build the folds, "
                            "assert that no fold leaks, and report fold sizes and which thresholds are met. No predictor is fitted or scored and no holdout outcome is read."),
                "protocol": {"id": self.protocol["protocol_id"], "version": self.protocol["protocol_version"], "canonical_sha256": pr.protocol_sha256(self.protocol)},
                "integrity_checks": checks, "integrity_ok": all(c["ok"] for c in checks), "plan": plan,
                "agreement_with_the_freeze_record": {"compared": "fold counts and development statuses for the five primary targets in both versions",
                                                     "disagreements": self.cross_check(plan)},
                "holdout": self.holdout_status(), "evaluated": {"predictors_fitted": 0, "predictions_made": 0, "metrics_computed": 0},
                "not_a_claim": ["Not a result: nothing was evaluated.", "Not Milestone 4 acceptance.", "Not evidence that any predictor beats the base rate."]}

    # ---- evaluation on the development folds -----------------------------------------------------------------------------------------------

    def evaluate(self, target_id, version, predictors=None):
        """One primary target in one version on the development folds: fold states, out-of-fold predictions, metrics, contrasts.

        Every predictor is contrasted with the comparator C1 (model minus comparator, lower is better). The one contrast that can support a status is the
        confirmatory model's against C1 in the clean-window version; the all-event contrast of the same pair is its companion in the status rule, and every
        other contrast (the other predictors against C1, the pairs in OTHER_CONTRASTS, and each development fold) is labelled exploratory.
        """
        self._guard(target_id)
        target = self.targets[target_id]
        if target.role != "primary":
            raise DataError("%s is %s: no predictor is fitted for it" % (target_id, target.role))
        predictors = predictors or [PooledRate() if target.kind == "binary" else PooledQuantiles()]
        if any(p.kind != target.kind for p in predictors):
            raise DataError("every predictor must be of the target's kind (%s)" % target.kind)
        report, usable = self._prepare(target, version)
        result = {"target": target.id, "version": version, "kind": target.kind, "clock": target.clock, **report, "predictors": {}, "contrasts": {},
                  "other_contrasts": {}, "fold_contrasts": {}}
        for predictor in predictors:
            result["predictors"][predictor.id] = self._run(predictor, target, report, usable)
        runs = result["predictors"]
        comparator = runs.get(COMPARATOR[target.kind])
        evaluated = lambda run: run is not None and run["state"] == EVALUATED  # noqa: E731
        # the all-event contrast of the confirmatory model accompanies the clean-window one, so it needs the clean-window version to be evaluable
        clean_evaluable = version == "clean_window" or self._prepare(target, "clean_window")[0]["pooled_development_test"]["state"] == d.EVALUABLE
        for pid, run in runs.items():
            if evaluated(comparator) and pid != COMPARATOR[target.kind] and evaluated(run):
                role, note = "exploratory", {}
                if pid == CONFIRMATORY[target.kind]:
                    if version == "clean_window":
                        role = "confirmatory"
                    elif clean_evaluable:
                        role = "companion_of_the_confirmatory_contrast"
                    else:
                        note = {"role_note": "the clean-window version is INSUFFICIENT_DATA, so there is no confirmatory contrast for this one to accompany"}
                result["contrasts"][pid] = {"role": role, **note, "baseline": COMPARATOR[target.kind], **self._contrast(target, run["rows"], comparator["rows"])}
        for model_id, baseline_id in OTHER_CONTRASTS[target.kind]:
            if evaluated(runs.get(model_id)) and evaluated(runs.get(baseline_id)):
                result["other_contrasts"]["%s_vs_%s" % (model_id, baseline_id)] = {
                    "role": "exploratory", "model": model_id, "baseline": baseline_id, **self._contrast(target, runs[model_id]["rows"], runs[baseline_id]["rows"])}
        confirmatory = runs.get(CONFIRMATORY[target.kind])
        if evaluated(confirmatory) and evaluated(comparator):
            for fold_name in confirmatory["folds"]:
                a, b = (run["folds"][fold_name].get("rows") for run in (confirmatory, comparator))
                if a and b:
                    result["fold_contrasts"][fold_name] = {"role": "exploratory", "model": CONFIRMATORY[target.kind], "baseline": COMPARATOR[target.kind],
                                                           **self._contrast(target, a, b)}
        return result

    def _run(self, predictor, target, report, usable):
        """One predictor over the development folds. A fold that is INSUFFICIENT_DATA, or whose fit fails, has null predictions and a reason."""
        pooled = report["pooled_development_test"]
        run = {"state": None, "reason": None, "folds": {}, "rows": []}
        for name, entry in report["folds"].items():
            if entry["role"] == "development":
                run["folds"][name] = {"state": entry["state"], "reason": entry["reason"], "predictions": None}
        if pooled["state"] != d.EVALUABLE:
            run["state"], run["reason"] = d.INSUFFICIENT_DATA, pooled["reason"]
            for entry in run["folds"].values():
                entry["state"] = d.INSUFFICIENT_DATA
                entry["reason"] = entry["reason"] or pooled["reason"]
            return run
        failure = None
        for fold, train, tests in usable:
            try:
                model = predictor.fit(train, target)
            except Abstain as abstention:
                run["folds"][fold.name] = {"state": abstention.state, "reason": abstention.reason, "predictions": None}
                failure = failure or abstention
                continue
            base = self._baseline_rate(target, train)
            rows = [self._row(e, v, rounded(predictor.predict(model, view_of(e, target))), fold, base) for e, v in tests]
            run["folds"][fold.name] = {"state": EVALUATED, "reason": None, "predictions": len(rows), "model": model,
                                       "model_checksum": digest(canonical(model)), "diagnostics": dict(getattr(model, "diagnostics", None) or {}), "rows": rows}
            run["rows"] += rows
        if failure is not None:
            run["state"], run["reason"], run["rows"] = failure.state, failure.reason, []
            return run
        run["state"] = EVALUATED
        run["metrics"] = self._metrics(target, run["rows"], pr.PRECISION_K_POOLED)
        run["metrics_by_fold"] = {name: self._metrics(target, entry["rows"], pr.PRECISION_K_FOLD) for name, entry in run["folds"].items() if entry["state"] == EVALUATED}
        run["metrics_by_source"] = {s: self._metrics(target, [r for r in run["rows"] if r["source"] == s], pr.PRECISION_K_POOLED)
                                    for s in sorted({r["source"] for r in run["rows"]})}
        return run

    @staticmethod
    def _baseline_rate(target, train):
        values = [v for v in d.target_values(target, train) if v is not None]
        return sum(1 for v in values if v) / len(values) if target.kind == "binary" and values else None

    def _row(self, event, outcome, prediction, fold, base):
        return {"event_id": event["event_id"], "fold": fold.name, "block": self.blocks[event["event_id"]], "source": self.source_of[event["event_id"]],
                "reaction_session": event["reaction_session"], "issuer": event["cik"], "y": outcome, "p": prediction, "base_rate": base,
                "day1_close_return": event["labels"]["day1_close_return"]["value"]}

    @staticmethod
    def _counts_header(target, rows):
        header = {"events": len(rows), "reaction_sessions": len({r["reaction_session"] for r in rows}), "issuers": len({r["issuer"] for r in rows})}
        if target.kind == "binary":
            header.update(positives=sum(1 for r in rows if r["y"]), negatives=sum(1 for r in rows if not r["y"]))
        return header

    def _metrics(self, target, rows, ks):
        if not rows:
            return {"state": m.INSUFFICIENT_DATA, "reason": "no events"}
        out = {"counts": self._counts_header(target, rows)}
        if target.kind == "regression":
            return {**out, **m.regression_metrics([r["y"] for r in rows], [r["p"] for r in rows])}
        scores, ys, keys = [r["p"] for r in rows], [r["y"] for r in rows], [r["event_id"] for r in rows]
        positives = out["counts"]["positives"]
        out["brier"], out["log_loss"] = m.brier(scores, ys), m.log_loss(scores, ys)
        out["pr_auc"] = m.average_precision(scores, ys) if positives >= pr.MIN_POSITIVES else {
            "state": m.INSUFFICIENT_DATA, "reason": "%d positives (at least %d needed)" % (positives, pr.MIN_POSITIVES)}
        base = m.mean([r["base_rate"] for r in rows])
        out["precision_at_k"] = {}
        for k in ks:
            if len(rows) < 2 * k:
                out["precision_at_k"][str(k)] = {"state": m.INSUFFICIENT_DATA, "reason": "%d events, fewer than 2K = %d" % (len(rows), 2 * k)}
                continue
            value = m.precision_at_k(scores, ys, keys, k)
            ranking = m.random_precision_at_k(ys, keys, k, self.seeds[pr.SEED_RANDOM_RANKING])
            out["precision_at_k"][str(k)] = {"precision": value, "lift_over_the_training_base_rate": value / base if base else None, "random_ranking": ranking,
                                             "lift_over_random_ranking": value / ranking["mean"] if ranking["mean"] else None}
        out["reliability"] = m.reliability(scores, ys, keys)
        out["false_positives_and_negatives"] = m.confusion(scores, ys, [r["base_rate"] for r in rows])
        out["expected_return_by_tercile"] = m.tercile_means(scores, [r["day1_close_return"] for r in rows], keys)
        return out

    def _contrast(self, target, model_rows, base_rows):
        """Model minus comparator on the same out-of-fold events (lower is better), with the cluster-bootstrap intervals."""
        if [r["event_id"] for r in model_rows] != [r["event_id"] for r in base_rows]:
            raise DataError("predictors must be compared on the same events")
        if target.kind == "binary":
            differences = [m.event_brier(a["p"], a["y"]) - m.event_brier(b["p"], b["y"]) for a, b in zip(model_rows, base_rows)]
            metric = "brier_score"
        else:
            differences = [m.event_pinball(a["y"], a["p"]) - m.event_pinball(b["y"], b["p"]) for a, b in zip(model_rows, base_rows)]
            metric = "mean_pinball_loss"
        clusters = {"reaction_session": [r["reaction_session"] for r in model_rows], "issuer": [r["issuer"] for r in model_rows]}
        return {"metric": metric, "direction": "model minus comparator; lower is better", **m.contrast(differences, clusters, self.seeds)}

    def status(self, predictor_id, results):
        """The protocol's status for one primary target and predictor from the target's two versions' results (each from evaluate)."""
        clean, every = results["clean_window"], results["all_event"]
        if clean["pooled_development_test"]["state"] != d.EVALUABLE:
            return m.INSUFFICIENT_DATA
        run = clean["predictors"][predictor_id]
        if run["state"] != EVALUATED:
            return run["state"]
        interval = clean["contrasts"][predictor_id]["headline"]["%g" % pr.CLAIM_LEVEL]
        every_contrast = every["contrasts"].get(predictor_id)
        return m.decide({"state": m.EVALUABLE, "claim_interval": [interval["low"], interval["high"]]},
                        {"estimate": every_contrast["estimate"] if every_contrast else None})

    # ---- logging ---------------------------------------------------------------------------------------------------------------------------

    def _train_ids(self, version, fold_name):
        fold = next(f for f in self.folds if f.name == fold_name)
        return [e["event_id"] for e in d.split(self.versions[version], self.blocks, fold)[0]]

    def experiment_records(self, result):
        """One record per predictor and development fold, and one for the pooled development set, in the protocol's fields."""
        target, commit, created, start = self.targets[result["target"]], self.commit(), self.clock(), len(reg.read(self.experiment_log))
        method = self.protocol["intervals"]["headline_interval_for_the_primary_contrast"]["method"]
        records = []
        for pid, run in result["predictors"].items():
            for name, entry in run["folds"].items():
                rows = entry.get("rows", [])
                metrics = run.get("metrics_by_fold", {}).get(name) or {"state": entry["state"], "reason": entry["reason"]}
                records.append(self._record(start + len(records), created, commit, target, pid, result, name, self._train_ids(result["version"], name), rows,
                                            entry.get("model", {}), {"fold": result["folds"][name], "metrics": metrics, "diagnostics": entry.get("diagnostics")},
                                            "none", entry["state"]))
            rows = run["rows"]
            metrics = run.get("metrics") or {"state": run["state"], "reason": run["reason"]}
            contrasts = {"against_the_comparator": result["contrasts"].get(pid),
                         "others": {k: v for k, v in result["other_contrasts"].items() if v["model"] == pid},
                         "by_fold": {k: v for k, v in result["fold_contrasts"].items() if v["model"] == pid}}
            records.append(self._record(start + len(records), created, commit, target, pid, result, "pooled_development", [], rows,
                                        {}, {"fold": result["pooled_development_test"], "metrics": metrics, "contrasts": contrasts}, method, run["state"]))
        return records

    def _record(self, sequence, created, commit, target, pid, result, name, train_ids, rows, parameters, metrics, interval_method, state):
        return reg.experiment_record(self.protocol, commit, created, sequence, target.id, target.clock, pid, result["version"], name, train_ids,
                                     [r["event_id"] for r in rows], feat.FEATURE_VERSION, parameters, [[r["event_id"], r["p"]] for r in rows], metrics,
                                     interval_method, self.seeds, state)

    def record_experiments(self, result):
        return [reg.append(self.experiment_log, "experiments", record, self.protocol) for record in self.experiment_records(result)]

    def prediction_record(self, predictor, model, target, version, fold_name, event, prediction, generated_at):
        """A prediction in the protocol's fields. Every one is MODEL_NOT_VALIDATED, NO_QUALIFIED_OPPORTUNITY and VERY_LOW: no other state is emitted."""
        fold = next(f for f in self.folds if f.name == fold_name)
        sessions = sorted(e["reaction_session"] for e in d.split(self.versions[version], self.blocks, fold)[0])
        when = self.inputs["calendar"].bounds(event["reaction_session"])[0] if target.clock == "C0" else event["cutoff"]
        snapshot = {k: self.protocol["inputs"][k] for k in ("event_table_sha256", "event_labels_sha256", "block_assignment_sha256")}
        return {"event_id": event["event_id"], "target_id": target.id, "version": version, "fold": fold_name, "prediction": prediction, **RESPONSE,
                "reasons": RESPONSE_REASONS, "model_version": "m4-%s-v1" % predictor.id, "feature_version": feat.FEATURE_VERSION,
                "training_window_dates": [sessions[0], sessions[-1]], "data_snapshot_sha256": digest(canonical(snapshot)),
                "model_checksum": digest(canonical(model)), "prediction_time": iso(when), "generated_at": generated_at}

    def prediction_records(self, result, generated_at):
        """Every out-of-fold prediction of one evaluate() result as a prediction record: one per predictor, development fold and test event."""
        target, version = self.targets[result["target"]], result["version"]
        snapshot = digest(canonical({k: self.protocol["inputs"][k] for k in ("event_table_sha256", "event_labels_sha256", "block_assignment_sha256")}))
        by_id = {e["event_id"]: e for e in self.events}
        records = []
        for pid, run in result["predictors"].items():
            for fold_name, entry in run["folds"].items():
                if entry["state"] != EVALUATED:
                    continue
                fold = next(f for f in self.folds if f.name == fold_name)
                sessions = sorted(e["reaction_session"] for e in d.split(self.versions[version], self.blocks, fold)[0])
                for row in entry["rows"]:
                    event = by_id[row["event_id"]]
                    when = self.inputs["calendar"].bounds(event["reaction_session"])[0] if target.clock == "C0" else event["cutoff"]
                    records.append({"event_id": row["event_id"], "target_id": target.id, "version": version, "fold": fold_name, "predictor_id": pid,
                                    "prediction": list(row["p"]) if isinstance(row["p"], tuple) else row["p"], **RESPONSE, "reasons": RESPONSE_REASONS,
                                    "model_version": "m4-%s-v1" % pid, "feature_version": feat.FEATURE_VERSION, "training_window_dates": [sessions[0], sessions[-1]],
                                    "data_snapshot_sha256": snapshot, "model_checksum": entry["model_checksum"], "prediction_time": iso(when),
                                    "generated_at": generated_at})
        return records

    # ---- the holdout evaluation (Phase 4): from the events the logged look returned ---------------------------------------------------------------

    def holdout_fold(self):
        return next(f for f in self.folds if f.role == "holdout")

    def evaluate_holdout(self, target_id, version, unsealed, predictors=None):
        """One primary target in one version on the holdout fold, from the holdout events that Harness.look returned for this version.

        Nothing here unseals anything: `unsealed` is what the logged look handed back. The fold is trained on blocks 1 to 4 as the version sees them. A fold whose
        training events fail the fold-level rule is INSUFFICIENT_DATA; holdout test events that fail the holdout-level rule make the target COUNTS_ONLY (nothing is
        fitted or scored: only the counts, the base rate and its Wilson interval); otherwise every predictor is fitted on the training events and scored on the test
        events. Every contrast is a holdout contrast and none is a claim: the holdout alone never creates one.
        """
        self._guard(target_id)
        target = self.targets[target_id]
        if target.role != "primary":
            raise DataError("%s is %s: no predictor is fitted for it" % (target_id, target.role))
        predictors = predictors or [PooledRate() if target.kind == "binary" else PooledQuantiles()]
        if any(p.kind != target.kind for p in predictors):
            raise DataError("every predictor must be of the target's kind (%s)" % target.kind)
        fold = self.holdout_fold()
        train, sealed_test = d.split(self.versions[version], self.blocks, fold)
        test = sorted(unsealed, key=fp.event_order)
        if [e["event_id"] for e in test] != [e["event_id"] for e in sealed_test] or any(d.is_sealed(e) for e in test):
            raise DataError("the events given are not the holdout fold's test events with their labels")
        d.assert_clusters_whole(train, test, self.blocks)
        slack_all = d.assert_label_maturity(train, test, fp.LABELS, fold.name)
        slack_target = d.assert_label_maturity(train, test, target.source_labels, fold.name)
        train_values, test_values = d.target_values(target, train), d.target_values(target, test)
        entry = {"role": fold.role, "train_blocks": list(fold.train_blocks), "test_block": fold.test_block, "train_events": len(train), "test_events": len(test),
                 "smallest_label_slack_days": {"all_sixteen_labels": round(slack_all, 2), "this_target": round(slack_target, 2)}, **d.fold_state(target, train, train_values)}
        held = d.holdout_state(target, test_values)
        entry["test"] = held["test"]
        train_defined = [e for e, v in zip(train, train_values) if v is not None]
        tests = [(e, v) for e, v in zip(test, test_values) if v is not None]
        result = {"target": target.id, "version": version, "kind": target.kind, "clock": target.clock, "fold": entry, "state": None, "reason": None,
                  "test_counts": self._holdout_counts(target, tests), "selection_regime": self.protocol["holdout"]["selection_regime"],
                  "predictors": {}, "contrasts": {}, "other_contrasts": {}}
        if entry["state"] != d.EVALUABLE:
            result["state"], result["reason"] = d.INSUFFICIENT_DATA, entry["reason"]
        elif held["state"] != d.EVALUABLE:
            result["state"] = d.COUNTS_ONLY
            result["reason"] = (d.shortfall(held["test"]) if target.kind == "binary"
                                else "%d test events with the target defined (at least %d needed)" % (held["test"]["defined"], pr.MIN_REGRESSION_TEST_EVENTS))
        if result["state"] is not None:
            for predictor in predictors:
                result["predictors"][predictor.id] = {"state": result["state"], "reason": result["reason"], "predictions": None}
            return result
        result["state"] = EVALUATED
        for predictor in predictors:
            result["predictors"][predictor.id] = self._run_holdout(predictor, target, fold, train_defined, tests)
        runs = result["predictors"]
        comparator = runs.get(COMPARATOR[target.kind])
        evaluated = lambda run: run is not None and run["state"] == EVALUATED  # noqa: E731
        no_claim = "none: the holdout alone never creates a claim"
        for pid, run in runs.items():
            if evaluated(comparator) and pid != COMPARATOR[target.kind] and evaluated(run):
                role = "holdout_replication_check" if pid == CONFIRMATORY[target.kind] else "exploratory"
                result["contrasts"][pid] = {"role": role, "claim": no_claim, "baseline": COMPARATOR[target.kind], **self._contrast(target, run["rows"], comparator["rows"])}
        for model_id, baseline_id in OTHER_CONTRASTS[target.kind]:
            if evaluated(runs.get(model_id)) and evaluated(runs.get(baseline_id)):
                result["other_contrasts"]["%s_vs_%s" % (model_id, baseline_id)] = {
                    "role": "exploratory", "claim": no_claim, "model": model_id, "baseline": baseline_id, **self._contrast(target, runs[model_id]["rows"], runs[baseline_id]["rows"])}
        return result

    def _run_holdout(self, predictor, target, fold, train_defined, tests):
        """One predictor fitted on the holdout fold's training events and scored on its test events; a fit that fails has null predictions and a reason."""
        try:
            model = predictor.fit(train_defined, target)
        except Abstain as abstention:
            return {"state": abstention.state, "reason": abstention.reason, "predictions": None}
        base = self._baseline_rate(target, train_defined)
        rows = [self._row(e, v, rounded(predictor.predict(model, view_of(e, target))), fold, base) for e, v in tests]
        return {"state": EVALUATED, "reason": None, "predictions": len(rows), "model": model, "model_checksum": digest(canonical(model)),
                "diagnostics": dict(getattr(model, "diagnostics", None) or {}), "rows": rows, "metrics": self._metrics(target, rows, pr.PRECISION_K_FOLD),
                "metrics_by_source": {s: self._metrics(target, [r for r in rows if r["source"] == s], pr.PRECISION_K_FOLD) for s in sorted({r["source"] for r in rows})}}

    def _holdout_counts(self, target, tests):
        """What a holdout target-version is described by whatever its state: the defined test events, their positives and negatives, sessions and issuers, and for a binary
        target the base rate with its Wilson interval at the reporting level."""
        header = self._counts_header(target, [{"y": v, "reaction_session": e["reaction_session"], "issuer": e["cik"]} for e, v in tests])
        if target.kind == "binary" and tests:
            low, high = fp.wilson(header["positives"], header["events"], pr.REPORTING_LEVEL)
            header.update(base_rate=header["positives"] / header["events"], wilson_low=low, wilson_high=high, wilson_level=pr.REPORTING_LEVEL)
        return header

    def holdout_experiment_records(self, result):
        """One record per predictor for the holdout fold: EVALUATED with its predictions and metrics, or COUNTS_ONLY, INSUFFICIENT_DATA or MODEL_FIT_FAILED with the counts."""
        target, commit, created, start = self.targets[result["target"]], self.commit(), self.clock(), len(reg.read(self.experiment_log))
        method = self.protocol["intervals"]["headline_interval_for_the_primary_contrast"]["method"]
        fold = self.holdout_fold()
        records = []
        for pid, run in result["predictors"].items():
            contrasts = {"against_the_comparator": result["contrasts"].get(pid), "others": {k: v for k, v in result["other_contrasts"].items() if v["model"] == pid}}
            metrics = {"fold": result["fold"], "holdout_state": result["state"], "test_counts": result["test_counts"], "selection_regime": result["selection_regime"],
                       "metrics": run.get("metrics") or {"state": run["state"], "reason": run["reason"]}, "diagnostics": run.get("diagnostics"), "contrasts": contrasts}
            records.append(self._record(start + len(records), created, commit, target, pid, result, fold.name, self._train_ids(result["version"], fold.name), run.get("rows", []),
                                        run.get("model", {}), metrics, method if run["state"] == EVALUATED else "none", run["state"]))
        return records

    def record_holdout_experiments(self, result):
        return [reg.append(self.experiment_log, "experiments", record, self.protocol) for record in self.holdout_experiment_records(result)]

    def holdout_prediction_records(self, result, generated_at):
        """Every holdout prediction of one evaluate_holdout() result as a prediction record: one per predictor and test event, for the predictors that were scored."""
        target, version, fold = self.targets[result["target"]], result["version"], self.holdout_fold()
        snapshot = digest(canonical({k: self.protocol["inputs"][k] for k in ("event_table_sha256", "event_labels_sha256", "block_assignment_sha256")}))
        sessions = sorted(e["reaction_session"] for e in d.split(self.versions[version], self.blocks, fold)[0])
        by_id = {e["event_id"]: e for e in self.events}
        records = []
        for pid, run in result["predictors"].items():
            if run["state"] != EVALUATED:
                continue
            for row in run["rows"]:
                event = by_id[row["event_id"]]
                when = self.inputs["calendar"].bounds(event["reaction_session"])[0] if target.clock == "C0" else event["cutoff"]
                records.append({"event_id": row["event_id"], "target_id": target.id, "version": version, "fold": fold.name, "predictor_id": pid,
                                "prediction": list(row["p"]) if isinstance(row["p"], tuple) else row["p"], **RESPONSE, "reasons": RESPONSE_REASONS,
                                "model_version": "m4-%s-v1" % pid, "feature_version": feat.FEATURE_VERSION, "training_window_dates": [sessions[0], sessions[-1]],
                                "data_snapshot_sha256": snapshot, "model_checksum": run["model_checksum"], "prediction_time": iso(when), "generated_at": generated_at})
        return records

    # ---- the holdout -----------------------------------------------------------------------------------------------------------------------

    def look(self, reason):
        """The only way to a holdout outcome: the access record is written first, then the labels are unsealed. Returns {version: the holdout events}."""
        if not ALLOW_HOLDOUT_LOOK:
            raise d.HoldoutNotAuthorized("the holdout look is not authorized in this version of the harness")
        sealed = [e for e in self.events if d.is_sealed(e)]
        number = len(reg.read(self.holdout_log))
        record = reg.holdout_access_record(self.protocol, self.commit(), self.clock(), number, reason, [e["event_id"] for e in sealed])
        reg.append(self.holdout_log, "holdout_access", record, self.protocol)
        return {version: self.gate.unseal(sealed, version) for version in d.VERSIONS}


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return digest(canonical(report))


def main(argv=None):
    parser = argparse.ArgumentParser(description="The Milestone 4 harness: verify, plan and dry-run only (nothing is evaluated).")
    parser.add_argument("command", choices=("verify", "plan", "dry-run", "verify-logs", "init-logs"))
    parser.add_argument("--output", help="write the report here (plan and dry-run)")
    args = parser.parse_args(argv)
    protocol = pr.load_json(pr.PROTOCOL_PATH)
    if args.command == "init-logs":
        commit, clean = reg.harness_commit()
        if not clean:
            print(json.dumps({"state": "REFUSED", "reason": "the working tree has uncommitted changes; commit the harness first"}))
            return 2
        records = reg.init_logs(protocol, commit, reg.now())
        print(json.dumps({"state": "WRITTEN", "harness_commit": commit, "records": len(records), "experiment_log": str(reg.EXPERIMENT_LOG),
                          "holdout_access_log": str(reg.HOLDOUT_LOG)}, sort_keys=True))
        return 0
    if args.command == "verify-logs":
        found = {"experiments": reg.verify_chain(reg.EXPERIMENT_LOG, "experiments", protocol), "holdout_access": reg.verify_chain(reg.HOLDOUT_LOG, "holdout_access", protocol)}
        print(json.dumps({"state": "VERIFIED", **found}, sort_keys=True))
        return 0
    harness = Harness.from_repository()
    if args.command == "verify":
        checks = harness.verify()
        failed = [c["check"] for c in checks if not c["ok"]]
        print(json.dumps({"state": "MISMATCH" if failed else "VERIFIED", "checks": len(checks), "failed": failed}))
        return 1 if failed else 0
    report = harness.plan() if args.command == "plan" else harness.dry_run()
    summary = {"state": "PLAN" if args.command == "plan" else "DRY_RUN", "report_sha256": digest(canonical(report))}
    if args.output:
        summary["output"] = args.output
        write_report(args.output, report)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
