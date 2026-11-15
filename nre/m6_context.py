"""The one authorized M6 issuer-context development comparison."""
import argparse
import math
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from . import caveat_sensitivity, fingerprints, m4_metrics, m4_models, m4_protocol
from .core import canonical, digest
from .m4_data import mask_labels
from .m4_scoping_evidence import assign_blocks
from .m5_phase1b_audit import load

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "config/m6-context-protocol.json"
FREEZE = "reports/m6-context-freeze-2026-11-15.json"
ATTEMPT = "reports/m6-context-attempt-2026-11-15.json"
RESULT = "reports/m6-context-result-2026-11-15.json"
OPEN = "day1_open_return"
CLOSE = "day1_close_return"


def valid_return(value):
    return type(value) in (int, float) and math.isfinite(value) and value > -1


def exclusion(event):
    gap, close = (event["labels"][name]["value"] for name in (OPEN, CLOSE))
    if not valid_return(gap):
        return "opening_unavailable"
    if gap == 0:
        return "zero_opening_gap"
    if not valid_return(close):
        return "close_unavailable"
    return None


def outcome(event):
    if exclusion(event) is not None:
        return None
    gap, close = (event["labels"][name]["value"] for name in (OPEN, CLOSE))
    return (-1 if gap > 0 else 1) * ((1 + close) / (1 + gap) - 1)


def issuer_context(event, history, prior=10):
    pooled = [e for e in history if e["event_id"] != event["event_id"]
              and e["reaction_session"] < event["reaction_session"]
              and e["available_at"][CLOSE] < event["cutoff"]
              and valid_return(e["labels"][CLOSE]["value"])]
    own = [e["labels"][CLOSE]["value"] for e in pooled if e["cik"] == event["cik"]]
    if not own:
        return 0.0, pooled
    pooled_mean = mean(e["labels"][CLOSE]["value"] for e in pooled)
    return math.fsum(value - pooled_mean for value in own) / (len(own) + prior), pooled


def fold_rows(events, blocks, test_block, prior=10):
    train = [e for e in events if blocks[e["event_id"]] < test_block]
    test = [e for e in events if blocks[e["event_id"]] == test_block]
    if not train or not test:
        raise ValueError("Missing fold partition")
    for key in ("cluster_id", "reaction_session"):
        if {e[key] for e in train} & {e[key] for e in test}:
            raise ValueError("Fold splits a cluster or session")
    boundary = min(e["cutoff"] for e in test)
    if max(e["reaction_session"] for e in train) >= min(e["reaction_session"] for e in test):
        raise ValueError("Fold is not chronological")
    # The earliest test cutoff bounds the complete fit, including its prior pool.
    history = [e for e in train if e["available_at"][CLOSE] < boundary]

    def row(event, training):
        reason = exclusion(event)
        if training and event["available_at"][CLOSE] >= boundary:
            reason = "fit_label_not_mature"
        if reason:
            return {"event": event, "exclusion": reason}
        gap = event["labels"][OPEN]["value"]
        sign = 1 if gap > 0 else -1
        context, pool = issuer_context(event, history, prior)
        return {"event": event, "target": outcome(event), "baseline": (abs(gap), sign),
                "context": -sign * context / (1 + gap), "issuer_deviation": context,
                "own_history": sum(e["cik"] == event["cik"] for e in pool),
                "history_ids": [e["event_id"] for e in pool]}

    return [row(e, True) for e in train], [row(e, False) for e in test]


def fit(rows, contextual):
    def inputs(row):
        values = row["baseline"]
        return (*values, row["context"]) if contextual else values

    matrix = [inputs(row) for row in rows]
    means, scales, kept, dropped = m4_models.standardization(matrix)
    x = [m4_models.standardized(row, means, scales, kept) for row in matrix]
    beta = m4_models.fit_ridge(x, [row["target"] for row in rows])

    def predict(row):
        scaled = m4_models.standardized(inputs(row), means, scales, kept)
        return beta[0] + math.fsum(b * value for b, value in zip(beta[1:], scaled))

    return predict, dropped


def evaluate_fold(events, blocks, test_block, prior):
    fit_candidates, test_candidates = fold_rows(events, blocks, test_block, prior)
    train = [row for row in fit_candidates if "exclusion" not in row]
    test = [row for row in test_candidates if "exclusion" not in row]
    report = {"test_block": test_block, "fit_rows": len(train), "paired_rows": [],
              "fit_exclusions": dict(Counter(row["exclusion"] for row in fit_candidates if "exclusion" in row)),
              "test_exclusions": dict(Counter(row["exclusion"] for row in test_candidates if "exclusion" in row))}
    if not train or not test:
        return dict(report, status="insufficient_data")
    baseline, baseline_dropped = fit(train, False)
    challenger, challenger_dropped = fit(train, True)
    report["dropped_column_indexes"] = {"baseline": baseline_dropped, "challenger": challenger_dropped}
    report["history_inputs"] = {row["event"]["event_id"]: row["history_ids"] for row in train + test}
    for row in test:
        event = row["event"]
        base = baseline(row)
        context = challenger(row) if row["own_history"] else base
        report["paired_rows"].append({
            "event_id": event["event_id"], "issuer": event["cik"],
            "reaction_session": event["reaction_session"], "gap_sign": row["baseline"][1],
            "target": row["target"], "baseline": base, "challenger": context,
            "issuer_deviation": row["issuer_deviation"], "own_history": row["own_history"],
            "baseline_fallback": not row["own_history"],
        })
    return dict(report, status="scored")


def summarize(folds, protocol):
    rows = [row for fold in folds for row in fold["paired_rows"]]
    n = len(rows)
    counts = {"paired_rows": n, "issuers": len({row["issuer"] for row in rows}),
              "sessions": len({row["reaction_session"] for row in rows}),
              "up_gaps": sum(row["gap_sign"] == 1 for row in rows),
              "down_gaps": sum(row["gap_sign"] == -1 for row in rows),
              "baseline_fallbacks": sum(row["baseline_fallback"] for row in rows),
              "folds_with_minimum_pairs": sum(len(fold["paired_rows"]) >= protocol["gates"]["pairs_per_fold"]
                                              for fold in folds)}
    if not n:
        return {"counts": counts, "mean_improvement": None, "relative_mse_reduction": None,
                "interval_99": None}
    base = [(row["target"] - row["baseline"]) ** 2 for row in rows]
    challenger = [(row["target"] - row["challenger"]) ** 2 for row in rows]
    differences = [a - b for a, b in zip(base, challenger)]
    intervals = {axis: m4_metrics.cluster_bootstrap(
        differences, [row[axis] for row in rows], seed, replicates=protocol["bootstrap"]["replicates"],
        levels=(0.99,))["intervals"]["0.99"] for axis, seed in protocol["bootstrap"]["seeds"].items()}
    return {"counts": counts, "baseline_mse": mean(base), "challenger_mse": mean(challenger),
            "mean_improvement": mean(differences),
            "relative_mse_reduction": mean(differences) / mean(base) if mean(base) > 0 else None,
            "interval_99_by_axis": intervals,
            "interval_99": [min(x[0] for x in intervals.values()), max(x[1] for x in intervals.values())]}


def decision(clean, all_event, gates):
    pairs = ("paired_rows", "issuers", "sessions", "up_gaps", "down_gaps", "folds_with_minimum_pairs")
    if any(clean["counts"][key] < gates[key] for key in pairs):
        return "STOP_INSUFFICIENT_SUPPORT"
    if (clean["interval_99"][0] > 0 and clean["relative_mse_reduction"] is not None
            and clean["relative_mse_reduction"] >= gates["relative_mse_reduction"]
            and all_event["mean_improvement"] is not None and all_event["mean_improvement"] >= 0):
        return "ELIGIBLE_FOR_FRESH_STUDY_SCOPING"
    return "STOP_DEVELOPMENT_GATE_NOT_MET"


def pinned_inputs(root, protocol):
    for path, expected in protocol["input_canonical_sha256"].items():
        if digest(canonical(load(root / path))) != expected:
            raise ValueError(f"Pinned input mismatch: {path}")
    m4 = load(root / "config/m4-protocol.json")
    pins = m4["inputs"]
    spec_path = root / pins["events_spec"]["path"]
    spec = load(spec_path)
    data = fingerprints.load_inputs(spec_path, root / pins["sector_map"]["path"],
                                    root / pins["fingerprint_policy"]["path"], root,
                                    root / pins["calendar"]["path"])
    m4_protocol.require_verified(m4_protocol.verify_inputs(m4, data, spec, root))
    if m4_protocol.RIDGE_LAMBDA != protocol["ridge_penalty"]:
        raise ValueError("Ridge penalty changed")
    return (fingerprints.dedupe_clusters(data["events"]), assign_blocks(data["events"]),
            caveat_sensitivity.caveated_pairs(spec, with_derived=True))


def run_once():
    protocol, freeze = load(ROOT / PROTOCOL), load(ROOT / FREEZE)
    protocol_hash = digest(canonical(protocol))
    if protocol_hash != freeze["canonical_sha256"]:
        raise ValueError("Protocol hash mismatch")
    scope = protocol["scope"]
    scope_bytes = (ROOT / scope["path"]).read_bytes().replace(b"\r\n", b"\n")
    if digest(scope_bytes) != scope["sha256_git_lf"]:
        raise ValueError("Scope hash mismatch")
    if (ROOT / ATTEMPT).exists() or (ROOT / RESULT).exists():
        raise ValueError("The authorized comparison already has an attempt or result")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("Run from a clean committed checkout")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    provenance = {"code_commit": revision, "protocol_sha256": protocol_hash,
                  "started_at": datetime.now(timezone.utc).isoformat()}
    events, blocks, caveats = pinned_inputs(ROOT, protocol)
    with (ROOT / ATTEMPT).open("xb") as stream:
        stream.write(canonical(provenance) + b"\n")
    reports = {}
    for name, mask in (("clean_window", caveats), ("all_event", {})):
        rows = [dict(e, labels=mask_labels(e["labels"], mask.get(e["event_id"], ()))) for e in events]
        folds = [evaluate_fold(rows, blocks, block, protocol["issuer_prior"]) for block in protocol["test_blocks"]]
        reports[name] = {"folds": folds, "summary": summarize(folds, protocol)}
    result = {"schema_version": 1, **provenance, "development_events": len(events),
              "holdout_accesses": 0, "prospective_study": "ON_HOLD",
              "history_calendar": {e["event_id"]: {"close_available_at": e["available_at"][CLOSE].isoformat(),
                                                    "news_cutoff": e["cutoff"].isoformat()}
                                   for e in events},
              "reports": reports, "decision": decision(reports["clean_window"]["summary"],
                                                       reports["all_event"]["summary"], protocol["gates"])}
    with (ROOT / RESULT).open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    return result["decision"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", required=True)
    parser.parse_args()
    print(run_once())


if __name__ == "__main__":
    main()
