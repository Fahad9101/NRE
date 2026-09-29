"""Point-in-time analogue retrieval over the accepted Milestone 1 events.

For a target (a historical event at its own cutoff, or a new event described by what is known about it) and one label, the pool is
every other event whose label had matured by the cutoff. Analogues are chosen by categorical distance alone, never by outcome,
expanding only as far as needed to reach the policy minimum and never beyond the policy maximum. Each answer lists every analogue and
every exclusion with its reason, and abstains explicitly when the pool falls short.

The one outcome-dependent fact is whether positive_gap_retained_half and positive_gap_filled exist for an event, because they are
defined only after a positive opening gap. That is those labels' own definition; it appears as LABEL_ABSENT, not as a choice of analogue.
"""
import math
from collections import Counter

from . import fingerprints as fp
from .core import DataError, iso

FOUND, INSUFFICIENT = "ANALOGUES_FOUND", "INSUFFICIENT_ANALOGUES"
HORIZON_LABELS = ("day1_close_return", "session_2_close_return", "session_5_close_return", "session_10_close_return",
                  "session_20_close_return")


def effective_sample_size(weights):
    """Kish: the squared sum of weights over the sum of squared weights; equals the count while weights are uniform."""
    squares = math.fsum(w * w for w in weights)
    return math.fsum(weights) ** 2 / squares if squares else 0.0


def sector_relation(a, b):
    if a["sic_major_group"] == b["sic_major_group"]:
        return "same_major_group"
    return "same_division" if a["sic_division"] == b["sic_division"] else "other"


def distance(target, event, policy):
    """Categorical mismatch only: release timing and sector. No price, return or label value enters."""
    rules = policy["analogues"]["distance"]
    timing = 0.0 if target["release_timing"] == event["release_timing"] else rules["timing_mismatch"]
    return round(timing + rules["sector_mismatch"][sector_relation(target, event)], 12)


def _counts(events, unit):
    return {"members": len(events), "issuers": len({e["cik"] for e in events}),
            "reaction_sessions": len({e["reaction_session"] for e in events}), "gate_n": fp.gate_count(events, unit),
            "effective_sample_size": fp.rounded(effective_sample_size([1.0] * len(events)))}


def _member(event, d, cutoff):
    keys = ("event_id", "ticker", "cik", "cluster_id", "reaction_session", "category", "source_id", "source_url", "release_timing",
            "sic", "sic_division", "sic_major_group")
    row = {key: event[key] for key in keys}
    row.update(published_at=iso(event["published_at"]), distance=d, weight=1.0,
               outcomes={name: event["labels"][name]["value"] for name in fp.LABELS if event["available_at"][name] <= cutoff})
    return row


def retrieve(target, events, label, policy):
    """The analogues of `target` for one label, as known at the target's cutoff."""
    if label not in fp.LABELS:
        raise DataError("unknown label " + str(label))
    limits, unit, cutoff = policy["analogues"], policy["count_unit"], target["cutoff"]
    result = {"label": label, "kind": fp.label_kind(label), "count_unit": unit, "minimum_members": limits["min_members"],
              "maximum_distance": limits["max_distance"]}
    if target["category"] != fp.CATEGORY:
        return {**result, "state": INSUFFICIENT, "reason": "NO_EVENTS_OF_CATEGORY", "pool": {"eligible": 0, "excluded_by_reason": {}},
                "distance_reached": None, "counts": _counts([], unit), "members": [], "summary": None, "excluded": []}
    ordered = sorted(events, key=fp.event_order)
    rows, candidates, counted = {}, [], set()
    for event in ordered:
        name, value = event["event_id"], event["labels"][label]
        if name == target["event_id"]:
            rows[name] = "SELF"
        elif event["cluster_id"] == target["cluster_id"]:
            rows[name] = "SAME_CLUSTER"
        elif event["available_at"][label] > cutoff:  # checked before absence: a label's absence is not known before it matures
            rows[name] = "LABEL_NOT_YET_MATURED"
        elif value["value"] is None:
            rows[name] = "LABEL_ABSENT"
        elif event["cluster_id"] in counted:
            rows[name] = "CLUSTER_ALREADY_COUNTED"
        else:
            counted.add(event["cluster_id"])
            candidates.append((distance(target, event, policy), event))
    within = [(d, e) for d, e in candidates if d <= limits["max_distance"]]
    members, reached = within, max((d for d, _ in within), default=None)
    for level in sorted({d for d, _ in within}):
        nearest = [(d, e) for d, e in within if d <= level]
        if fp.gate_count([e for _, e in nearest], unit) >= limits["min_members"]:
            members, reached = nearest, level
            break
    found = fp.gate_count([e for _, e in members], unit) >= limits["min_members"]
    chosen = {e["event_id"] for _, e in members}
    for d, event in candidates:
        if event["event_id"] not in chosen:
            rows[event["event_id"]] = "BEYOND_MAX_DISTANCE" if d > limits["max_distance"] else "BEYOND_EXPANSION"
    excluded = []
    for event in ordered:
        if event["event_id"] in rows:
            row = {"event_id": event["event_id"], "reason": rows[event["event_id"]]}
            if row["reason"] == "LABEL_ABSENT":
                row["detail"] = event["labels"][label]["reason"]
            excluded.append(row)
    counts = _counts([e for _, e in members], unit)
    summary = None
    if found:
        values = [e["labels"][label]["value"] for _, e in members]
        summary = {"n": len(values), "gate_n": counts["gate_n"], **fp.label_statistics(values, result["kind"], counts["gate_n"], policy)}
    reasons = Counter(row["reason"] for row in excluded)
    result.update(state=FOUND if found else INSUFFICIENT,
                  pool={"eligible": len(candidates), "excluded_by_reason": dict(sorted(reasons.items()))},
                  distance_reached=reached, counts=counts,
                  members=[_member(e, d, cutoff) for d, e in sorted(members, key=lambda item: (item[0], fp.event_order(item[1])))],
                  summary=summary, excluded=excluded)
    return result


def analogue_query(inputs, target, labels=None):
    labels = list(labels or fp.LABELS)
    return {**fp.provenance(inputs, "analogue_query"), "target": fp.target_view(target),
            "queries": [retrieve(target, inputs["events"], label, inputs["policy"]) for label in labels]}


def pool_report(inputs):
    """Every accepted event queried as a historical target at its own cutoff, for every label: how many matured events it could draw on."""
    events, policy = inputs["events"], inputs["policy"]
    targets = []
    for event in events:
        target = fp.historical_target(event)
        row = {"event_id": event["event_id"], "ticker": event["ticker"], "cutoff": iso(event["cutoff"]),
               "release_timing": event["release_timing"], "sic_division": event["sic_division"], "labels": {}}
        for label in fp.LABELS:
            result = retrieve(target, events, label, policy)
            row["labels"][label] = {"state": result["state"], "eligible": result["pool"]["eligible"],
                                    "members": result["counts"]["members"], "distance_reached": result["distance_reached"]}
        targets.append(row)
    summary = {}
    for label in HORIZON_LABELS + fp.CONDITIONAL_LABELS:
        sizes = [t["labels"][label]["eligible"] for t in targets]
        summary[label] = {"targets": len(sizes), "with_5_or_more": sum(s >= 5 for s in sizes), "with_10_or_more": sum(s >= 10 for s in sizes),
                          "with_20_or_more": sum(s >= 20 for s in sizes), "with_none": sum(s == 0 for s in sizes),
                          "analogues_found": sum(t["labels"][label]["state"] == FOUND for t in targets)}
    return {**fp.provenance(inputs, "analogue_pool_report"),
            "note": ("Each accepted event treated as a target at its own recorded cutoff. 'eligible' counts the other events whose label had matured "
                     "by then and exists; it uses calendar dates and cutoffs only. day1_close_return stands for every unconditional day-1 label "
                     "(returns and gap flags), which mature together."),
            "summary": summary, "targets": targets}


def analogues_command(args):
    inputs = fp.load_inputs(args.spec, args.sector_map, args.policy, args.root, args.calendar)
    if args.all_targets:
        if args.event or args.descriptor or args.label:
            raise DataError("--all-targets cannot be combined with --event, --descriptor or --label")
        report = pool_report(inputs)
    else:
        report = analogue_query(inputs, fp.resolve_target(inputs, args.event, args.descriptor), args.label)
    return {"state": "WRITTEN", "kind": report["kind"], "output": str(args.output), "policy_sha256": inputs["policy_sha256"],
            "report_sha256": fp.write_report(args.output, report)}
