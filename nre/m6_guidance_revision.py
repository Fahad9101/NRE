"""Verify the separately versioned, source-only annual-guidance warmup extension."""
import argparse
import copy
import json
import math
import re
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlparse

from .calendar import Calendar
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load
from .m6_guidance_protocol import (
    FREEZE as PARENT_FREEZE, PROTOCOL as PARENT_PROTOCOL, ROOT, check_registration,
)
from .m6_guidance_readiness import (
    FREEZE as PARENT_PREPARATION, MASKS as PARENT_MASKS, WARMUP as PARENT_WARMUP,
    check_preparation, partition, support,
)

PROTOCOL = "config/m6-guidance-protocol-v2.json"
FREEZE = "reports/m6-guidance-v2-freeze-2026-11-19.json"
EARLIER = "reports/m6-guidance-earlier-evidence-2026-11-19.json"
MASKS = "reports/m6-guidance-earlier-source-masks-2026-11-19.json"
RESULT = "reports/m6-guidance-v2-readiness-2026-11-19.json"
PARENT_RESULT = "reports/m6-guidance-preparation-result-2026-11-19.json"
PARENT_SHA256 = "9aab2dbb0e56d2e484081df701c9951780ff30feae3b3644dd4b017d7be47d77"
EARLIER_WINDOW = ["2024-07-01", "2024-12-31"]
WARMUP_WINDOW = ["2024-07-01", "2025-06-30"]
SOURCE_PREPARATION = {"earlier_evidence": EARLIER, "earlier_source_masks": MASKS}


def verify_revision(protocol, parent):
    """Permit the disclosed training-window adaptation without changing the experiment."""
    lineage = protocol.get("lineage", {})
    if (lineage.get("parent_protocol") != PARENT_PROTOCOL
            or lineage.get("parent_protocol_sha256") != PARENT_SHA256
            or lineage.get("parent_source_decision") != PARENT_RESULT
            or protocol.get("source_preparation") != SOURCE_PREPARATION
            or protocol.get("version") != 2
            or protocol["warmup"]["reaction_sessions"] != WARMUP_WINDOW):
        raise DataError("Invalid guidance revision lineage or fixed warmup window")
    normalized = copy.deepcopy(protocol)
    normalized.pop("lineage")
    normalized.pop("source_preparation")
    normalized["version"] = parent["version"]
    normalized["warmup"]["reaction_sessions"] = parent["warmup"]["reaction_sessions"]
    if not isinstance(normalized["warmup"]["reason_for_fit_floor"], str) or not normalized["warmup"]["reason_for_fit_floor"].strip():
        raise DataError("Guidance revision needs a training-support rationale")
    normalized["warmup"]["reason_for_fit_floor"] = parent["warmup"]["reason_for_fit_floor"]
    for field in ("current_stage", "outcome_exposure"):
        if not isinstance(normalized["execution"][field], str) or not normalized["execution"][field].strip():
            raise DataError("Guidance revision needs explicit stage and outcome exposure")
        normalized["execution"][field] = parent["execution"][field]
    normalized["input_canonical_sha256"] = parent["input_canonical_sha256"]
    normalized["implementation_sha256_git_lf"] = parent["implementation_sha256_git_lf"]
    if normalized != parent:
        raise DataError("Guidance revision changes a setting outside the allowed warmup adaptation")


def verify_source(row, symbol, cik, calendar):
    if (row.get("symbol") != symbol or row.get("cik") != cik
            or not re.fullmatch(r"[0-9a-f]{64}", row.get("archive_sha256", ""))):
        raise DataError("Earlier source identity or digest is invalid")
    if row.get("source_kind") == "issuer_release":
        url = urlparse(row.get("release_url", ""))
        if url.scheme != "https" or not url.hostname:
            raise DataError("Earlier original issuer source URL is invalid")
        if row.get("published_at"):
            source_at = timestamp(row["published_at"])
            proxy = source_at + timedelta(minutes=1)
        else:
            # A publication date supplies an interval, never a fabricated acceptance.
            day = datetime.fromisoformat(row["publication_date"]).date()
            source_at = datetime.combine(day, time(), calendar.zone).astimezone(timezone.utc)
            proxy = datetime.combine(day + timedelta(days=1), time(), calendar.zone).astimezone(timezone.utc)
        if timestamp(row["availability_proxy"]) != proxy:
            raise DataError("Earlier source clock has a different issuer availability bound")
        values = row["range_usd_millions"]
        if (len(values) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or not 0 <= values[0] <= values[1]):
            raise DataError("Earlier guidance range is invalid")
        return source_at, proxy
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", row.get("accession", "")):
        raise DataError("Earlier SEC source accession is invalid")
    expected_path = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{row['accession'].replace('-', '')}/"
    if not row.get("release_url", "").startswith(expected_path):
        raise DataError("Earlier source URL differs from its SEC identity")
    accepted = timestamp(row["accepted_at"])
    if accepted.astimezone(calendar.zone).time() >= time(17, 30):
        raise DataError("Earlier source clock has a late SEC acceptance")
    filed = datetime.combine(datetime.fromisoformat(row["source_date"]).date(), time(), calendar.zone)
    proxy = max(accepted + timedelta(minutes=2), filed.astimezone(timezone.utc))
    if timestamp(row["availability_proxy"]) != proxy:
        raise DataError("Earlier source clock has a different availability proxy")
    values = row["range_usd_millions"]
    if (len(values) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
            or not 0 <= values[0] <= values[1]):
        raise DataError("Earlier guidance range is invalid")
    return accepted, proxy


def verify_earlier(protocol, evidence, source_masks, inherited, held, taxonomy, calendar):
    if (evidence.get("parent_protocol_sha256") != PARENT_SHA256
            or source_masks.get("parent_protocol_sha256") != PARENT_SHA256
            or evidence.get("reaction_sessions") != EARLIER_WINDOW
            or source_masks["taxonomy"] != taxonomy):
        raise DataError("Earlier source metadata differs from the parent registration")
    candidates, mask_rows = evidence["candidate_events"], source_masks["events"]
    masks = {r["event_id"]: r for r in mask_rows}
    ids = [r["event_id"] for r in candidates]
    inherited_ids = {r["event_id"] for r in inherited + held}
    if (len(set(ids)) != len(ids) or len(masks) != len(mask_rows) or set(ids) != set(masks)
            or set(ids) & inherited_ids):
        raise DataError("Earlier source membership is duplicated, overlaps inheritance, or lacks masks")
    current_keys = [(r["cik"], r["current"]["accession"]) for r in candidates]
    session_keys = [(r["cik"], r["reaction_session"]) for r in candidates]
    if len(set(current_keys)) != len(current_keys) or len(set(session_keys)) != len(session_keys):
        raise DataError("Earlier economic event is duplicated by accession or issuer session")
    qualified = {r["cik"] for r in held}
    lead = timedelta(minutes=protocol["clocks"]["revenue_feature_lead_minutes"])
    for row in candidates:
        day, symbol, cik = row["reaction_session"], row["symbol"], row["cik"]
        if cik not in qualified or not EARLIER_WINDOW[0] <= day <= EARLIER_WINDOW[1]:
            raise DataError("Earlier warmup membership is outside the registered window or issuer set")
        prior, current = row["prior"], row["current"]
        prior_at, prior_proxy = verify_source(prior, symbol, cik, calendar)
        current_at, current_proxy = verify_source(current, symbol, cik, calendar)
        session, timing = calendar.classify(current["source_time"])
        opening, _ = calendar.bounds(day)
        _, anchor = calendar.bounds(calendar.offset(day, -1))
        cutoff = opening - lead
        if (timestamp(current["source_time"]) != current_at or session != day
                or timing != row["release_timing"] or timestamp(row["scheduled_open_at"]) != opening
                or timestamp(row["feature_cutoff_at"]) != cutoff
                or not prior_at < prior_proxy < current_at < current_proxy < cutoff):
            raise DataError("Earlier source clock violates the strict feature cutoff or chronology")
        previous_total = sum(prior["range_usd_millions"])
        if previous_total <= 0:
            raise DataError("Earlier prior guidance midpoint must be positive")
        revision = sum(current["range_usd_millions"]) / previous_total - 1
        if not math.isclose(revision, row["revision_fraction"], rel_tol=1e-12, abs_tol=1e-14):
            raise DataError("Earlier guidance midpoint revision differs")
        listing, mask = row["listing_evidence"], masks[row["event_id"]]
        cover_prefix = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{current['accession'].replace('-', '')}/"
        if (listing["event_id"] != row["event_id"]
                or not re.fullmatch(r"[0-9a-f]{64}", listing["cover_sha256"])
                or not listing.get("cover_url", "").startswith(cover_prefix)
                or listing.get("cover_url") != current.get("cover_url")
                or not any(s["symbol"] == symbol and "nasdaq" in s["exchange"].lower()
                           for s in listing["listed_securities"])):
            raise DataError("Earlier dated listing evidence differs")
        if (mask["symbol"] != symbol or mask["cik"] != cik or mask["reaction_session"] != day
                or timestamp(mask["observation_window"]["start_inclusive"]) != anchor
                or timestamp(mask["observation_window"]["end_exclusive"]) != cutoff):
            raise DataError("Earlier source mask identity or observation window differs")
        for field in ("hard_exclusions", "soft_caveats"):
            if len(set(mask[field])) != len(mask[field]) or not set(mask[field]) <= set(taxonomy[field]):
                raise DataError("Earlier source mask uses an unregistered category")
        if not mask["evidence"] or not mask["rationale"]:
            raise DataError("Earlier source mask has no evidence or rationale")
    discovery = evidence["filing_dispositions"]
    keys = [(r["cik"], r["accession"]) for r in discovery]
    current_keys = set(current_keys)
    reviewed = {(r["cik"], r["accession"]) for r in discovery if r["disposition"] == "PAIR_REVIEWED"}
    if len(set(keys)) != len(keys) or not current_keys <= set(keys) or current_keys != reviewed:
        raise DataError("Earlier filing disposition ledger differs from the reviewed pairs")
    for row in discovery:
        if (row["cik"] not in qualified or not re.fullmatch(r"[0-9a-f]{64}", row.get("archive_sha256", ""))
                or not row.get("rationale")):
            raise DataError("Earlier filing disposition lacks identity, source digest or rationale")
    return candidates, masks


def check_revision(root=ROOT):
    protocol, freeze = load(root / PROTOCOL), load(root / FREEZE)
    if digest(canonical(protocol)) != freeze["canonical_sha256"]:
        raise DataError("Guidance revision protocol differs from its freeze")
    parent = load(root / PARENT_PROTOCOL)
    if digest(canonical(parent)) != PARENT_SHA256:
        raise DataError("Guidance revision parent protocol changed")
    verify_revision(protocol, parent)
    legacy_registration = check_registration(root)
    legacy = check_preparation(root)
    if legacy != load(root / PARENT_RESULT) or legacy["decision"] != "STOP_INSUFFICIENT_SOURCE_SUPPORT":
        raise DataError("Guidance revision does not preserve the original source-only stop")
    inherited_paths = {PARENT_PROTOCOL, PARENT_FREEZE, PARENT_WARMUP, PARENT_MASKS,
                       PARENT_PREPARATION, PARENT_RESULT}
    expected_inputs = set(parent["input_canonical_sha256"]) | inherited_paths | {EARLIER, MASKS}
    if set(protocol["input_canonical_sha256"]) != expected_inputs:
        raise DataError("Guidance revision must pin the complete inherited and earlier source chain")
    for path, expected in protocol["input_canonical_sha256"].items():
        if (path in parent["input_canonical_sha256"] and expected != parent["input_canonical_sha256"][path]
                or digest(canonical(load(root / path))) != expected):
            raise DataError(f"Guidance revision input changed: {path}")
    expected_implementations = {**parent["implementation_sha256_git_lf"],
                                "nre/m6_guidance_readiness.py": load(root / PARENT_PREPARATION)["implementation_sha256_git_lf"]["nre/m6_guidance_readiness.py"]}
    if (set(protocol["implementation_sha256_git_lf"]) != set(expected_implementations) | {"nre/m6_guidance_revision.py"}
            or any(protocol["implementation_sha256_git_lf"][p] != h for p, h in expected_implementations.items())):
        raise DataError("Guidance revision implementation inheritance differs")
    for path, expected in protocol["implementation_sha256_git_lf"].items():
        if digest((root / path).read_bytes().replace(b"\r\n", b"\n")) != expected:
            raise DataError(f"Guidance revision implementation changed: {path}")
    inherited = load(root / PARENT_WARMUP)["candidate_events"]
    held = load(root / protocol["held_evidence"])["guidance_candidates"]
    old_masks = load(root / PARENT_MASKS)
    earlier, masks = verify_earlier(protocol, load(root / EARLIER), load(root / MASKS), inherited, held,
                                    old_masks["taxonomy"], Calendar(load(root / protocol["calendar"])))
    masks.update({r["event_id"]: r for r in old_masks["events"]})
    reports = {}
    for variant, clean in (("clean_window", True), ("all_defined", False)):
        warmup, excluded = partition(earlier + inherited, masks, clean=clean)
        tests, held_excluded = partition(held, masks, clean=clean)
        folds = []
        for fold in protocol["folds"]:
            fit = support(warmup + [r for r in tests if r["held_block"] in fold["fit_blocks"]])
            scored = support([r for r in tests if r["held_block"] == fold["test_block"]])
            folds.append({"test_block": fold["test_block"], "source_eligible_fit": fit,
                          "source_eligible_test": scored,
                          "fit_floor_possible": fit["rows"] >= protocol["warmup"]["minimum_common_fit_rows"]
                          and fit["issuers"] >= protocol["warmup"]["minimum_common_fit_issuers"]})
        counts, gates = support(tests), protocol["gates"]
        possible = (counts["rows"] >= gates["paired_rows"] and counts["issuers"] >= gates["issuers"]
                    and counts["sessions"] >= gates["sessions"]
                    and sum(f["source_eligible_test"]["rows"] >= gates["pairs_per_fold"] for f in folds)
                    >= gates["folds_with_minimum_pairs"] and all(f["fit_floor_possible"] for f in folds))
        reports[variant] = {"warmup": support(warmup), "warmup_exclusions": excluded,
                            "held": counts, "held_exclusions": held_excluded, "folds": folds,
                            "source_support_possible": possible}
    return {"protocol_sha256": freeze["canonical_sha256"], "parent_protocol_sha256": PARENT_SHA256,
            "parent_source_decision": legacy["decision"], "source_support": reports,
            "raw_held_opening_coverage_passed": legacy_registration["raw_opening_coverage_passed"],
            "count_semantics": "Source-eligible upper bounds before raw earlier/warmup openings, price basis, mature labels and training feature-variation checks.",
            "decision": "READY_FOR_RAW_WARMUP_OPENINGS" if reports["clean_window"]["source_support_possible"] else "STOP_INSUFFICIENT_SOURCE_SUPPORT",
            "closing_outcome_requests": 0, "model_runs": 0}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(check_revision(), sort_keys=True))


if __name__ == "__main__":
    main()
