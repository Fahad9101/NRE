"""Does treating caveated labels as absent change what the pools say? A read-only sensitivity check.

Each accepted event may carry label-level caveats (config/m2-step*-events.json): a competing catalyst or an earlier disclosure that may have
moved the labels it names. The fingerprints/analogues machinery never reads them, so those labels enter every pool like any other. This module
re-runs that machinery with the caveated labels treated as absent and reports how much the pools move. It changes no policy, no spec and no
committed report, and it makes no prediction: it describes the accepted events only.

Three variants, because "treat caveated labels as absent" has more than one reading:
  as_recorded     only the labels a caveat names ('all' meaning every label of that event)
  with_derived    those, plus the labels derived from them (a caveat on the open touches every gap flag; on the close or the low, the
                  conditional gap-retention and gap-fill flags), since dataset.build() computes them from the same prices
  events_dropped  every event that carries any caveat is left out of the pools altogether
"""
import argparse
import copy
import json
import math
from pathlib import Path

from . import analogues as an
from . import fingerprints as fp
from .core import DataError, canonical, digest

CAVEAT_REASON = "CAVEAT"
# a caveat on the key also touches these labels, because nre.dataset.build() derives them from the same price
DERIVED = {"day1_open_return": tuple("gap_ge_%dpct" % t for t in fp.GAP_THRESHOLDS) + fp.CONDITIONAL_LABELS,
           "day1_close_return": ("positive_gap_retained_half",),
           "day1_low_return": ("positive_gap_filled",)}
VARIANTS = ("as_recorded", "with_derived", "events_dropped")
HEADLINE = ("day1_close_return", "session_2_close_return", "session_5_close_return", "session_10_close_return", "session_20_close_return",
            "gap_ge_3pct", "gap_ge_5pct", "gap_ge_10pct", "positive_gap_retained_half", "positive_gap_filled")
HEALTH = ("day1_close_return", "session_2_close_return", "session_5_close_return", "session_10_close_return", "session_20_close_return",
          "positive_gap_retained_half", "positive_gap_filled")
# a shift of the pooled estimate, in units of its own standard error, declared before looking at any result
YARDSTICK = {"notable_at_or_above": 0.5, "large_at_or_above": 1.0}
VARIANT_DEFINITIONS = {
    "as_recorded": "only the labels a caveat names are treated as absent ('all' meaning every label of that event)",
    "with_derived": ("those, plus the labels derived from them: a caveat on day1_open_return also touches every gap flag and both conditional "
                     "gap flags; on day1_close_return, positive_gap_retained_half; on day1_low_return, positive_gap_filled"),
    "events_dropped": "every event that carries any caveat is left out of the pools altogether",
}
PURPOSE = ("Does treating caveated labels as absent change what the pools say? Read-only: it changes no policy, no spec and no committed report, "
           "and describes the accepted events only. The machinery never reads caveats, so today's reports pool them like any other label.")
YARDSTICK_NOTE = ("shift_in_standard_errors is (estimate without - estimate with) / standard error of the estimate with, for a mean (returns) or a "
                  "proportion (flags), over the 'all' pool and the two timing pools. The two thresholds were fixed before any result was looked at; "
                  "they are a yardstick for 'is this movement bigger than the pool's own sampling noise', not a significance test.")


def caveated_pairs(spec, with_derived=False):
    """{event_id: {labels}} named by the events' caveats ('all' meaning every label), optionally closed under derivation."""
    pairs = {}
    for event in spec["events"]:
        if "recorded_result" not in event or not event.get("caveats"):
            continue
        names = set()
        for item in event["caveats"]:
            if "all" in item["labels"]:
                names.update(fp.LABELS)
            else:
                unknown = set(item["labels"]) - set(fp.LABELS)
                if unknown:
                    raise DataError(event["event_id"] + ": caveat names labels the pipeline never computes: " + ", ".join(sorted(unknown)))
                names.update(item["labels"])
        if with_derived:
            for name in sorted(names):
                names.update(DERIVED.get(name, ()))
        pairs[event["event_id"]] = names
    return pairs


def variant_inputs(inputs, pairs, variant):
    """A copy of the loaded inputs with the caveats applied as the variant says. Never mutates `inputs`."""
    out = dict(inputs)
    if variant == "events_dropped":
        out["events"] = [e for e in inputs["events"] if e["event_id"] not in pairs]
        return out
    events = copy.deepcopy(inputs["events"])
    for event in events:
        for name in pairs.get(event["event_id"], ()):
            event["labels"][name] = {"value": None, "reason": CAVEAT_REASON}
    out["events"] = events
    return out


def _values(events, label, timing=None):
    return [e["labels"][label]["value"] for e in events
            if e["labels"][label]["value"] is not None and (timing is None or e["release_timing"] == timing)]


def _median(ordered):
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _estimate(values, boolean):
    """The headline estimate of one pool and its standard error: a mean for returns, a proportion for flags."""
    n = len(values)
    if n == 0:
        return {"n": 0, "estimate": None, "median": None, "se": None}
    if boolean:
        p = sum(1 for v in values if v) / n
        return {"n": n, "estimate": p, "median": None, "se": math.sqrt(p * (1 - p) / n) if 0 < p < 1 else None}
    ordered = sorted(values)
    mean = math.fsum(ordered) / n
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in ordered) / (n - 1)) if n > 1 else None
    return {"n": n, "estimate": mean, "median": _median(ordered), "se": sd / math.sqrt(n) if sd is not None else None}


def _round(value):
    return None if value is None else round(value, 6)


def headline_pool(events_with, events_without, timing=None):
    rows = {}
    for label in HEADLINE:
        boolean = fp.label_kind(label) == "boolean"
        before, after = _estimate(_values(events_with, label, timing), boolean), _estimate(_values(events_without, label, timing), boolean)
        shift = None
        if before["estimate"] is not None and after["estimate"] is not None and before["se"]:
            shift = (after["estimate"] - before["estimate"]) / before["se"]
        rows[label] = {"kind": "proportion" if boolean else "mean", "n_with": before["n"], "n_without": after["n"],
                       "estimate_with": _round(before["estimate"]), "estimate_without": _round(after["estimate"]),
                       "shift_in_standard_errors": _round(shift),
                       "median_with": _round(before["median"]), "median_without": _round(after["median"])}
    return rows


def _health(inputs):
    summary = an.pool_report(inputs)["summary"]
    return {label: summary[label] for label in HEALTH}


def _headline_state(cell, label):
    if "labels" not in cell:
        return "WITHHELD"
    block = cell["labels"][label]
    return block["proportion"]["state"] if block["kind"] == "boolean" else block["mean"]["state"]


def _cell_states(table_with, table_without):
    pooled = {"compared": 0, "changed": []}
    issuer_pairs = {"compared": 0, "changed": 0}
    without = {(c["level"], c["key"]): c for c in table_without["cells"]}
    for cell in table_with["cells"]:
        other = without.get((cell["level"], cell["key"]))  # a cell can vanish when every event in it is dropped
        for label in HEADLINE:
            a = _headline_state(cell, label)
            b = "ABSENT" if other is None else _headline_state(other, label)
            if cell["level"] == "issuer":
                issuer_pairs["compared"] += 1
                issuer_pairs["changed"] += a != b
            else:
                pooled["compared"] += 1
                if a != b:
                    pooled["changed"].append({"level": cell["level"], "key": cell["key"], "label": label, "with": a, "without": b})
    pooled["changed_count"] = len(pooled["changed"])
    return {"pooled_cells": pooled, "issuer_cells": issuer_pairs}


def _shift_summary(rows_by_cell):
    shifts = [(abs(row["shift_in_standard_errors"]), cell, label) for cell, rows in rows_by_cell.items() for label, row in rows.items()
              if row["shift_in_standard_errors"] is not None]
    largest = max(shifts) if shifts else None
    return {"comparisons": len(shifts),
            "notable": sum(1 for s, _, _ in shifts if s >= YARDSTICK["notable_at_or_above"]),
            "large": sum(1 for s, _, _ in shifts if s >= YARDSTICK["large_at_or_above"]),
            "largest": None if largest is None else {"abs_shift_in_standard_errors": _round(largest[0]), "cell": largest[1], "label": largest[2]}}


def analyse(spec, inputs):
    """The whole comparison for one loaded dataset. Pure: the same spec and inputs always give the same report."""
    base_health = _health(inputs)
    base_table = fp.fingerprint_table(inputs)
    report = {"inventory": {}, "variants": {}}
    recorded, derived = caveated_pairs(spec), caveated_pairs(spec, with_derived=True)
    existing = {label: sum(1 for e in inputs["events"] if e["labels"][label]["value"] is not None) for label in fp.LABELS}
    report["inventory"] = {
        "events": len(inputs["events"]),
        "events_with_caveats": len(recorded),
        "events_using_the_all_sentinel": sorted(e["event_id"] for e in spec["events"] if "recorded_result" in e
                                                 and any("all" in c["labels"] for c in e.get("caveats", []))),
        "pairs_as_recorded": sum(len(v) for v in recorded.values()),
        "pairs_with_derived": sum(len(v) for v in derived.values()),
        "pairs_named_explicitly": sum(1 for event in spec["events"] if "recorded_result" in event
                                      for name in {n for item in event.get("caveats", []) for n in item["labels"]} if name != "all"),
        "by_label": {label: {"values_that_exist": existing[label],
                             "caveated_as_recorded": sum(1 for names in recorded.values() if label in names),
                             "caveated_with_derived": sum(1 for names in derived.values() if label in names)}
                     for label in fp.LABELS},
    }
    for variant in VARIANTS:
        pairs = derived if variant == "with_derived" else recorded
        changed = variant_inputs(inputs, pairs, variant)
        table = fp.fingerprint_table(changed)
        cells = {"all": headline_pool(inputs["events"], changed["events"]),
                 "premarket": headline_pool(inputs["events"], changed["events"], "premarket"),
                 "after_hours": headline_pool(inputs["events"], changed["events"], "after_hours")}
        health = _health(changed)
        report["variants"][variant] = {
            "events_in_pool": len(changed["events"]),
            "pool_health": {label: {"before": base_health[label], "after": health[label],
                                    "share_with_analogues_before": _round(base_health[label]["analogues_found"] / base_health[label]["targets"]),
                                    "share_with_analogues_after": _round(health[label]["analogues_found"] / health[label]["targets"])}
                            for label in HEALTH},
            "headline_pools": cells,
            "shift_summary": _shift_summary(cells),
            "cell_states": _cell_states(base_table, table),
        }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare the pools with and without caveated labels (read-only; changes no policy or report).")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--calendar", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    inputs = fp.load_inputs(spec_path=args.spec, calendar_path=args.calendar)
    report = analyse(spec, inputs)
    provenance = fp.provenance(inputs, "caveat_sensitivity")
    report = {"schema_version": 1, "kind": "caveat_sensitivity", "purpose": PURPOSE, "variant_definitions": VARIANT_DEFINITIONS,
              "yardstick": YARDSTICK, "yardstick_note": YARDSTICK_NOTE, "reason_code": CAVEAT_REASON,
              "inputs": {"spec": args.spec, "calendar": args.calendar, "policy_sha256": inputs["policy_sha256"],
                         "event_table_sha256": provenance["inputs"]["event_table_sha256"]}, **report}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"state": "WRITTEN", "output": str(path), "report_sha256": digest(canonical(report))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
