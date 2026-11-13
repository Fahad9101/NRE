"""Phase 2 development harness. Real evaluation requires separate Phase 3 authorization."""
import json
import random
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

from . import m4_metrics as metrics, m4_models as baseline, m5_models as models
from .core import canonical, digest, timestamp
from .fingerprints import quantile
from .m4_harness import Abstain
from .m5_phase1b_audit import load
from .m5_phase1c import FEATURES, REGIME, STRUCTURE, load_inputs

RECORD = "reports/m5-phase1c-acquisition-result-2026-11-13.json"
FAMILIES = {"ticker_reaction": ("issuer_history",), "analogue": ("analogue",),
            "market_structure": tuple(STRUCTURE), "market_regime": REGIME}


def verify_artifact(path, root=Path(".")):
    """Read development features only, and verify them against the committed result."""
    protocol_hash, _, cohorts = load_inputs(root)
    record = load(root / RECORD)
    if digest(Path(path).read_bytes()) != record["artifact"]["zip_sha256"]:
        raise ValueError("Development artifact checksum mismatch")
    with ZipFile(path) as archive:
        if sorted(archive.namelist()) != ["development.json", "summary.json"]:
            raise ValueError("Unexpected development archive contents")
        data = json.loads(archive.read("development.json"))
        summary = json.loads(archive.read("summary.json"))
    if (summary != record["summary"] or data["partition"] != "development"
            or data["protocol_sha256"] != protocol_hash
            or digest(canonical(data)) != summary["development_sha256"]):
        raise ValueError("Development artifact disagrees with the pinned acquisition")
    rows = data["events"]
    if ([row["event_id"] for row in rows] != sorted(e["event_id"] for e in cohorts["development"])
            or any(set(row["features"]) != set(FEATURES) for row in rows)):
        raise ValueError("Unexpected development membership or feature schema")
    return {row["event_id"]: row["features"] for row in rows}


def order(event):
    return event["reaction_session"], event["event_id"]


def partitions(train, test):
    """Allocate whole sessions, then move connected clusters to the latest partition."""
    train = sorted(train, key=order)
    sessions = [list(rows) for _, rows in groupby(train, key=lambda e: e["reaction_session"])]
    minimum = (15 * len(train) + 99) // 100
    tail = []
    for _ in range(2):
        part = []
        while sessions and len(part) < minimum:
            part.extend(sessions.pop())
        tail.append(part)
    groups = [[event for session in sessions for event in session], tail[1], tail[0], list(test)]
    latest = {}
    # Alternating cluster and session edges can link more than two events.
    while True:
        changed = False
        for i, group in enumerate(groups):
            for event in group:
                keys = (("cluster", event["cluster_id"]), ("session", event["reaction_session"]))
                index = max(i, *(latest.get(key, 0) for key in keys))
                for key in keys:
                    if latest.get(key, -1) < index:
                        latest[key] = index
                        changed = True
        if not changed:
            break
    out = [[], [], [], []]
    for group in groups:
        for event in group:
            out[latest["cluster", event["cluster_id"]]].append(event)
    return tuple(sorted(group, key=order) for group in out)


def eligible_before(events, boundary):
    """Rows carry a target-specific maturity and outcome end, in addition to the clock."""
    return [e for e in events if e["outcome"] is not None and
            max(timestamp(e["maturity"]), timestamp(e["outcome_end"])) < boundary]


def row_for(event, fit, daily, clock):
    eligible = eligible_before([e for e in fit if e["reaction_session"] < event["reaction_session"]],
                               timestamp(event["clock"]))
    issuer = [e["outcome"] for e in eligible if e["issuer"] == event["issuer"]]
    pooled = mean(e["outcome"] for e in eligible) if eligible else None
    history = (sum(issuer) + 10 * pooled) / (len(issuer) + 10) if pooled is not None else None
    candidates = sorted((e for e in eligible if e["issuer"] != event["issuer"]
                         and e["release_timing"] == event["release_timing"]),
                        key=lambda e: (-int(e["reaction_session"].replace("-", "")), e["event_id"]))
    analogues = {}
    for candidate in candidates:
        analogues.setdefault(candidate["reaction_session"], candidate)
        if len(analogues) == 10:
            break
    selected = list(analogues.values()) if len(analogues) >= 5 else []
    row = {"after_hours": int(event["release_timing"] == "after_hours"), "issuer_history": history,
           "analogue": mean(e["outcome"] for e in selected) if selected else None,
           **daily[event["event_id"]]}
    if clock == "C0":
        row["open_gap"] = event["open_gap"]
    return row, [e["event_id"] for e in selected]


def seeded(protocol, target, fold, operation):
    return protocol["seeds"][operation] + int(digest(canonical([target, fold, operation]))[:16], 16)


def primary_loss(binary, actual, prediction):
    return metrics.event_brier(prediction, actual) if binary else metrics.event_pinball(actual, prediction)


def baseline_fit(name, rows, outcomes, binary, minimum):
    def pooled(values):
        if binary:
            return mean(values)
        ordered = sorted(values)
        return tuple(quantile(ordered, q) for q in (0.1, 0.5, 0.9))

    overall = pooled(outcomes)
    if name in ("m4_pooled_rate", "m4_pooled_quantiles"):
        return lambda row: (overall, False)
    if name in ("m4_timing_rate", "m4_timing_quantiles", "m4_sector_group"):
        field = "sector_group" if name == "m4_sector_group" else "after_hours"
        cells = defaultdict(list)
        for row, outcome in zip(rows, outcomes):
            cells[row[field]].append(outcome)
        estimates = {key: pooled(values) for key, values in cells.items() if len(values) >= 10}
        return lambda row: (estimates.get(row[field], overall), row[field] not in estimates)
    if name == "m4_issuer_history_rate":
        return lambda row: (row["issuer_history"] if row["issuer_history"] is not None else overall,
                            row["issuer_history"] is None)
    if name in ("momentum_stump", "rvol_stump"):
        field = "return_5" if name == "momentum_stump" else "rvol_20"
        pairs = [({field: row[field]}, outcome) for row, outcome in zip(rows, outcomes)
                 if row[field] is not None]
        if len(pairs) < 2 * minimum:
            return lambda row: (overall, True)
        x, y = map(list, zip(*pairs))
        model = models.tree(x, y, 1, minimum, binary)
        if not binary:
            model = models.quantiles(model, x, y)
        return lambda row: (model(row), False) if row[field] is not None else (overall, True)
    if name not in ("m4_logistic_without_sector", "m4_ridge_without_sector"):
        raise ValueError("Unknown registered baseline")

    def columns(row):
        history = row["issuer_history"]
        if history is None or "open_gap" in row and row["open_gap"] is None:
            return None
        values = [row["after_hours"], baseline.logit(baseline.clip_rate(history)) if binary else history]
        return values + ([row["open_gap"]] if "open_gap" in row else [])

    pairs = [(values, outcome) for row, outcome in zip(rows, outcomes)
             if (values := columns(row)) is not None]
    if not pairs:
        raise Abstain("INSUFFICIENT_DATA", "No fit rows have baseline inputs")
    x, y = map(list, zip(*pairs))
    means, deviations, kept, _ = baseline.standardization(x)
    scaled = [baseline.standardized(row, means, deviations, kept) for row in x]
    beta = baseline.fit_logistic(scaled, y)[0] if binary else baseline.fit_ridge(scaled, y)

    def point(values):
        normalized = baseline.standardized(values, means, deviations, kept)
        score = beta[0] + sum(a * b for a, b in zip(beta[1:], normalized))
        return baseline.sigmoid(score) if binary else score

    model = point if binary else models.quantiles(point, x, y)

    def predict(row):
        values = columns(row)
        if values is None:
            raise Abstain("INSUFFICIENT_DATA", "Baseline inputs unavailable")
        return model(values), False

    return predict


def enough(events, binary, threshold):
    if not binary:
        return len(events) >= threshold
    positives = sum(e["outcome"] for e in events)
    return min(positives, len(events) - positives) >= threshold


def run_fold(protocol, target, fold, train, test, daily, choices=None):
    """Fit, select, calibrate and score one fold on caller-supplied development fixtures."""
    binary = target["kind"] == "binary"
    fit, select, calibration, test = partitions(train, test)
    phases = (fit, select, calibration, test)
    boundaries = [min(timestamp(e["clock"]) for e in group) if group else None for group in phases]
    eligible_test = [e for e in test if e["outcome"] is not None]
    report = {"partitions": [[e["event_id"] for e in group] for group in phases],
              "selection": [], "predictions": [], "eligible_test": len(eligible_test)}
    if any(boundary is None for boundary in boundaries) or not eligible_test:
        return dict(report, status="INSUFFICIENT_DATA")
    fit, select, calibration = [eligible_before(group, min(boundaries[i + 1:]))
                                for i, group in enumerate(phases[:-1])]
    report["eligible_partitions"] = [[e["event_id"] for e in group]
                                     for group in (fit, select, calibration, eligible_test)]
    support = protocol["validation"]["support"]
    if not all(enough(group, binary, support[key]) for group, key in
               ((fit, "binary_fit_minimum_each_class" if binary else "regression_fit_minimum"),
                (select, "binary_selection_minimum_each_class" if binary else "regression_selection_minimum"))):
        return dict(report, status="INSUFFICIENT_DATA")
    grid = protocol["models"]["grid"]
    seed = seeded(protocol, target["id"], fold, "random_forest")
    report["seed"] = seed
    all_rows = {e["event_id"]: row_for(e, fit, daily, target["clock"])
                for group in (fit, select, calibration, eligible_test) for e in group}
    report["analogue_ids"] = {key: analogues for key, (_, analogues) in all_rows.items()}
    report["feature_coverage"] = [
        {name: sum(all_rows[e["event_id"]][0][name] is not None for e in group)
         for name in next(iter(all_rows.values()))[0]}
        for group in (fit, select, calibration, eligible_test)]
    y = [e["outcome"] for e in fit]

    def raw(event):
        return all_rows[event["event_id"]][0]

    def train_advanced(config, omit=None):
        family, depth = config
        drop = FAMILIES.get(omit, ())

        def reduced(event):
            return {key: value for key, value in raw(event).items() if key not in drop}

        x = [reduced(e) for e in fit]
        encode = models.encoder(x, set(x[0]) - {"after_hours"})
        predict = models.advanced(family, [encode(row) for row in x], y, depth, grid, binary, seed)
        return lambda event, override=None: predict(encode(reduced(event) if override is None else override))

    def train_baseline(name):
        def row(event):
            return dict(raw(event), sector_group=event.get("sector_group", "other"))

        predict = baseline_fit(name, [row(e) for e in fit], y, binary, grid["minimum_leaf_events"])
        return lambda event: predict(row(event))

    def choose(configs, factory, kind):
        successful = []
        for config in configs:
            try:
                model = factory(config)
                loss = None
                if choices is None:
                    predictions = [model(e) for e in select]
                    if kind == "baseline":
                        predictions = [prediction for prediction, _ in predictions]
                    loss = mean(primary_loss(binary, e["outcome"], prediction)
                                for e, prediction in zip(select, predictions))
                report["selection"].append({"kind": kind, "config": config, "loss": loss,
                                            "status": "SCORED" if choices is None else "FROZEN_CHOICE"})
                successful.append((loss, config, model))
            except (Abstain, OverflowError, ValueError) as error:
                report["selection"].append({"kind": kind, "config": config, "status": "MODEL_FIT_FAILED",
                                            "reason": type(error).__name__})
        return min(successful, key=lambda item: item[0] if item[0] is not None else 0) if successful else (None, None, None)

    configs = [(family, depth) for family in protocol["models"]["advanced_family_order"]
               for depth in grid["max_depth"]]
    baselines = protocol["models"]["baselines_binary_order" if binary else "baselines_regression_order"]
    _, advanced_choice, candidate = choose([tuple(choices[0])] if choices else configs, train_advanced, "advanced")
    _, baseline_choice, comparator = choose([choices[1]] if choices else baselines, train_baseline, "baseline")
    if candidate is None or comparator is None:
        return dict(report, status="MODEL_FIT_FAILED")
    report["choices"] = [advanced_choice, baseline_choice]
    report["training_base_rate"] = mean(y) if binary else None

    def calibrated(model):
        if not binary:
            return float, "NOT_APPLICABLE"
        return models.platt([model(e) for e in calibration], [e["outcome"] for e in calibration],
                            support["binary_calibration_minimum_each_class"])

    transform, report["calibration"] = calibrated(candidate)
    ablations = {}
    for family in FAMILIES:
        model = train_advanced(advanced_choice, family)
        adjust, state = calibrated(model)
        ablations[family] = (model, adjust, state)
    baseline_model = comparator
    sector_model = train_baseline("m4_sector_group")
    report["abstentions"] = []
    for event in eligible_test:
        try:
            comparison, fallback = baseline_model(event)
        except Abstain as error:
            report["abstentions"].append({"event_id": event["event_id"], "reason": str(error)})
            continue
        value = candidate(event)
        actual = event["outcome"]
        prediction = transform(value) if binary else value
        report["predictions"].append({
            "event_id": event["event_id"], "issuer": event["issuer"], "reaction_session": event["reaction_session"],
            "actual": actual, "candidate": prediction, "candidate_raw": value, "baseline": comparison,
            "baseline_fallback": fallback, "sector_sensitivity": sector_model(event)[0],
            "difference": primary_loss(binary, actual, prediction) - primary_loss(binary, actual, comparison),
            "ablations": {key: {"prediction": adjust(model(event)) if binary else model(event), "calibration": state}
                          for key, (model, adjust, state) in ablations.items()}})
    if report["predictions"]:
        by_id = {event["event_id"]: event for event in eligible_test}
        paired = [(by_id[row["event_id"]], row) for row in report["predictions"]]
        rng = random.Random(seeded(protocol, target["id"], fold, "permutation_importance"))
        report["permutation_importance"] = {}
        for name in sorted(raw(fit[0])):
            values = [raw(event)[name] for event, _ in paired]
            rng.shuffle(values)
            differences = []
            for (event, row), value in zip(paired, values):
                permuted = candidate(event, dict(raw(event), **{name: value}))
                adjusted = transform(permuted) if binary else permuted
                actual = row["actual"]
                differences.append(primary_loss(binary, actual, adjusted)
                                   - primary_loss(binary, actual, row["candidate"]))
            report["permutation_importance"][name] = mean(differences)
    return dict(report, status="EVALUABLE" if len(report["predictions"]) == len(eligible_test)
                else "PREDICTION_ABSTENTION")

def target_rows(events, target, calendar, caveats):
    """Adapt verified development rows without exposing labels to model callables."""
    from . import m4_data

    if any(m4_data.is_sealed(event) for event in events):
        raise m4_data.HoldoutSealed("Sealed events cannot enter the development harness")
    rows = []
    for event in events:
        labels = m4_data.mask_labels(event["labels"], caveats.get(event["event_id"], ()))
        session = event["reaction_session"]
        opening, close = calendar.bounds(session)
        clock = opening if target.clock == "C0" else event["cutoff"]
        if target.clock == "B" and clock >= opening:
            raise ValueError("Release cutoff must precede the reaction open")
        rows.append({"event_id": event["event_id"], "cluster_id": event["cluster_id"],
                     "issuer": event["cik"], "reaction_session": session,
                     "release_timing": event["release_timing"], "clock": clock.isoformat(),
                     "outcome": target.function(labels), "outcome_end": close.isoformat(),
                     "maturity": max(event["available_at"][name] for name in target.source_labels).isoformat(),
                     "open_gap": labels["day1_open_return"]["value"] if target.clock == "C0" else None,
                     "sector_group": baseline.sector_cell(event)})
    return rows


def develop_target(protocol, target, variants, daily, blocks):
    """Run the registered outer folds for one target on verified development inputs."""
    plan = protocol["validation"]
    results = {"clean_window": [], "all_event": []}
    for test_block, train_blocks in zip(plan["outer_development_test_blocks"], plan["outer_train_blocks"]):
        choices = None
        for variant in results:
            events = variants[variant]
            train = [e for e in events if blocks[e["event_id"]] in train_blocks]
            test = [e for e in events if blocks[e["event_id"]] == test_block]
            if variant == "all_event" and choices is None:
                report = {"status": "NO_CLEAN_WINDOW_CHOICE", "predictions": [],
                          "eligible_test": sum(e["outcome"] is not None for e in test)}
            else:
                report = run_fold(protocol, target, str(test_block), train, test, daily, choices)
            choices = report.get("choices")
            results[variant].append(dict(report, test_block=test_block))
    return results


def summarize_development(protocol, target, reports):
    binary = target["kind"] == "binary"
    support = protocol["validation"]["support"]
    output = {}
    for variant, folds in reports.items():
        rows = [row for fold in folds for row in fold["predictions"]]
        counts = {"events": len(rows), "eligible": sum(fold["eligible_test"] for fold in folds),
                  "issuers": len({row["issuer"] for row in rows}),
                  "reaction_sessions": len({row["reaction_session"] for row in rows}),
                  "folds": sum(bool(fold["predictions"]) for fold in folds)}
        if binary:
            counts.update(positives=sum(row["actual"] for row in rows))
            counts["negatives"] = len(rows) - counts["positives"]
        threshold = support["binary_development_and_holdout_minimum_each_class" if binary
                            else "regression_development_and_holdout_minimum"]
        if not enough([{"outcome": row["actual"]} for row in rows], binary, threshold):
            output[variant] = {"status": "INSUFFICIENT_DATA", "counts": counts}
            continue
        actual = [row["actual"] for row in rows]
        ids = [row["event_id"] for row in rows]
        loss = {key: mean(primary_loss(binary, row["actual"], row[key]) for row in rows)
                for key in ("candidate", "candidate_raw", "baseline", "sector_sensitivity")}
        paired = [row["difference"] for row in rows]
        cluster = {key: metrics.cluster_bootstrap(paired, [row[key] for row in rows],
                                                   seeded(protocol, target["id"], "pooled", "bootstrap_" + key),
                                                   replicates=5000)
                   for key in ("reaction_session", "issuer")}
        envelope = {level: [min(axis["intervals"][level][0] for axis in cluster.values()),
                            max(axis["intervals"][level][1] for axis in cluster.values())]
                    for level in ("0.95", "0.99")}
        ablations = {name: mean(primary_loss(binary, row["actual"], row["ablations"][name]["prediction"])
                                - primary_loss(binary, row["actual"], row["candidate"]) for row in rows)
                     for name in FAMILIES}
        candidate = [row["candidate"] for row in rows]
        if binary:
            base_rates = [fold["training_base_rate"] for fold in folds for _ in fold["predictions"]]
            secondary = {"confusion": metrics.confusion(candidate, actual, base_rates), "log_loss": metrics.log_loss(candidate, actual),
                         "average_precision": metrics.average_precision(candidate, actual),
                         "reliability": metrics.reliability(candidate, actual, ids)}
            secondary["precision_at_k"] = {}
            samples = [(str(fold.get("test_block", index)), fold["predictions"], (5, 10),
                        [fold.get("training_base_rate")] * len(fold["predictions"]))
                       for index, fold in enumerate(folds)]
            samples.append(("pooled", rows, (10, 20), base_rates))
            for fold_id, sample, limits, sample_rates in samples:
                outcomes = [row["actual"] for row in sample]
                scores = [row["candidate"] for row in sample]
                keys = [row["event_id"] for row in sample]
                for k in limits:
                    if len(sample) >= 2 * k:
                        seed = seeded(protocol, target["id"], fold_id, "random_ranking")
                        random_reference = metrics.random_precision_at_k(outcomes, keys, k, seed)
                        precision = metrics.precision_at_k(scores, outcomes, keys, k)
                        base_rate = mean(sample_rates)
                        secondary["precision_at_k"][f"{fold_id}:{k}"] = {
                            "candidate": precision, "lift_over_fit_rate": precision / base_rate if base_rate else None,
                            "lift_over_random": precision / random_reference["mean"] if random_reference["mean"] else None,
                            "baseline": metrics.precision_at_k([row["baseline"] for row in sample], outcomes, keys, k),
                            "random_reference": random_reference}
            calibration_ok = (abs(mean(candidate) - mean(actual)) <= 0.10
                              and all(fold.get("calibration") == "CALIBRATED" for fold in folds
                                      if fold["predictions"]))
        else:
            secondary = metrics.regression_metrics(actual, candidate)
            calibration_ok = abs(secondary["interval_coverage"] - 0.80) <= 0.15
        output[variant] = {"status": "EVALUABLE", "counts": counts, "loss": loss,
                           "contrast": mean(paired), "cluster_intervals": cluster, "envelope": envelope,
                           "secondary": secondary, "ablations": ablations, "calibration_ok": calibration_ok}
    clean, all_event = output["clean_window"], output["all_event"]
    output["development_gate_passed"] = (
        clean["status"] == all_event["status"] == "EVALUABLE"
        and clean["counts"]["events"] == clean["counts"]["eligible"]
        and all_event["counts"]["events"] == all_event["counts"]["eligible"]
        and clean["counts"]["folds"] >= support["minimum_evaluable_development_folds_for_claim"]
        and min(clean["counts"][key] for key in ("issuers", "reaction_sessions"))
        >= support["minimum_clusters_per_axis_for_claim"]
        and clean["envelope"]["0.99"][1] < 0
        and clean["calibration_ok"] and all_event["contrast"] <= 0)
    return output

def development_inputs(artifact, root=Path(".")):
    """Verify frozen development inputs for a separately authorized evaluator."""
    from . import caveat_sensitivity, fingerprints, m4_data, m4_protocol, m4_scoping_evidence
    from .m5_phase1c import PROTOCOL

    daily = verify_artifact(artifact, root)
    protocol = load(root / PROTOCOL)
    pin = protocol["inputs"]["m4_protocol"]
    if digest((root / pin["path"]).read_bytes().replace(b"\r\n", b"\n")) != pin["sha256_git_lf"]:
        raise ValueError("Milestone 4 protocol checksum mismatch")
    m4 = load(root / pin["path"])
    paths = m4["inputs"]
    spec_path = root / paths["events_spec"]["path"]
    spec = load(spec_path)
    data = fingerprints.load_inputs(spec_path, root / paths["sector_map"]["path"],
                                    root / paths["fingerprint_policy"]["path"], root,
                                    root / paths["calendar"]["path"])
    m4_protocol.require_verified(m4_protocol.verify_inputs(m4, data, spec, root))
    if {e["event_id"] for e in data["events"]} != set(daily):
        raise ValueError("Development feature and event memberships differ")
    return (protocol, m4_data.targets(m4), data["events"], data["calendar"],
            caveat_sensitivity.caveated_pairs(spec, with_derived=True),
            m4_scoping_evidence.assign_blocks(data["events"]), daily)


def monotonic_sensitivity(gap_3, gap_5):
    """Cap nested predictions for paired rows, leaving the primary records intact."""
    lower = {row["event_id"]: row for row in gap_3}
    adjusted, caps = [], {"candidate": 0, "baseline": 0}
    for row in gap_5:
        new = dict(row)
        if row["event_id"] in lower:
            for key in caps:
                cap = lower[row["event_id"]][key]
                if row[key] > cap:
                    new[key] = cap
                    caps[key] += 1
            new["difference"] = (primary_loss(True, row["actual"], new["candidate"])
                                 - primary_loss(True, row["actual"], new["baseline"]))
        adjusted.append(new)
    return adjusted, caps
