"""Run the formal cohort audit where raw prices are reachable (GitHub Actions) and print only its result.

Assembles one bundle from every accepted event in config/m1-events.json (those with a recorded_result), refetches their
prices, and applies nre.acceptance.audit_cohort to it with the repository's protocol, ledger and review files. Raw prices
stay in this process's memory; the audit result holds only gates, counts and hashes.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import build_opener

from . import event_acquire as ea
from .acceptance import audit_cohort
from .calendar import Calendar
from .core import DataError, digest

ROOT = ea.ROOT


def accepted_events(spec):
    return [e for e in spec["events"] if "recorded_result" in e]


def merge_bundles(bundles):
    if not bundles:
        raise DataError("no accepted events to audit")
    merged = {"schema_version": 1, "synthetic": False, "as_of": bundles[0]["as_of"],
              "availability_mode": bundles[0]["availability_mode"], "providers": [], "sources": [], "securities": [],
              "events": [], "prices": [], "corporate_actions": [], "features": []}
    providers = {}
    for bundle in bundles:
        if (bundle["as_of"], bundle["availability_mode"]) != (merged["as_of"], merged["availability_mode"]):
            raise DataError("bundles disagree on as_of or availability mode")
        for key in ("sources", "securities", "events", "prices", "corporate_actions", "features"):
            merged[key].extend(bundle[key])
        for provider in bundle["providers"]:
            if providers.setdefault(provider["provider_id"], provider) != provider:
                raise DataError("bundles disagree on provider terms")
    merged["providers"] = list(providers.values())
    return merged


def archive_sources(directory):
    """Sources from the original SEC freeze artifact: each observation's payload, verified against its recorded hash.

    A missing directory means the archive is unavailable; the candidate_source_hashes gate then fails rather than the run.
    """
    raw = Path(directory) / "nre-sec-freeze" / "raw"
    if not raw.is_dir():
        return []
    sources, seen = [], set()
    for path in sorted(raw.glob("*.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(meta, dict) or not {"payload_file", "sha256", "url", "retrieved_at"} <= set(meta):
            continue
        payload = (raw / Path(meta["payload_file"]).name).read_bytes()
        if digest(payload) != meta["sha256"]:
            raise DataError("archived payload does not match its recorded hash")
        if meta["sha256"] in seen:
            continue
        seen.add(meta["sha256"])
        sources.append({"source_id": "sec-freeze-" + meta["sha256"][:16], "url": meta["url"], "text": payload.decode("utf-8"),
                        "sha256": meta["sha256"], "first_seen_at": meta["retrieved_at"], "retrieved_at": meta["retrieved_at"]})
    return sources


def assemble(spec, events, fetch, calendar, retrieved_at, extra_sources=()):
    bundles = []
    for event in events:
        window = ea.event_window(event, calendar)
        bars, _, actions, _ = ea.fetch_event_data(event, window, fetch)
        bundles.append(ea.build_bundle(event, spec["provider"], window, bars, actions, retrieved_at, calendar))
    merged = merge_bundles(bundles)
    merged["sources"].extend(extra_sources)
    return merged


def summarize(result, archive_observations=0):
    return {"archive_observations": archive_observations, "status": result["status"], "milestone_accepted": result["milestone_accepted"],
            "failed_gates": result["failed_gates"], "passed_gates": sorted(k for k, v in result["gates"].items() if v),
            "counts": result["counts"],
            "invalid_candidate_dispositions": len(result["details"]["invalid_candidate_dispositions"]),
            "spot_checked_events_by_timing": result["details"]["spot_checked_events_by_timing"],
            "hashes": {k: result[k] for k in ("protocol_sha256", "membership_sha256", "input_sha256",
                                              "ledger_sha256", "review_sha256")}}


def _annotation(level, payload):
    message = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return "::" + level + " title=NRE cohort audit::" + message


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the formal cohort audit over every accepted M1 event.")
    parser.add_argument("--spec", default=str(ea.DEFAULT_SPEC))
    parser.add_argument("--protocol", default=str(ROOT / "config" / "pilot.json"))
    parser.add_argument("--ledger", default=str(ROOT / "reports" / "m1-reviewed-candidate-ledger.json"))
    parser.add_argument("--review", default=str(ROOT / "reports" / "m1-acceptance-review.json"))
    parser.add_argument("--archive-dir", help="directory holding the extracted SEC freeze artifact")
    parser.add_argument("--strict", action="store_true", help="exit 2 when any gate fails")
    args = parser.parse_args(argv)
    out = {"audit_ran": False}

    def finish(code):
        print(json.dumps(out, sort_keys=True, indent=2))
        return code

    try:
        calendar = Calendar()
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        ea.validate_spec(spec, calendar)
        protocol, ledger, review = [json.loads(Path(p).read_text(encoding="utf-8"))
                                    for p in (args.protocol, args.ledger, args.review)]
        events = accepted_events(spec)
        if not events:
            raise DataError("no accepted events in the spec")
    except Exception as exc:
        out["error"] = "INPUT_INVALID: " + ("not valid JSON" if isinstance(exc, json.JSONDecodeError) else ea._error_category(exc))
        return finish(2)

    key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        out["error"] = "MISSING_GITHUB_ACTIONS_SECRETS"
        return finish(2)

    fetch = ea.make_fetch(build_opener(ea.NoRedirect()), key, secret)
    try:
        archived = archive_sources(args.archive_dir) if args.archive_dir else []
        bundle = assemble(spec, events, fetch, calendar, datetime.now(timezone.utc), archived)
        result = audit_cohort(bundle, protocol, ledger, review)
    except Exception as exc:
        out["error"] = ea._error_category(exc)
        return finish(2)
    out.update(audit_ran=True, accepted_events=len(events), archive_observations=len(archived), result=result)
    code = finish(2 if args.strict and result["failed_gates"] else 0)
    if os.getenv("GITHUB_ACTIONS") == "true":
        print(_annotation("notice", summarize(result, len(archived))))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
