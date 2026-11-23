"""Acquire and bind guidance labels privately, then execute the single logged comparison."""
import argparse
import copy
import json
import math
import os
import subprocess
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener

from . import event_acquire as ea
from .calendar import Calendar
from .core import DataError, canonical, digest, timestamp
from .m5_phase1b_audit import load
from .m6_guidance_revision import EARLIER, PARENT_WARMUP, PARENT_MASKS, MASKS, PROTOCOL, ROOT
from .m6_guidance_preparation_audit import verify_preparation, RESULT as PREPARATION
from .m6_guidance_warmup_opening import locked_cohort as training_cohort, trade_params, opening_commitment, validate_trade_request
from .m6_guidance_price_basis import locked_cohort as basis_cohort, anchor_params, checked_anchor, inventory, bridge_status
from .m6_historical_opening import first_minute_open, VENUES

CONFIG = "config/m6-guidance-execution-v2.json"
FREEZE = "reports/m6-guidance-execution-freeze-2026-11-23.json"
ACQUISITION = "reports/m6-guidance-acquisition-2026-11-23.json"
ATTEMPT = "reports/m6-guidance-attempt-v2-001.json"
RESULT = "reports/m6-guidance-result-2026-11-23.json"
DOMAIN = "nre-guidance-v2-private-labels-v1"


def require(condition, message):
    if not condition:
        raise DataError(message)


def locked_inputs(root=ROOT):
    config, freeze = load(root / CONFIG), load(root / FREEZE)
    require(digest(canonical(config)) == freeze["canonical_sha256"], "Execution configuration changed")
    verify_preparation(root)
    protocol = load(root / PROTOCOL)
    require(digest(canonical(protocol)) == config["protocol_sha256"], "Execution protocol changed")
    for path, expected in config["input_canonical_sha256"].items():
        require(digest(canonical(load(root / path))) == expected, "Execution input changed")
    for path, expected in config["implementation_sha256_git_lf"].items():
        require(digest((root / path).read_bytes().replace(b"\r\n", b"\n")) == expected, "Execution implementation changed")
    warmup, basis = training_cohort(root), basis_cohort(root)
    warm_ids = {r["event_id"] for r in warmup["events"]}
    candidates = load(root / PARENT_WARMUP)["candidate_events"] + load(root / EARLIER)["candidate_events"]
    events = [r for r in candidates if r["event_id"] in warm_ids]
    events += load(root / protocol["held_evidence"])["guidance_candidates"]
    masks = {r["event_id"]: r for path in (PARENT_MASKS, MASKS) for r in load(root / path)["events"]}
    review = load(root / config["final_source_review"])
    additional = {r["event_id"]: r for r in review["events"]}
    require(len(additional) == len(review["events"])
            and set(additional) == {r["event_id"] for r in basis["events"]}, "Final review membership differs")
    require(review["closing_outcome_requests"] == review["model_runs"] == 0, "Final source review crossed the outcome boundary")
    for descriptor in basis["events"]:
        row = additional[descriptor["event_id"]]
        require(all(row[k] == descriptor[k] for k in ("symbol", "cik", "anchor_session", "reaction_session",
                "source_event_sha256", "source_mask_sha256")), "Final review source identity differs")
    taxonomy = load(root / PARENT_MASKS)["taxonomy"]
    quality = {}
    for event in events:
        mask = masks[event["event_id"]]
        q = {k: list(mask[k]) for k in ("hard_exclusions", "soft_caveats")}
        extra = additional.get(event["event_id"])
        if extra:
            require(extra["review_complete"] is True, "Final source review incomplete")
            for field in ("hard_exclusions", "soft_caveats"):
                values = extra["additional_" + field]
                require(set(values) <= set(taxonomy[field]), "Unregistered final source category")
                q[field] = sorted(set(q[field]) | set(values))
        quality[event["event_id"]] = q
    require(len(events) == 110 and len(quality) == 110, "Unexpected comparison membership")
    return config, protocol, events, quality, warmup, basis


def selected_opening(event, fetch):
    pages = []

    def capture(endpoint, params):
        validate_trade_request(event, endpoint, params)
        raw = fetch(endpoint, params)
        pages.append(json.loads(raw))
        return raw

    start = timestamp(event["scheduled_open_at"])
    price, reason = first_minute_open(event["symbol"], VENUES["NASDAQ"], start, capture,
                                      asof=event["reaction_session"], page_limit=5000)
    if reason:
        return None, None, reason
    selected = {}
    for page in pages:
        for row in page.get("trades") or ():
            if ((row.get("x"), row.get("z")) == VENUES["NASDAQ"] and "Q" in (row.get("c") or ())
                    and row.get("u") is None and row.get("p") == price and type(row.get("i")) is int
                    and start <= timestamp(row["t"]) < start + timedelta(minutes=1)):
                selected[(row["i"], row["t"], row["p"])] = row
    require(len(selected) == 1, "Opening selection differs")
    return price, next(iter(selected.values())), None


def acquire(root, fetch):
    config, protocol, events, quality, warmup, basis = locked_inputs(root)
    calendar = Calendar(load(root / protocol["calendar"]))
    by_id = {e["event_id"]: e for e in events}
    warm = {e["event_id"]: e for e in warmup["events"]}
    preparation = load(root / PREPARATION)
    old_openings = {e["event_id"]: e for e in preparation["warmup_openings"]["events"]}
    old_anchors = {e["event_id"]: e for e in preparation["price_basis"]["events"]}
    requests, receipts, closes = 0, [], 0
    ca_params = dict(preparation["price_basis"]["corporate_action_inventory"]["query"])
    ca_params["end"] = config["corporate_action_inventory_end"]
    recipes = [(ea.ACTIONS_ENDPOINT, ca_params)]
    for descriptor in basis["events"]:
        if quality[descriptor["event_id"]]["hard_exclusions"]:
            continue
        event = by_id[descriptor["event_id"]]
        recipes.extend([(f"https://data.alpaca.markets/v2/stocks/{event['symbol']}/trades", trade_params(event)),
                        (ea.BARS_ENDPOINT, anchor_params(descriptor, calendar)),
                        (ea.BARS_ENDPOINT, anchor_params(dict(descriptor, anchor_session=event["reaction_session"]), calendar))])
    allowed = {digest(canonical({"endpoint": endpoint, "params": params})) for endpoint, params in recipes}

    def checked(endpoint, params):
        nonlocal requests
        require(requests < config["request_budget"], "Acquisition request budget exhausted")
        recipe = {k: v for k, v in params.items() if k != "page_token"}
        require(digest(canonical({"endpoint": endpoint, "params": recipe})) in allowed, "Unregistered acquisition request")
        require("page_token" not in params or isinstance(params["page_token"], str)
                and 0 < len(params["page_token"]) <= 4096, "Invalid acquisition pagination")
        requests += 1
        raw = fetch(endpoint, params)
        require(isinstance(raw, bytes) and len(raw) <= 4_000_000, "Acquisition response representation differs")
        receipts.append({"request_sha256": digest(canonical({"endpoint": endpoint, "params": params})), "response_sha256": digest(raw)})
        return raw

    pages, _ = ea._paginate(lambda p: checked(ea.ACTIONS_ENDPOINT, p), ca_params, "corporate_actions")
    actions, unresolved = inventory(pages, {e["symbol"] for e in basis["events"]})
    ca_receipts = list(receipts)
    public, private, reasons = [], {}, Counter()
    for descriptor in basis["events"]:
        event = by_id[descriptor["event_id"]]
        q = quality[event["event_id"]]
        base = {k: descriptor[k] for k in ("event_id", "symbol", "cik", "subset", "anchor_session", "reaction_session")}
        receipt_start = len(receipts)
        row_public = {**base, "status": "withheld", "label_commitment_sha256": None,
                      "close_mature_at": (calendar.bounds(event["reaction_session"])[1] + timedelta(minutes=5)).isoformat()}
        reason = None
        if q["hard_exclusions"]:
            reason = "hard_source_exclusion"
        elif bridge_status(descriptor, actions, unresolved)[0] != "no_observed_action_in_bridge":
            reason = "unresolved_price_basis"
        else:
            opening_event = dict(event, venue="NASDAQ")
            price, selected, reason = selected_opening(opening_event, checked)
            if reason is None and event["event_id"] in warm:
                original = opening_commitment(warm[event["event_id"]], selected, warmup["protocol_sha256"], warmup["cohort_sha256"])
                if original != old_openings[event["event_id"]]["opening_commitment_sha256"]:
                    reason = "opening_commitment_mismatch"
            if reason is None:
                params = anchor_params(descriptor, calendar)
                pages, _ = ea._paginate(lambda p: checked(ea.BARS_ENDPOINT, p), params, "bars")
                anchor, reason = checked_anchor(pages, descriptor, calendar)
                reason = None if reason == "verified_raw_anchor" else reason
                if reason is None:
                    anchor_commitment = digest(canonical({"domain": preparation["price_basis"]["anchor_commitment_scheme"],
                        "protocol_sha256": basis["protocol_sha256"], "cohort_sha256": basis["cohort_sha256"],
                        "event_id": event["event_id"], "symbol": event["symbol"], "anchor_session": descriptor["anchor_session"],
                        "query": params, "raw_anchor_bar": anchor}))
                    if anchor_commitment != old_anchors[event["event_id"]]["anchor_commitment_sha256"]:
                        reason = "anchor_commitment_mismatch"
            if reason is None:
                close_descriptor = dict(descriptor, anchor_session=event["reaction_session"])
                params = anchor_params(close_descriptor, calendar)
                closes += 1
                pages, _ = ea._paginate(lambda p: checked(ea.BARS_ENDPOINT, p), params, "bars")
                close, close_status = checked_anchor(pages, close_descriptor, calendar)
                if close_status != "verified_raw_anchor":
                    reason = "reaction_close_unavailable"
                else:
                    gap, target_close = price / anchor["c"] - 1, close["c"] / anchor["c"] - 1
                    if not all(math.isfinite(v) and v > -1 for v in (gap, target_close)) or gap == 0:
                        reason = "unusable_price_labels"
                    else:
                        label = {"gap": gap, "close_return": target_close, "mature_at": row_public["close_mature_at"]}
                        commitment = digest(canonical({"domain": DOMAIN, "protocol_sha256": config["protocol_sha256"],
                            "execution_configuration_sha256": digest(canonical(config)),
                            "event_sha256": digest(canonical(event)), "quality_sha256": digest(canonical(q)), "labels": label}))
                        row_public.update(status="labels_committed", label_commitment_sha256=commitment)
                        private[event["event_id"]] = label
        if reason:
            reasons[reason] += 1
            # Price-derived missingness never identifies an event's numerical return.
            row_public["quality_state"] = "source_withheld" if reason == "hard_source_exclusion" else "price_quality_withheld"
        row_public["receipts"] = receipts[receipt_start:]
        public.append(row_public)
    manifest = {"schema_version": 1, "scope": "guidance_v2_hash_only_label_acquisition",
        "protocol_sha256": config["protocol_sha256"], "execution_configuration_sha256": digest(canonical(config)),
        "source_review_sha256": config["input_canonical_sha256"][config["final_source_review"]],
        "basis_cohort_sha256": basis["cohort_sha256"], "label_commitment_scheme": DOMAIN,
        "events": public, "screened": len(public), "labels_committed": len(private),
        "dispositions": dict(Counter(r["status"] for r in public)), "aggregate_attrition": dict(reasons),
        "corporate_action_receipts": ca_receipts, "corporate_actions_sha256": digest(canonical(actions)),
        "requests": requests, "closing_outcome_requests": closes, "model_runs": 0}
    return manifest, private, (protocol, events, quality)


def compare_acquisitions(expected, reproduced):
    """Require identical labels, quality and requests; retain wire-only changes as hashes."""
    old, new = copy.deepcopy(expected), copy.deepcopy(reproduced)
    changes = []
    receipt_lists = [(old["corporate_action_receipts"], new["corporate_action_receipts"])]
    require(len(old["events"]) == len(new["events"]), "Acquisition membership changed before scoring")
    for before, after in zip(old["events"], new["events"]):
        receipt_lists.append((before["receipts"], after["receipts"]))
    for before, after in receipt_lists:
        require(len(before) == len(after), "Acquisition requests changed before scoring")
        for left, right in zip(before, after):
            prior, current = left.pop("response_sha256"), right.pop("response_sha256")
            if prior != current:
                changes.append({"request_sha256": right["request_sha256"],
                                "prior_response_sha256": prior, "reproduced_response_sha256": current})
    require(old == new, "Acquisition commitments, quality or requests changed before scoring")
    return changes


def score_once(root, fetch, claim):
    config, _, _, _, _, _ = locked_inputs(root)
    expected = load(root / ACQUISITION)
    require(claim["attempt_id"] == "guidance-v2-001" and claim["protocol_sha256"] == config["protocol_sha256"], "Attempt identity differs")
    require(claim["acquisition_sha256"] == digest(canonical(expected))
            and claim["execution_configuration_sha256"] == digest(canonical(config)), "Attempt inputs differ")
    require(str(claim["workflow_run_id"]) == os.environ.get("GITHUB_RUN_ID")
            and claim["execution_commit"] == os.environ.get("GITHUB_SHA"), "Attempt execution differs")
    manifest, labels, (protocol, events, quality) = acquire(root, fetch)
    wire_changes = compare_acquisitions(expected, manifest)
    from .m6_guidance_compare import compare
    result = compare(protocol, events, labels, quality)
    return {"schema_version": 1, "scope": "guidance_v2_single_registered_comparison",
            "protocol_sha256": config["protocol_sha256"], "acquisition_sha256": digest(canonical(expected)),
            "attempt_sha256": digest(canonical(claim)), "execution_commit": claim["execution_commit"],
            "workflow_run_id": claim["workflow_run_id"], "comparison": result, "scoring_attempts": 1,
            "reproduction_manifest_sha256": digest(canonical(manifest)), "provider_wire_changes": wire_changes,
            "closing_outcome_requests": manifest["closing_outcome_requests"], "raw_prices_or_event_returns_published": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("acquire", "score"))
    args = parser.parse_args()
    try:
        require(not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip(), "Execution checkout is not clean")
        require(not (ROOT / RESULT).exists(), "Comparison already completed")
        if args.stage == "acquire":
            require(not (ROOT / ATTEMPT).exists(), "Scoring attempt already claimed")
        provider = ea.make_fetch(build_opener(ea.NoRedirect()), os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"])
        next_request = time.monotonic()

        def fetch(endpoint, params):
            nonlocal next_request
            time.sleep(max(0, next_request - time.monotonic()))
            next_request = time.monotonic() + 0.45
            return provider(endpoint, params)

        if args.stage == "acquire":
            report, _, _ = acquire(ROOT, fetch)
        else:
            require(os.environ.get("GITHUB_ACTIONS") == "true", "Scoring requires the claimed workflow")
            report = score_once(ROOT, fetch, load(Path(os.environ["GUIDANCE_ATTEMPT_FILE"])))
        print(json.dumps(report, sort_keys=True))
    except HTTPError as error:
        print(json.dumps({"status": "provider_error", "http_status": error.code}))
        return 2
    except Exception as error:
        print(json.dumps({"status": "guidance_execution_failed", "reason": type(error).__name__}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
