"""Standard-library estimators for the frozen Milestone 5 comparison."""
import math
import random
from dataclasses import dataclass
from statistics import mean, median

from .fingerprints import quantile
from .m4_harness import Abstain
from .m4_models import clip_rate, fit_logistic, logit, sigmoid


@dataclass(frozen=True)
class Node:
    value: float
    feature: str = ""
    threshold: float = 0
    left: object = None
    right: object = None

    def __call__(self, row):
        if not self.feature:
            return self.value
        return (self.left if row[self.feature] <= self.threshold else self.right)(row)


def tree(rows, y, depth, minimum, binary=False, rng=None):
    center = mean(y)
    if depth == 0 or len(y) < 2 * minimum:
        return Node(center)
    names = sorted(rows[0])
    if rng is not None:
        names = sorted(rng.sample(names, max(1, math.isqrt(len(names)))))
    # SSE for binary observations is proportional to Gini impurity.
    best_gain, split = 0.0, None
    for name in names:
        order = sorted(range(len(rows)), key=lambda i: rows[i][name])
        values = [rows[i][name] for i in order]
        total = math.fsum(y)
        left = 0.0
        for size, i in enumerate(order[:-1], 1):
            left += y[i]
            if minimum <= size <= len(y) - minimum and values[size - 1] < values[size]:
                gain = size * (left / size - center) ** 2
                gain += (len(y) - size) * ((total - left) / (len(y) - size) - center) ** 2
                if gain > best_gain:
                    best_gain = gain
                    a, b = values[size - 1], values[size]
                    midpoint = a / 2 + b / 2
                    split = name, midpoint if midpoint < b else a, order[:size], order[size:]
    if split is None:
        return Node(center)
    name, threshold, left, right = split
    children = [tree([rows[i] for i in group], [y[i] for i in group], depth - 1, minimum, binary, rng)
                for group in (left, right)]
    return Node(center, name, threshold, *children)


def forest(rows, y, depth, grid, seed):
    rng = random.Random(seed)
    trees = []
    for _ in range(grid["forest_trees"]):
        indices = rng.choices(range(len(rows)), k=len(rows))
        trees.append(tree([rows[i] for i in indices], [y[i] for i in indices],
                          depth, grid["minimum_leaf_events"], rng=rng))
    return lambda row: mean(model(row) for model in trees)


def boosting(rows, y, depth, grid, binary):
    start = logit(clip_rate(mean(y))) if binary else mean(y)
    transform = sigmoid if binary else float
    rate = grid["boosting_learning_rate"]
    scores = [start] * len(y)
    trees = []
    for _ in range(grid["boosting_rounds"]):
        residuals = [actual - transform(score) for actual, score in zip(y, scores)]
        model = tree(rows, residuals, depth, grid["minimum_leaf_events"])
        trees.append(model)
        scores = [score + rate * model(row) for score, row in zip(scores, rows)]

    def predict(row):
        score = start
        for model in trees:
            score += rate * model(row)
        return transform(score)

    return predict


def quantiles(model, rows, y):
    residuals = sorted(actual - model(row) for row, actual in zip(rows, y))
    shifts = tuple(quantile(residuals, q) for q in (0.1, 0.5, 0.9))
    return lambda row: tuple(model(row) + shift for shift in shifts)


def advanced(family, rows, y, depth, grid, binary, seed):
    if family == "single_tree":
        model = tree(rows, y, depth, grid["minimum_leaf_events"], binary)
    elif family == "random_forest":
        model = forest(rows, y, depth, grid, seed)
    elif family == "gradient_boosting":
        model = boosting(rows, y, depth, grid, binary)
    elif family == "equal_weight_ensemble":
        first = forest(rows, y, depth, grid, seed)
        second = boosting(rows, y, depth, grid, binary)
        model = lambda row: (first(row) + second(row)) / 2
    else:
        raise ValueError("Unknown registered model family")
    return model if binary else quantiles(model, rows, y)


def encoder(rows, continuous):
    medians = {}
    for name in continuous:
        values = [row[name] for row in rows if row[name] is not None]
        medians[name] = median(values) if values else 0

    def encode(row):
        encoded = dict(row)
        for name, midpoint in medians.items():
            missing = row[name] is None
            encoded[name] = midpoint if missing else row[name]
            encoded[name + "_missing"] = int(missing)
        return encoded

    return encode


def platt(predictions, outcomes, minimum):
    if min(sum(outcomes), len(outcomes) - sum(outcomes)) < minimum:
        return float, "INSUFFICIENT_DATA"
    try:
        (intercept, slope), _, _ = fit_logistic([[logit(clip_rate(p))] for p in predictions], outcomes)
    except (Abstain, OverflowError, ValueError):
        return float, "MODEL_FIT_FAILED"
    if slope < 0:
        intercept, slope = logit(mean(outcomes)), 0.0
    if not all(map(math.isfinite, (intercept, slope))):
        return float, "MODEL_FIT_FAILED"
    return lambda p: sigmoid(intercept + slope * logit(clip_rate(p))), "CALIBRATED"
