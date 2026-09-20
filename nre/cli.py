import argparse
import json
import os
import sys
from pathlib import Path
from .core import DataError, canonical, digest
from .dataset import build, verify_snapshot, write_snapshot
from .ingestion import PublicClient, SourceUnavailable, nasdaq_directory, sec_candidates


def parser():
    p = argparse.ArgumentParser(description="NRE M1: research datasets, no forecasts or trading")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("input")
    b.add_argument("--output", required=True)
    for name in ("verify", "replay"):
        sub.add_parser(name).add_argument("snapshot")
    d = sub.add_parser("discover-sec")
    d.add_argument("input")
    d.add_argument("--cik", required=True)
    d.add_argument("--output", required=True)
    s = sub.add_parser("fetch-sec")
    s.add_argument("--cik", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--include-history", action="store_true")
    u = sub.add_parser("fetch-universe")
    u.add_argument("--output", required=True)
    a = sub.add_parser("audit-cohort")
    a.add_argument("input")
    a.add_argument("--protocol", required=True)
    a.add_argument("--ledger", required=True)
    a.add_argument("--review", required=True)
    a.add_argument("--output", required=True)
    p_alpaca = sub.add_parser("audit-alpaca")
    p_alpaca.add_argument("input")
    p_alpaca.add_argument("--retrieved-at", required=True)
    p_alpaca.add_argument("--output", required=True)
    return p


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "audit-alpaca":
            from .alpaca import audit_daily
            result = audit_daily(json.loads(Path(args.input).read_text()), args.retrieved_at)
            save_json(args.output, result)
            print(canonical(result).decode())
            return 2  # Staged inputs never constitute accepted label data.
        elif args.command == "audit-cohort":
            from .acceptance import audit_cohort
            inputs = [json.loads(Path(p).read_text()) for p in
                      (args.input, args.protocol, args.ledger, args.review)]
            result = audit_cohort(*inputs)
            save_json(args.output, result)
            print(canonical(result).decode())
            return 2 if result["failed_gates"] else 0
        elif args.command == "build":
            path, report = write_snapshot(json.loads(Path(args.input).read_text()), args.output)
            print(canonical({"snapshot": str(path), "report": report}).decode())
        elif args.command in {"verify", "replay"}:
            manifest = verify_snapshot(args.snapshot)
            if args.command == "replay":
                rows, report = build(json.loads((Path(args.snapshot) / "input.json").read_text()))
                if digest(canonical(rows)) != manifest["output_sha256"] or digest(canonical(report)) != manifest["report_sha256"]:
                    raise DataError("replay differs from sealed snapshot")
            print(canonical({"state": "VERIFIED", "snapshot_id": manifest["snapshot_id"],
                             "replayed": args.command == "replay"}).decode())
        elif args.command == "discover-sec":
            result = sec_candidates(json.loads(Path(args.input).read_text()), args.cik)
            save_json(args.output, result)
            print(canonical({"state": "DISCOVERED", "candidate_count": len(result["candidates"]),
                             "historical_coverage_complete": result["historical_coverage_complete"]}).decode())
        elif args.command == "fetch-sec":
            if not args.cik.isdigit():
                raise DataError("CIK must contain digits only")
            client = PublicClient(os.environ.get("SEC_USER_AGENT", ""))
            raw, meta = client.fetch(f"https://data.sec.gov/submissions/CIK{args.cik.zfill(10)}.json", Path(args.output) / "raw")
            result = sec_candidates(json.loads(raw), args.cik)
            observations = [meta]
            if args.include_history:
                for item in result["continuation_files"]:
                    name = item["name"]
                    if Path(name).name != name or not name.endswith(".json"):
                        raise DataError("unsafe continuation filename")
                    raw, meta = client.fetch("https://data.sec.gov/submissions/" + name, Path(args.output) / "raw")
                    result["candidates"].extend(sec_candidates(json.loads(raw), args.cik)["candidates"])
                    observations.append(meta)
                # SEC can repeat records across files: keep one exact copy, reject conflicts.
                dedup = {}
                for row in result["candidates"]:
                    key = row["candidate_id"]
                    if key in dedup and dedup[key] != row:
                        raise DataError("conflicting accession across continuation files")
                    dedup[key] = row
                result["candidates"] = sorted(dedup.values(), key=lambda r: r["candidate_id"])
                result["historical_coverage_complete"] = True
            result["observations"] = observations
            result["coverage_scope"] = "specified CIK only; not a market-wide event census"
            save_json(Path(args.output) / "sec-ledger.json", result)
            print(canonical({"state": "FETCHED", "count": len(result["candidates"])}).decode())
        elif args.command == "fetch-universe":
            client = PublicClient("NRE research contact https://github.com/Fahad9101/NRE")
            counts, observations = {}, []
            for name in ("nasdaqlisted.txt", "otherlisted.txt"):
                raw, meta = client.fetch("https://www.nasdaqtrader.com/dynamic/SymDir/" + name, Path(args.output) / "raw")
                rows = nasdaq_directory(raw.decode("utf-8-sig"), meta["retrieved_at"])
                save_json(Path(args.output) / (name + ".json"), rows)
                counts[name] = len(rows)
                observations.append(meta)
            report = {"state": "CURRENT_DIRECTORY_ONLY", "counts": counts,
                      "historical_membership_established": False, "observations": observations}
            save_json(Path(args.output) / "universe-report.json", report)
            print(canonical(report).decode())
        return 0
    except (DataError, SourceUnavailable, OSError, ValueError, KeyError, TypeError) as exc:
        state = "SOURCE_UNAVAILABLE" if isinstance(exc, SourceUnavailable) else "INVALID_INPUT"
        # No URLs with credentials, request headers or raw provider bodies are logged.
        error = {"state": state, "error_type": type(exc).__name__, "message": str(exc)}
        if args.command.startswith("fetch-"):
            save_json(Path(args.output) / "failure.json", error)
        print(canonical(error).decode(), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
