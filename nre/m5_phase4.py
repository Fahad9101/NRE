"""Prepare and execute the single authorized Milestone 5 holdout evaluation."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from urllib.request import build_opener

from . import caveat_sensitivity, event_acquire as ea, fingerprints, m4_metrics
from . import m5_harness as h, m5_phase1c as features
from .calendar import Calendar
from .core import canonical, digest
from .m4_harness import Abstain
from .m5_phase1b_audit import load

AUTH = "reports/m5-phase4-authorization-2026-11-13.json"
PHASE3 = "reports/m5-phase3-results-2026-11-13.json"
VERSIONS = ("clean_window", "all_event")


def prepare(artifact):
    authority = load(AUTH)
    if digest(Path(PHASE3).read_bytes().replace(b"\r\n", b"\n")) != authority["phase3_sha256"]:
        raise ValueError("Phase 3 evidence checksum mismatch")
    protocol, targets, events, calendar, caveats, _, daily = h.development_inputs(artifact)
    protocol_hash, feature_calendar, cohorts = features.load_inputs(Path("."))
    if protocol_hash != authority["protocol_sha256"]:
        raise ValueError("Authorization protocol checksum mismatch")
    specs = cohorts["holdout"]
    label_calendar = Calendar()
    m4 = load(protocol["inputs"]["m4_protocol"]["path"])
    sectors, _, _ = fingerprints.load_sector_map(m4["inputs"]["sector_map"]["path"])
    if ({event["cluster_id"] for event in events} & {event["cluster_id"] for event in specs}
            or max(e["reaction_session"] for e in events) >= min(e["expected_reaction_session"] for e in specs)):
        raise ValueError("Development and holdout are not disjoint and chronological")
    plans, predictors = {}, {}
    for target in protocol["targets"]:
        key = target["id"]
        plans[key], predictors[key] = {}, {}
        # Only metadata supplies the final cutoff. No holdout feature or label enters fitting.
        boundary_rows = [{"event_id": e["event_id"], "cluster_id": e["cluster_id"],
                          "reaction_session": e["expected_reaction_session"], "outcome": None,
                          "clock": (label_calendar.bounds(e["expected_reaction_session"])[0].isoformat()
                                    if target["clock"] == "C0" else e["cutoff"])} for e in specs]
        choices = None
        for version, pairs in (("clean_window", caveats), ("all_event", {})):
            if version == "all_event" and choices is None:
                plans[key][version] = {"status": "NO_CLEAN_WINDOW_CHOICE"}
                continue
            rows = h.target_rows(events, targets[key], calendar, pairs)
            result = h.run_fold(protocol, target, "final", rows, boundary_rows, daily, choices,
                                prepare_only=True)
            if isinstance(result, tuple):
                plan, predictor = result
                predictors[key][version] = predictor
                choices = plan["choices"]
            else:
                plan = result
            plans[key][version] = plan
    return protocol, targets, specs, label_calendar, feature_calendar, sectors, plans, predictors


def verified_holdout(protocol, specs, label_calendar, feature_calendar, sectors, fetch):
    provider = load(protocol["inputs"]["holdout"]["events_spec"]["path"])["provider"]
    observed = []
    for event in specs:
        window = ea.event_window(event, label_calendar)
        bars, _, actions, _ = ea.fetch_event_data(event, window, fetch)
        bundle = ea.build_bundle(event, provider, window, bars, actions, datetime.now(timezone.utc),
                                 label_calendar)
        outcomes, _ = ea.build(bundle, label_calendar)
        outcome, = outcomes
        if outcome["state"] != "MAPPED" or ea.labels_digest(outcome) != event["recorded_result"]["labels_sha256"]:
            raise ValueError("Holdout label commitment mismatch")
        security = event["security"]
        observed.append(fingerprints.make_event(
            label_calendar, event["event_id"], event["cluster_id"], security["ticker"], security["cik"],
            window["release_timing"], event["published_at"], event["cutoff"], window["reaction_session"],
            sectors[security["cik"]], outcome["labels"], labels_sha256=event["recorded_result"]["labels_sha256"]))
    data = features.acquire(specs, feature_calendar, fetch)
    rows = [features.event_features(event, feature_calendar, data)
            for event in sorted(specs, key=lambda event: event["event_id"])]
    commitment = digest(canonical(rows))
    if commitment != load(h.RECORD)["summary"]["holdout_features_sha256"]:
        raise ValueError("Holdout feature commitment mismatch")
    return observed, {row["event_id"]: row["features"] for row in rows}, commitment


def evaluate(protocol, targets, observed, calendar, daily, caveats, predictors):
    results = {}
    development = load(PHASE3)["targets"]
    for target in protocol["targets"]:
        key = target["id"]
        binary = target["kind"] == "binary"
        results[key] = {"development_gate_passed": development[key]["development_gate_passed"]}
        for version in VERSIONS:
            rows = h.target_rows(observed, targets[key], calendar, caveats if version == "clean_window" else {})
            eligible = [row for row in rows if row["outcome"] is not None]
            summary = {"eligible": len(eligible), "status": "COUNTS_ONLY"}
            if binary:
                summary["positives"] = sum(row["outcome"] for row in eligible)
                summary["negatives"] = len(eligible) - summary["positives"]
            results[key][version] = summary
            support = protocol["validation"]["support"]
            threshold = support["binary_development_and_holdout_minimum_each_class" if binary
                                else "regression_development_and_holdout_minimum"]
            predict = predictors[key].get(version)
            if predict is None or not h.enough(eligible, binary, threshold):
                continue
            scored = []
            for row in eligible:
                try:
                    candidate, baseline = predict(row, daily)
                except Abstain:
                    continue
                scored.append((row, candidate, baseline))
            summary["scored"] = len(scored)
            if not h.enough([row for row, _, _ in scored], binary, threshold):
                continue
            candidate_loss = [h.primary_loss(binary, row["outcome"], value) for row, value, _ in scored]
            baseline_loss = [h.primary_loss(binary, row["outcome"], value) for row, _, value in scored]
            contrasts = [a - b for a, b in zip(candidate_loss, baseline_loss)]
            intervals = {axis: m4_metrics.cluster_bootstrap(
                contrasts, [row[axis] for row, _, _ in scored],
                h.seeded(protocol, key, "final", "bootstrap_" + axis), replicates=5000)
                for axis in ("issuer", "reaction_session")}
            actual = [row["outcome"] for row, _, _ in scored]
            predictions = [value for _, value, _ in scored]
            calibration = ({"mean_forecast": mean(predictions), "observed_rate": mean(actual),
                            "reliability": m4_metrics.reliability(predictions, actual,
                                                                [row["event_id"] for row, _, _ in scored])}
                           if binary else m4_metrics.regression_metrics(actual, predictions))
            summary.update(status="EVALUABLE", candidate_loss=mean(candidate_loss),
                           baseline_loss=mean(baseline_loss), contrast=mean(contrasts),
                           cluster_intervals=intervals, calibration=calibration)
        # Phase 3 determined that no target cleared the prerequisite for promotion.
        if results[key]["development_gate_passed"]:
            raise ValueError("Unexpected Phase 3 promotion prerequisite")
        results[key]["promoted"] = False
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "look"))
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        protocol, targets, specs, calendar, feature_calendar, sectors, plans, predictors = prepare(args.artifact)
        lock = {"protocol_sha256": digest(canonical(protocol)), "code_commit": os.environ["GITHUB_SHA"],
                "development_artifact_sha256": digest(args.artifact.read_bytes()), "plans": plans}
        locked = args.output / "lock.json"
        if args.stage == "prepare":
            args.output.mkdir()
            locked.write_bytes(canonical(lock) + b"\n")
            print("Development pipeline locked.")
            return
        if canonical(load(locked)) != canonical(lock):
            raise ValueError("Development pipeline lock mismatch")
        fetch = features.bounded_fetch(ea.make_fetch(build_opener(ea.NoRedirect()),
                                                      os.environ["APCA_API_KEY_ID"],
                                                      os.environ["APCA_API_SECRET_KEY"]))
        # The workflow claims the durable GitHub tag before injecting Alpaca secrets.
        if os.environ.get("GITHUB_RUN_ATTEMPT") is None:
            raise ValueError("Phase 4 live access requires GitHub Actions")
        observed, daily, commitment = verified_holdout(protocol, specs, calendar, feature_calendar, sectors, fetch)
        caveats = caveat_sensitivity.caveated_pairs({"events": specs}, with_derived=True)
        results = evaluate(protocol, targets, observed, calendar, daily, caveats, predictors)
        result = {"protocol_sha256": lock["protocol_sha256"], "code_commit": lock["code_commit"],
                  "pipeline_lock_sha256": digest(canonical(lock)), "run_id": int(os.environ["GITHUB_RUN_ID"]),
                  "accesses": 1, "label_commitments_verified": len(observed),
                  "holdout_features_sha256": commitment, "targets": results}
        with (args.output / "result.json").open("xb") as stream:
            stream.write(canonical(result) + b"\n")
    except Exception:
        parser.exit(2, "Phase 4 stopped. No holdout metrics were released. Inspect the run and access marker before any retry.\n")


if __name__ == "__main__":
    main()
