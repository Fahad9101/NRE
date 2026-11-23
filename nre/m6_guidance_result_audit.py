"""Audit the one guidance result using hashes and aggregate evidence only."""
import json
import math

from .core import canonical, digest, timestamp
from .m5_phase1b_audit import load
from .m6_guidance_acquire import ACQUISITION, ATTEMPT, CONFIG, RESULT, ROOT, locked_inputs, require
from .m6_guidance_compare import decide


def membership(ids):
    return digest(canonical(sorted(ids)))


def verify_result(root=ROOT):
    config, protocol, events, quality, _, _ = locked_inputs(root)
    acquisition, attempt, result = (load(root / path) for path in (ACQUISITION, ATTEMPT, RESULT))
    require(attempt["attempt_id"] == "guidance-v2-001" and result["scoring_attempts"] == 1, "Unexpected attempt count")
    require(attempt["protocol_sha256"] == result["protocol_sha256"] == config["protocol_sha256"], "Result protocol differs")
    require(attempt["execution_configuration_sha256"] == digest(canonical(config)), "Attempt configuration differs")
    require(attempt["acquisition_sha256"] == result["acquisition_sha256"] == digest(canonical(acquisition)), "Result acquisition differs")
    require(result["attempt_sha256"] == digest(canonical(attempt))
            and result["execution_commit"] == attempt["execution_commit"]
            and result["workflow_run_id"] == attempt["workflow_run_id"], "Result attempt binding differs")
    require(result["raw_prices_or_event_returns_published"] is False, "Result disclosure boundary differs")
    require(acquisition["model_runs"] == 0 and result["closing_outcome_requests"] == acquisition["closing_outcome_requests"], "Result acquisition accounting differs")
    if not result["provider_wire_changes"]:
        require(result["reproduction_manifest_sha256"] == digest(canonical(acquisition)), "Exact acquisition replay digest differs")
    committed = {r["event_id"]: r for r in acquisition["events"] if r["status"] == "labels_committed"}
    by_id = {r["event_id"]: r for r in events}
    comparison = result["comparison"]
    close = lambda a, b: math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-15)
    for variant, clean in (("clean_window", True), ("all_defined", False)):
        report = comparison["reports"][variant]
        expected_pairs = []
        require(len(report["folds"]) == len(protocol["folds"]), "Result fold count differs")
        for specification, fold in zip(protocol["folds"], report["folds"]):
            require(fold["test_block"] == specification["test_block"], "Result fold ordering differs")
            full = [e for e in events if e.get("held_block") == specification["test_block"]]
            boundary = min(timestamp(e["feature_cutoff_at"]) for e in full)
            require(timestamp(fold["first_full_block_feature_cutoff"]) == boundary, "Full-block maturity boundary differs")

            def eligible(event, fit=False):
                q = quality[event["event_id"]]
                label = committed.get(event["event_id"])
                return (label is not None and not q["hard_exclusions"] and (not clean or not q["soft_caveats"])
                        and (not fit or timestamp(label["close_mature_at"]) < boundary))

            fit = [e for e in events if (e.get("held_block") or "warmup") in specification["fit_blocks"] and eligible(e, True)]
            test = [e for e in full if eligible(e)]
            for name, rows in (("fit", fit), ("test", test)):
                counts = {"rows": len(rows), "issuers": len({e["cik"] for e in rows}), "sessions": len({e["reaction_session"] for e in rows})}
                require(fold["fit_support" if name == "fit" else "eligible_test_support"] == counts, "Result support differs")
                require(fold[name + "_membership_sha256"] == membership([e["event_id"] for e in rows]), "Result membership digest differs")
            paired = [e["event_id"] for e in test] if fold["status"] == "scored" else []
            require(fold["paired_rows"] == len(paired) and fold["pair_membership_sha256"] == membership(paired), "Paired membership differs")
            expected_pairs.extend(paired)
        summary, counts = report["summary"], report["summary"]["counts"]
        require(summary["pair_membership_sha256"] == membership(expected_pairs)
                and counts["paired_rows"] == len(expected_pairs), "Pooled membership differs")
        require(counts["issuers"] == len({by_id[i]["cik"] for i in expected_pairs})
                and counts["sessions"] == len({by_id[i]["reaction_session"] for i in expected_pairs})
                and counts["up_gaps"] + counts["down_gaps"] == len(expected_pairs), "Pooled support differs")
        require(counts["folds_with_minimum_pairs"] == sum(f["paired_rows"] >= protocol["gates"]["pairs_per_fold"] for f in report["folds"]), "Fold support gate differs")
        for key, predicate in (("raises", lambda r: r > 0), ("cuts", lambda r: r < 0), ("unchanged", lambda r: r == 0)):
            require(counts[key] == sum(predicate(by_id[i]["revision_fraction"]) for i in expected_pairs), "Revision-sign support differs")
        if expected_pairs:
            baseline = math.fsum(f["baseline_squared_error_sum"] for f in report["folds"]) / len(expected_pairs)
            challenger = math.fsum(f["challenger_squared_error_sum"] for f in report["folds"]) / len(expected_pairs)
            require(close(summary["baseline_mse"], baseline) and close(summary["challenger_mse"], challenger)
                    and close(summary["mean_improvement"], baseline - challenger), "Aggregate loss arithmetic differs")
            require(baseline == 0 and summary["relative_mse_reduction"] is None or baseline > 0
                    and close(summary["relative_mse_reduction"], summary["mean_improvement"] / baseline), "Relative improvement differs")
            intervals = summary["cluster_bootstrap"]
            require(set(intervals) == set(protocol["bootstrap"]["seeds"]), "Bootstrap clusterings differ")
            for axis, boot in intervals.items():
                require(boot["seed"] == protocol["bootstrap"]["seeds"][axis]
                        and boot["replicates"] == protocol["bootstrap"]["replicates"]
                        and boot["events"] == len(expected_pairs)
                        and boot["clusters"] == counts["issuers" if axis == "issuer" else "sessions"], "Bootstrap settings differ")
            require(summary["interval_99"] == [min(v["intervals"]["0.99"][0] for v in intervals.values()),
                                                max(v["intervals"]["0.99"][1] for v in intervals.values())], "Outer bootstrap envelope differs")
    expected_decision = decide(comparison["reports"]["clean_window"], comparison["reports"]["all_defined"], protocol)
    require(comparison["decision"] == expected_decision, "Registered decision differs")
    return {"protocol_sha256": config["protocol_sha256"], "attempt_id": attempt["attempt_id"],
            "scoring_attempts": 1, "decision": expected_decision,
            "clean_counts": comparison["reports"]["clean_window"]["summary"]["counts"],
            "aggregate_and_membership_audit": "passed"}


if __name__ == "__main__":
    print(json.dumps(verify_result(), sort_keys=True))
