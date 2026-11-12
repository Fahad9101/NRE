"""Verify the S7 GitHub Actions annotations and emit a hash-only registry."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from nre import event_acquire as ea
from nre.calendar import Calendar

SPEC = "config/m5-phase1b-events.json"
LEDGER = "config/m5-phase1b-frozen-candidate-ledger.json"
PRIOR = "reports/m5-phase1b-batch5-sealed-run-2026-10-15.json"
REGISTRY = "reports/m5-phase1b-s7-registry.json"
WORKFLOW = "M5 Phase 1b sealed event acquisition"
WORKFLOW_PATH = ".github/workflows/m5-phase1b-event-acquire.yml"
ANNOTATION_TITLE = "NRE sealed event acquisition"
ACQUISITION_STEP = "Fetch real bars and corporate actions and print only the sealed view"
EXCLUSIONS = {
    "0001104659-26-091646": ("pending_cash_take_private", "reports/m5-phase1b-s2-decisions-2026-10-09.json"),
    "0001193125-26-211922": ("bell_ambiguous", "reports/m5-phase1b-batch1-signoff-2026-10-09.json"),
    "0001193125-26-352193": ("bell_ambiguous", "reports/m5-phase1b-batch4-signoff-2026-10-14.json"),
    "0001437749-26-023616": ("preliminary_preannouncement", "reports/m5-phase1b-s2-decisions-2026-10-09.json"),
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys)


def unique_keys(pairs):
    values = {}
    for key, value in pairs:
        require(key not in values, "Duplicate JSON key")
        values[key] = value
    return values


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def input_hashes(root):
    # Hash Git's LF form so checkout line-ending settings do not affect replay.
    return {path: sha256((root / path).read_bytes().replace(b"\r\n", b"\n"))
            for path in (SPEC, LEDGER, PRIOR)}


def run_provenance(evidence, expected_sha):
    run, job, check = (evidence[name] for name in ("run", "job", "check"))
    require(re.fullmatch(r"[0-9a-f]{40}", expected_sha)
            and all(item["head_sha"] == expected_sha and item["status"] == "completed"
                    and item["conclusion"] == "success" for item in (run, job, check)),
            "Run, job and check must succeed on the expected commit")
    require(run["name"] == WORKFLOW and run["path"] == WORKFLOW_PATH
            and run["event"] == "workflow_dispatch" and run["head_branch"] == "main"
            and job["run_id"] == run["id"] and job["run_attempt"] == run["run_attempt"]
            and job["name"] == check["name"] == "acquire"
            and job["check_run_url"].rsplit("/", 1)[-1] == str(check["id"]),
            "Unexpected sealed workflow provenance")
    require(any(step["name"] == ACQUISITION_STEP and step["conclusion"] == "success"
                for step in job["steps"]), "Sealed acquisition step did not succeed")
    require(all(type(value) is int and value > 0 for value in
                (run["id"], run["run_number"], run["run_attempt"], job["id"], check["id"])),
            "Invalid GitHub identifiers")
    return {"workflow": WORKFLOW, "run_id": run["id"], "run_number": run["run_number"],
            "run_attempt": run["run_attempt"], "job_id": job["id"], "check_run_id": check["id"],
            "head_sha": expected_sha, "conclusion": "success"}


def read_parts(annotations):
    """Refuse incomplete, duplicated or unsafe evidence before building the registry."""
    total = len(annotations)
    require(1 <= total <= 10, "Invalid sealed annotation count")
    events, parts = {}, {}
    for annotation in annotations:
        message = annotation["message"]
        require(annotation["title"] == ANNOTATION_TITLE and annotation["annotation_level"] == "notice"
                and len(message) < 4096 and not ea.SEALED_TRIPWIRE.search(message),
                "Unexpected or unsafe sealed annotation")
        part = json.loads(message, object_pairs_hook=unique_keys)
        require(set(part) == {"all_ok", "part", "events"} and part["all_ok"] is True
                and isinstance(part["events"], dict) and part["events"],
                "Invalid sealed annotation payload")
        part_id = part["part"]
        require(part_id in {f"{i}/{total}" for i in range(1, total + 1)} and part_id not in parts
                and not events.keys() & part["events"].keys(), "Invalid part number or repeated event")
        parts[part_id] = {"part": part_id, "events": sorted(part["events"]),
                          "message_sha256": sha256(message.encode("utf-8"))}
        events.update(part["events"])
    return events, [parts[f"{i}/{total}"] for i in range(1, total + 1)]


def audit_events(observed, root):
    spec = load(root / SPEC)
    ea.validate_spec(spec, Calendar())
    events = spec["events"]
    prior = load(root / PRIOR)["sealed_view"]["events"]
    require(len(events) == len(observed) == 43
            and observed.keys() == prior.keys() == {event["event_id"] for event in events},
            "Audit requires exactly the 43 events in the extension")
    ledger = load(root / LEDGER)["candidates"]
    candidate_ids = {event["candidate_id"] for event in events}
    require(len(ledger) == 47 and len(candidate_ids) == 43
            and {candidate["candidate_id"] for candidate in ledger} == candidate_ids | EXCLUSIONS.keys()
            and not candidate_ids & EXCLUSIONS.keys(), "Frozen candidate reconciliation failed")
    registry, pin_records = [], {}
    for event in events:
        event_id = event["event_id"]
        view = observed[event_id]
        pin = event["recorded_result"]
        require(event["seal"] == ea.SEAL and all(a["reviewer"] == "Fahad9101"
                                               for a in event["attestations"].values()),
                f"Missing seal or owner attestation for {event_id}")
        if pin["recorded_in"] not in pin_records:
            pin_records[pin["recorded_in"]] = load(root / pin["recorded_in"])["sealed_view"]["events"]
        commitment = pin["labels_sha256"]
        require(re.fullmatch(r"[0-9a-f]{64}", commitment)
                and commitment == pin_records[pin["recorded_in"]][event_id]["labels_sha256"]
                == view.get("labels_sha256") and view.get("labels_match_recorded") is True,
                f"Commitment verification failed for {event_id}")
        # The preceding attested run is already tested against the calendar and seal.
        # Require every sealed fact to agree, with only the five new pins now marked matched.
        require(json.dumps(view, sort_keys=True)
                == json.dumps(dict(prior[event_id], labels_match_recorded=True), sort_keys=True)
                and set(view) <= ea.SEALED_REPORT_KEYS and view["state"] == "MAPPED"
                and view["access_check_passed"] is True and "error" not in view
                and not view["missing_sessions"] and not view["zero_volume_sessions"],
                f"Sealed evidence differs for {event_id}")
        registry.append({"event_id": event_id, "candidate_id": event["candidate_id"],
                         "ticker": view["ticker"], "state": "MAPPED", "labels_sha256": commitment,
                         "recorded_in": pin["recorded_in"], "labels_match_recorded": True,
                         "session_labels_unavailable": sorted(
                             name for name, label in view["session_labels"].items() if not label["exists"])})
    return registry


def build_registry(evidence, expected_sha, root=Path(".")):
    provenance = run_provenance(evidence, expected_sha)
    observed, parts = read_parts(evidence["annotations"])
    registry = audit_events(observed, root)
    return {"schema_version": 1, "kind": "m5_phase1b_s7_registry", "seal": ea.SEAL,
            "status": "awaiting_owner_declaration", "run": provenance,
            "input_sha256": input_hashes(root),
            "annotation_parts": parts,
            "summary": {"frozen_candidates": 47, "mapped_events": len(registry),
                        "commitments_verified": len(registry), "mismatches": 0,
                        "events_with_missing_or_zero_volume_sessions": 0,
                        "unavailable_session_labels": sum(len(e["session_labels_unavailable"]) for e in registry)},
            "excluded_candidates": [{"candidate_id": cid, "reason": reason, "decision_record": record}
                                    for cid, (reason, record) in sorted(EXCLUSIONS.items())],
            "events": registry}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="JSON with run, job, check and sealed annotations from GitHub")
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, default=Path(REGISTRY))
    args = parser.parse_args()
    try:
        registry = build_registry(load(args.evidence), args.expected_sha)
        output = json.dumps(registry, indent=2, sort_keys=True) + "\n"
        require(not ea.SEALED_TRIPWIRE.search(output), "Registry failed the seal tripwire")
    except (ValueError, TypeError, KeyError, OSError):
        # Do not echo any unvalidated evidence or exception payload.
        parser.exit(2, "S7 audit refused the evidence. No registry was written.\n")
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(output)


if __name__ == "__main__":
    main()
