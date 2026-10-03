"""Descriptive evidence for the Milestone 4 scope proposal (docs/M4-BASELINE-PREDICTIVE-MODELS-SCOPE.md).

Counts, structure and uncertainty only: no model, no prediction, no score and no ranking, and nothing is fitted to anything. Everything is derived
from the committed accepted events (their labels, never prices) and the reviewed candidate ledgers, so the same inputs always give the same report.

What it answers, for the 128 accepted events: which of the master prompt's section-12 targets the labels can express and how many positives each has;
how the events fall in time and how many walk-forward folds that supports; how wide the uncertainty is at these sample sizes; how dependent the events
are; and how the three sources of events were selected.
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from . import fingerprints as fp
from .core import canonical, digest

BLOCK_GAP_DAYS = 28  # the longest label horizon is 20 sessions, a little under 28 calendar days
MIN_TRAIN_EVENTS = 40  # a declared yardstick for "enough events to fit anything at all", not a result
BUCKETS = {"estimable_at_or_above": 30, "thin_at_or_above": 10}  # positives and negatives; declared yardsticks, to be fixed in a pre-registered protocol
SOURCES = (("milestone_1", "config/m1-events.json"), ("milestone_2_step_2", "config/m2-step2-events.json"),
           ("milestone_2_step_3", "config/m2-step3-events.json"))
LEDGERS = (("milestone_1", "reports/m1-reviewed-candidate-ledger.json"), ("milestone_2_step_2", "reports/m2-step2-reviewed-candidate-ledger.json"),
           ("milestone_2_step_3", "reports/m2-step3-reviewed-candidate-ledger.json"))


def _gap(pct):
    return lambda labels: labels["gap_ge_%dpct" % pct]["value"]


def _ge(name, pct):
    def f(labels):
        value = labels[name]["value"]
        return None if value is None else value >= pct / 100.0
    return f


def _extension(pct):
    """Opening-anchored: the day's high relative to the open, H/O - 1."""
    def f(labels):
        opened, high = labels["day1_open_return"]["value"], labels["day1_high_return"]["value"]
        return None if opened is None or high is None else (1 + high) / (1 + opened) - 1 >= pct / 100.0
    return f


def _loses_half(labels):
    retained = labels["positive_gap_retained_half"]["value"]
    return None if retained is None else not retained


def _closes_below_open(labels):
    opened, close = labels["day1_open_return"]["value"], labels["day1_close_return"]["value"]
    return None if opened is None or close is None else (1 + close) / (1 + opened) - 1 < 0


# (id, family, definition, function over an event's labels): the master prompt's section 12 as far as the sixteen labels can express it
TARGETS = (
    [("gap_ge_%dpct" % t, "opening_gap", "opening gap O/Cprev - 1 >= %d%%" % t, _gap(t)) for t in (3, 5, 10, 15, 20, 30)]
    + [("day1_high_ge_%dpct" % t, "day1", "event-relative day-1 high H/P0 - 1 >= %d%%" % t, _ge("day1_high_return", t)) for t in (10, 20, 30)]
    + [("day1_close_ge_%dpct" % t, "day1", "event-relative day-1 close C/P0 - 1 >= %d%%" % t, _ge("day1_close_return", t)) for t in (10, 20)]
    + [("extension_after_open_ge_%dpct" % t, "continuation", "opening-anchored day-1 high H/O - 1 >= %d%%" % t, _extension(t)) for t in (5, 10)]
    + [("session5_close_ge_%dpct" % t, "continuation", "close of reaction session 5 / P0 - 1 >= %d%%" % t, _ge("session_5_close_return", t)) for t in (10, 20)]
    + [("loses_half_of_gap", "fade", "positive gaps of at least 0.5% only: the day-1 close keeps less than half of the gap", _loses_half),
       ("full_gap_fill", "fade", "positive gaps of at least 0.5% only: the day-1 low reaches the previous close", lambda labels: labels["positive_gap_filled"]["value"]),
       ("closes_below_open", "fade", "day-1 close below the day-1 open, C/O - 1 < 0", _closes_below_open)])
KEY_TARGETS = ("gap_ge_3pct", "gap_ge_5pct", "gap_ge_10pct", "day1_close_ge_10pct", "session5_close_ge_10pct", "loses_half_of_gap", "full_gap_fill")
REGRESSION_LABELS = ("day1_open_return", "day1_high_return", "day1_close_return", "session_5_close_return", "session_20_close_return")


def _r(value, places=6):
    return None if value is None else round(value, places)


def bucket(positives, negatives):
    if min(positives, negatives) >= BUCKETS["estimable_at_or_above"]:
        return "estimable_with_wide_uncertainty"
    if positives >= BUCKETS["thin_at_or_above"] and negatives >= BUCKETS["thin_at_or_above"]:
        return "thin"
    return "insufficient"


def assign_blocks(events):
    """Events in reaction-session order, cut wherever two consecutive reaction sessions are more than BLOCK_GAP_DAYS apart (1-based block numbers)."""
    ordered = sorted(events, key=lambda e: (e["reaction_session"], e["event_id"]))
    blocks, number, previous = {}, 1, None
    for event in ordered:
        day = date.fromisoformat(event["reaction_session"])
        if previous is not None and (day - previous).days > BLOCK_GAP_DAYS:
            number += 1
        blocks[event["event_id"]] = number
        previous = day
    return blocks


def target_row(events, function, blocks, confidence):
    rows = [(event, function(event["labels"])) for event in events]
    defined = [(event, value) for event, value in rows if value is not None]
    positive = [event for event, value in defined if value]
    n, k = len(defined), len(positive)
    low, high = fp.wilson(k, n, confidence) if n else (None, None)
    last = max(blocks.values())
    return {"n_defined": n, "positives": k, "negatives": n - k, "base_rate": _r(k / n) if n else None,
            "wilson_low": _r(low), "wilson_high": _r(high),
            "positives_by_timing": {t: sum(1 for e in positive if e["release_timing"] == t) for t in ("premarket", "after_hours")},
            "positive_reaction_sessions": len({e["reaction_session"] for e in positive}), "positive_issuers": len({e["cik"] for e in positive}),
            "defined_by_block": [sum(1 for e, _ in defined if blocks[e["event_id"]] == b) for b in range(1, last + 1)],
            "positives_by_block": [sum(1 for e in positive if blocks[e["event_id"]] == b) for b in range(1, last + 1)],
            "bucket": bucket(k, n - k)}


def regression_row(events, label):
    values = sorted(e["labels"][label]["value"] for e in events if e["labels"][label]["value"] is not None)
    n = len(values)
    mean = math.fsum(values) / n
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1))
    return {"n": n, "mean": _r(mean), "sd": _r(sd), "standard_error_of_mean": _r(sd / math.sqrt(n)), "p10": _r(fp.quantile(values, 0.1)),
            "median": _r(fp.quantile(values, 0.5)), "p90": _r(fp.quantile(values, 0.9))}


def time_structure(events, blocks, source_of):
    last = max(blocks.values())
    table = []
    for b in range(1, last + 1):
        members = [e for e in events if blocks[e["event_id"]] == b]
        days = sorted(date.fromisoformat(e["reaction_session"]) for e in members)
        table.append({"block": b, "first_reaction_session": days[0].isoformat(), "last_reaction_session": days[-1].isoformat(), "events": len(members),
                      "by_source": dict(sorted(Counter(source_of[e["event_id"]] for e in members).items())),
                      "by_timing": dict(sorted(Counter(e["release_timing"] for e in members).items()))})
    boundaries = []
    for b in range(1, last):
        before = [e for e in events if blocks[e["event_id"]] == b]
        after = [e for e in events if blocks[e["event_id"]] == b + 1]
        latest_label = max(e["available_at"]["session_20_close_return"] for e in before)
        earliest_cutoff = min(e["cutoff"] for e in after)
        slack = (earliest_cutoff - latest_label).total_seconds() / 86400
        boundaries.append({"between_blocks": [b, b + 1], "latest_session_20_label_available": latest_label.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "earliest_next_cutoff": earliest_cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"), "slack_days": _r(slack, 2),
                           "needs_purge_for_the_20_session_horizon": slack <= 0})
    return {"block_rule": ("reaction sessions are cut into blocks wherever two consecutive ones are more than %d calendar days apart (the longest label "
                           "horizon, 20 sessions, is a little under that)" % BLOCK_GAP_DAYS),
            "blocks": table, "boundaries": boundaries}


def walk_forward_plan(events, blocks, confidence):
    functions = {t[0]: t[3] for t in TARGETS}
    last = max(blocks.values())
    plan = []
    for test in range(2, last + 1):
        train = [e for e in events if blocks[e["event_id"]] < test]
        held = [e for e in events if blocks[e["event_id"]] == test]
        first_cutoff = min(e["cutoff"] for e in held)
        row = {"test_block": test, "train_blocks": list(range(1, test)), "train_events": len(train), "test_events": len(held),
               "train_events_with_session_20_label_mature_at_the_first_test_cutoff": sum(
                   1 for e in train if e["available_at"]["session_20_close_return"] <= first_cutoff),
               "enough_training_events_to_fit_anything": len(train) >= MIN_TRAIN_EVENTS, "targets": {}}
        for name in KEY_TARGETS:
            tr = [functions[name](e["labels"]) for e in train]
            te = [functions[name](e["labels"]) for e in held]
            row["targets"][name] = {"train_defined": sum(v is not None for v in tr), "train_positives": sum(1 for v in tr if v),
                                    "test_defined": sum(v is not None for v in te), "test_positives": sum(1 for v in te if v)}
        plan.append(row)
    viable = [p["test_block"] for p in plan if p["enough_training_events_to_fit_anything"]]
    holdout = [e for e in events if blocks[e["event_id"]] == last]
    development = [p for p in plan if p["test_block"] != last and p["enough_training_events_to_fit_anything"]]
    return {"expanding_window_folds": plan,
            "folds_with_enough_training_events": viable,
            "if_the_last_block_is_the_final_holdout": {"holdout_block": last, "holdout_events": len(holdout),
                                                       "development_test_blocks": [p["test_block"] for p in development],
                                                       "development_test_events": sum(p["test_events"] for p in development)},
            "yardstick_note": "MIN_TRAIN_EVENTS is a declared yardstick for 'enough events to fit anything at all', not a statistical result."}


def wilson_halfwidth(k, n, confidence):
    low, high = fp.wilson(k, n, confidence)
    return (high - low) / 2


def uncertainty(base_rates, confidence):
    sizes = (128, 103, 82, 61, 44, 23)
    halfwidth = {str(n): {str(p): _r(wilson_halfwidth(round(p * n), n, confidence), 4) for p in (0.1, 0.25, 0.5)} for n in sizes}
    needed = {}
    for target in (0.10, 0.15, 0.20):
        n = 2
        while wilson_halfwidth(n // 2, n, confidence) > target:
            n += 1
        needed[str(target)] = n
    lift = {}
    for name, base in base_rates.items():
        per_k = {}
        for k_selected in (10, 20, 40):
            hits = next((h for h in range(k_selected + 1) if fp.wilson(h, k_selected, confidence)[0] > base), None)
            per_k[str(k_selected)] = None if hits is None else {"hits_needed": hits, "precision_needed": _r(hits / k_selected, 4),
                                                                "lift_over_base_rate": _r(hits / k_selected / base, 3)}
        lift[name] = {"base_rate": _r(base), "if_the_top_k_events_are_selected": per_k}
    return {"wilson_confidence": confidence,
            "halfwidth_of_an_observed_proportion_by_sample_size": halfwidth,
            "sample_size_needed_for_a_halfwidth_at_an_observed_proportion_of_0.5": needed,
            "smallest_precision_at_k_whose_lower_bound_clears_the_base_rate": lift,
            "note": ("Interval widths for a plain binomial sample; events are not independent (see dependence), so real intervals are wider. "
                     "The last block answers: with K events selected, what observed precision is needed before its interval excludes the base rate.")}


def dependence(events):
    per_session = Counter(Counter(e["reaction_session"] for e in events).values())
    groups = Counter(e["sic_major_group"] for e in events)
    top2 = groups.most_common(2)
    return {"events": len(events), "issuers": len({e["cik"] for e in events}), "distinct_reaction_sessions": len({e["reaction_session"] for e in events}),
            "reaction_sessions_by_number_of_events": {str(k): v for k, v in sorted(per_session.items())},
            "most_events_on_one_reaction_session": max(Counter(e["reaction_session"] for e in events).values()),
            "events_per_issuer": {str(k): v for k, v in sorted(Counter(Counter(e["cik"] for e in events).values()).items())},
            "events_by_sic_division": dict(sorted(Counter(e["sic_division"] for e in events).items())),
            "two_largest_sic_major_groups": {k: v for k, v in top2}, "share_of_events_in_the_two_largest_groups": _r(sum(v for _, v in top2) / len(events), 4)}


def selection(ledgers):
    out = {}
    for name, ledger in ledgers.items():
        counts = Counter(c.get("disposition", "unknown") for c in ledger["candidates"])
        out[name] = {"candidates": len(ledger["candidates"]), "candidate_issuers": len({c["cik"] for c in ledger["candidates"]}),
                     "included": counts["included"], "excluded": counts["excluded"], "quarantined": counts["quarantined"],
                     "included_share": _r(counts["included"] / len(ledger["candidates"]), 4)}
    return out


def analyse(inputs, source_of, ledgers):
    events = inputs["events"]
    confidence = inputs["policy"]["wilson_confidence"]
    blocks = assign_blocks(events)
    targets = [{"target": t[0], "family": t[1], "definition": t[2], **target_row(events, t[3], blocks, confidence)} for t in TARGETS]
    base = {t["target"]: t["base_rate"] for t in targets if t["target"] in ("gap_ge_3pct", "gap_ge_5pct", "gap_ge_10pct")}
    return {"declared_yardsticks": {"block_gap_days": BLOCK_GAP_DAYS, "min_train_events": MIN_TRAIN_EVENTS, "bucket_positives_and_negatives": BUCKETS,
                                    "note": "Declared before any result was looked at; to be fixed, or replaced, in the pre-registered protocol."},
            "targets": targets,
            "regression_targets": {label: regression_row(events, label) for label in REGRESSION_LABELS},
            "time_structure": time_structure(events, blocks, source_of),
            "walk_forward": walk_forward_plan(events, blocks, confidence),
            "uncertainty": uncertainty(base, confidence),
            "dependence": dependence(events),
            "selection": selection(ledgers)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Descriptive evidence for the Milestone 4 scope proposal (no model, no prediction).")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--calendar", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    root = fp.ROOT
    inputs = fp.load_inputs(spec_path=args.spec, calendar_path=args.calendar)
    source_of = {}
    for name, rel in SOURCES:
        for event in json.loads((root / rel).read_text(encoding="utf-8"))["events"]:
            if "recorded_result" in event:
                source_of[event["event_id"]] = name
    assert set(source_of) == {e["event_id"] for e in inputs["events"]}, "every event must come from exactly one source spec"
    ledgers = {name: json.loads((root / rel).read_text(encoding="utf-8")) for name, rel in LEDGERS}
    provenance = fp.provenance(inputs, "m4_scoping_evidence")
    report = {"schema_version": 1, "kind": "m4_scoping_evidence",
              "purpose": ("Descriptive evidence for the Milestone 4 scope proposal: counts, structure and uncertainty over the accepted events. No model, no prediction, "
                          "no score and no ranking; nothing is fitted."),
              "inputs": {"spec": args.spec, "calendar": args.calendar, "events": len(inputs["events"]), "policy_sha256": inputs["policy_sha256"],
                         "event_table_sha256": provenance["inputs"]["event_table_sha256"]},
              **analyse(inputs, source_of, ledgers),
              "not_a_claim": ["Not a model, a prediction or a score.", "Not market base rates: the events are a convenience sample (see selection).",
                              "Not evidence of any predictive edge."]}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"state": "WRITTEN", "output": str(path), "report_sha256": digest(canonical(report))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
