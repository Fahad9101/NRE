"""Run the owner-authorized M5 development comparison."""
import argparse
import json
import platform
import subprocess
from pathlib import Path
from statistics import mean

from . import m5_harness as harness
from .core import canonical, digest

ROOT = Path(__file__).resolve().parents[1]
AUTH = "reports/m5-phase3-authorization-2026-11-13.json"


def comparison(protocol, targets, events, calendar, caveats, blocks, daily, log):
    results = {}
    for target in protocol["targets"]:
        key = target["id"]
        variants = {version: harness.target_rows(events, targets[key], calendar, pairs)
                    for version, pairs in (("clean_window", caveats), ("all_event", {}))}
        folds = harness.develop_target(protocol, target, variants, daily, blocks)
        for variant, records in folds.items():
            for fold in records:
                for attempt in fold.get("selection", []):
                    log({"kind": "configuration", "target": key, "variant": variant,
                         "fold": fold["test_block"], "attempt": attempt})
                log({"kind": "fold", "target": key, "variant": variant, "result": fold})
        results[key] = {"summary": harness.summarize_development(protocol, target, folds),
                        "folds": folds}
    sensitivity = {}
    for variant in ("clean_window", "all_event"):
        low, high = ([row for fold in results[key]["folds"][variant] for row in fold["predictions"]]
                     for key in ("gap_ge_3pct", "gap_ge_5pct"))
        adjusted, caps = harness.monotonic_sensitivity(low, high)
        sensitivity[variant] = {"caps": caps, "rows": len(adjusted),
                                "contrast": mean(row["difference"] for row in adjusted) if adjusted else None}
    return {"targets": {key: result["summary"] for key, result in results.items()},
            "nested_gap_sensitivity": sensitivity}


def run(artifact, output, root=ROOT):
    authority = harness.load(root / AUTH)
    protocol = harness.load(root / authority["protocol"])
    protocol_hash = digest(canonical(protocol))
    if protocol_hash != authority["protocol_sha256"]:
        raise ValueError("Authorization protocol checksum mismatch")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("Run from a clean checkout and write outputs outside it")
    output.mkdir()
    with (output / "experiments.jsonl").open("x", encoding="utf-8", newline="\n") as journal:
        def log(record):
            journal.write(canonical(record).decode("utf-8") + "\n")
            journal.flush()

        provenance = {"protocol_sha256": protocol_hash, "code_commit": revision,
                      "artifact_sha256": digest(artifact.read_bytes()),
                      "python": platform.python_version(), "authorization": AUTH}
        log({"kind": "run_started", **provenance})
        try:
            inputs = harness.development_inputs(artifact, root)
            report = comparison(*inputs, log)
            result = {"schema_version": 1, **provenance, **report,
                      "development_events": len(inputs[2]), "holdout_accesses": 0}
            (output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                                 encoding="utf-8", newline="\n")
        except Exception as error:
            log({"kind": "run_failed", "error_type": type(error).__name__})
            raise
        log({"kind": "run_completed", "results_sha256": digest(canonical(result))})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.artifact, args.output)


if __name__ == "__main__":
    main()
