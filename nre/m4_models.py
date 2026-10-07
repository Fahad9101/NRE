"""The Milestone 4 baselines beyond the pooled rate (Phase 2), built to the frozen protocol's words (config/m4-protocol.json: predictors and features).

Binary targets: C2, the rate within the event's release timing; C3, the rate within its sector group (each falling back to the pooled rate for a cell with fewer
than 10 defined training events, every fallback counted); C4, the issuer-history rate used directly as the probability; and M2, a ridge-penalized logistic
regression on after_hours, the two sector indicators and the logit of the issuer-history rate (plus the opening gap on the C0 clock), fitted by Newton-Raphson.
The regression target: the same two cell baselines as quantiles, and M3, a ridge linear regression on the same kind of features whose quantile outputs are the
fitted mean plus the 10th, 50th and 90th percentiles of the training residuals. M2 and M3 each have a without-sector sensitivity.

Each model is a pure function of the training events it is given. Its history features are built point-in-time (nre/m4_features.py): a training row sees only
earlier, matured training events, exactly as a test event does. Where the protocol gives no answer (a regression history mean with no earlier event) the model
leaves the row out and counts it; nothing is filled in. The choices Phase 2 made where the protocol is silent are in reports/m4-phase2-authorization-2026-10-07.json.
"""
import math

from . import fingerprints as fp
from . import m4_data as d
from . import m4_features as feat
from . import m4_protocol as pr
from .m4_data import ProtocolGap
from .m4_harness import Abstain, FittedModel, PooledQuantiles, PooledRate, Predictor

PIVOT_MINIMUM = 1e-12  # a pivot smaller than this makes the linear system singular
ZERO_SD = 1e-12  # a standard deviation this small, relative to the feature's scale, is zero to within floating-point rounding
DIGITS = 12  # fitted parameters are rounded like predictions, so that what is hashed and logged reproduces across platforms


def clean(value):
    """A number rounded for the record, and never -0.0."""
    return round(value, DIGITS) + 0.0


def solve(matrix, vector):
    """x with matrix x = vector, by Gaussian elimination with partial pivoting; a pivot below PIVOT_MINIMUM is MODEL_FIT_FAILED."""
    n = len(vector)
    a = [list(row) + [value] for row, value in zip(matrix, vector)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda r: abs(a[r][column]))
        if abs(a[pivot][column]) < PIVOT_MINIMUM:
            raise Abstain("MODEL_FIT_FAILED", "the linear system is singular (pivot %.3g in column %d)" % (abs(a[pivot][column]), column))
        a[column], a[pivot] = a[pivot], a[column]
        for r in range(column + 1, n):
            factor = a[r][column] / a[column][column]
            for c in range(column, n + 1):
                a[r][c] -= factor * a[column][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (a[r][n] - math.fsum(a[r][c] * x[c] for c in range(r + 1, n))) / a[r][r]
    return x


def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def logit(p):
    return math.log(p / (1 - p))


def clip_rate(rate):
    return min(max(rate, pr.RATE_CLIP[0]), pr.RATE_CLIP[1])


def standardization(rows):
    """Per-feature mean and population standard deviation of the training rows, and which features have a usable (non-zero) one: (means, sds, kept, dropped)."""
    n = len(rows)
    means, sds, kept, dropped = [], [], [], []
    for j in range(len(rows[0])):
        column = [row[j] for row in rows]
        mean = math.fsum(column) / n
        sd = math.sqrt(math.fsum((x - mean) ** 2 for x in column) / n)
        means.append(mean)
        sds.append(sd)
        (dropped if sd <= ZERO_SD * max(1.0, abs(mean)) else kept).append(j)
    return means, sds, kept, dropped


def standardized(row, means, sds, kept):
    return [(row[j] - means[j]) / sds[j] for j in kept]


def fit_logistic(z, y):
    """Newton-Raphson on the negative log-likelihood plus (lambda / 2) times the sum of squared coefficients, the intercept not penalized.

    Starts at zero; converged when the largest absolute coefficient change is below the protocol's tolerance, at most its iteration limit; otherwise
    MODEL_FIT_FAILED. Returns (coefficients with the intercept first, iterations, the largest absolute gradient component at the solution).
    """
    rows = [[1.0] + list(r) for r in z]
    k = len(rows[0])
    penalty = [0.0] + [pr.RIDGE_LAMBDA] * (k - 1)
    beta = [0.0] * k

    def gradient(beta, p):
        return [math.fsum(row[j] * (yi - pi) for row, yi, pi in zip(rows, y, p)) - penalty[j] * beta[j] for j in range(k)]

    for iteration in range(1, pr.NEWTON_MAX_ITERATIONS + 1):
        p = [sigmoid(math.fsum(b * x for b, x in zip(beta, row))) for row in rows]
        hessian = [[math.fsum(row[a] * row[b] * pi * (1 - pi) for row, pi in zip(rows, p)) + (penalty[a] if a == b else 0.0) for b in range(k)] for a in range(k)]
        step = solve(hessian, gradient(beta, p))
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < pr.NEWTON_TOLERANCE:
            p = [sigmoid(math.fsum(b * x for b, x in zip(beta, row))) for row in rows]
            return beta, iteration, max(abs(g) for g in gradient(beta, p))
    raise Abstain("MODEL_FIT_FAILED", "Newton-Raphson did not converge in %d iterations" % pr.NEWTON_MAX_ITERATIONS)


def fit_ridge(z, y):
    """Coefficients (the intercept first) of the ridge linear regression, lambda on every coefficient but the intercept, in closed form."""
    rows = [[1.0] + list(r) for r in z]
    k = len(rows[0])
    a = [[math.fsum(row[i] * row[j] for row in rows) + (pr.RIDGE_LAMBDA if i == j and i > 0 else 0.0) for j in range(k)] for i in range(k)]
    b = [math.fsum(row[i] * yi for row, yi in zip(rows, y)) for i in range(k)]
    return solve(a, b)


def open_gap(event):
    """The C0 feature: the event's opening return, from the test view or, for a training event, from its own labels. An event that has none is a gap in the protocol,
    which gives no default and no rule for leaving the row out (the audit counts these before the run)."""
    value = event["open_gap"] if "open_gap" in event else event["labels"]["day1_open_return"]["value"]
    if value is None:
        raise ProtocolGap("event %s has no opening return, which M2 takes as a feature on the C0 clock, and the protocol gives it no default" % event["event_id"])
    return value


# ---- the cell baselines: C2 (release timing) and C3 (sector group) --------------------------------------------------------------------------

def timing_cell(event):
    return event["release_timing"]


def sector_cell(event):
    return feat.sector_group(event)


class CellRate(Predictor):
    """The training rate within the event's cell; the pooled rate if the cell has fewer than 10 defined training events (counted and logged)."""
    kind = "binary"

    def __init__(self, predictor_id, cell_of):
        self.id, self.cell_of = predictor_id, cell_of

    def fit(self, train, target):
        pairs = [(self.cell_of(e), v) for e, v in zip(train, d.target_values(target, train)) if v is not None]
        if not pairs:
            raise Abstain("INSUFFICIENT_DATA", "no training event has the target defined")
        cells = {}
        for key, value in pairs:
            n, positives = cells.get(key, (0, 0))
            cells[key] = (n + 1, positives + (1 if value else 0))
        pooled = sum(1 for _, v in pairs if v) / len(pairs)
        parameters = {"pooled_rate": pooled, "n": len(pairs), "cell_minimum": pr.CELL_MINIMUM,
                      "cells": {key: {"n": n, "positives": k, "rate": k / n} for key, (n, k) in sorted(cells.items())}}
        return FittedModel(parameters, diagnostics={"fallbacks_to_the_pooled_rate": 0, "fallback_event_ids": []})

    def predict(self, model, view):
        cell = model["cells"].get(self.cell_of(view))
        if cell is None or cell["n"] < pr.CELL_MINIMUM:
            model.diagnostics["fallbacks_to_the_pooled_rate"] += 1
            model.diagnostics["fallback_event_ids"].append(view["event_id"])
            return model["pooled_rate"]
        return cell["rate"]


def timing_rate():
    return CellRate("C2_timing_rate", timing_cell)


def sector_group_rate():
    return CellRate("C3_sector_group_rate", sector_cell)


class CellQuantiles(Predictor):
    """The 10th, 50th and 90th percentiles (type 7) of the target within the event's cell; the pooled ones if the cell has fewer than 10 training events."""
    kind = "regression"

    def __init__(self, predictor_id, cell_of):
        self.id, self.cell_of = predictor_id, cell_of

    def fit(self, train, target):
        pairs = [(self.cell_of(e), v) for e, v in zip(train, d.target_values(target, train)) if v is not None]
        if not pairs:
            raise Abstain("INSUFFICIENT_DATA", "no training event has the target defined")
        by_cell = {}
        for key, value in pairs:
            by_cell.setdefault(key, []).append(value)
        quantiles = lambda values: [fp.quantile(sorted(values), q) for q in pr.QUANTILE_LEVELS]  # noqa: E731
        parameters = {"pooled_quantiles": quantiles([v for _, v in pairs]), "n": len(pairs), "cell_minimum": pr.CELL_MINIMUM,
                      "cells": {key: {"n": len(values), "quantiles": quantiles(values)} for key, values in sorted(by_cell.items())}}
        return FittedModel(parameters, diagnostics={"fallbacks_to_the_pooled_quantiles": 0, "fallback_event_ids": []})

    def predict(self, model, view):
        cell = model["cells"].get(self.cell_of(view))
        if cell is None or cell["n"] < pr.CELL_MINIMUM:
            model.diagnostics["fallbacks_to_the_pooled_quantiles"] += 1
            model.diagnostics["fallback_event_ids"].append(view["event_id"])
            return tuple(model["pooled_quantiles"])
        return tuple(cell["quantiles"])


def timing_quantiles():
    return CellQuantiles("C2_timing_quantiles", timing_cell)


def sector_group_quantiles():
    return CellQuantiles("C3_sector_group_quantiles", sector_cell)


# ---- C4: the issuer's own shrunk history, used directly ------------------------------------------------------------------------------------

class IssuerHistoryRate(Predictor):
    """The issuer_history_rate of the features, (k + m p) / (n + m), used directly as the probability."""
    id, kind = "C4_issuer_history_rate", "binary"

    def fit(self, train, target):
        if not any(v is not None for v in d.target_values(target, train)):
            raise Abstain("INSUFFICIENT_DATA", "no training event has the target defined")
        return FittedModel({"n": len(train), "prior_strength": pr.PRIOR_STRENGTH}, context={"train": train, "target": target},
                           diagnostics={"test_events_by_prior_source": {}, "test_events_without_an_earlier_event_of_their_own_issuer": 0})

    def predict(self, model, view):
        result = feat.issuer_history_rate(view, model.context["train"], model.context["target"])
        counts = model.diagnostics["test_events_by_prior_source"]
        counts[result["prior_source"]] = counts.get(result["prior_source"], 0) + 1
        if result["n"] == 0:
            model.diagnostics["test_events_without_an_earlier_event_of_their_own_issuer"] += 1
        return result["rate"]


# ---- M2: ridge-penalized logistic regression --------------------------------------------------------------------------------------------------

class Logistic(Predictor):
    """M2 (or, without the two sector indicators, M2_without_sector).

    `cap` is the monotone repair for the nested thresholds: a mapping from event id to the probability of the looser threshold (gap_ge_3pct) from this same
    model; a probability above it is lowered to it, and every repair is counted. A target with no nested looser threshold has no cap.
    """
    kind = "binary"

    def __init__(self, with_sector=True, cap=None):
        self.with_sector, self.cap = with_sector, cap
        self.id = "M2_logistic" if with_sector else "M2_without_sector"

    def names(self, target):
        return (["after_hours"] + (["is_I", "is_other"] if self.with_sector else []) + ["logit_issuer_history_rate"] + (["open_gap"] if target.clock == "C0" else []))

    def raw(self, event, train, target):
        indicators = feat.indicators(event)
        row = [indicators["after_hours"]] + ([indicators["is_I"], indicators["is_other"]] if self.with_sector else [])
        row.append(logit(clip_rate(feat.issuer_history_rate(event, train, target)["rate"])))
        if target.clock == "C0":
            row.append(open_gap(event))
        return row

    def fit(self, train, target):
        if self.cap is not None and not self.cap:
            raise Abstain("MODEL_FIT_FAILED", "the monotone repair needs this model's probabilities for the looser threshold, and there are none")
        defined = [(e, v) for e, v in zip(train, d.target_values(target, train)) if v is not None]
        ys = [1.0 if v else 0.0 for _, v in defined]
        raw = [self.raw(e, train, target) for e, _ in defined]
        means, sds, kept, dropped = standardization(raw)
        beta, iterations, gradient = fit_logistic([standardized(row, means, sds, kept) for row in raw], ys)
        names = self.names(target)
        parameters = {"features": names, "kept": [names[j] for j in kept], "dropped": [names[j] for j in dropped], "means": [clean(m) for m in means],
                      "standard_deviations": [clean(s) for s in sds], "intercept": clean(beta[0]), "coefficients": [clean(b) for b in beta[1:]],
                      "lambda": pr.RIDGE_LAMBDA, "rows": len(raw)}
        context = {"train": train, "target": target, "means": means, "sds": sds, "kept": kept, "beta": beta}
        return FittedModel(parameters, context=context, diagnostics={"iterations": iterations, "converged": True, "largest_gradient_component": float("%.1e" % gradient),
                                                                     "dropped_features": [names[j] for j in dropped], "rows": len(raw),
                                                                     "repairs_of_the_nested_threshold": 0, "repaired_event_ids": []})

    def predict(self, model, view):
        c = model.context
        z = standardized(self.raw(view, c["train"], c["target"]), c["means"], c["sds"], c["kept"])
        p = sigmoid(c["beta"][0] + math.fsum(b * x for b, x in zip(c["beta"][1:], z)))
        if self.cap is not None:
            if view["event_id"] not in self.cap:
                raise ProtocolGap("event %s has no prediction for the looser threshold to cap %s by" % (view["event_id"], self.id))
            if p > self.cap[view["event_id"]]:
                model.diagnostics["repairs_of_the_nested_threshold"] += 1
                model.diagnostics["repaired_event_ids"].append(view["event_id"])
                p = self.cap[view["event_id"]]
        return p


# ---- M3: ridge linear regression with residual quantiles ------------------------------------------------------------------------------------

class Ridge(Predictor):
    """M3 (or, without the two sector indicators, M3_without_sector): the quantile outputs are the fitted mean plus the 10th, 50th and 90th percentiles of
    the training residuals.

    A training row with no earlier matured event has no history mean (the protocol gives none), so it is left out of the fit, counted, and logged; it still
    counts as history for later events. A fit with fewer than 40 rows left is INSUFFICIENT_DATA. A test event with no history mean stops the run.
    """
    kind = "regression"

    def __init__(self, with_sector=True):
        self.with_sector = with_sector
        self.id = "M3_ridge_linear" if with_sector else "M3_without_sector"

    def names(self, target):
        return ["after_hours"] + (["is_I", "is_other"] if self.with_sector else []) + ["issuer_history_mean"]

    def raw(self, event, train, target):
        indicators = feat.indicators(event)
        row = [indicators["after_hours"]] + ([indicators["is_I"], indicators["is_other"]] if self.with_sector else [])
        row.append(feat.issuer_history_mean(event, train, target)["mean"])
        return row

    def fit(self, train, target):
        rows, ys, excluded = [], [], []
        for event, value in zip(train, d.target_values(target, train)):
            if value is None:
                continue
            try:
                rows.append(self.raw(event, train, target))
            except ProtocolGap:
                excluded.append(event["event_id"])
                continue
            ys.append(value)
        if len(rows) < pr.MIN_TRAIN_EVENTS:
            raise Abstain("INSUFFICIENT_DATA", "%d training rows with a history mean, fewer than the %d needed to fit anything" % (len(rows), pr.MIN_TRAIN_EVENTS))
        means, sds, kept, dropped = standardization(rows)
        z = [standardized(row, means, sds, kept) for row in rows]
        beta = fit_ridge(z, ys)
        fitted = [beta[0] + math.fsum(b * x for b, x in zip(beta[1:], zi)) for zi in z]
        residuals = sorted(y - f for y, f in zip(ys, fitted))
        residual_quantiles = [fp.quantile(residuals, q) for q in pr.QUANTILE_LEVELS]
        names = self.names(target)
        parameters = {"features": names, "kept": [names[j] for j in kept], "dropped": [names[j] for j in dropped], "means": [clean(m) for m in means],
                      "standard_deviations": [clean(s) for s in sds], "intercept": clean(beta[0]), "coefficients": [clean(b) for b in beta[1:]],
                      "residual_quantiles": [clean(q) for q in residual_quantiles], "lambda": pr.RIDGE_LAMBDA, "rows": len(rows)}
        context = {"train": train, "target": target, "means": means, "sds": sds, "kept": kept, "beta": beta, "residual_quantiles": residual_quantiles}
        return FittedModel(parameters, context=context, diagnostics={"rows": len(rows), "training_rows_without_an_earlier_event": len(excluded),
                                                                     "left_out_event_ids": excluded, "dropped_features": [names[j] for j in dropped]})

    def predict(self, model, view):
        c = model.context
        z = standardized(self.raw(view, c["train"], c["target"]), c["means"], c["sds"], c["kept"])
        mean = c["beta"][0] + math.fsum(b * x for b, x in zip(c["beta"][1:], z))
        return tuple(mean + q for q in c["residual_quantiles"])


def binary_predictors(caps=None):
    """C1 to C4 and the two M2 variants. `caps` maps a predictor id to its looser-threshold probabilities, for the nested threshold's monotone repair."""
    caps = caps or {}
    return [PooledRate(), timing_rate(), sector_group_rate(), IssuerHistoryRate(), Logistic(True, caps.get("M2_logistic")), Logistic(False, caps.get("M2_without_sector"))]


def regression_predictors():
    return [PooledQuantiles(), timing_quantiles(), sector_group_quantiles(), Ridge(True), Ridge(False)]
