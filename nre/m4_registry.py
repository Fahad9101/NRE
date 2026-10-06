"""The Milestone 4 experiment log and holdout access log: append-only JSON lines, each carrying the sha256 of the line before it.

A log's first line is a genesis record, written before anything is evaluated, so every later record is part of one chain that starts at a commit anyone can
read. The chain makes edits and deletions in the middle of a log visible; that nothing was cut off the end is what the repository's history is for.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import m4_protocol as pr
from .core import DataError, canonical, digest

EXPERIMENT_LOG = pr.ROOT / "reports" / "m4-experiment-log.jsonl"
HOLDOUT_LOG = pr.ROOT / "reports" / "m4-holdout-access-log.jsonl"
STATES = ("EVALUATED", "INSUFFICIENT_DATA", "MODEL_FIT_FAILED", "COUNTS_ONLY")
GENESIS_NOTES = {"experiments": "Start of the Milestone 4 experiment log. No predictor has been fitted, scored or evaluated; every experiment is recorded after this line.",
                 "holdout_access": "Start of the Milestone 4 holdout access log. No holdout outcome has been read; every read is recorded after this line."}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def harness_commit(root=pr.ROOT):
    """HEAD's commit hash and whether the working tree is otherwise clean (the two logs themselves are ignored)."""
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout
    names = (EXPERIMENT_LOG.name, HOLDOUT_LOG.name)
    changed = [line for line in git("status", "--porcelain", "--untracked-files=all").splitlines() if not any(name in line for name in names)]
    return git("rev-parse", "HEAD").strip(), not changed


def line_of(record):
    return canonical(record).decode("utf-8")


def read(path):
    """[(record, sha256 of its line)] for a log, in order. The line's own terminator (LF or CRLF) is not part of the line."""
    path = Path(path)
    if not path.is_file():
        return []
    rows = []
    for raw in path.read_bytes().split(b"\n"):
        raw = raw.rstrip(b"\r")
        if not raw:
            continue
        rows.append((json.loads(raw.decode("utf-8")), digest(raw)))
    return rows


def expected_fields(protocol, kind):
    key = {"experiments": "experiment_record_fields", "holdout_access": "holdout_access_record_fields"}[kind]
    return list(protocol["experiment_log"][key])


def verify_chain(path, kind, protocol):
    """Checks every record of a log: the genesis first, only fields the protocol lists, and each link equal to the hash of the line before it."""
    rows = read(path)
    if not rows:
        raise DataError("%s has no genesis record" % path)
    fields = set(expected_fields(protocol, kind))
    previous = None
    for number, (record, line_sha) in enumerate(rows):
        if record.get("previous_record_sha256") != previous:
            raise DataError("%s: record %d does not carry the hash of the line before it" % (path, number))
        if number == 0:
            if record.get("kind") != "genesis" or record.get("log") != kind:
                raise DataError("%s: the first record must be the %s log's genesis" % (path, kind))
        elif record.get("kind") == "genesis" or set(record) != fields:
            raise DataError("%s: record %d does not have exactly the protocol's fields" % (path, number))
        previous = line_sha
    return {"records": len(rows), "last_record_sha256": previous, "genesis_created_at": rows[0][0]["created_at"]}


def append(path, kind, record, protocol):
    """Adds `record` (without previous_record_sha256) to the log after verifying its chain; returns the record as written."""
    path = Path(path)
    rows = read(path)
    if rows:
        verify_chain(path, kind, protocol)
    if kind not in ("experiments", "holdout_access"):
        raise DataError("unknown log kind " + str(kind))
    if "previous_record_sha256" in record:
        raise DataError("previous_record_sha256 is set by the log, not the caller")
    is_genesis = record.get("kind") == "genesis"
    if is_genesis != (not rows):
        raise DataError("a genesis record is written once, first, and only first")
    if not is_genesis and set(record) | {"previous_record_sha256"} != set(expected_fields(protocol, kind)):
        raise DataError("a record must have exactly the protocol's fields: " + ", ".join(expected_fields(protocol, kind)))
    written = {**record, "previous_record_sha256": rows[-1][1] if rows else None}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as handle:
        handle.write(line_of(written).encode("utf-8") + b"\n")
    return written


def genesis_record(kind, protocol, commit, created_at):
    base = {"kind": "genesis", "log": kind, "protocol_id": protocol["protocol_id"], "protocol_version": protocol["protocol_version"],
            "protocol_sha256": pr.protocol_sha256(protocol), "harness_commit": commit, "created_at": created_at, "note": GENESIS_NOTES[kind]}
    return {**base, "access_number": 0, "events_read": []} if kind == "holdout_access" else base


def init_logs(protocol, commit, created_at, experiment_path=EXPERIMENT_LOG, holdout_path=HOLDOUT_LOG):
    """Writes both genesis records, once; refuses if either log already exists."""
    for path in (experiment_path, holdout_path):
        if Path(path).exists():
            raise DataError("%s already exists; a log is started once" % path)
    return (append(experiment_path, "experiments", genesis_record("experiments", protocol, commit, created_at), protocol),
            append(holdout_path, "holdout_access", genesis_record("holdout_access", protocol, commit, created_at), protocol))


def hash_list(items):
    return digest(canonical(list(items)))


def experiment_record(protocol, commit, created_at, sequence, target_id, clock, predictor_id, version, fold, train_ids, test_ids, features_version,
                      parameters, predictions, metrics_with_counts, interval_method, seed, state):
    """One experiment's record in the protocol's fields (previous_record_sha256 is added by append)."""
    if state not in STATES:
        raise DataError("unknown experiment state " + str(state))
    return {"experiment_id": "m4-experiment-%05d" % sequence, "protocol_sha256": pr.protocol_sha256(protocol), "harness_commit": commit, "target_id": target_id,
            "clock": clock, "predictor_id": predictor_id, "version": version, "fold": fold, "train_event_ids_sha256": hash_list(sorted(train_ids)),
            "test_event_ids_sha256": hash_list(sorted(test_ids)), "features_version": features_version, "parameters_sha256": digest(canonical(parameters)),
            "predictions_sha256": digest(canonical(predictions)), "metrics_with_counts": metrics_with_counts, "interval_method": interval_method,
            "seed": seed, "state": state, "created_at": created_at}


def holdout_access_record(protocol, commit, created_at, access_number, reason, events_read):
    return {"access_number": access_number, "protocol_sha256": pr.protocol_sha256(protocol), "harness_commit": commit, "reason": reason,
            "events_read": sorted(events_read), "created_at": created_at}
