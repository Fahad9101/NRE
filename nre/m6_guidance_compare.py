"""Pure aggregate scorer for the single registered annual-guidance comparison.

The caller owns the committed acquisition manifest and exclusive attempt record.
This module never reads market data, writes an attempt, or publishes event targets
or predictions. ``evaluate_fold_private`` is an internal, in-memory test boundary.
"""
import math
from collections import Counter

from . import m4_metrics, m4_models, m4_protocol
from .core import DataError, canonical, digest, timestamp
from .m4_harness import Abstain

INSUFFICIENT = "STOP_INSUFFICIENT_SUPPORT"
NOT_MET = "STOP_DEVELOPMENT_GATE_NOT_MET"
PASS = "ELIGIBLE_FOR_FRESH_STUDY_SCOPING"


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def block_of(event):
    return event.get("held_block") or "warmup"


def membership(rows):
    return digest(canonical(sorted(row["event_id"] for row in rows)))


def validate_inputs(protocol, events, final_quality):
    if (protocol["models"]["ridge_penalty"] != m4_protocol.RIDGE_LAMBDA
            or protocol["models"]["baseline_columns"] != ["abs(g)", "sign(g)"]
            or protocol["models"]["challenger_columns"] != ["abs(g)", "sign(g)", "-sign(g) * asinh(r)"]):
        raise DataError("Scorer model settings differ from the registered ridge model")
    ids = [e["event_id"] for e in events]
    if len(set(ids)) != len(ids) or set(final_quality) != set(ids):
        raise DataError("Scorer source-quality membership differs")
    if sum(block_of(e) != "warmup" for e in events) != protocol["held_rows_before_label_screen"]:
        raise DataError("Scorer requires the complete frozen held membership before source exclusions")
    windows = {"warmup": protocol["warmup"]["reaction_sessions"]}
    windows.update({fold["test_block"]: fold["test_sessions"] for fold in protocol["folds"]})
    cluster_blocks, session_blocks, issuer_sessions = {}, {}, set()
    for event in events:
        block, day = block_of(event), event["reaction_session"]
        if block not in windows or not windows[block][0] <= day <= windows[block][1]:
            raise DataError("Scorer event falls outside its registered block")
        if not finite_number(event["revision_fraction"]) or event["revision_fraction"] < -1:
            raise DataError("Scorer guidance revision is invalid")
        timestamp(event["feature_cutoff_at"])
        cluster = event.get("cluster_id", event["event_id"])
        if cluster in cluster_blocks:
            raise DataError("Scorer repeats or splits an economic cluster")
        cluster_blocks[cluster] = block
        if day in session_blocks and session_blocks[day] != block:
            raise DataError("Scorer splits a reaction session across blocks")
        session_blocks[day] = block
        key = event["cik"], day
        if key in issuer_sessions:
            raise DataError("Scorer repeats an issuer reaction session")
        issuer_sessions.add(key)
        quality = final_quality[event["event_id"]]
        if (not isinstance(quality, dict)
                or any(not isinstance(quality.get(k), list) for k in ("hard_exclusions", "soft_caveats"))):
            raise DataError("Scorer quality disposition is invalid")
    if any(not any(block_of(e) == f["test_block"] for e in events) for f in protocol["folds"]):
        raise DataError("Scorer requires every full held block for its maturity boundary")


def private_row(event, label, quality, *, clean, fit_boundary=None):
    """A paired private row or one deterministic aggregate attrition reason."""
    if quality["hard_exclusions"]:
        return None, "hard_source_exclusion"
    if clean and quality["soft_caveats"]:
        return None, "soft_source_caveat"
    if quality.get("quality_exclusion"):
        return None, "acquisition_quality_exclusion"
    if not isinstance(label, dict):
        return None, "label_unavailable"
    if label.get("quality_exclusion"):
        return None, "acquisition_quality_exclusion"
    gap, close = label.get("gap"), label.get("close_return")
    if not finite_number(gap) or gap <= -1:
        return None, "opening_unavailable"
    if gap == 0:
        return None, "zero_opening_gap"
    if not finite_number(close) or close <= -1:
        return None, "close_unavailable"
    try:
        mature = timestamp(label["mature_at"])
    except (KeyError, DataError):
        return None, "label_maturity_unavailable"
    if fit_boundary is not None and mature >= fit_boundary:
        return None, "fit_label_not_mature"
    sign = 1 if gap > 0 else -1
    target = -sign * ((1 + close) / (1 + gap) - 1)
    guidance = -sign * math.asinh(event["revision_fraction"])
    if not finite_number(target) or not finite_number(guidance):
        return None, "invalid_fade_target"
    return {"event": event, "event_id": event["event_id"], "issuer": event["cik"],
            "reaction_session": event["reaction_session"], "gap_sign": sign,
            "revision_sign": (event["revision_fraction"] > 0) - (event["revision_fraction"] < 0),
            "target": target, "baseline": (abs(gap), sign), "guidance": guidance}, None


def fit_models_private(rows):
    """Population training scaling and existing ridge solve; no held row enters fit."""
    fitted, dropped = [], {}
    for contextual, name in ((False, "baseline"), (True, "challenger")):
        def columns(row, contextual=contextual):
            return (*row["baseline"], row["guidance"]) if contextual else row["baseline"]
        matrix = [columns(row) for row in rows]
        means, scales, kept, omitted = m4_models.standardization(matrix)
        if contextual and 2 in omitted:
            raise DataError("Guidance training column is constant")
        x = [m4_models.standardized(row, means, scales, kept) for row in matrix]
        beta = m4_models.fit_ridge(x, [row["target"] for row in rows])
        if not all(finite_number(v) for v in beta):
            raise DataError("Guidance model fit is not finite")

        def predict(row, columns=columns, means=means, scales=scales, kept=kept, beta=beta):
            scaled = m4_models.standardized(columns(row), means, scales, kept)
            value = beta[0] + math.fsum(b * v for b, v in zip(beta[1:], scaled))
            if not finite_number(value):
                raise DataError("Guidance prediction is not finite")
            return value
        fitted.append(predict)
        dropped[name] = omitted
    return fitted[0], fitted[1], dropped


def support(rows):
    return {"rows": len(rows), "issuers": len({r["issuer"] for r in rows}),
            "sessions": len({r["reaction_session"] for r in rows})}


def evaluate_fold_private(protocol, events, labels, quality, fold, *, clean):
    """Return private paired predictions; callers must strip them before reporting."""
    full_test = [e for e in events if block_of(e) == fold["test_block"]]
    earlier = [e for e in events if block_of(e) in fold["fit_blocks"]]
    if not full_test:
        raise DataError("Missing full held block")
    if earlier and max(e["reaction_session"] for e in earlier) >= min(e["reaction_session"] for e in full_test):
        raise DataError("Guidance fold is not chronological")
    if ({e.get("cluster_id", e["event_id"]) for e in earlier}
            & {e.get("cluster_id", e["event_id"]) for e in full_test}):
        raise DataError("Guidance fold splits an economic cluster")
    # This boundary includes hard-source-excluded and missing-label held events.
    boundary = min(timestamp(e["feature_cutoff_at"]) for e in full_test)

    def eligible(partition, training):
        accepted, reasons = [], Counter()
        for event in sorted(partition, key=lambda e: (e["reaction_session"], e["cik"], e["event_id"])):
            row, reason = private_row(event, labels.get(event["event_id"]), quality[event["event_id"]],
                                      clean=clean, fit_boundary=boundary if training else None)
            if reason:
                reasons[reason] += 1
            else:
                accepted.append(row)
        return accepted, dict(reasons)

    train, fit_exclusions = eligible(earlier, True)
    test, test_exclusions = eligible(full_test, False)
    report = {"test_block": fold["test_block"], "first_full_block_feature_cutoff": boundary.isoformat(),
              "fit_support": support(train), "eligible_test_support": support(test),
              "fit_exclusions": fit_exclusions, "test_exclusions": test_exclusions,
              "fit_membership_sha256": membership(train), "test_membership_sha256": membership(test),
              "paired_rows": []}
    minimum = protocol["warmup"]
    if (len(train) < minimum["minimum_common_fit_rows"]
            or len({row["issuer"] for row in train}) < minimum["minimum_common_fit_issuers"]):
        return dict(report, status="insufficient_support", reason="fit_support_floor")
    try:
        baseline, challenger, dropped = fit_models_private(train)
        pairs = [{**{k: row[k] for k in ("event_id", "issuer", "reaction_session", "gap_sign", "revision_sign", "target")},
                  "baseline": baseline(row), "challenger": challenger(row)} for row in test]
    except (Abstain, DataError, OverflowError, ZeroDivisionError, ValueError):
        return dict(report, status="insufficient_support", reason="constant_guidance_or_model_fit_failed")
    return dict(report, status="scored", dropped_column_indexes=dropped, paired_rows=pairs)


def summarize_private(folds, protocol):
    pairs = [row for fold in folds for row in fold["paired_rows"]]
    counts = {"paired_rows": len(pairs), "issuers": len({r["issuer"] for r in pairs}),
              "sessions": len({r["reaction_session"] for r in pairs}),
              "up_gaps": sum(r["gap_sign"] == 1 for r in pairs),
              "down_gaps": sum(r["gap_sign"] == -1 for r in pairs),
              "raises": sum(r["revision_sign"] == 1 for r in pairs),
              "cuts": sum(r["revision_sign"] == -1 for r in pairs),
              "unchanged": sum(r["revision_sign"] == 0 for r in pairs),
              "folds_with_minimum_pairs": sum(len(f["paired_rows"]) >= protocol["gates"]["pairs_per_fold"] for f in folds)}
    summary = {"counts": counts, "pair_membership_sha256": membership(pairs),
               "baseline_mse": None, "challenger_mse": None, "mean_improvement": None,
               "relative_mse_reduction": None, "interval_99": None, "cluster_bootstrap": {}}
    if not pairs:
        return summary
    baseline_errors = [(r["target"] - r["baseline"]) ** 2 for r in pairs]
    challenger_errors = [(r["target"] - r["challenger"]) ** 2 for r in pairs]
    differences = [a - b for a, b in zip(baseline_errors, challenger_errors)]
    n = len(pairs)
    baseline_mse, challenger_mse = math.fsum(baseline_errors) / n, math.fsum(challenger_errors) / n
    mean_improvement = math.fsum(differences) / n
    intervals = {axis: m4_metrics.cluster_bootstrap(
        differences, [r[axis] for r in pairs], seed, replicates=protocol["bootstrap"]["replicates"], levels=(0.99,))
        for axis, seed in protocol["bootstrap"]["seeds"].items()}
    outer = [min(v["intervals"]["0.99"][0] for v in intervals.values()),
             max(v["intervals"]["0.99"][1] for v in intervals.values())]
    return dict(summary, baseline_mse=baseline_mse, challenger_mse=challenger_mse,
                mean_improvement=mean_improvement,
                relative_mse_reduction=mean_improvement / baseline_mse if baseline_mse > 0 else None,
                interval_99=outer, cluster_bootstrap=intervals)


def decide(clean, sensitivity, protocol):
    gates = protocol["gates"]
    for report in (clean, sensitivity):
        if any(f["status"] != "scored" for f in report["folds"]):
            return INSUFFICIENT
    primary = clean["summary"]
    if (any(primary["counts"][key] < gates[key] for key in
            ("paired_rows", "issuers", "sessions", "up_gaps", "down_gaps", "folds_with_minimum_pairs"))
            or primary["counts"]["raises"] < 1 or primary["counts"]["cuts"] < 1):
        return INSUFFICIENT
    if (primary["relative_mse_reduction"] is not None
            and primary["relative_mse_reduction"] >= gates["relative_mse_reduction"]
            and primary["interval_99"] is not None and primary["interval_99"][0] > 0
            and sensitivity["summary"]["mean_improvement"] is not None
            and sensitivity["summary"]["mean_improvement"] >= 0):
        return PASS
    return NOT_MET


def compare(protocol, events, private_labels, final_quality):
    """Return only registered aggregate results; the caller enforces one attempt."""
    validate_inputs(protocol, events, final_quality)
    if set(private_labels) - {e["event_id"] for e in events}:
        raise DataError("Private labels contain an event outside the registered membership")
    reports = {}
    for variant, clean in (("clean_window", True), ("all_defined", False)):
        folds = [evaluate_fold_private(protocol, events, private_labels, final_quality, fold, clean=clean)
                 for fold in protocol["folds"]]
        summary = summarize_private(folds, protocol)
        public = []
        for fold in folds:
            pairs = fold.pop("paired_rows")
            public.append(dict(fold, paired_rows=len(pairs),
                               pair_membership_sha256=membership(pairs),
                               baseline_squared_error_sum=math.fsum((r["target"] - r["baseline"]) ** 2 for r in pairs),
                               challenger_squared_error_sum=math.fsum((r["target"] - r["challenger"]) ** 2 for r in pairs)))
        reports[variant] = {"folds": public, "summary": summary}
    return {"schema_version": 1, "reports": reports, "decision": decide(reports["clean_window"], reports["all_defined"], protocol),
            "interpretation": "Retrospective development comparison; a pass qualifies only fresh-study scoping."}
