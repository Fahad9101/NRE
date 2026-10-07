"""A plain-arithmetic recomputation of the Milestone 4 binary predictors' predictions and of the M2 fit, from the development labels alone, for the committed-results tests.

It shares no code with nre/m4_models.py or nre/m4_features.py (only the loaded events, the folds and the protocol's constants), so that a wiring error in the harness, such as
the wrong training set, cell, fold or feature, cannot be present in both the harness and its check. For every binary predictor, version and development fold in a predictions file it
rebuilds the training events with the target defined and recomputes:

  C1 the pooled training rate;  C2, C3 the rate within the release-timing or sector-group cell (the pooled rate for a cell of fewer than 10 events);
  C4 the issuer's earlier outcomes shrunk toward the same-SIC-major-group rate (all earlier events if the group has fewer than 10, 0.5 with none);
  M2 the training means and standard deviations of its features, the penalized optimality conditions at the stored coefficients (so the stored fit IS the optimum of the
     stated objective on the rebuilt training rows), and the predictions from the stored parameters, capped by the 3% model's where the 5% model was repaired.

`check` returns (the problems found, how many sets of predictions and fits were checked).
"""
import math

from nre import m4_data as d
from nre import m4_protocol as pr

BINARY = ("C1_pooled_rate", "C2_timing_rate", "C3_sector_group_rate", "C4_issuer_history_rate", "M2_logistic", "M2_without_sector")
TOLERANCE = 1e-9  # the predictions are rounded to 12 decimals
GRADIENT_TOLERANCE = 1e-7


def rate(values):
    return sum(1 for v in values if v) / len(values)


def group_of(event):
    return event["sic_division"] if event["sic_division"] in ("D", "I") else "other"


def issuer_rate(event, defined, target):
    """(k + 10 p) / (n + 10): the issuer's own earlier outcomes shrunk toward the group's rate; an earlier event is one on an earlier reaction session whose labels were available at the cutoff."""
    earlier = [(e, v) for e, v in defined if e["event_id"] != event["event_id"] and e["reaction_session"] < event["reaction_session"]
               and all(e["available_at"][name] <= event["cutoff"] for name in target.source_labels)]
    own = [v for e, v in earlier if e["cik"] == event["cik"]]
    if earlier:
        group = [(e, v) for e, v in earlier if e["sic_major_group"] == event["sic_major_group"]]
        prior = rate([v for _, v in (group if len(group) >= pr.GROUP_PRIOR_MINIMUM else earlier)])
    else:
        prior = pr.GROUP_PRIOR_DEFAULT
    return (sum(1 for v in own if v) + pr.PRIOR_STRENGTH * prior) / (len(own) + pr.PRIOR_STRENGTH)


def sigmoid(z):
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def features(event, defined, target, names):
    clipped = min(max(issuer_rate(event, defined, target), pr.RATE_CLIP[0]), pr.RATE_CLIP[1])
    available = {"after_hours": 1.0 if event["release_timing"] == "after_hours" else 0.0, "is_I": 1.0 if group_of(event) == "I" else 0.0,
                 "is_other": 1.0 if group_of(event) == "other" else 0.0, "logit_issuer_history_rate": math.log(clipped / (1 - clipped)),
                 "open_gap": event["labels"]["day1_open_return"]["value"]}
    return [available[name] for name in names]


def check(harness, report, by_key):
    """by_key maps (target id, version, predictor id) to that predictor's prediction records, as read from a predictions file; report is the matching results report."""
    problems, checked = [], 0
    development = {fold.name: fold for fold in harness.folds if fold.role == "development"}
    for (target_id, version, predictor), records in sorted(by_key.items()):
        target = harness.targets[target_id]
        if target.kind != "binary" or predictor not in BINARY:
            continue
        for fold_name in sorted({r["fold"] for r in records}):
            where = "%s %s %s %s" % (target_id, version, predictor, fold_name)
            train, test = d.split(harness.versions[version], harness.blocks, development[fold_name])
            defined = [(e, target.function(e["labels"])) for e in train]
            defined = [(e, v) for e, v in defined if v is not None]
            test_defined = [e for e in test if target.function(e["labels"]) is not None]
            got = {r["event_id"]: r["prediction"] for r in records if r["fold"] == fold_name}
            if set(got) != {e["event_id"] for e in test_defined}:
                problems.append("%s: the predicted events are not the test events with the target defined" % where)
                continue
            pooled = rate([v for _, v in defined])
            if predictor == "C1_pooled_rate":
                want = {e["event_id"]: pooled for e in test_defined}
            elif predictor in ("C2_timing_rate", "C3_sector_group_rate"):
                cell_of = (lambda e: e["release_timing"]) if predictor == "C2_timing_rate" else group_of
                want = {}
                for e in test_defined:
                    members = [v for x, v in defined if cell_of(x) == cell_of(e)]
                    want[e["event_id"]] = rate(members) if len(members) >= pr.CELL_MINIMUM else pooled
            elif predictor == "C4_issuer_history_rate":
                want = {e["event_id"]: issuer_rate(e, defined, target) for e in test_defined}
            else:
                model = report["evaluations"][target_id][version]["predictors"][predictor]["folds"][fold_name]["model"]
                names = model["kept"]
                if model["dropped"]:
                    problems.append("%s: features were dropped (%s)" % (where, model["dropped"]))
                raw = [features(e, defined, target, names) for e, _ in defined]
                y = [1.0 if v else 0.0 for _, v in defined]
                n = len(raw)
                means = [math.fsum(row[j] for row in raw) / n for j in range(len(names))]
                sds = [math.sqrt(math.fsum((row[j] - means[j]) ** 2 for row in raw) / n) for j in range(len(names))]
                for label, mine, stored in (("mean", means, model["means"]), ("standard deviation", sds, model["standard_deviations"])):
                    if max(abs(a - b) for a, b in zip(mine, stored)) > TOLERANCE:
                        problems.append("%s: the training %ss differ from the stored ones" % (where, label))
                if model["rows"] != n:
                    problems.append("%s: the model says %d rows, the training events with the target are %d" % (where, model["rows"], n))
                beta = [model["intercept"]] + list(model["coefficients"])
                z = [[1.0] + [(row[j] - means[j]) / sds[j] for j in range(len(names))] for row in raw]
                p = [sigmoid(math.fsum(b * x for b, x in zip(beta, zrow))) for zrow in z]
                gradient = [math.fsum(zrow[j] * (yi - pi) for zrow, yi, pi in zip(z, y, p)) - (0.0 if j == 0 else pr.RIDGE_LAMBDA * beta[j]) for j in range(len(beta))]
                if max(abs(g) for g in gradient) > GRADIENT_TOLERANCE:
                    problems.append("%s: the stored coefficients are not the penalized optimum (largest gradient component %.3g)" % (where, max(abs(g) for g in gradient)))
                want = {}
                for e in test_defined:
                    x = features(e, defined, target, names)
                    want[e["event_id"]] = sigmoid(beta[0] + math.fsum(beta[j + 1] * (x[j] - means[j]) / sds[j] for j in range(len(names))))
                if target_id == "gap_ge_5pct":  # the monotone repair: capped at the same model's probability for the looser 3% threshold on the same event
                    cap = {r["event_id"]: r["prediction"] for r in by_key[("gap_ge_3pct", version, predictor)] if r["fold"] == fold_name}
                    repaired = sum(1 for k in want if want[k] > cap[k] + 1e-12)
                    want = {k: min(v, cap[k]) for k, v in want.items()}
                    reported = report["evaluations"][target_id][version]["predictors"][predictor]["folds"][fold_name]["diagnostics"]["repairs_of_the_nested_threshold"]
                    if repaired != reported:
                        problems.append("%s: %d predictions exceed the 3%% model's, but the report counts %d repairs" % (where, repaired, reported))
                checked += 1
            worst = max(abs(got[k] - want[k]) for k in got)
            checked += 1
            if worst > TOLERANCE:
                problems.append("%s: the predictions differ from the recomputation by up to %.3g" % (where, worst))
    return problems, checked
