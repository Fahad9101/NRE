"""Check the frozen guidance study's source-only training and held support."""
import argparse
import json
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path

from .calendar import Calendar
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load
from .m6_guidance_protocol import PROTOCOL, ROOT, check_registration

WARMUP = "reports/m6-guidance-warmup-evidence-2026-11-19.json"
MASKS = "reports/m6-guidance-source-masks-2026-11-19.json"
FREEZE = "reports/m6-guidance-preparation-freeze-2026-11-19.json"


def partition(rows, masks, *, clean):
    accepted, reasons = [], Counter()
    for row in rows:
        mask = masks[row["event_id"]]
        if mask["hard_exclusions"]:
            reasons["hard_source_exclusion"] += 1
        elif clean and mask["soft_caveats"]:
            reasons["soft_source_caveat"] += 1
        else:
            accepted.append(row)
    return accepted, dict(reasons)


def support(rows):
    return {"rows": len(rows), "issuers": len({r["cik"] for r in rows}),
            "sessions": len({r["reaction_session"] for r in rows})}


def check_preparation(root=ROOT):
    registration = check_registration(root)
    protocol = load(root / PROTOCOL)
    freeze = load(root / FREEZE)
    if registration["protocol_sha256"] != freeze["protocol_sha256"]:
        raise DataError("Preparation protocol differs")
    if set(freeze["canonical_input_sha256"]) != {WARMUP, MASKS}:
        raise DataError("Preparation must pin both complete source manifests")
    for path, expected in freeze["canonical_input_sha256"].items():
        if digest(canonical(load(root / path))) != expected:
            raise DataError(f"Preparation source changed: {path}")
    if set(freeze["implementation_sha256_git_lf"]) != {"nre/m6_guidance_readiness.py"}:
        raise DataError("Preparation must pin its verifier")
    for path, expected in freeze["implementation_sha256_git_lf"].items():
        if digest((root / path).read_bytes().replace(b"\r\n", b"\n")) != expected:
            raise DataError(f"Preparation verifier changed: {path}")
    warmup, source_masks = load(root / WARMUP), load(root / MASKS)
    held = load(root / protocol["held_evidence"])["guidance_candidates"]
    candidates = warmup["candidate_events"]
    if (warmup["protocol_sha256"] != registration["protocol_sha256"]
            or source_masks["protocol_sha256"] != registration["protocol_sha256"]):
        raise DataError("Source preparation does not bind the registration")
    masks = {r["event_id"]: r for r in source_masks["events"]}
    all_ids = [r["event_id"] for r in candidates + held]
    if len(set(all_ids)) != len(all_ids) or len(masks) != len(source_masks["events"]) or set(masks) != set(all_ids):
        raise DataError("Source masks do not match the complete study membership")
    qualified = {r["cik"] for r in held}
    calendar = Calendar(load(root / protocol["calendar"]))
    lead = timedelta(minutes=protocol["clocks"]["revenue_feature_lead_minutes"])
    taxonomy = source_masks["taxonomy"]
    if (list(taxonomy["hard_exclusions"].values())[:-1] != protocol["source_quality"]["hard_catalysts"]
            or list(taxonomy["soft_caveats"].values()) != protocol["source_quality"]["soft_source_caveats"]
            or taxonomy["hard_exclusions"].get("unresolved_source_or_material_scope")
            != "Unknown provenance or unresolved material comparability is a hard exclusion, per the registered source-quality freeze rule."):
        raise DataError("Source taxonomy differs from the registration")
    for row in candidates + held:
        mask = masks[row["event_id"]]
        day = row["reaction_session"]
        opening, _ = calendar.bounds(day)
        _, anchor_close = calendar.bounds(calendar.offset(day, -1))
        if (mask["symbol"] != row["symbol"] or mask["cik"] != row["cik"]
                or mask["reaction_session"] != day
                or timestamp(mask["observation_window"]["start_inclusive"]) != anchor_close
                or timestamp(mask["observation_window"]["end_exclusive"]) != opening - lead):
            raise DataError("Source observation window or identity differs")
        for field in ("hard_exclusions", "soft_caveats"):
            if len(set(mask[field])) != len(mask[field]) or not set(mask[field]) <= set(taxonomy[field]):
                raise DataError("Unregistered source mask")
        if not mask["evidence"] or not mask["rationale"]:
            raise DataError("Source disposition has no evidence")
    first, last = protocol["warmup"]["reaction_sessions"]
    for row in candidates:
        if row["cik"] not in qualified or not first <= row["reaction_session"] <= last:
            raise DataError("Warmup membership is outside the registration")
        current, prior = row["current"], row["prior"]
        session, timing = calendar.classify(current["source_time"])
        opening, _ = calendar.bounds(session)
        if (row["reaction_session"] != session or row["release_timing"] != timing
                or timestamp(row["scheduled_open_at"]) != opening
                or timestamp(row["feature_cutoff_at"]) != opening - lead
                or not timestamp(prior["availability_proxy"]) < timestamp(current["source_time"])
                < timestamp(current["availability_proxy"]) < opening - lead):
            raise DataError("Warmup source clock differs")
        for source in (prior, current):
            low, high = source["range_usd_millions"]
            if not all(math.isfinite(v) for v in (low, high)) or not 0 <= low <= high or low + high <= 0:
                raise DataError("Invalid warmup guidance bounds")
        revision = sum(current["range_usd_millions"]) / sum(prior["range_usd_millions"]) - 1
        if not math.isclose(revision, row["revision_fraction"], rel_tol=1e-12, abs_tol=1e-12):
            raise DataError("Warmup guidance revision differs")
        listing = row["listing_evidence"]
        if (listing["event_id"] != row["event_id"] or not listing["cover_sha256"]
                or not any(r["symbol"] == row["symbol"] and "NASDAQ" in r["exchange"].upper()
                           for r in listing["listed_securities"])):
            raise DataError("Warmup listing evidence differs")
    eligible = {r["event_id"] for r in candidates if not masks[r["event_id"]]["hard_exclusions"]}
    if eligible != {r["event_id"] for r in warmup["guidance_candidates"]}:
        raise DataError("Warmup opening cohort differs from the source dispositions")
    discovery = warmup["filing_dispositions"]
    keys = [(r["cik"], r["accession"]) for r in discovery]
    candidate_keys = {(r["cik"], r["current"]["accession"]) for r in candidates}
    if len(set(keys)) != len(keys) or not candidate_keys <= set(keys):
        raise DataError("Warmup filing disposition ledger is inconsistent")
    reports = {}
    for variant, clean in (("clean_window", True), ("all_defined", False)):
        train, training_exclusions = partition(candidates, masks, clean=clean)
        tests, held_exclusions = partition(held, masks, clean=clean)
        folds = []
        for fold in protocol["folds"]:
            fit_rows = train + [r for r in tests if r["held_block"] in fold["fit_blocks"]]
            scored = [r for r in tests if r["held_block"] == fold["test_block"]]
            fit_support = support(fit_rows)
            fit_possible = (fit_support["rows"] >= protocol["warmup"]["minimum_common_fit_rows"]
                            and fit_support["issuers"] >= protocol["warmup"]["minimum_common_fit_issuers"])
            folds.append({"test_block": fold["test_block"], "source_eligible_fit": fit_support,
                          "source_eligible_test": support(scored), "fit_floor_possible": fit_possible})
        counts = support(tests)
        gates = protocol["gates"]
        held_possible = (counts["rows"] >= gates["paired_rows"] and counts["issuers"] >= gates["issuers"]
                         and counts["sessions"] >= gates["sessions"]
                         and sum(f["source_eligible_test"]["rows"] >= gates["pairs_per_fold"] for f in folds)
                         >= gates["folds_with_minimum_pairs"])
        reports[variant] = {"warmup": support(train), "warmup_exclusions": training_exclusions,
                            "held": counts, "held_exclusions": held_exclusions, "folds": folds,
                            "source_support_possible": held_possible and all(f["fit_floor_possible"] for f in folds)}
    possible = reports["clean_window"]["source_support_possible"]
    return {"protocol_sha256": registration["protocol_sha256"],
            "preparation_manifest_sha256": freeze["canonical_input_sha256"],
            "implementation_sha256_git_lf": freeze["implementation_sha256_git_lf"],
            "count_semantics": "Source-eligible upper bounds for reviewed candidates, before raw warmup openings, price basis, label maturity and other market-quality checks.",
            "source_support": reports,
            "decision": "READY_FOR_RAW_WARMUP_OPENINGS" if possible else "STOP_INSUFFICIENT_SOURCE_SUPPORT",
            "closing_outcome_requests": 0, "model_runs": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(check_preparation(args.root), sort_keys=True))


if __name__ == "__main__":
    main()
