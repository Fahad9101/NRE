"""Verify the published opening/basis receipts against frozen code and membership."""
import json
import re
from collections import Counter

from .core import DataError, canonical, digest
from .m5_phase1b_audit import load
from .m6_guidance_revision import ROOT
from .m6_guidance_warmup_opening import implementation_hashes, locked_cohort as warmup_cohort
from .m6_guidance_price_basis import bridge_status, locked_cohort as basis_cohort

FREEZE = "reports/m6-guidance-data-preparation-freeze-2026-11-21.json"
RESULT = "reports/m6-guidance-data-preparation-result-2026-11-21.json"
EXECUTION_COMMIT = "1808a035522a62c5685efa8cad09cace96b45db1"


def require(condition, reason):
    if not condition:
        raise DataError(reason)


def hex_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def verify_preparation(root=ROOT):
    seal, record = load(root / FREEZE), load(root / RESULT)
    for path, expected in seal["implementation_sha256_git_lf"].items():
        require(digest((root / path).read_bytes().replace(b"\r\n", b"\n")) == expected, "Preparation implementation changed")
    for path, expected in seal["canonical_input_sha256"].items():
        require(digest(canonical(load(root / path))) == expected, "Preparation input changed")
    warmup, basis = warmup_cohort(root), basis_cohort(root)
    require(record["protocol_sha256"] == seal["protocol_sha256"] == warmup["protocol_sha256"], "Preparation protocol differs")
    execution = record["execution"]
    require(execution["head_sha"] == EXECUTION_COMMIT and execution["conclusion"] == "success"
            and execution["run_id"] == 44940040789, "Preparation execution reference differs")
    for name, cohort in (("warmup_openings", warmup), ("price_basis", basis)):
        output = record[name]
        require(output["protocol_sha256"] == cohort["protocol_sha256"]
                and output["cohort_sha256"] == cohort["cohort_sha256"]
                and output["source_canonical_sha256"] == cohort["source_canonical_sha256"], "Preparation output membership binding differs")
        rows, expected = output["events"], {r["event_id"]: r for r in cohort["events"]}
        require(len(rows) == len(expected) and len({r["event_id"] for r in rows}) == len(rows)
                and {r["event_id"] for r in rows} == set(expected), "Preparation event membership differs")
        for row in rows:
            source = expected[row["event_id"]]
            require(all(row[k] == source[k] for k in ("symbol", "cik", "reaction_session", "clean_window")), "Preparation event identity differs")
            if name == "price_basis":
                require(row["anchor_session"] == source["anchor_session"] and row["subset"] == source["subset"], "Preparation anchor differs")
        require(output["screened"] == len(rows)
                and output["dispositions"] == dict(Counter(r["status"] for r in rows)), "Preparation disposition counts differ")
        implementations = implementation_hashes(root)
        if name == "price_basis":
            implementations["nre/m6_guidance_price_basis.py"] = seal["implementation_sha256_git_lf"]["nre/m6_guidance_price_basis.py"]
        require(output["implementation_sha256_git_lf"] == implementations, "Preparation output code pins differ")
        require(output["closing_outcome_requests"] == output["model_runs"] == 0, "Preparation crossed its outcome boundary")
    opening, prices = record["warmup_openings"], record["price_basis"]
    inventory = prices["corporate_action_inventory"]
    require(seal["warmup_cohort_sha256"] == opening["cohort_sha256"]
            and seal["basis_cohort_sha256"] == prices["cohort_sha256"], "Preparation seal cohort differs")
    require(opening["matched"] == sum(r["status"] == "verified_open" for r in opening["events"])
            and opening["clean_matched"] == sum(r["status"] == "verified_open" and r["clean_window"] for r in opening["events"]), "Opening match counts differ")
    for row in opening["events"]:
        require((row["status"] == "verified_open") == hex_digest(row["opening_commitment_sha256"]), "Opening commitment missing or unexpected")
        require(len(row["provider_request_sha256"]) == len(row["provider_response_sha256"])
                and bool(row["provider_request_sha256"])
                and all(hex_digest(h) for h in row["provider_request_sha256"] + row["provider_response_sha256"]), "Opening receipts differ")
    require(opening["requests"] == sum(len(r["provider_request_sha256"]) for r in opening["events"]), "Opening request total differs")
    for row in prices["events"]:
        passed = row["status"] == "provider_basis_checks_passed"
        require(not passed or inventory["status"] == "complete_paginated_inventory"
                and inventory["http_status"] is None, "Basis pass lacks a complete inventory")
        replay_status, replay_hits = bridge_status(row, inventory["actions"], set(inventory["unresolved_symbols"]))
        require((row["corporate_action_status"], row["intersecting_action_sha256"]) == (replay_status, replay_hits), "Corporate-action bridge replay differs")
        require(not passed or row["anchor_status"] == "verified_raw_anchor"
                and row["corporate_action_status"] == "no_observed_action_in_bridge"
                and not row["intersecting_action_sha256"], "Basis pass contradicts its quality states")
        require((row["anchor_status"] == "verified_raw_anchor") == hex_digest(row["anchor_commitment_sha256"]), "Anchor commitment missing or unexpected")
        require(all(hex_digest(r["request_sha256"]) and hex_digest(r["response_sha256"]) for r in row["anchor_receipts"]), "Anchor receipts differ")
    require(all(hex_digest(r["request_sha256"]) and hex_digest(r["response_sha256"]) for r in inventory["receipts"]), "Inventory receipts differ")
    require(prices["requests"] == len(inventory["receipts"]) + sum(len(r["anchor_receipts"]) for r in prices["events"]), "Basis request total differs")
    require(prices["reaction_session_bar_requests"] == record["closing_outcome_requests"] == record["model_runs"] == 0, "Preparation acquired closing outcomes")
    complete = opening["matched"] == len(opening["events"]) and all(r["status"] == "provider_basis_checks_passed" for r in prices["events"])
    return {"protocol_sha256": seal["protocol_sha256"], "execution_commit": EXECUTION_COMMIT,
            "verified_training_openings": opening["matched"], "clean_training_openings": opening["clean_matched"],
            "basis_events_passed": sum(r["status"] == "provider_basis_checks_passed" for r in prices["events"]),
            "decision": "READY_FOR_REMAINING_SOURCE_AND_LABEL_PREPARATION" if complete else "DATA_QUALITY_PENDING",
            "closing_outcome_requests": 0, "model_runs": 0}


if __name__ == "__main__":
    print(json.dumps(verify_preparation(), sort_keys=True))
