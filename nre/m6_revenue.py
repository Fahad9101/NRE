"""Run the frozen M6 revenue-growth development comparison once."""
import argparse
import math
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone

from .calendar import Calendar
from .core import canonical, digest, timestamp
from .m4_data import mask_labels
from .m5_phase1b_audit import load
from .m6_context import CLOSE, OPEN, ROOT, decision, exclusion, fit, outcome, pinned_inputs, summarize

PROTOCOL = "config/m6-revenue-protocol.json"
FREEZE = "reports/m6-revenue-freeze-2026-11-16.json"
ATTEMPT = "reports/m6-revenue-attempt-2026-11-16.json"
RESULT = "reports/m6-revenue-result-2026-11-16.json"


def revenue_feature(audit_row, cutoff):
    evidence = audit_row["scheduled_open"]
    if evidence["status"] != "usable":
        return None, "revenue_unavailable"
    if timestamp(evidence["availability_proxy"]) >= cutoff:
        return None, "revenue_at_or_after_cutoff"
    growth = evidence["growth_fraction"]
    current, prior = evidence["current_usd"], evidence["prior_usd"]
    if (type(current) not in (int, float) or type(prior) not in (int, float)
            or not math.isfinite(current) or not math.isfinite(prior) or current < 0 or prior <= 0
            or type(growth) not in (int, float) or not math.isfinite(growth)
            or growth != current / prior - 1):
        raise ValueError("Invalid revenue growth in pinned evidence")
    return math.asinh(growth), None


def join_features(events, blocks, caveats, calendar, audit, protocol):
    by_id = {row["event_id"]: row for row in audit["events"]}
    ids = {e["event_id"] for e in events}
    if (len(events) != protocol["development_events"] or len(ids) != len(events)
            or len(by_id) != len(audit["events"]) or by_id.keys() != ids
            or set(blocks.values()) != set(range(1, max(protocol["test_blocks"]) + 1))):
        raise ValueError("Unexpected development cohort or audit membership")
    features = {}
    for event in events:
        eid = event["event_id"]
        row = by_id[eid]
        opening, _ = calendar.bounds(event["reaction_session"])
        if (any(row[key] != event[key] for key in ("cik", "reaction_session", "release_timing"))
                or row["block"] != blocks[eid]
                or timestamp(row["published_at"]) != event["published_at"]
                or timestamp(row["news_cutoff_at"]) != event["cutoff"]
                or timestamp(row["scheduled_open_at"]) != opening
                or row["clean_label_metadata"] != (not ({OPEN, CLOSE} & set(caveats.get(eid, ()))))):
            raise ValueError(f"Audit evidence does not join to development event {eid}")
        cutoff = opening - timedelta(minutes=protocol["feature_lead_minutes"])
        if event["published_at"] >= cutoff:
            context, reason = None, "release_at_or_after_cutoff"
        else:
            context, reason = revenue_feature(row, cutoff)
        features[eid] = {"cutoff": cutoff, "context": context, "revenue_exclusion": reason,
                         "source": row["scheduled_open"].get("source", "sec_periodic_filing") if not reason else None}
    return features


def evaluate_fold(events, blocks, features, block, minimum_fit_rows):
    earlier = [e for e in events if blocks[e["event_id"]] < block]
    held = [e for e in events if blocks[e["event_id"]] == block]
    if not earlier or not held:
        raise ValueError("Missing fold partition")
    if max(e["reaction_session"] for e in earlier) >= min(e["reaction_session"] for e in held):
        raise ValueError("Fold splits a session or is not chronological")
    if {e["cluster_id"] for e in earlier} & {e["cluster_id"] for e in held}:
        raise ValueError("Fold splits an economic cluster")
    boundary = min(features[e["event_id"]]["cutoff"] for e in held)

    def eligible(partition, training):
        rows, exclusions = [], Counter()
        for event in partition:
            feature = features[event["event_id"]]
            reason = feature["revenue_exclusion"] or exclusion(event)
            if training and event["available_at"][CLOSE] >= boundary:
                reason = "fit_label_not_mature"
            if reason:
                exclusions[reason] += 1
                continue
            gap = event["labels"][OPEN]["value"]
            rows.append({"event": event, "target": outcome(event), "context": feature["context"],
                         "source": feature["source"], "baseline": (abs(gap), 1 if gap > 0 else -1)})
        return rows, dict(exclusions)

    train, fit_exclusions = eligible(earlier, True)
    test, test_exclusions = eligible(held, False)
    report = {"test_block": block, "fit_rows": len(train), "eligible_test_rows": len(test),
              "fit_exclusions": fit_exclusions, "test_exclusions": test_exclusions,
              "first_test_feature_cutoff": boundary.isoformat(), "paired_rows": []}
    if len(train) < minimum_fit_rows or not test:
        return dict(report, status="insufficient_data")
    baseline, base_dropped = fit(train, False)
    challenger, rev_dropped = fit(train, True)
    for row in test:
        event = row["event"]
        report["paired_rows"].append({
            "event_id": event["event_id"], "issuer": event["cik"], "reaction_session": event["reaction_session"],
            "gap_sign": row["baseline"][1], "target": row["target"], "baseline": baseline(row),
            "challenger": challenger(row), "baseline_fallback": False,
            "revenue_sign": (row["context"] > 0) - (row["context"] < 0), "source": row["source"],
        })
    return dict(report, status="scored", dropped_column_indexes={"baseline": base_dropped, "challenger": rev_dropped})


def coverage(events, features):
    dimensions = {
        "issuer": lambda e: e["cik"],
        "reaction_quarter": lambda e: f'{e["reaction_session"][:4]}Q{(int(e["reaction_session"][5:7]) - 1) // 3 + 1}',
        "release_timing": lambda e: e["release_timing"],
    }
    report = {}
    for dimension, group in dimensions.items():
        screened = Counter(group(e) for e in events)
        usable = Counter(group(e) for e in events if features[e["event_id"]]["revenue_exclusion"] is None)
        report[dimension] = {key: {"screened": count, "usable": usable[key]} for key, count in screened.items()}
    return report


def evaluate(events, blocks, features, mask, protocol):
    masked = [dict(e, labels=mask_labels(e["labels"], mask.get(e["event_id"], ()))) for e in events]
    folds = [evaluate_fold(masked, blocks, features, block, protocol["minimum_fit_rows"])
             for block in protocol["test_blocks"]]
    summary = summarize(folds, protocol)
    rows = [row for fold in folds for row in fold["paired_rows"]]
    summary["growth_signs"] = dict(Counter(str(row["revenue_sign"]) for row in rows))
    summary["feature_sources"] = dict(Counter(row["source"] for row in rows))
    for fold in folds:
        paired = fold.pop("paired_rows")
        fold["pairs"] = len(paired)
        fold["pair_membership_sha256"] = digest(canonical([r["event_id"] for r in paired]))
        fold["baseline_squared_error_sum"] = math.fsum((r["target"] - r["baseline"]) ** 2 for r in paired)
        fold["challenger_squared_error_sum"] = math.fsum((r["target"] - r["challenger"]) ** 2 for r in paired)
    return {"folds": folds, "summary": summary}


def run_once():
    protocol, freeze = load(ROOT / PROTOCOL), load(ROOT / FREEZE)
    protocol_hash = digest(canonical(protocol))
    if protocol_hash != freeze["canonical_sha256"]:
        raise ValueError("Protocol hash mismatch")
    if (ROOT / ATTEMPT).exists() or (ROOT / RESULT).exists():
        raise ValueError("The comparison already has an attempt or result")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("Run from a clean committed checkout")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    events, blocks, caveats = pinned_inputs(ROOT, protocol)
    calendar = Calendar(load(ROOT / protocol["calendar"]))
    audit = load(ROOT / protocol["audit"])
    if audit["method_sha256"] != protocol["input_canonical_sha256"][protocol["audit_method"]]:
        raise ValueError("Coverage audit method hash mismatch")
    features = join_features(events, blocks, caveats, calendar, audit, protocol)
    provenance = {"code_commit": revision, "protocol_sha256": protocol_hash,
                  "started_at": datetime.now(timezone.utc).isoformat()}
    with (ROOT / ATTEMPT).open("xb") as stream:
        stream.write(canonical(provenance) + b"\n")
    clean = evaluate(events, blocks, features, caveats, protocol)
    all_event = evaluate(events, blocks, features, {}, protocol)
    status = decision(clean["summary"], all_event["summary"], protocol["gates"])
    if any(fold["fit_rows"] < protocol["minimum_fit_rows"] for fold in clean["folds"]):
        status = "STOP_INSUFFICIENT_SUPPORT"
    result = {"schema_version": 1, **provenance, "development_events": len(events),
              "confirmation_cohort_accesses": 0, "prospective_study": "ON_HOLD",
              "coverage_before_label_screen": coverage(events, features),
              "reports": {"clean_window": clean, "all_event": all_event}, "decision": status}
    with (ROOT / RESULT).open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", required=True)
    parser.parse_args()
    print(run_once())


if __name__ == "__main__":
    main()
