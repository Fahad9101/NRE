"""The metrics, intervals and decision rule of the frozen Milestone 4 protocol, as pure functions of predictions and outcomes.

Nothing here knows about events, folds or data files, so nothing here can leak: it is handed predictions and outcomes and computes what the protocol says
to compute from them. Every random draw is random.random() on a seeded generator, whose stream does not change between the Python versions the repository
supports (randrange, shuffle and sample have changed between versions, so they are not used).

Where the protocol is silent on a detail these functions must settle, the choice does not depend on any outcome and is stated in the function's docstring:
ties in a ranking are broken by the events' keys, ascending.
"""
import math
import random

from . import fingerprints as fp
from . import m4_protocol as pr

DISTINGUISHABLE_BETTER, DISTINGUISHABLE_WORSE = "DISTINGUISHABLE_BETTER", "DISTINGUISHABLE_WORSE"
NOT_DISTINGUISHABLE, INSUFFICIENT_DATA, REPORTED = "NOT_DISTINGUISHABLE", "INSUFFICIENT_DATA", "REPORTED"
EVALUABLE = "EVALUABLE"


def mean(values):
    return math.fsum(values) / len(values)


def _flag(outcome):
    return 1.0 if outcome else 0.0


def brier(probabilities, outcomes):
    """Mean of (p - y)^2."""
    return mean([(p - _flag(y)) ** 2 for p, y in zip(probabilities, outcomes)])


def event_brier(p, outcome):
    return (p - _flag(outcome)) ** 2


def log_loss(probabilities, outcomes):
    """Mean negative log-likelihood, probabilities clipped to [1e-6, 1 - 1e-6]."""
    low, high = pr.LOG_LOSS_CLIP, 1 - pr.LOG_LOSS_CLIP
    return mean([-math.log(min(max(p, low), high)) if y else -math.log(1 - min(max(p, low), high)) for p, y in zip(probabilities, outcomes)])


def ranked(scores, keys):
    """Indices from the highest score to the lowest; equal scores are ordered by key, ascending."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], keys[i]))


def average_precision(scores, outcomes):
    """Average precision: the sum over distinct score thresholds of (recall gained) x (precision at that threshold). Tied scores share a threshold, so
    no tie-break enters it. Needs at least one positive."""
    positives = sum(1 for y in outcomes if y)
    if positives == 0:
        raise ValueError("average precision needs a positive")
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    true_pos = false_pos = 0
    previous_recall = total = 0.0
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and scores[order[j]] == scores[order[i]]:
            j += 1
        for index in order[i:j]:
            if outcomes[index]:
                true_pos += 1
            else:
                false_pos += 1
        recall = true_pos / positives
        total += (recall - previous_recall) * true_pos / (true_pos + false_pos)
        previous_recall = recall
        i = j
    return total


def precision_at_k(scores, outcomes, keys, k):
    """The share of positives among the k highest scores (equal scores ordered by key, ascending)."""
    return sum(1 for i in ranked(scores, keys)[:k] if outcomes[i]) / k


def random_precision_at_k(outcomes, keys, k, seed, rankings=pr.RANDOM_RANKINGS):
    """Precision at k of `rankings` seeded random rankings of the same events: the mean and the 2.5th to 97.5th percentile range."""
    order = sorted(range(len(outcomes)), key=lambda i: keys[i])
    rng = random.Random(seed)
    values = []
    for _ in range(rankings):
        draws = {i: rng.random() for i in order}
        top = sorted(order, key=lambda i: (draws[i], keys[i]))[:k]
        values.append(sum(1 for i in top if outcomes[i]) / k)
    values.sort()
    return {"mean": mean(values), "low": fp.quantile(values, 0.025), "high": fp.quantile(values, 0.975), "rankings": rankings, "seed": seed}


def reliability(scores, outcomes, keys):
    """Equal-frequency bins on the predictions, min(4, floor(n / 10)) of them, each with n, mean prediction, observed rate and its Wilson interval.

    The events are ordered by (score, key), ascending, and cut into bins of n // bins events, the first n % bins bins taking one more.
    """
    n = len(scores)
    bins = min(pr.MAX_RELIABILITY_BINS, n // pr.MIN_PER_BIN)
    if bins < 1:
        return {"state": INSUFFICIENT_DATA, "reason": "%d predictions, fewer than the %d one bin needs" % (n, pr.MIN_PER_BIN)}
    order = sorted(range(n), key=lambda i: (scores[i], keys[i]))
    size, extra = divmod(n, bins)
    out, start = [], 0
    for b in range(bins):
        members = order[start:start + size + (1 if b < extra else 0)]
        start += len(members)
        k = sum(1 for i in members if outcomes[i])
        low, high = fp.wilson(k, len(members), pr.REPORTING_LEVEL)
        out.append({"bin": b + 1, "n": len(members), "mean_prediction": mean([scores[i] for i in members]), "observed_rate": k / len(members),
                    "wilson_low": low, "wilson_high": high})
    return {"state": REPORTED, "bins": out}


def confusion(scores, outcomes, thresholds):
    """Counts, FPR and FNR when an event is called positive if its score is at least its own threshold (the fold's training base rate)."""
    tp = fn = tn = fp_ = 0
    for score, outcome, threshold in zip(scores, outcomes, thresholds):
        called = score >= threshold
        if outcome:
            tp, fn = tp + called, fn + (not called)
        else:
            fp_, tn = fp_ + called, tn + (not called)
    return {"true_positives": tp, "false_negatives": fn, "false_positives": fp_, "true_negatives": tn,
            "false_positive_rate": fp_ / (fp_ + tn) if fp_ + tn else None, "false_negative_rate": fn / (fn + tp) if fn + tp else None}


def tercile_means(scores, values, keys):
    """The mean of `values` (None when absent for an event) in each tercile of the score, lowest first, with counts (descriptive).

    The events are ordered by (score, key), ascending, and cut into n // 3 each, the first n % 3 terciles taking one more.
    """
    n = len(scores)
    if n < pr.TERCILES:
        return {"state": INSUFFICIENT_DATA, "reason": "%d predictions, fewer than %d" % (n, pr.TERCILES)}
    order = sorted(range(n), key=lambda i: (scores[i], keys[i]))
    size, extra = divmod(n, pr.TERCILES)
    out, start = [], 0
    for t in range(pr.TERCILES):
        members = order[start:start + size + (1 if t < extra else 0)]
        start += len(members)
        known = [values[i] for i in members if values[i] is not None]
        out.append({"tercile": t + 1, "events": len(members), "events_with_a_return": len(known), "mean_return": mean(known) if known else None})
    return {"state": REPORTED, "terciles": out}


def pinball(outcome, forecast, level):
    error = outcome - forecast
    return max(level * error, (level - 1) * error)


def event_pinball(outcome, forecasts):
    """The pinball loss of one event's 10th, 50th and 90th percentile forecasts, averaged over the three levels."""
    return math.fsum(pinball(outcome, f, q) for f, q in zip(forecasts, pr.QUANTILE_LEVELS)) / len(pr.QUANTILE_LEVELS)


def regression_metrics(outcomes, forecasts):
    """Mean pinball loss over the three levels (and by level), the coverage of the 10th-90th interval and the MAE of the median forecast."""
    by_level = [mean([pinball(y, f[j], q) for y, f in zip(outcomes, forecasts)]) for j, q in enumerate(pr.QUANTILE_LEVELS)]
    return {"mean_pinball_loss": mean(by_level), "pinball_loss_by_level": {"%g" % q: v for q, v in zip(pr.QUANTILE_LEVELS, by_level)},
            "interval_coverage": mean([1.0 if f[0] <= y <= f[-1] else 0.0 for y, f in zip(outcomes, forecasts)]),
            "mae_of_the_median": mean([abs(y - f[1]) for y, f in zip(outcomes, forecasts)])}


def cluster_bootstrap(differences, clusters, seed, replicates=pr.BOOTSTRAP_REPLICATES, levels=(pr.REPORTING_LEVEL, pr.CLAIM_LEVEL)):
    """Percentile bootstrap of the mean of per-event differences, resampling whole clusters with replacement; the predictions behind the differences are fixed."""
    ids = sorted(set(clusters))
    index = {c: i for i, c in enumerate(ids)}
    sums, sizes = [0.0] * len(ids), [0] * len(ids)
    for difference, cluster in zip(differences, clusters):
        sums[index[cluster]] += difference
        sizes[index[cluster]] += 1
    rng = random.Random(seed)
    m = len(ids)
    replicate_means = []
    for _ in range(replicates):
        total, count = 0.0, 0
        for _ in range(m):
            j = int(rng.random() * m)
            total, count = total + sums[j], count + sizes[j]
        replicate_means.append(total / count)
    replicate_means.sort()
    intervals = {}
    for level in levels:
        tail = (1 - level) / 2
        intervals["%g" % level] = [fp.quantile(replicate_means, tail), fp.quantile(replicate_means, 1 - tail)]
    return {"estimate": mean(differences), "events": len(differences), "clusters": m, "replicates": replicates, "seed": seed, "intervals": intervals}


def headline(by_clustering):
    """At each level, the wider of the two clusterings' intervals (the first listed on a tie): {"0.95": {"clustering", "low", "high"}, ...}."""
    out = {}
    for level in next(iter(by_clustering.values()))["intervals"]:
        best = None
        for name in pr.BOOTSTRAP_CLUSTERINGS:
            low, high = by_clustering[name]["intervals"][level]
            if best is None or high - low > best["high"] - best["low"]:
                best = {"clustering": name, "low": low, "high": high}
        out[level] = best
    return out


def contrast(differences, clusters_by_name, seeds):
    """The bootstrap of per-event differences (model minus comparator; lower is better) under each clustering, and the headline intervals."""
    by_clustering = {name: cluster_bootstrap(differences, clusters_by_name[name], seeds[name]) for name in pr.BOOTSTRAP_CLUSTERINGS}
    return {"estimate": mean(differences), "by_clustering": by_clustering, "headline": headline(by_clustering)}


def decide(clean_window, all_event):
    """The protocol's status for one primary target.

    clean_window: {"state": EVALUABLE or not, "claim_interval": [low, high]}; all_event: {"estimate": the all-event contrast's point estimate or None}.
    DISTINGUISHABLE_BETTER needs the clean-window 99% interval entirely below 0 and the all-event estimate below 0 (WORSE: both above); INSUFFICIENT_DATA
    when the clean-window thresholds were not met; NOT_DISTINGUISHABLE otherwise. None of these is a claim of a tradable edge.
    """
    if clean_window["state"] != EVALUABLE:
        return INSUFFICIENT_DATA
    low, high = clean_window["claim_interval"]
    estimate = all_event.get("estimate")
    if high < 0 and estimate is not None and estimate < 0:
        return DISTINGUISHABLE_BETTER
    if low > 0 and estimate is not None and estimate > 0:
        return DISTINGUISHABLE_WORSE
    return NOT_DISTINGUISHABLE
