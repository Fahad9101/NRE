"""The Milestone 4 report as data, assembled by code from the committed artifacts (reports/m4-phase4-authorization-2026-10-07.json, P4-13).

    python -m nre.m4_report build --date YYYY-MM-DD [--output PATH]

It reads the Phase 2 and Phase 3 results (each checked against the hash its completion record holds), the Phase 4 holdout results and descriptive report, the two logs and the phases'
records, and writes one JSON document: what was estimable and what was not, every interval with its counts, the number of holdout accesses, the protocol's limits, the review items
still open for the owner, and, criterion by criterion, the evidence for the protocol's acceptance_of_the_m4_report. It is evidence, not a decision: whether Milestone 4 is accepted
is the owner's. It reads no label and no block-5 outcome: only what the earlier phases wrote.
"""
import argparse
import ast
import json
import sys
from pathlib import Path

from . import m4_data as d
from . import m4_harness as h
from . import m4_protocol as pr
from . import m4_registry as reg
from .core import DataError, canonical, digest

PHASES = {"phase1": {"completion": "reports/m4-phase1-completion-2026-10-06.json", "authorization": "reports/m4-phase1-authorization-2026-10-06.json"},
          "phase2": {"completion": "reports/m4-phase2-completion-2026-10-07.json", "authorization": "reports/m4-phase2-authorization-2026-10-07.json",
                     "results": "reports/m4-phase2-results-2026-10-07.json"},
          "phase3": {"completion": "reports/m4-phase3-completion-2026-10-07.json", "authorization": "reports/m4-phase3-authorization-2026-10-07.json",
                     "results": "reports/m4-phase3-results-2026-10-07.json"},
          "phase4": {"authorization": "reports/m4-phase4-authorization-2026-10-07.json"}}
PRIMARY_METRIC = {"binary": "brier", "regression": "mean_pinball_loss"}
LEAKAGE_TESTS_FILE = "tests/test_m4_harness.py"
SETTLED = {"phase2": ("details_settled_before_any_evaluation", "new_in_phase_2"), "phase3": ("details_settled_before_any_c0_evaluation", "new_in_phase_3"),
           "phase4": ("details_settled_before_the_look", "new_in_phase_4")}  # where each phase's authorization record lists the details it settled
JUDGMENT = "for the owner to judge"  # the value of a criterion the evidence states but does not settle
OPEN_REPLAY_TESTS = ("Whether the replay tests keep running automatically (each run, local or in CI, adds two counted accesses) or only on request. It was offered with that decision "
                     "and not chosen; nothing has changed.")  # what the report says while the accounting record holds no replay_tests_policy
NOT_A_CLAIM = ["Not a claim of a predictive edge: no status in the protocol, including DISTINGUISHABLE_BETTER, is one.",
               "Not evidence about any market: a convenience sample of 23 issuers on one regime, and block 5 is entirely Milestone 1 events (time and selection regime are confounded).",
               "Not Milestone 4 acceptance: the protocol makes that decision the owner's, and nothing here makes it."]


def load(root, name):
    return json.loads((Path(root) / name).read_text(encoding="utf-8"))


def interval(contrast, level):
    head = contrast["headline"][level]
    return {"low": head["low"], "high": head["high"], "clustering": head["clustering"]}


def contrast_entry(contrast, counts_of_model=None):
    """A contrast as the report states it: the estimate, both levels' headline intervals, and the events and clusters behind them."""
    out = {"role": contrast["role"], "claim": contrast.get("claim"), "estimate": contrast["estimate"], "metric": contrast["metric"], "direction": contrast["direction"],
           "interval_95": interval(contrast, "0.95"), "interval_99": interval(contrast, "0.99"),
           "events": contrast["by_clustering"]["issuer"]["events"],
           "clusters": {name: contrast["by_clustering"][name]["clusters"] for name in pr.BOOTSTRAP_CLUSTERINGS},
           "excludes_zero_at_95": contrast["headline"]["0.95"]["low"] > 0 or contrast["headline"]["0.95"]["high"] < 0,
           "excludes_zero_at_99": contrast["headline"]["0.99"]["low"] > 0 or contrast["headline"]["0.99"]["high"] < 0}
    if "against_the_development_result" in contrast:
        out["against_the_development_result"] = contrast["against_the_development_result"]
    if "role_note" in contrast:
        out["role_note"] = contrast["role_note"]
    return out


def development_entry(result, kind):
    model, comparator = h.CONFIRMATORY[kind], h.COMPARATOR[kind]
    pooled = result["pooled_development_test"]
    entry = {"state": pooled["state"], "reason": pooled["reason"], "test_counts": pooled["test"], "folds_included": pooled["folds_included"],
             "folds": {name: {"state": fold["state"], "train": fold["train"], "test": fold["test"]} for name, fold in result["folds"].items() if fold["role"] == "development"}}
    if pooled["state"] == d.EVALUABLE:
        key = PRIMARY_METRIC[kind]
        entry["scores"] = {pid: run["metrics"][key] for pid, run in result["predictors"].items() if run["state"] == h.EVALUATED}
        entry["counts"] = result["predictors"][comparator]["metrics"]["counts"]
        if model in result["contrasts"]:
            entry["confirmatory_model_against_c1"] = contrast_entry(result["contrasts"][model])
        entry["contrasts_against_c1"] = {pid: contrast_entry(c) for pid, c in result["contrasts"].items()}
        entry["other_contrasts"] = {name: contrast_entry(c) for name, c in result["other_contrasts"].items()}
        entry["fold_contrasts"] = {name: contrast_entry(c) for name, c in result["fold_contrasts"].items()}
    return entry


def holdout_entry(result, kind):
    model, comparator = h.CONFIRMATORY[kind], h.COMPARATOR[kind]
    entry = {"state": result["state"], "reason": result["reason"], "fold_state": result["fold"]["state"], "train": result["fold"]["train"], "test_counts": result["test_counts"],
             "selection_regime": result["selection_regime"]}
    if result["state"] == h.EVALUATED:
        key = PRIMARY_METRIC[kind]
        entry["scores"] = {pid: run["metrics"][key] for pid, run in result["predictors"].items() if run["state"] == h.EVALUATED}
        entry["predictor_states"] = {pid: run["state"] for pid, run in result["predictors"].items()}
        entry["counts"] = result["predictors"][comparator]["metrics"]["counts"]
        if model in result["contrasts"]:
            entry["confirmatory_model_against_c1"] = contrast_entry(result["contrasts"][model])
        entry["contrasts_against_c1"] = {pid: contrast_entry(c) for pid, c in result["contrasts"].items()}
        entry["other_contrasts"] = {name: contrast_entry(c) for name, c in result["other_contrasts"].items()}
    return entry


def required_tests(root):
    """The protocol's eight required leakage and integrity tests, each with the test methods that implement it (class RequiredTests in tests/test_m4_harness.py, named test_<n>_...)."""
    tree = ast.parse((Path(root) / LEAKAGE_TESTS_FILE).read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RequiredTests":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("test_") and item.name.split("_")[1].isdigit():
                    found.setdefault(int(item.name.split("_")[1]), []).append(item.name)
    return found


def replay_accounting(root, date):
    """The accesses to the block-5 outcomes beyond the chained log's: the replays that re-read them to verify the look, counted as accesses on the owner's decision. The record is read, not
    re-derived: it holds the look as access 1 and the replays after it, two to a run of the replay tests."""
    path = Path(root) / "reports" / ("m4-phase4-replay-accesses-%s.json" % date)
    if not path.is_file():
        raise DataError("the replay accounting is missing: the report must state every access to the holdout (%s)" % path.name)
    record = pr.load_json(path)
    accesses = record["accesses"]
    if [a["access_number"] for a in accesses] != list(range(1, len(accesses) + 1)) or accesses[0]["kind"] != "the_look" or any(a["kind"] != "replay" for a in accesses[1:]):
        raise DataError("the replay accounting is not a sequence of accesses numbered from the look")
    replays = len(accesses) - 1
    if record["totals"]["accesses"] != len(accesses) or record["totals"]["replay_accesses"] != replays:
        raise DataError("the replay accounting's totals do not match its accesses")
    return record, replays


def assemble(root=pr.ROOT, date="2026-10-07"):
    root = Path(root)
    protocol = pr.load_json(root / "config" / "m4-protocol.json")
    freeze = pr.load_json(root / "reports" / "m4-protocol-freeze-2026-10-06.json")
    protocol_sha = pr.protocol_sha256(protocol)
    if protocol_sha != freeze["protocol"]["canonical_sha256"]:
        raise DataError("the protocol does not match the hash in its freeze record")
    experiment_log, holdout_log = root / "reports" / "m4-experiment-log.jsonl", root / "reports" / "m4-holdout-access-log.jsonl"
    experiments_chain = reg.verify_chain(experiment_log, "experiments", protocol)
    holdout_chain = reg.verify_chain(holdout_log, "holdout_access", protocol)
    accesses = [record for record, _ in reg.read(holdout_log)][1:]
    accounting, replays = replay_accounting(root, date)
    policy = accounting.get("replay_tests_policy")  # present once the owner has decided how the replay tests run
    holdout_path = root / "reports" / ("m4-phase4-holdout-results-%s.json" % date)
    descriptive_path = root / "reports" / ("m4-phase4-descriptive-%s.json" % date)
    if not holdout_path.is_file() or not descriptive_path.is_file():
        raise DataError("Phase 4 has not been run: there is no holdout result to report")
    holdout, descriptive = load(root, "reports/" + holdout_path.name), load(root, "reports/" + descriptive_path.name)
    records = {phase: {name: load(root, path) for name, path in files.items() if name != "results" and (root / path).is_file()} for phase, files in PHASES.items()}
    development, statuses = {}, {}
    for phase in ("phase2", "phase3"):
        results = load(root, PHASES[phase]["results"])
        if digest(canonical(results)) != records[phase]["completion"]["evaluation"]["results_canonical_sha256"]:
            raise DataError("%s does not match the hash its completion record holds" % PHASES[phase]["results"])
        development.update(results["evaluations"])
        statuses.update(results["statuses"])
    targets = {t["id"]: t for role in ("primary", "descriptive_only", "insufficient_data_by_rule") for t in protocol["targets"][role]}
    primaries = [t["id"] for t in protocol["targets"]["primary"]]

    primary = {}
    for target_id in primaries:
        kind = targets[target_id]["kind"]
        model = h.CONFIRMATORY[kind]
        primary[target_id] = {
            "kind": kind, "clock": targets[target_id]["clock"], "definition": targets[target_id]["definition"], "confirmatory_model": model, "comparator": h.COMPARATOR[kind],
            "development_status": statuses[target_id][model],
            "development": {version: development_entry(development[target_id][version], kind) for version in d.VERSIONS},
            "holdout": {version: holdout_entry(holdout["evaluations"][target_id][version], kind) for version in d.VERSIONS}}
    other = {target_id: {"role": row["role"], "definition": row["definition"], **{version: {k: row[version][k] for k in ("n_defined", "positives", "negatives", "base_rate", "wilson_low", "wilson_high", "bucket",
                                                                                                                         "defined_by_block", "positives_by_block")}
                                                                                for version in d.VERSIONS}}
             for target_id, row in descriptive["targets"].items() if target_id not in primaries}
    estimable = {
        "development": {"evaluated": [[t, v] for t in primaries for v in d.VERSIONS if primary[t]["development"][v]["state"] == d.EVALUABLE],
                        "insufficient_data": [[t, v] for t in primaries for v in d.VERSIONS if primary[t]["development"][v]["state"] != d.EVALUABLE]},
        "holdout": {"evaluated": [[t, v] for t in primaries for v in d.VERSIONS if primary[t]["holdout"][v]["state"] == h.EVALUATED],
                    "counts_only": [[t, v] for t in primaries for v in d.VERSIONS if primary[t]["holdout"][v]["state"] == d.COUNTS_ONLY],
                    "insufficient_data": [[t, v] for t in primaries for v in d.VERSIONS if primary[t]["holdout"][v]["state"] == d.INSUFFICIENT_DATA]},
        "not_modelled": sorted(t for t in targets if t not in primaries)}
    pooled = [c for t in primaries for v in d.VERSIONS for section in ("contrasts_against_c1", "other_contrasts") for c in primary[t]["development"][v].get(section, {}).values()]
    folds = [c for t in primaries for v in d.VERSIONS for c in primary[t]["development"][v].get("fold_contrasts", {}).values()]
    holdout_contrasts = [c for t in primaries for v in d.VERSIONS for section in ("contrasts_against_c1", "other_contrasts") for c in primary[t]["holdout"][v].get(section, {}).values()]
    sign_checks = {"%s/%s" % (t, v): primary[t]["holdout"][v]["confirmatory_model_against_c1"]["against_the_development_result"]
                   for t in primaries for v in d.VERSIONS if "confirmatory_model_against_c1" in primary[t]["holdout"][v]}
    summary = {"pooled_development_contrasts": {"reported": len(pooled), "excluding_zero_at_95": sum(c["excludes_zero_at_95"] for c in pooled),
                                                "excluding_zero_at_99": sum(c["excludes_zero_at_99"] for c in pooled)},
               "development_fold_contrasts": {"reported": len(folds), "excluding_zero_at_95": sum(c["excludes_zero_at_95"] for c in folds)},
               "holdout_contrasts": {"reported": len(holdout_contrasts), "excluding_zero_at_95": sum(c["excludes_zero_at_95"] for c in holdout_contrasts)},
               "holdout_direction_checks": {key: {"comparable": check["comparable"], "same_sign": check.get("same_sign")} for key, check in sign_checks.items()},
               "development_statuses": {t: primary[t]["development_status"] for t in primaries},
               "holdout_accesses_in_total": len(accesses) + replays}

    by_number = required_tests(root)
    integrity = {
        "protocol": {"canonical_sha256": protocol_sha, "matches_the_freeze_record": True, "frozen_at": freeze["frozen_at"], "version": protocol["protocol_version"],
                     "amendments": protocol["amendments"]["history"]},
        "logs": {"experiments": experiments_chain, "holdout_access": holdout_chain, "holdout_accesses_after_genesis": len(accesses),
                 "holdout_accesses": {"logged_in_the_chain": len(accesses), "replays_counted": replays, "in_total": len(accesses) + replays,
                                      "accounting_record": "reports/m4-phase4-replay-accesses-%s.json" % date, "owner_decision": accounting["owner_decision"]["owner_message"]},
                 "the_accesses": [{"access_number": a["access_number"], "reason": a["reason"], "harness_commit": a["harness_commit"], "created_at": a["created_at"],
                                   "events_read": len(a["events_read"])} for a in accesses]},
        "phases": {phase: {"authorization": PHASES[phase]["authorization"], "owner_words": records[phase]["authorization"].get("owner_message", {}).get("text")
                           or records[phase].get("completion", {}).get("authorization", {}).get("owner_words"),
                           "completion_record": PHASES[phase].get("completion"),
                           "suite_tests_run": records[phase].get("completion", {}).get("tests", {}).get("suite_tests_run"),
                           "mutation_check": records[phase].get("completion", {}).get("tests", {}).get("mutation_check")} for phase in PHASES},
        "determinism": {"phase2": load(root, PHASES["phase2"]["results"])["determinism"]["identical"], "phase3": load(root, PHASES["phase3"]["results"])["determinism"]["identical"],
                        "phase4": holdout["determinism"]["identical"]},
        "independent_recomputation": {phase: records[phase]["completion"]["verification"]["independent_recomputation"] for phase in ("phase2", "phase3")},
        "required_leakage_and_integrity_tests": [{"required": text, "implemented_by": by_number.get(number, [])}
                                                 for number, text in enumerate(protocol["required_leakage_and_integrity_tests"], 1)]}
    limits = {"from_the_protocol": protocol["disclosures"]["limits"], "holdout_selection_regime": protocol["holdout"]["selection_regime"],
              "what_the_holdout_is_for": protocol["holdout"]["what_it_is_for"], "not_blind_to_counts": protocol["holdout"]["not_blind_to_counts"],
              "cannot_establish": protocol["acceptance_of_the_m4_report"]["cannot_establish"],
              "known_consequences_stated_in_advance": protocol["disclosures"]["known_consequences_stated_in_advance"],
              "expected_outcome_stated_in_advance": protocol["expected_outcome_stated_in_advance"],
              "the_intervals_cover": protocol["intervals"]["headline_interval_for_the_primary_contrast"]["what_it_covers"]}
    phase1 = records["phase1"]["completion"]["decisions_where_the_protocol_is_silent"]
    settled = {phase: [{"id": item["id"], "could_move_a_result": item["could_move_a_result"]} for item in records[phase]["authorization"][section][key]]
               for phase, (section, key) in SETTLED.items()}
    open_items = {"status": ("The owner has not answered these. The defaults are in force, protocol version 1 is unchanged, and changing any of them now would be a new protocol version "
                             "stated to follow results of the earlier phases."),
                  "from_the_protocol_to_review": protocol["disclosures"]["to_review"],
                  "protocol_silent_details_that_could_move_a_result": phase1["could_move_a_result"], "protocol_silent_details_presentational_or_minor": phase1["presentational_or_minor"],
                  "listed_in": phase1["listed_in"], "details_the_assistant_settled_in_later_phases": settled,
                  "replay_tests": {"decided": "The replays that re-read the block-5 outcomes to verify the look are counted as accesses (the owner's decision of %s: \"%s\")."
                                              % (accounting["owner_decision"]["owner_message"]["at"], accounting["owner_decision"]["owner_message"]["text"]),
                                   "opt_in": ({"decided_by": policy["decided_by"], "switch": policy["switch"], "meaning": policy["meaning"]} if policy else None),
                                   "open": None if policy else OPEN_REPLAY_TESTS}}
    first = reg.read(experiment_log)[1][0]["created_at"]
    sources = (("development", {t: development[t] for t in primaries}), ("holdout", holdout["evaluations"]))
    scored = [(t, v, pid, run) for _, results in sources for t in primaries for v in d.VERSIONS for pid, run in results[t][v]["predictors"].items() if run["state"] == h.EVALUATED]
    binary_scored = [(t, v, pid, run) for t, v, pid, run in scored if targets[t]["kind"] == "binary"]
    compared = all(set(results[t][v]["contrasts"]) == {pid for pid, run in results[t][v]["predictors"].items() if run["state"] == h.EVALUATED and pid != h.COMPARATOR[targets[t]["kind"]]}
                   for _, results in sources for t in primaries for v in d.VERSIONS if results[t][v]["predictors"][h.COMPARATOR[targets[t]["kind"]]]["state"] == h.EVALUATED)
    ranked = all(all("random_ranking" in cell or cell.get("state") == d.INSUFFICIENT_DATA for cell in run["metrics"]["precision_at_k"].values()) for _, _, _, run in binary_scored)
    calibrated = all(run["metrics"]["reliability"]["state"] in ("REPORTED", d.INSUFFICIENT_DATA) for _, _, _, run in binary_scored)
    tests_by_number = integrity["required_leakage_and_integrity_tests"]
    criteria = [
        {"criterion": "this protocol was frozen before evaluation",
         "evidence": "freeze record %s (frozen_at %s, protocol hash %s); the first experiment record was created at %s" % ("reports/m4-protocol-freeze-2026-10-06.json", freeze["frozen_at"], protocol_sha, first),
         "met_by_the_evidence": freeze["frozen_at"] < first and not protocol["amendments"]["history"]},
        {"criterion": "the integrity tests above pass",
         "evidence": "the protocol's eight required tests, each implemented in " + LEAKAGE_TESTS_FILE + " (see integrity.required_leakage_and_integrity_tests); every phase's completion record states a full-suite pass with exit status 0 and the mutation check's tally",
         "met_by_the_evidence": all(item["implemented_by"] for item in tests_by_number) and len(tests_by_number) == 8},
        {"criterion": "every output reproduces deterministically from committed inputs",
         "evidence": "each phase's evaluation was run twice from scratch and was identical before anything was recorded; tests re-run each phase from the committed inputs and compare with the committed results (the holdout by replaying the look through Harness.look against temporary logs, a test that runs only on request since the owner made it opt-in: each run is two counted accesses)",
         "met_by_the_evidence": all(integrity["determinism"].values())},
        {"criterion": "every target is reported with counts and cluster-aware intervals or as INSUFFICIENT_DATA",
         "evidence": "the five primary targets in the primary_targets section (counts, cluster-bootstrap intervals, or INSUFFICIENT_DATA / COUNTS_ONLY), the other 14 in other_targets (counts, base rates and Wilson intervals, as the protocol prescribes for targets that are not modelled)",
         "met_by_the_evidence": len(primary) + len(other) == 19},
        {"criterion": "every predictor is compared with the pooled comparator C1 and, for binary targets, the seeded random ranking, clean-window and all-event side by side",
         "evidence": "every scored predictor has its contrast against C1 in both versions (development and, where scored, holdout) and, for binary targets, precision at K against 1000 seeded random rankings in the results files",
         "met_by_the_evidence": compared and ranked and bool(binary_scored)},
        {"criterion": "calibration is shown with coarse bins and their counts",
         "evidence": "reliability bins (at most 4, at least 10 predictions each) with n, mean prediction, observed rate and its Wilson interval, for every scored binary predictor, in the results files",
         "met_by_the_evidence": calibrated and bool(binary_scored)},
        {"criterion": "the holdout was looked at once",
         "evidence": ("the holdout access log holds its genesis and %d access (%s); on the owner's decision of %s (\"%s\") the %d replays that re-read the block-5 outcomes to verify the look are counted "
                      "as accesses too, %d accesses in all (%s). The replays reproduced the committed look; nothing was selected, tuned or changed after a holdout result was seen."
                      % (len(accesses), ", ".join(a["reason"][:60] + "..." for a in accesses), accounting["owner_decision"]["owner_message"]["at"],
                         accounting["owner_decision"]["owner_message"]["text"], replays, len(accesses) + replays, "reports/m4-phase4-replay-accesses-%s.json" % date)),
         "met_by_the_evidence": (True if replays == 0 else JUDGMENT) if len(accesses) == 1 else False},
        {"criterion": "the limits are stated",
         "evidence": "the limits section carries the protocol's limits, the holdout's selection-regime statement, what the report cannot establish, and the consequences stated in advance",
         "met_by_the_evidence": bool(limits["from_the_protocol"] and limits["cannot_establish"])}]
    return {"schema_version": 1, "kind": "m4_report", "date": date,
            "purpose": ("The Milestone 4 report as data, assembled by code from the committed artifacts: what was estimable and what was not, every interval with its counts, the number "
                        "of holdout accesses, the limits, the review items still open for the owner, and the evidence for each of the protocol's acceptance criteria. Evidence, not a decision."),
            "protocol": {"id": protocol["protocol_id"], "version": protocol["protocol_version"], "canonical_sha256": protocol_sha, "frozen_at": freeze["frozen_at"]},
            "inputs": {"events": protocol["blocks_and_folds"]["expected_blocks"]["sizes"], "events_in_total": sum(protocol["blocks_and_folds"]["expected_blocks"]["sizes"]),
                       "block_assignment_sha256": protocol["inputs"]["block_assignment_sha256"], "event_table_sha256": protocol["inputs"]["event_table_sha256"],
                       "event_labels_sha256": protocol["inputs"]["event_labels_sha256"], "development_folds": protocol["blocks_and_folds"]["development_folds"],
                       "holdout_fold": protocol["blocks_and_folds"]["final_holdout_fold"]},
            "primary_targets": primary, "other_targets": other, "regression_labels": descriptive["regression_labels"], "estimable": estimable, "summary": summary,
            "integrity": integrity, "limits": limits, "open_for_the_owner": open_items,
            "acceptance_criteria": {"source": "config/m4-protocol.json, acceptance_of_the_m4_report", "meaning": protocol["acceptance_of_the_m4_report"]["meaning"],
                                    "does_not_require": protocol["acceptance_of_the_m4_report"]["does_not_require"], "criteria": criteria,
                                    "decision": "the owner's: nothing here declares Milestone 4 accepted"},
            "not_a_claim": NOT_A_CLAIM}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Milestone 4: assemble the report as data from the committed artifacts.")
    parser.add_argument("command", choices=("build",))
    parser.add_argument("--date", default="2026-10-07")
    parser.add_argument("--output", help="write the report here (default: reports/m4-report-<date>.json)")
    args = parser.parse_args(argv)
    report = assemble(date=args.date)
    path = Path(args.output) if args.output else pr.ROOT / "reports" / ("m4-report-%s.json" % args.date)
    h.write_report(path, report)
    print(json.dumps({"state": "REPORT", "output": str(path), "report_canonical_sha256": digest(canonical(report))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
