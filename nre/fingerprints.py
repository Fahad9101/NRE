"""Reaction fingerprints over the accepted Milestone 1 events: grouped base rates with counts, uncertainty and suppression.

Reads only committed derived records: config/m1-events.json, the per-event records it names, config/sector-map.json and
config/fingerprint-policy.json. No network, prices or credentials are used. Every statistic describes the accepted convenience
sample, not the market, and nothing here predicts, scores or ranks.
"""
import json
import math
import re
from collections import Counter
from datetime import timedelta
from pathlib import Path
from statistics import NormalDist

from . import event_acquire as ea
from .calendar import Calendar
from .core import DataError, canonical, digest, iso, timestamp

ROOT = ea.ROOT
DEFAULT_POLICY = ROOT / "config" / "fingerprint-policy.json"
DEFAULT_SECTOR_MAP = ROOT / "config" / "sector-map.json"
CATEGORY = ea.EVENT_CATEGORY + "/" + ea.EVENT_SUBTYPE
BAR_LAG = timedelta(minutes=1)  # a session's bar becomes available a minute after its close (event_acquire.build_bundle)
HORIZONS = (2, 5, 10, 20)
GAP_THRESHOLDS = (3, 5, 10, 15, 20, 30)
CONDITIONAL_LABELS = ("positive_gap_retained_half", "positive_gap_filled")
RETURN_LABELS = (tuple("day1_%s_return" % field for field in ("open", "high", "low", "close"))
                 + tuple("session_%d_close_return" % n for n in HORIZONS))
BOOLEAN_LABELS = tuple("gap_ge_%dpct" % t for t in GAP_THRESHOLDS) + CONDITIONAL_LABELS
LABELS = RETURN_LABELS + BOOLEAN_LABELS
DAY1_LABEL = "day1_close_return"  # every day-1 label matures with the reaction session
# The only null reasons the accepted records contain; the two 2026-09-23 records predate their label_reasons field.
INFERRED_REASONS = {"positive_gap_retained_half": "NOT_POSITIVE_GAP_GE_0_5PCT", "positive_gap_filled": "NOT_POSITIVE_GAP_GE_0_5PCT",
                    "session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"}
LEVELS = ("all", "timing", "sic_division", "sic_major_group", "issuer")
PARENT = {"timing": "all", "sic_division": "all", "sic_major_group": "sic_division", "issuer": "sic_major_group"}
DIVISIONS = (("A", "Agriculture, Forestry and Fishing", 1, 9), ("B", "Mining", 10, 14), ("C", "Construction", 15, 17),
             ("D", "Manufacturing", 20, 39),
             ("E", "Transportation, Communications, Electric, Gas and Sanitary Services", 40, 49),
             ("F", "Wholesale Trade", 50, 51), ("G", "Retail Trade", 52, 59), ("H", "Finance, Insurance and Real Estate", 60, 67),
             ("I", "Services", 70, 89), ("J", "Public Administration", 91, 99))
DIVISION_NAMES = {letter: name for letter, name, _, _ in DIVISIONS}
COUNT_UNITS = ("event", "reaction_session")
REPORTED, UNRELIABLE, WITHHELD = "REPORTED", "REPORTED_UNRELIABLE", "WITHHELD"
SCOPE_NOTE = ("These figures describe the accepted Milestone 1 events only: a convenience sample chosen because a minute-stamped wire release "
              "and a clean SEC neighbourhood existed, one event per issuer. They are not market base rates, and nothing here predicts, scores or ranks.")
POLICY_KEYS = ("schema_version", "policy_version", "confirmed_by", "count_unit", "wilson_confidence", "proportion", "mean_median",
               "quantiles", "pooling", "analogues")


def _whole(value, label, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DataError("%s must be an integer of at least %d" % (label, minimum))
    return value


def _nonnegative(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise DataError(label + " must be a non-negative number")
    return value


def _exact_keys(mapping, keys, label):
    if not isinstance(mapping, dict) or set(mapping) != set(keys):
        raise DataError("%s must have exactly the keys: %s" % (label, ", ".join(sorted(keys))))


def validate_policy(policy):
    _exact_keys(policy, POLICY_KEYS, "policy")
    if policy["schema_version"] != 1 or not isinstance(policy["policy_version"], str) or not policy["policy_version"]:
        raise DataError("policy needs schema_version 1 and a policy_version")
    if not isinstance(policy["confirmed_by"], dict):
        raise DataError("policy.confirmed_by must record who confirmed the defaults")
    if policy["count_unit"] not in COUNT_UNITS:
        raise DataError("policy.count_unit must be event or reaction_session")
    confidence = policy["wilson_confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 < confidence < 1:
        raise DataError("policy.wilson_confidence must be between 0 and 1")
    for name in ("proportion", "mean_median"):
        _exact_keys(policy[name], ("report_from_n", "unreliable_below_n"), "policy." + name)
        report, reliable = (_whole(policy[name][key], "policy.%s.%s" % (name, key)) for key in ("report_from_n", "unreliable_below_n"))
        if report > reliable:
            raise DataError("policy.%s.report_from_n cannot exceed unreliable_below_n" % name)
    quantiles = policy["quantiles"]
    _exact_keys(quantiles, ("levels", "report_from_n"), "policy.quantiles")
    levels = quantiles["levels"]
    if (not isinstance(levels, list) or not levels
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 < x < 1 for x in levels)
            or levels != sorted(set(levels))):
        raise DataError("policy.quantiles.levels must increase strictly between 0 and 1")
    if _whole(quantiles["report_from_n"], "policy.quantiles.report_from_n") < policy["mean_median"]["report_from_n"]:
        raise DataError("policy.quantiles.report_from_n cannot be below the mean and median minimum")
    _exact_keys(policy["pooling"], ("prior_strength",), "policy.pooling")
    _nonnegative(policy["pooling"]["prior_strength"], "policy.pooling.prior_strength")
    analogues = policy["analogues"]
    _exact_keys(analogues, ("min_members", "max_distance", "distance"), "policy.analogues")
    _whole(analogues["min_members"], "policy.analogues.min_members")
    _nonnegative(analogues["max_distance"], "policy.analogues.max_distance")
    _exact_keys(analogues["distance"], ("timing_mismatch", "sector_mismatch"), "policy.analogues.distance")
    _nonnegative(analogues["distance"]["timing_mismatch"], "policy.analogues.distance.timing_mismatch")
    sector = analogues["distance"]["sector_mismatch"]
    _exact_keys(sector, ("same_major_group", "same_division", "other"), "policy.analogues.distance.sector_mismatch")
    steps = [_nonnegative(sector[key], "policy sector_mismatch." + key) for key in ("same_major_group", "same_division", "other")]
    if steps != sorted(steps):
        raise DataError("policy sector_mismatch distances must not fall from same_major_group to other")


def load_policy(path=DEFAULT_POLICY):
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_policy(policy)
    return policy, digest(canonical(policy))


def sic_parts(sic):
    """Division letter and two-digit major group for a four-digit SIC code."""
    if not isinstance(sic, str) or not re.fullmatch(r"\d{4}", sic):
        raise DataError("SIC code must be four digits")
    group = int(sic[:2])
    for letter, _, low, high in DIVISIONS:
        if low <= group <= high:
            return letter, sic[:2]
    raise DataError("SIC major group %s belongs to no division" % sic[:2])


def sector_from_sic(sic):
    division, group = sic_parts(sic)
    return {"sic": sic, "sic_division": division, "sic_division_name": DIVISION_NAMES[division], "sic_major_group": group}


def load_sector_map(path=DEFAULT_SECTOR_MAP):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("issuers"), dict) or not raw["issuers"]:
        raise DataError("sector map needs schema_version 1 and an issuers object")
    read = raw.get("retrieval", {}).get("retrieved_between_utc")
    if not isinstance(read, list) or not read or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", str(read[0])):
        raise DataError("sector map must record when the SEC records were read")
    sectors = {}
    for cik, entry in raw["issuers"].items():
        if not re.fullmatch(r"\d{10}", cik) or not isinstance(entry, dict):
            raise DataError("sector map issuer keys must be ten-digit CIKs")
        if entry.get("source_url") != "https://data.sec.gov/submissions/CIK%s.json" % cik:
            raise DataError("sector map source_url for %s is not the SEC submissions record" % cik)
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("payload_sha256"))):
            raise DataError("sector map payload_sha256 for %s must be 64 hex digits" % cik)
        sectors[cik] = dict(sector_from_sic(entry.get("sic")), ticker=entry.get("ticker"), sic_description=entry.get("sic_description"))
    return sectors, digest(canonical(raw)), read[0][:10]


def label_kind(name):
    return "boolean" if name in BOOLEAN_LABELS else "return"


def label_available_at(name, reaction_session, calendar):
    """When a label can first be known: the close of the last session in its window plus a minute (the Milestone 1 rule)."""
    if name not in LABELS:
        raise DataError("unknown label " + str(name))
    last = calendar.offset(reaction_session, int(name.split("_")[1]) - 1) if name.startswith("session_") else reaction_session
    return calendar.bounds(last)[1] + BAR_LAG


def make_event(calendar, event_id, cluster_id, ticker, cik, release_timing, published_at, cutoff, reaction_session, sector, labels,
               source_id="", source_url="", labels_sha256=None):
    """One accepted event with its labels and, for every label, when it becomes available. Validates what it is given."""
    for value in (event_id, cluster_id, ticker, cik):
        if not isinstance(value, str) or not value:
            raise DataError("event needs nonempty string identifiers")
    if release_timing not in ea.TIMINGS:
        raise DataError(event_id + ": release timing must be premarket or after_hours")
    if not isinstance(labels, dict) or set(labels) != set(LABELS):
        raise DataError(event_id + ": an event must carry exactly the sixteen labels")
    for name in LABELS:
        value, reason = labels[name].get("value"), labels[name].get("reason")
        if value is None:
            if not isinstance(reason, str) or not reason:
                raise DataError("%s: null label %s needs a reason" % (event_id, name))
        elif reason is not None:
            raise DataError("%s: label %s has a value and a reason" % (event_id, name))
        elif label_kind(name) == "boolean" and not isinstance(value, bool):
            raise DataError("%s: label %s must be boolean" % (event_id, name))
        elif label_kind(name) == "return" and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise DataError("%s: label %s must be a finite number" % (event_id, name))
    published, cut = timestamp(published_at), timestamp(cutoff)
    if cut < published:
        raise DataError(event_id + ": cutoff precedes publication")
    return {"event_id": event_id, "cluster_id": cluster_id, "ticker": ticker, "cik": cik, "category": CATEGORY,
            "release_timing": release_timing, "published_at": published, "cutoff": cut,
            "anchor_session": calendar.offset(reaction_session, -1), "reaction_session": reaction_session,
            "source_id": source_id, "source_url": source_url, **sector, "labels": labels, "labels_sha256": labels_sha256,
            "available_at": {name: label_available_at(name, reaction_session, calendar) for name in LABELS}}


def event_from_record(entry, record, sector, calendar):
    """An accepted event built from its spec entry and committed record, refusing anything that departs from either."""
    name = entry["event_id"]
    pin = entry["recorded_result"]
    security = entry["security"]
    if (record.get("event_id"), record.get("ticker"), record.get("cik")) != (name, security["ticker"], security["cik"]):
        raise DataError(name + ": record identity differs from the spec")
    window = ea.event_window(entry, calendar)
    context = record.get("event_context", {})
    if any(context.get(key) != window[key] for key in ("release_timing", "reaction_session", "anchor_session")):
        raise DataError(name + ": record timing differs from the timing derived from the spec")
    values = record.get("computed_labels")
    if not isinstance(values, dict) or set(values) != set(LABELS):
        raise DataError(name + ": record must hold exactly the sixteen labels")
    reasons = record["label_reasons"] if "label_reasons" in record else {n: INFERRED_REASONS[n] for n in LABELS
                                                                          if values[n] is None and n in INFERRED_REASONS}
    labels = {n: {"value": values[n], "reason": reasons.get(n)} for n in LABELS}
    if ea.labels_digest({"labels": labels}) != pin["labels_sha256"]:
        raise DataError(name + ": committed label values do not reproduce the pinned digest")
    return make_event(calendar, name, entry["cluster_id"], security["ticker"], security["cik"], window["release_timing"],
                      entry["published_at"], entry["cutoff"], window["reaction_session"], sector, labels,
                      entry["source"]["source_id"], entry["source"]["url"], pin["labels_sha256"])


def load_events(spec, sectors, calendar, root=ROOT):
    root = Path(root)
    ea.validate_spec(spec, calendar, root)
    events = []
    for entry in spec["events"]:
        if "recorded_result" not in entry:
            continue
        cik = entry["security"]["cik"]
        if cik not in sectors:
            raise DataError("%s: no SIC entry for CIK %s" % (entry["event_id"], cik))
        record = json.loads((root / entry["recorded_result"]["recorded_in"]).read_text(encoding="utf-8"))
        sector = {k: sectors[cik][k] for k in ("sic", "sic_division", "sic_division_name", "sic_major_group", "sic_description")}
        events.append(event_from_record(entry, record, sector, calendar))
    if not events:
        raise DataError("no accepted events in the spec")
    if len({e["event_id"] for e in events}) != len(events):
        raise DataError("duplicate event_id")
    return sorted(events, key=event_order)


def load_inputs(spec_path=None, sector_map_path=None, policy_path=None, root=None):
    """Everything step 1 reads, validated and hashed. Nothing here touches the network."""
    calendar = Calendar()
    spec = json.loads(Path(spec_path or ea.DEFAULT_SPEC).read_text(encoding="utf-8"))
    sectors, sector_sha, sector_read_on = load_sector_map(sector_map_path or DEFAULT_SECTOR_MAP)
    policy, policy_sha = load_policy(policy_path or DEFAULT_POLICY)
    events = load_events(spec, sectors, calendar, root or ROOT)
    return {"events": events, "policy": policy, "policy_sha256": policy_sha, "sectors": sectors, "sector_map_sha256": sector_sha,
            "sector_read_on": sector_read_on, "calendar": calendar}


def event_order(event):
    return event["cutoff"], event["event_id"]


def dedupe_clusters(events):
    """One event per economic cluster (the earliest), so a repeated release never inflates a count."""
    kept, seen = [], set()
    for event in sorted(events, key=event_order):
        if event["cluster_id"] not in seen:
            seen.add(event["cluster_id"])
            kept.append(event)
    return kept


def gate_count(events, unit):
    """The number every threshold is compared with: events (one per cluster) or distinct reaction sessions."""
    return len({e["cluster_id"] for e in events}) if unit == "event" else len({e["reaction_session"] for e in events})


def rounded(value):
    return round(value, 10)


def wilson(k, n, confidence):
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def quantile(ordered, p):
    """Linear interpolation between order statistics (the common 'type 7' definition)."""
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def band(count, rule):
    """Whether an estimate resting on `count` observations is reported, reported as unreliable, or withheld."""
    if count < rule["report_from_n"]:
        return WITHHELD, "count %d is below the minimum of %d" % (count, rule["report_from_n"])
    if count < rule.get("unreliable_below_n", 0):
        return UNRELIABLE, "count %d is below %d, from which estimates count as reliable" % (count, rule["unreliable_below_n"])
    return REPORTED, None


def _stat(state, reason, **values):
    block = {"state": state}
    if reason:
        block["reason"] = reason
    block.update(values)
    return block


def label_statistics(values, kind, gate_n, policy):
    """Estimates for one label over the values that exist, gated on `gate_n` (events or reaction sessions)."""
    n = len(values)
    if kind == "boolean":
        state, reason = band(gate_n, policy["proportion"])
        k = sum(1 for v in values if v)
        proportion = _stat(state, reason)
        if state != WITHHELD:
            low, high = wilson(k, n, policy["wilson_confidence"])
            proportion.update(value=rounded(k / n), wilson_low=rounded(low), wilson_high=rounded(high))
        return {"k": k, "proportion": proportion}
    ordered = sorted(values)
    state, reason = band(gate_n, policy["mean_median"])
    mean, median = _stat(state, reason), _stat(state, reason)
    if state != WITHHELD:
        mean["value"], median["value"] = rounded(math.fsum(ordered) / n), rounded(quantile(ordered, 0.5))
    state, reason = band(gate_n, {"report_from_n": policy["quantiles"]["report_from_n"]})
    quantiles = _stat(state, reason)
    if state != WITHHELD:
        quantiles["values"] = {"p%g" % (level * 100): rounded(quantile(ordered, level)) for level in policy["quantiles"]["levels"]}
    return {"mean": mean, "median": median, "quantiles": quantiles}


def statistic_blocks(block):
    return [block["proportion"]] if block["kind"] == "boolean" else [block["mean"], block["median"], block["quantiles"]]


def describe_cell(members, cutoff, policy):
    """Counts and estimates for the events of one group, using only labels that had matured by `cutoff`."""
    unit = policy["count_unit"]
    known = [e for e in members if e["available_at"][DAY1_LABEL] <= cutoff]
    cell = {"counts": {"events": len(known), "issuers": len({e["cik"] for e in known}),
                       "reaction_sessions": len({e["reaction_session"] for e in known})}, "labels": {}}
    for name in LABELS:
        matured = [e for e in members if e["available_at"][name] <= cutoff]
        present = [e for e in matured if e["labels"][name]["value"] is not None]
        absent = Counter(e["labels"][name]["reason"] for e in matured if e["labels"][name]["value"] is None)
        gate_n = gate_count(present, unit)
        block = {"kind": label_kind(name), "n": len(present), "gate_n": gate_n, "n_absent": sum(absent.values())}
        if absent:
            block["absent_reasons"] = dict(sorted(absent.items()))
        block.update(label_statistics([e["labels"][name]["value"] for e in present], block["kind"], gate_n, policy))
        cell["labels"][name] = block
    return cell


def cell_keys(attrs):
    """The group of each level that an event or target belongs to; the issuer level exists only when the issuer is known."""
    keys = {"all": CATEGORY, "timing": attrs["release_timing"], "sic_division": attrs["sic_division"],
            "sic_major_group": attrs["sic_major_group"]}
    if attrs.get("cik"):
        keys["issuer"] = attrs["cik"]
    return keys


def _prior(cells, cell, name):
    """The estimate of the nearest ancestor that has one, and where it came from."""
    parent = cell["parent"]
    while parent is not None:
        ancestor = cells[parent]
        block = ancestor["labels"][name]
        pooled = block.get("pooled") or block.get("pooled_mean")
        if pooled:
            return parent, pooled["value"]
        raw = block.get("proportion") or block.get("mean")
        if raw["state"] != WITHHELD:
            return parent, raw["value"]
        parent = ancestor["parent"]
    return None


def _pool(cells, policy):
    """Partial pooling toward the nearest reported ancestor with a fixed prior strength; the cell's own n is never inflated."""
    strength = policy["pooling"]["prior_strength"]
    if not strength:
        return
    for cell in cells.values():  # root first, so an ancestor is pooled before its descendants
        for name, block in cell["labels"].items():
            own, key = (block["proportion"], "pooled") if block["kind"] == "boolean" else (block["mean"], "pooled_mean")
            prior = None if own["state"] == WITHHELD else _prior(cells, cell, name)
            if prior is not None:
                (level, group), value = prior
                n = block["n"]
                block[key] = {"value": rounded((n * own["value"] + strength * value) / (n + strength)),
                              "toward": {"level": level, "key": group}, "prior_strength": strength,
                              "weight_on_cell": rounded(n / (n + strength))}


def compute_cells(events, cutoff, policy, key_sets, all_events=None):
    """Cells for every group named in `key_sets`, as known at `cutoff`, computed from the root down."""
    usable = dedupe_clusters(events)
    parents, wanted = {}, set()
    for keys in key_sets:
        for level, key in keys.items():
            wanted.add((level, key))
            if level in PARENT:
                parents[(level, key)] = (PARENT[level], keys[PARENT[level]])
    cells = {}
    for level, key in sorted(wanted, key=lambda cell: (LEVELS.index(cell[0]), cell[1])):
        cell = describe_cell([e for e in usable if cell_keys(e)[level] == key], cutoff, policy)
        cell.update(level=level, key=key, parent=parents.get((level, key)))
        if level == "sic_division":
            cell["name"] = DIVISION_NAMES[key]
        elif level == "issuer":
            cell["name"] = next((e["ticker"] for e in (all_events or events) if e["cik"] == key), None)
        cells[(level, key)] = cell
    _pool(cells, policy)
    return cells


def render_cell(cell):
    """A cell for a report; a cell with every statistic withheld keeps its counts and names its parent."""
    rendered = {"level": cell["level"], "key": cell["key"]}
    if cell.get("name"):
        rendered["name"] = cell["name"]
    rendered["parent"] = None if cell["parent"] is None else {"level": cell["parent"][0], "key": cell["parent"][1]}
    rendered["counts"] = cell["counts"]
    blocks = cell["labels"]
    if all(stat["state"] == WITHHELD for block in blocks.values() for stat in statistic_blocks(block)):
        rendered.update(all_statistics_withheld=True, falls_back_to_parent=cell["parent"] is not None,
                        reason="every statistic is below its reporting minimum", n_by_label={n: b["n"] for n, b in blocks.items()})
    else:
        rendered["labels"] = blocks
    return rendered


def provenance(inputs, kind):
    events, policy = inputs["events"], inputs["policy"]
    table = [{"event_id": e["event_id"], "cluster_id": e["cluster_id"], "ticker": e["ticker"], "cik": e["cik"], "sic": e["sic"],
              "release_timing": e["release_timing"], "published_at": iso(e["published_at"]), "cutoff": iso(e["cutoff"]),
              "reaction_session": e["reaction_session"], "source_id": e["source_id"], "source_url": e["source_url"]}
             for e in sorted(events, key=lambda e: e["event_id"])]
    return {"schema_version": 1, "kind": kind,
            "policy": {"version": policy["policy_version"], "sha256": inputs["policy_sha256"], "count_unit": policy["count_unit"]},
            "inputs": {"event_table_sha256": digest(canonical(table)), "sector_map_sha256": inputs["sector_map_sha256"],
                       "event_labels_sha256": {e["event_id"]: e["labels_sha256"] for e in sorted(events, key=lambda e: e["event_id"])}},
            "scope_note": SCOPE_NOTE,
            "limits": ["SIC codes are each issuer's assignment when read on %s, not the one in force at the event's date." % inputs["sector_read_on"],
                       "Labels are raw daily returns, not market-adjusted, and events on one reaction session share market moves; "
                       "reaction sessions are counted beside events.",
                       "Counts and intervals treat events as independent. No significance is claimed and nothing is tested or ranked.",
                       "positive_gap_retained_half and positive_gap_filled exist only for events that opened at least 0.5% above the "
                       "prior close, so their counts are smaller than the group's."]}


def historical_target(event):
    return {"kind": "historical", "event_id": event["event_id"], "cluster_id": event["cluster_id"], "ticker": event["ticker"],
            "cik": event["cik"], "category": CATEGORY, "release_timing": event["release_timing"], "sic": event["sic"],
            "sic_division": event["sic_division"], "sic_division_name": event["sic_division_name"],
            "sic_major_group": event["sic_major_group"], "cutoff": event["cutoff"]}


def new_target(descriptor, sectors):
    """A target that is not in the dataset: what is known about it, and the moment it is being asked about."""
    allowed = {"category", "release_timing", "sic", "cik", "cluster_id", "as_of"}
    if not isinstance(descriptor, dict) or set(descriptor) - allowed or not {"release_timing", "as_of"} <= set(descriptor):
        raise DataError("a new event descriptor needs release_timing and as_of, and may add category, sic, cik, cluster_id")
    if descriptor["release_timing"] not in ea.TIMINGS:
        raise DataError("release_timing must be premarket or after_hours")
    sic, cik = descriptor.get("sic"), descriptor.get("cik")
    if cik is not None:
        if cik not in sectors:
            raise DataError("no SIC entry for CIK %s; give sic instead" % cik)
        if sic not in (None, sectors[cik]["sic"]):
            raise DataError("sic disagrees with the sector map for this CIK")
        sic = sectors[cik]["sic"]
    if sic is None:
        raise DataError("a new event descriptor needs sic or a mapped cik")
    return {"kind": "new", "event_id": None, "cluster_id": descriptor.get("cluster_id"), "ticker": None, "cik": cik,
            "category": descriptor.get("category", CATEGORY), "release_timing": descriptor["release_timing"],
            **sector_from_sic(sic), "cutoff": timestamp(descriptor["as_of"])}


def resolve_target(inputs, event_id=None, descriptor_path=None):
    if bool(event_id) == bool(descriptor_path):
        raise DataError("give exactly one of --event and --descriptor")
    if event_id:
        for event in inputs["events"]:
            if event["event_id"] == event_id:
                return historical_target(event)
        raise DataError("no accepted event " + event_id)
    return new_target(json.loads(Path(descriptor_path).read_text(encoding="utf-8")), inputs["sectors"])


def target_view(target):
    view = {k: target[k] for k in ("kind", "event_id", "cluster_id", "ticker", "cik", "category", "release_timing", "sic",
                                   "sic_division", "sic_division_name", "sic_major_group")}
    view["cutoff"] = iso(target["cutoff"])
    return view


def fingerprint_table(inputs, as_of=None):
    """Every group's statistics as known at `as_of` (default: once every label has matured)."""
    events = inputs["events"]
    if as_of is None:
        as_of = max(t for e in events for t in e["available_at"].values())
    cells = compute_cells(events, as_of, inputs["policy"], [cell_keys(e) for e in events])
    return {**provenance(inputs, "reaction_fingerprint_table"), "as_of": iso(as_of), "cells": [render_cell(c) for c in cells.values()]}


def target_fingerprint(inputs, target):
    """The statistics of the groups a target belongs to, from earlier matured events only and never from the target's own cluster."""
    events = [e for e in inputs["events"] if e["cluster_id"] != target.get("cluster_id")]
    cells = compute_cells(events, target["cutoff"], inputs["policy"], [cell_keys(target)], inputs["events"])
    return {**provenance(inputs, "reaction_fingerprint"), "target": target_view(target), "chain": [render_cell(c) for c in cells.values()]}


def dump_report(value, depth=0, compact_from=4, flat_limit=400):
    """Readable JSON: indented down to `compact_from` levels, one line for each object below that or short and flat."""
    flat = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if (depth >= compact_from or not isinstance(value, (dict, list)) or not value
            or (len(flat) <= flat_limit and not any(isinstance(v, (dict, list)) for v in (value.values() if isinstance(value, dict) else value)))):
        return flat
    pad, inner = "  " * depth, "  " * (depth + 1)
    if isinstance(value, dict):
        rows = [inner + json.dumps(key, ensure_ascii=False) + ": " + dump_report(item, depth + 1, compact_from, flat_limit)
                for key, item in value.items()]
        return "{\n" + ",\n".join(rows) + "\n" + pad + "}"
    return "[\n" + ",\n".join(inner + dump_report(item, depth + 1, compact_from, flat_limit) for item in value) + "\n" + pad + "]"


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_report(report) + "\n")
    return digest(canonical(report))


def fingerprints_command(args):
    inputs = load_inputs(args.spec, args.sector_map, args.policy, args.root)
    if args.event or args.descriptor:
        report = target_fingerprint(inputs, resolve_target(inputs, args.event, args.descriptor))
    else:
        report = fingerprint_table(inputs, timestamp(args.as_of) if args.as_of else None)
    return {"state": "WRITTEN", "kind": report["kind"], "output": str(args.output), "policy_sha256": inputs["policy_sha256"],
            "report_sha256": write_report(args.output, report)}
