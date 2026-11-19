"""Verify the guidance study registration using source metadata and opening dispositions."""
import argparse
import json
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path

from .calendar import Calendar
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "config/m6-guidance-protocol.json"
FREEZE = "reports/m6-guidance-freeze-2026-11-19.json"


def verify_evidence(protocol, frame, evidence, raw, calendar_spec):
    if digest(canonical(frame)) != evidence["frame_canonical_sha256"]:
        raise DataError("Guidance frame differs from the evidence")
    if digest(canonical(evidence)) != raw["evidence_canonical_sha256"]:
        raise DataError("Raw openings do not bind the guidance evidence")
    output = raw["output"]
    if (raw["conclusion"] != "success" or output["scope"] != "guidance_expanded_official_open_coverage"
            or output["guidance_evidence_sha256"] != raw["evidence_canonical_sha256"]):
        raise DataError("Raw opening verification is incomplete")
    events = evidence["guidance_candidates"]
    keys = [(row["symbol"], row["reaction_session"]) for row in events]
    if (len(set(keys)) != len(keys) or len(keys) != protocol["held_rows_before_label_screen"]
            or keys != [(row["symbol"], row["reaction_session"]) for row in output["events"]]
            or output["screened"] != len(keys)):
        raise DataError("Opening results do not match the frozen membership")
    counts = Counter(row["status"] for row in output["events"])
    if dict(counts) != output["dispositions"] or output["matched"] != counts["verified_open"]:
        raise DataError("Opening disposition counts differ")
    calendar = Calendar(calendar_spec)
    lead = timedelta(minutes=protocol["clocks"]["revenue_feature_lead_minutes"])
    verified = []
    for event, opening in zip(events, output["events"]):
        session, timing = calendar.classify(event["current"]["source_time"])
        scheduled, _ = calendar.bounds(session)
        cutoff = scheduled - lead
        prior_at = timestamp(event["prior"]["accepted_at"])
        current_at = timestamp(event["current"]["source_time"])
        if (event["reaction_session"] != session or event["release_timing"] != timing
                or timestamp(event["scheduled_open_at"]) != scheduled
                or timestamp(event["feature_cutoff_at"]) != cutoff
                or not prior_at < current_at < timestamp(event["current"]["availability_proxy"]) < cutoff):
            raise DataError("Guidance clock fails the registered strict cutoff")
        low, high = event["prior"]["range_usd_millions"]
        new_low, new_high = event["current"]["range_usd_millions"]
        values = (low, high, new_low, new_high)
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
                or not 0 <= low <= high or low + high <= 0 or not 0 <= new_low <= new_high):
            raise DataError("Invalid guidance range")
        revision = (new_low + new_high) / (low + high) - 1
        if not math.isclose(revision, event["revision_fraction"], rel_tol=1e-12, abs_tol=1e-14):
            raise DataError("Guidance midpoint arithmetic differs")
        folds = [fold for fold in protocol["folds"]
                 if fold["test_sessions"][0] <= session <= fold["test_sessions"][1]]
        if len(folds) != 1 or folds[0]["test_block"] != event["held_block"]:
            raise DataError("Held block differs from the registered chronology")
        listing = event["listing_evidence"]
        if listing["symbol"] != event["symbol"] or "nasdaq" not in listing["exchange"].lower():
            raise DataError("Historical listing evidence differs")
        if opening["status"] == "verified_open":
            verified.append(event)
    blocks = Counter(row["held_block"] for row in verified)
    signs = Counter("raise" if row["revision_fraction"] > 0 else "cut" if row["revision_fraction"] < 0
                    else "unchanged" for row in verified)
    support = {"rows": len(verified), "issuers": len({row["cik"] for row in verified}),
               "sessions": len({row["reaction_session"] for row in verified}), "held_blocks": dict(blocks),
               "guidance_signs": dict(signs),
               "cut_issuers": len({row["cik"] for row in verified if row["revision_fraction"] < 0})}
    floors = frame["planning_floors"]
    coverage = (support["rows"] >= floors["clean_held_pairs"] and support["issuers"] >= floors["issuers"]
                and support["sessions"] >= floors["sessions"]
                and sum(n >= floors["minimum_pairs_per_held_block"] for n in blocks.values())
                >= floors["held_blocks_with_minimum"] and signs["raise"] > 0 and signs["cut"] > 0)
    return {"raw_opening_support": support, "raw_opening_coverage_passed": coverage}


def check_registration(root=ROOT):
    protocol, freeze = load(root / PROTOCOL), load(root / FREEZE)
    if digest(canonical(protocol)) != freeze["canonical_sha256"]:
        raise DataError("Guidance protocol differs from the freeze")
    for path, expected in protocol["input_canonical_sha256"].items():
        if digest(canonical(load(root / path))) != expected:
            raise DataError(f"Registered input changed: {path}")
    for path, expected in protocol["implementation_sha256_git_lf"].items():
        if digest((root / path).read_bytes().replace(b"\r\n", b"\n")) != expected:
            raise DataError(f"Registered model implementation changed: {path}")
    frame = load(root / protocol["frame"])
    evidence = load(root / protocol["held_evidence"])
    for path, expected in frame["excluded_cohort_canonical_hashes"].items():
        if protocol["input_canonical_sha256"].get(path) != expected:
            raise DataError("Prior-cohort exclusion pins differ")
    old = load(root / "config/m2-step3-combined-events.json")
    extension = load(root / "config/m5-phase1b-cohort-spec.json")
    excluded = {row["security"]["cik"] for row in old["events"]} | {row["cik"] for row in extension["issuers"]}
    if any(event["cik"] in excluded for event in evidence["guidance_candidates"]):
        raise DataError("A previously studied issuer entered the new cohort")
    result = verify_evidence(protocol, frame, evidence, load(root / protocol["raw_opening_result"]),
                             load(root / protocol["calendar"]))
    return {"protocol_id": protocol["protocol_id"], "protocol_sha256": freeze["canonical_sha256"],
            **result, "stage": protocol["execution"]["current_stage"],
            "pending": ["Lock the complete warmup features and source masks", "Verify raw warmup openings",
                        "Acquire and commit hash-only label and quality manifests", "Implement and freeze the one-run scorer"],
            "model_runs": 0}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(check_registration(), sort_keys=True))


if __name__ == "__main__":
    main()
