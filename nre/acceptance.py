"""Structural pilot acceptance; never certifies truth of source attestations."""
from collections import Counter
from datetime import date
from zoneinfo import ZoneInfo
from .core import DataError, canonical, digest, timestamp, unique
from .dataset import build


def audit_cohort(bundle, protocol, ledger, review):
    """Recompute labels and reconcile all candidates to the frozen cohort.

    Counts are derived from data, never accepted from a submitted report.
    A clean result still requires independent source/timestamp review.
    """
    rows, _ = build(bundle)
    start = date.fromisoformat(protocol["event_window_start"])
    end = date.fromisoformat(protocol["event_window_end"])
    price_end = date.fromisoformat(protocol["price_window_end"])
    if start > end or price_end < end:
        raise DataError("invalid pilot window")
    for key in ("minimum_eligible_events", "minimum_unique_issuers"):
        if type(protocol[key]) is not int or protocol[key] < 1:
            raise DataError("positive integer cohort threshold required")
    events = unique(bundle["events"], "event_id")
    candidates = unique(ledger["candidates"], "candidate_id")
    securities = unique(bundle["securities"], "security_id")
    gates, details = {}, {}
    gates["real_data"] = bundle["synthetic"] is False and bool(events)
    gates["availability_mode"] = bundle["availability_mode"] == protocol["availability_mode"]
    protocol_sha = digest(canonical(protocol))
    gates["protocol_hash"] = ledger.get("protocol_sha256") == protocol_sha
    try:
        gates["selection_frozen_before_prices"] = timestamp(ledger["frozen_at"]) < timestamp(review["prices_first_accessed_at"])
    except (KeyError, DataError):
        gates["selection_frozen_before_prices"] = False
    # The prior freeze must bind candidate membership, not mutable result/disposition fields.
    membership = sorted([{k: c.get(k) for k in ("candidate_id", "source_sha256")}
                         for c in candidates.values()], key=lambda c: c["candidate_id"])
    membership_sha = digest(canonical(membership))
    gates["frozen_membership_hash"] = review.get("frozen_membership_sha256") == membership_sha
    gates["discovery_coverage_review"] = bool(review.get("discovery_coverage_evidence"))
    gates["identity_history_review"] = bool(review.get("identity_history_evidence"))
    gates["provider_rights_review"] = bool(review.get("provider_rights_evidence"))
    available_hashes = {digest(s["text"].encode("utf-8")) for s in bundle["sources"]}
    gates["candidate_source_hashes"] = bool(candidates) and all(c.get("source_sha256") in available_hashes for c in candidates.values())
    represented, bad_dispositions = [], []
    for candidate in candidates.values():
        state, event_id = candidate.get("disposition"), candidate.get("event_id")
        if state == "included" and event_id in events:
            represented.append(event_id)
        elif state == "excluded" and candidate.get("reason") and not event_id:
            continue
        else:
            bad_dispositions.append(candidate["candidate_id"])
    gates["candidate_accounting"] = bool(candidates) and not bad_dispositions and len(represented) == len(set(represented)) and set(represented) == set(events)
    details["invalid_candidate_dispositions"] = bad_dispositions
    outcomes = {r["event_id"]: r for r in rows}
    in_window, earnings, complete, issuer_ids = [], [], [], set()
    unsupported_identities = []
    for event_id, event in events.items():
        row = outcomes[event_id]
        if event["precision"] in {"second", "minute"}:
            day = timestamp(event["published_at"]).astimezone(ZoneInfo("America/New_York")).date()
            if start <= day <= end:
                in_window.append(event_id)
        if event.get("category") == "earnings" and event.get("subtype") == "results":
            earnings.append(event_id)
        security = securities[event["security_id"]]
        cik = str(security.get("cik", ""))
        valid_cik = cik.isdigit() and 0 < int(cik) < 10**10
        if not valid_cik:
            unsupported_identities.append(event_id)
        horizon = row["labels"].get("session_20_close_return", {})
        if (event_id in in_window and event_id in earnings and valid_cik
                and row["state"] == "MAPPED" and horizon.get("value") is not None
                and all(date.fromisoformat(day) <= price_end for day in horizon["window"])):
            complete.append(event_id)
            issuer_ids.add(cik.zfill(10))
    gates["all_events_in_window"] = len(in_window) == len(events) and bool(events)
    gates["earnings_results_only"] = len(earnings) == len(events) and bool(events)
    gates["issuer_identity"] = not unsupported_identities and bool(events)
    gates["minimum_events"] = len(complete) >= protocol["minimum_eligible_events"]
    gates["minimum_issuers"] = len(issuer_ids) >= protocol["minimum_unique_issuers"]
    details["invalid_issuer_events"] = unsupported_identities
    # Two distinct reviewed events per timing class; two distinct reviewers per event.
    timing_classes = {outcomes[e]["release_timing"] for e in complete}
    checks = review.get("spot_checks", [])
    checked = {timing: set() for timing in timing_classes}
    for check in checks:
        event_id = check.get("event_id")
        if event_id not in complete or not check.get("evidence"):
            continue
        reviewers = check.get("reviewers", [])
        if (isinstance(reviewers, list) and all(isinstance(x, str) and x.strip() for x in reviewers)
                and len(set(reviewers)) >= 2):
            checked[outcomes[event_id]["release_timing"]].add(event_id)
    gates["independent_timing_spot_checks"] = bool(timing_classes) and all(len(v) >= 2 for v in checked.values())
    details["spot_checked_events_by_timing"] = {k: sorted(v) for k, v in sorted(checked.items())}
    failures = [name for name, ok in gates.items() if not ok]
    return {
        "status": "BLOCKED" if failures else "STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED",
        "milestone_accepted": False,
        "protocol_sha256": protocol_sha, "membership_sha256": membership_sha,
        "input_sha256": digest(canonical(bundle)), "ledger_sha256": digest(canonical(ledger)),
        "review_sha256": digest(canonical(review)), "gates": gates, "failed_gates": failures,
        "counts": {"candidates": len(candidates), "events": len(events),
                   "eligible_complete_events": len(complete), "unique_issuers": len(issuer_ids),
                   "dispositions": dict(Counter(c.get("disposition", "unknown") for c in candidates.values()))},
        "details": details,
        "review_limit": "Hashes and declarations establish internal consistency, not genuine publication, permission or review. Independent evidence sign-off is still required."
    }
