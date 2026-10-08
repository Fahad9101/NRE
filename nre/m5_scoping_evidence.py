"""Milestone 5 scoping evidence: the planning arithmetic the scope proposal (docs/M5-ADVANCED-MODELS-SCOPE.md) rests on.

    python -m nre.m5_scoping_evidence build [--output PATH]

It is a pure function of artifacts already committed: the Milestone 4 report (development results and fold sizes), the frozen Milestone 4 protocol (the block structure) and the
Milestone 2 step 3 fingerprint table's scope note (events per issuer and the span). It fits nothing, predicts nothing, scores nothing, reads no event-level outcome and acquires no
data. It uses no result of the Milestone 4 holdout: of the holdout fold it reads only the size of its training set and of its test set. The tests prove that last statement by
corrupting every other holdout field and checking that the output does not change.

The arithmetic is planning arithmetic with its assumptions stated in the output. It does not describe the intervals an advanced model would get.
"""
import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

from . import m4_protocol as pr
from .core import canonical, digest

ROOT = pr.ROOT
REPORT = "reports/m4-report-2026-10-07.json"
PROTOCOL = "config/m4-protocol.json"
TABLE = "reports/m2-step3-combined-fingerprint-table-2026-10-02.json"
INPUTS = (REPORT, PROTOCOL, TABLE)
AS_OF = "2026-10-08"
HELD_BACK_SHARE = 0.2                      # of a training set: one slice for hyperparameter selection and one for calibration, as the contract's ordered periods require
MIN_LEAF = (3, 5, 10)                      # events in a tree's smallest leaf
RELATIVE_IMPROVEMENTS = (0.05, 0.10)       # of the comparator's score
TEST_SIZES_AS_MULTIPLES_OF_THE_DATASET = (1, 2, 4, 8)
VERSIONS = ("clean_window", "all_event")
OUT_NAME = "reports/m5-scoping-evidence-%s.json" % AS_OF
ASSUMPTIONS = [
    "A contrast's 99% half-width shrinks with the square root of the number of test events, with the same per-event variability (the usual planning approximation; real intervals depend on the model, "
    "the targets' clustering and the bootstrap).",
    "The half-widths are those of Milestone 4's confirmatory contrasts (a logistic or ridge model against the pooled comparator) on the pooled development test set; an advanced model's contrast "
    "against a stronger comparator could be wider or narrower.",
    "A model could only be declared better at the 99% level if its improvement exceeded the half-width; the 'required events' ask what test-set size would make a stated relative improvement "
    "equal the half-width.",
    "The held-back share is arithmetic about how small the fit set gets when the contract's ordered periods are cut from a training set; it is not a proposed design.",
    "The data-supply figure applies the dataset's own event rate to the days since its last reaction session; it assumes the same issuers kept reporting on the same cadence and stayed eligible, "
    "which has not been checked.",
]


def load(root, relative):
    return pr.load_json(Path(root) / relative)


def relative_cells(report):
    """The primary-target cells with a development confirmatory contrast, in the report's order."""
    for target, entry in report["primary_targets"].items():
        for version in VERSIONS:
            development = entry["development"][version]
            if development.get("confirmatory_model_against_c1"):
                yield target, version, entry, development


def split_sizes(train, share=HELD_BACK_SHARE):
    held = max(1, int(share * train))
    return {"training_events": train, "held_back_for_hyperparameter_selection": held, "held_back_for_calibration": held, "left_to_fit": train - 2 * held}


def fold_sizes(report):
    out = {}
    for target, entry in report["primary_targets"].items():
        for version in VERSIONS:
            development, holdout = entry["development"][version], entry["holdout"][version]
            folds = {}
            for name, fold in (development.get("folds") or {}).items():
                if fold.get("state") == "EVALUABLE":
                    folds[name] = {"train_events": fold["train"]["defined"], "train_positives": fold["train"].get("positives"), "test_events": fold["test"]["defined"]}
            if holdout.get("train"):      # a return has no positives: the field is then null
                folds["block_5_as_a_fold"] = {"train_events": holdout["train"]["defined"], "train_positives": holdout["train"].get("positives"), "test_events": holdout["test_counts"]["events"]}
            for fold in folds.values():
                fold["if_a_fifth_is_held_back_twice"] = split_sizes(fold["train_events"])
                fold["leaves_at_most"] = {str(m): fold["if_a_fifth_is_held_back_twice"]["left_to_fit"] // m for m in MIN_LEAF}
            out["%s/%s" % (target, version)] = folds
    return out


def detectability(report, dataset_events):
    out = {}
    for target, version, entry, development in relative_cells(report):
        contrast = development["confirmatory_model_against_c1"]
        events = contrast["events"]
        comparator = entry["comparator"]
        scores = development["scores"]
        simple = {pid: score for pid, score in scores.items() if pid.startswith("C") and score is not None}       # the rate and quantile baselines C1 to C4
        everything = {pid: score for pid, score in scores.items() if score is not None}                             # and the logistic or ridge models too
        best_simple, best_any = min(simple, key=simple.get), min(everything, key=everything.get)
        interval = contrast["interval_99"]
        half_width = (interval["high"] - interval["low"]) / 2
        comparator_score = scores[comparator]
        cell = {"events": events, "metric": contrast["metric"], "comparator": comparator, "comparator_score": comparator_score,
                "strongest_simple_baseline": best_simple, "strongest_simple_baseline_score": simple[best_simple],
                "strongest_m4_predictor": best_any, "strongest_m4_predictor_score": everything[best_any],
                "half_width_99": half_width, "half_width_as_share_of_comparator_score": half_width / comparator_score,
                "observed_difference_of_the_m4_model": contrast["estimate"]}
        cell["events_for_a_stated_improvement_to_equal_the_half_width"] = {
            "%d%%" % round(100 * r): math.ceil(events * (half_width / (r * comparator_score)) ** 2) for r in RELATIVE_IMPROVEMENTS}
        cell["half_width_as_share_of_comparator_score_at_test_sizes"] = {
            str(m * dataset_events): (half_width / comparator_score) * math.sqrt(events / (m * dataset_events)) for m in TEST_SIZES_AS_MULTIPLES_OF_THE_DATASET}
        out["%s/%s" % (target, version)] = cell
    return out


def data_supply(protocol, table, as_of=AS_OF):
    blocks = protocol["blocks_and_folds"]["expected_blocks"]
    sizes, spans = blocks["sizes"], blocks["first_and_last_reaction_session"]
    first, last = date.fromisoformat(spans[0][0]), date.fromisoformat(spans[-1][1])
    span_days = (last - first).days
    since = (date.fromisoformat(as_of) - last).days
    events = sum(sizes)
    note = re.search(r"describe the (\d+) accepted events.*?for the same (\d+) issuers \((\d+) to (\d+) events each, (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\)", table["scope_note"], re.S)
    if not note:
        raise ValueError("the fingerprint table's scope note no longer has the wording this reads (events, issuers, events per issuer, dates)")
    if int(note.group(1)) != events:
        raise ValueError("the fingerprint table's scope note counts %s events and the Milestone 4 protocol's blocks hold %d" % (note.group(1), events))
    return {"events": events, "issuers": int(note.group(2)), "block_sizes": sizes, "first_reaction_session": spans[0][0], "last_reaction_session": spans[-1][1], "span_days": span_days,
            "events_per_issuer_in_the_fingerprint_table_note": {"fewest": int(note.group(3)), "most": int(note.group(4)), "from": note.group(5), "to": note.group(6)},
            "as_of": as_of, "days_since_the_last_reaction_session": since,
            "events_at_the_same_rate_since_then": round(events * since / span_days, 1),
            "reading": "an estimate, not a count: nothing was enumerated, and the issuers' cadence and eligibility since the data ended have not been checked"}


def parts_read(report, protocol, table):
    """Exactly the parts of the three inputs the evidence reads, so that its provenance hashes them and an unrelated update to a living input (the report is regenerated when the replay accounting
    grows) does not disturb it. Of the holdout fold only the sizes of the training and test sets are here."""
    cells = {}
    for target, entry in report["primary_targets"].items():
        cells[target] = {"comparator": entry["comparator"]}
        for version in VERSIONS:
            development, holdout = entry["development"][version], entry["holdout"][version]
            cells[target][version] = {"development": {key: development.get(key) for key in ("folds", "scores", "confirmatory_model_against_c1")},
                                      "holdout_sizes": {"train": holdout.get("train"), "test_events": holdout["test_counts"]["events"]}}
    return {REPORT: cells, PROTOCOL: protocol["blocks_and_folds"]["expected_blocks"], TABLE: table["scope_note"]}


def build(root=ROOT, as_of=AS_OF):
    report, protocol, table = (load(root, name) for name in INPUTS)
    parts = parts_read(report, protocol, table)
    return {"schema_version": 1, "kind": "m5_scoping_evidence", "as_of": as_of,
            "scope_note": ("Planning arithmetic from committed Milestone 4 artifacts for the Milestone 5 scope proposal. It fits nothing, predicts nothing, scores nothing, reads no event-level outcome and "
                           "acquires no data. It uses no result of the Milestone 4 holdout: of the holdout fold it reads only the sizes of its training and test sets."),
            "inputs": {name: {"canonical_sha256_of_the_part_read": digest(canonical(parts[name]))} for name in INPUTS},
            "assumptions": ASSUMPTIONS,
            "fold_sizes": fold_sizes(report), "detectability": detectability(report, sum(protocol["blocks_and_folds"]["expected_blocks"]["sizes"])),
            "data_supply": data_supply(protocol, table, as_of)}


def _pct(x):
    return "%d%%" % math.floor(100 * x + 0.5)


def _score(value, metric):
    return ("%.5f" if "pinball" in metric else "%.4f") % value


def figures(evidence):
    """The numbers the scope proposal quotes in its prose, as strings, so that the proposal and the evidence cannot drift apart."""
    cells = evidence["detectability"]
    main = {name: cell for name, cell in cells.items() if not name.startswith("loses_half_of_gap")}
    shares = [c["half_width_as_share_of_comparator_score"] for c in main.values()]
    five = {name: c["events_for_a_stated_improvement_to_equal_the_half_width"]["5%"] for name, c in main.items()}
    ten = [c["events_for_a_stated_improvement_to_equal_the_half_width"]["10%"] for c in main.values()]
    dataset = evidence["data_supply"]["events"]
    at_dataset = [c["half_width_as_share_of_comparator_score_at_test_sizes"][str(dataset)] for c in main.values()]
    trains = [fold["train_events"] for name, folds in evidence["fold_sizes"].items() if not name.startswith("loses_half_of_gap") for fold in folds.values()]
    held = [fold["if_a_fifth_is_held_back_twice"]["held_back_for_calibration"] for name, folds in evidence["fold_sizes"].items() if not name.startswith("loses_half_of_gap") for fold in folds.values()]
    supply = evidence["data_supply"]
    return {"SHARE_MIN": _pct(min(shares)), "SHARE_MAX": _pct(max(shares)), "LOSES_SHARE": _pct(cells["loses_half_of_gap/all_event"]["half_width_as_share_of_comparator_score"]),
            "EV5_MIN": "{:,}".format(min(five.values())), "EV5_MAX": "{:,}".format(max(five.values())), "EV10_MIN": "{:,}".format(min(ten)), "EV10_MAX": "{:,}".format(max(ten)),
            "X_POOLED_MIN": "%d" % math.floor(min(five[n] / main[n]["events"] for n in main) + 0.5), "X_POOLED_MAX": "%d" % math.floor(max(five[n] / main[n]["events"] for n in main) + 0.5),
            "X_DATASET_MIN": "%d" % math.floor(min(five.values()) / dataset + 0.5), "X_DATASET_MAX": "%d" % math.floor(max(five.values()) / dataset + 0.5),
            "SHARE_AT_128_MIN": _pct(min(at_dataset)), "SHARE_AT_128_MAX": _pct(max(at_dataset)),
            "SUPPLY": "%d" % math.floor(supply["events_at_the_same_rate_since_then"] + 0.5),
            "SUPPLY_FORMULA": "%d events over %d days, %d days since the last reaction session" % (supply["events"], supply["span_days"], supply["days_since_the_last_reaction_session"]),
            "TRAIN_MIN": str(min(trains)), "TRAIN_MAX": str(max(trains)), "CAL_MIN": str(min(held)), "CAL_MAX": str(max(held))}


def tables(evidence):
    """The two tables of the scope proposal, as markdown, from the evidence."""
    rows = ["| Target | Version | Test events | Comparator (pooled) score | 99% half-width | Half-width as a share of the score | Events for a 5% / 10% improvement to equal it | The share at 128 / 256 / 512 / 1,024 test events |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, cell in evidence["detectability"].items():
        target, version = name.split("/")
        needed = cell["events_for_a_stated_improvement_to_equal_the_half_width"]
        sizes = cell["half_width_as_share_of_comparator_score_at_test_sizes"]
        rows.append("| `%s` | %s | %d | %s | %s | %s | %s / %s | %s |" % (
            target, version.replace("_", "-"), cell["events"], _score(cell["comparator_score"], cell["metric"]), _score(cell["half_width_99"], cell["metric"]),
            _pct(cell["half_width_as_share_of_comparator_score"]), "{:,}".format(needed["5%"]), "{:,}".format(needed["10%"]), " / ".join(_pct(sizes[k]) for k in sorted(sizes, key=int))))
    folds = evidence["fold_sizes"]["extension_after_open_ge_5pct/clean_window"]
    fold_rows = ["| Fold | Training events | Training positives | Held back for selection / for calibration | Left to fit | Leaves at most, smallest leaf 3 / 5 / 10 events |", "| --- | --- | --- | --- | --- | --- |"]
    for name, fold in folds.items():
        split = fold["if_a_fifth_is_held_back_twice"]
        label = {"dev_test_block_3": "tested on block 3", "dev_test_block_4": "tested on block 4", "block_5_as_a_fold": "tested on block 5 (now development data)"}[name]
        fold_rows.append("| %s | %d | %d | %d / %d | %d | %s |" % (label, fold["train_events"], fold["train_positives"], split["held_back_for_hyperparameter_selection"],
                                                                 split["held_back_for_calibration"], split["left_to_fit"], " / ".join(str(fold["leaves_at_most"][str(m)]) for m in MIN_LEAF)))
    return {"DETECTABILITY_TABLE": "\n".join(rows), "FOLD_TABLE": "\n".join(fold_rows)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Milestone 5 scoping evidence, computed from committed Milestone 4 artifacts.")
    parser.add_argument("command", choices=("build",))
    parser.add_argument("--output", help="write the evidence here (default: %s)" % OUT_NAME)
    args = parser.parse_args(argv)
    evidence = build()
    path = Path(args.output) if args.output else ROOT / OUT_NAME
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"state": "EVIDENCE", "output": str(path), "canonical_sha256": digest(canonical(evidence))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
