"""The frozen Milestone 4 protocol, and the check that nothing it pins has changed.

Every run of the harness starts here: it recomputes the protocol's canonical sha256 and the hash of every input the protocol pins, and refuses to go on if
any of them differs from the recorded value (config/m4-protocol.json, required_leakage_and_integrity_tests). It also checks that the numbers the code
uses are the numbers the protocol states. Nothing here fits or scores anything.
"""
import json
import re
from pathlib import Path

from . import caveat_sensitivity as cs
from . import fingerprints as fp
from . import m4_scoping_evidence as ev
from .core import DataError, canonical, digest

ROOT = fp.ROOT
PROTOCOL_PATH = ROOT / "config" / "m4-protocol.json"
FREEZE_PATH = ROOT / "reports" / "m4-protocol-freeze-2026-10-06.json"
PINNED_FILES = ("events_spec", "calendar", "fingerprint_policy", "sector_map", "scoping_evidence", "caveat_check")

# The numbers the frozen protocol states in prose, as the code uses them. constant_readings() finds each in the protocol's own words, so that changing a
# constant here without a new protocol version (or the protocol without the code) fails the integrity check.
MIN_POSITIVES = MIN_NEGATIVES = 10
MIN_TRAIN_EVENTS = 40
MIN_REGRESSION_TEST_EVENTS = 20
PRECISION_K_FOLD, PRECISION_K_POOLED = (5, 10), (10, 20)
MAX_RELIABILITY_BINS, MIN_PER_BIN = 4, 10
LOG_LOSS_CLIP = 1e-6
BOOTSTRAP_REPLICATES = 5000
RANDOM_RANKINGS = 1000
REPORTING_LEVEL, CLAIM_LEVEL = 0.95, 0.99
QUANTILE_LEVELS = (0.1, 0.5, 0.9)
CELL_MINIMUM = 10  # C2 and C3: a cell with fewer defined training events falls back to the pooled value
RATE_CLIP = (0.01, 0.99)
GROUP_PRIOR_MINIMUM, GROUP_PRIOR_DEFAULT = 10, 0.5
PRIOR_STRENGTH = 10
RIDGE_LAMBDA = 1.0  # the penalty of M2 and M3, on standardized features, the intercept not penalized
NEWTON_TOLERANCE, NEWTON_MAX_ITERATIONS = 1e-8, 100
TERCILES = 3
BOOTSTRAP_CLUSTERINGS = ("reaction_session", "issuer")
SEED_KEYS = {"bootstrap_reaction_session": "reaction_session", "bootstrap_issuer": "issuer"}
SEED_RANDOM_RANKING = "random_ranking"
_ENOUGH = r"fewer than (\d+) positives or fewer than (\d+) negatives"


def constant_readings():
    """(name, path in the protocol, pattern, the numbers the pattern must find there) for each constant above, with the code's current values."""
    return (
        ("minimum positives and negatives, target level", ("insufficient_data", "target_level", "rule"), _ENOUGH, (MIN_POSITIVES, MIN_NEGATIVES)),
        ("minimum positives and negatives, fold level", ("insufficient_data", "fold_level", "rule"), _ENOUGH, (MIN_POSITIVES, MIN_NEGATIVES)),
        ("minimum positives and negatives, pooled test", ("insufficient_data", "pooled_test_level", "rule"), _ENOUGH, (MIN_POSITIVES, MIN_NEGATIVES)),
        ("minimum positives and negatives, holdout", ("insufficient_data", "holdout_level", "rule"), _ENOUGH, (MIN_POSITIVES, MIN_NEGATIVES)),
        ("regression minimums", ("insufficient_data", "regression_level", "rule"), r"fewer than (\d+) training events .*fewer than (\d+) test events",
         (MIN_TRAIN_EVENTS, MIN_REGRESSION_TEST_EVENTS)),
        ("training events to fit", ("blocks_and_folds", "minimum_training_events_to_fit"), r"(\d+)", (MIN_TRAIN_EVENTS,)),
        ("precision at K", ("metrics", "binary_secondary", "precision_at_k"),
         r"per development fold for K = (\d+) and K = (\d+), and pooled for K = (\d+) and K = (\d+)", PRECISION_K_FOLD + PRECISION_K_POOLED),
        ("reliability bins", ("metrics", "binary_secondary", "reliability"), r"min\((\d+), floor\(n / (\d+)\)\)", (MAX_RELIABILITY_BINS, MIN_PER_BIN)),
        ("reliability minimum per bin", ("insufficient_data", "metric_level", "reliability"), r"at least (\d+) predictions per bin", (MIN_PER_BIN,)),
        ("PR-AUC minimum", ("insufficient_data", "metric_level", "pr_auc"), r"at least (\d+) pooled positives", (MIN_POSITIVES,)),
        ("log-loss clip", ("metrics", "binary_secondary", "log_loss"), r"\[(\S+), 1 - (\S+)\]", (LOG_LOSS_CLIP, LOG_LOSS_CLIP)),
        ("bootstrap replicates", ("intervals", "headline_interval_for_the_primary_contrast", "method"), r"(\d+) replicates", (BOOTSTRAP_REPLICATES,)),
        ("random rankings", ("intervals", "random_ranking"), r"(\d+) seeded random rankings", (RANDOM_RANKINGS,)),
        ("quantile levels", ("predictors", "regression_target", "C1_pooled_quantiles"), r"the (\d+)th, (\d+)th and (\d+)th percentiles",
         tuple(round(100 * q) for q in QUANTILE_LEVELS)),
        ("C2 cell minimum", ("predictors", "binary_targets", "C2_timing_rate"), r"fewer than (\d+) defined training events", (CELL_MINIMUM,)),
        ("C3 cell minimum", ("predictors", "binary_targets", "C3_sector_group_rate"), r"fewer than (\d+) defined training events", (CELL_MINIMUM,)),
        ("issuer rate clip", ("features", "B_and_C0", "issuer_history_rate", "used_in_the_model_as"), r"clipped to \[(\S+), (\S+)\]", RATE_CLIP),
        ("group prior minimum", ("features", "B_and_C0", "issuer_history_rate", "group_prior_p"), r"at least (\d+) of them", (GROUP_PRIOR_MINIMUM,)),
        ("group prior default", ("features", "B_and_C0", "issuer_history_rate", "group_prior_p"), r"p = (\d\.\d+)", (GROUP_PRIOR_DEFAULT,)),
        ("prior strength", ("features", "B_and_C0", "issuer_history_rate", "formula"), r"m = (\d+)", (PRIOR_STRENGTH,)),
        ("logistic penalty", ("predictors", "binary_targets", "M2_logistic", "objective"), r"lambda = (\d+)", (RIDGE_LAMBDA,)),
        ("ridge penalty", ("predictors", "regression_target", "M3_ridge_linear", "fit"), r"lambda = (\d+)", (RIDGE_LAMBDA,)),
        ("Newton convergence", ("predictors", "binary_targets", "M2_logistic", "solver"), r"below (\S+), at most (\d+) iterations",
         (NEWTON_TOLERANCE, NEWTON_MAX_ITERATIONS)),
    )


class ProtocolMismatch(DataError):
    """The protocol, its freeze record or an input it pins no longer matches its recorded hash: the harness must not run."""


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def protocol_sha256(protocol):
    return digest(canonical(protocol))


def file_digest(path):
    return digest(canonical(load_json(path)))


def _at(protocol, path):
    node = protocol
    for key in path:
        node = node[key]
    return node


def constants_check(protocol, policy=None):
    """The constants whose code value is not what the protocol states, as readable strings (empty when they all agree)."""
    wrong = []
    for name, path, pattern, expected in constant_readings():
        try:
            node = _at(protocol, path)
            found = re.search(pattern, node if isinstance(node, str) else str(node), re.DOTALL)
            got = tuple(float(g) for g in found.groups()) if found else None
        except (KeyError, TypeError, ValueError):
            got = None
        if got != tuple(float(x) for x in expected):
            wrong.append("%s: the protocol states %s, the code uses %s" % (name, got, expected))
    levels = protocol["intervals"]["headline_interval_for_the_primary_contrast"]["levels"]
    if (levels["reporting"], levels["claims"]) != (REPORTING_LEVEL, CLAIM_LEVEL):
        wrong.append("interval levels: the protocol states %s, the code uses %s" % ((levels["reporting"], levels["claims"]), (REPORTING_LEVEL, CLAIM_LEVEL)))
    if tuple(protocol["intervals"]["headline_interval_for_the_primary_contrast"]["clusterings"]) != BOOTSTRAP_CLUSTERINGS:
        wrong.append("bootstrap clusterings differ from the protocol's")
    seeds = protocol["seeds"]
    if not all(isinstance(seeds.get(k), int) for k in (*SEED_KEYS, SEED_RANDOM_RANKING)):
        wrong.append("the protocol's seeds are not all integers")
    if policy is not None and (policy["pooling"]["prior_strength"], policy["wilson_confidence"]) != (PRIOR_STRENGTH, REPORTING_LEVEL):
        wrong.append("the fingerprint policy's prior strength and Wilson confidence differ from the protocol's")
    return wrong


def _checker():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
    return checks, check


def verify_protocol(protocol, freeze, policy=None):
    """The protocol against its freeze record, and the code's constants against the protocol's words. Needs no event."""
    checks, check = _checker()
    actual, recorded = protocol_sha256(protocol), freeze["protocol"]["canonical_sha256"]
    check("protocol_hash", actual == recorded, "computed %s, recorded %s" % (actual, recorded))
    check("protocol_version", protocol["protocol_version"] == freeze["protocol"]["protocol_version"],
          "protocol %s, freeze record %s" % (protocol["protocol_version"], freeze["protocol"]["protocol_version"]))
    check("freeze_record_pins_the_protocol_inputs", freeze["inputs_pinned"] == protocol["inputs"])
    derived_map = protocol["caveats"]["derived_labels"]
    check("derived_labels_map", {k: list(v) for k, v in cs.DERIVED.items()} == {k: list(v) for k, v in derived_map.items()},
          "the code's derivation map must be the protocol's")
    wrong = constants_check(protocol, policy)
    check("constants_match_the_protocol_text", not wrong, "; ".join(wrong))
    return checks


def verify_inputs(protocol, inputs, spec, root=ROOT):
    """Every input the protocol pins against its pinned hash."""
    checks, check = _checker()
    pins = protocol["inputs"]
    for key in PINNED_FILES:
        try:
            got = file_digest(Path(root) / pins[key]["path"])
        except (OSError, ValueError) as exc:
            check("pinned_file:" + key, False, "unreadable: %s" % exc)
            continue
        check("pinned_file:" + key, got == pins[key]["canonical_sha256"], pins[key]["path"])
    events = inputs["events"]
    check("event_table", fp.provenance(inputs, "m4_harness")["inputs"]["event_table_sha256"] == pins["event_table_sha256"])
    check("event_labels", digest(canonical({e["event_id"]: e["labels_sha256"] for e in events})) == pins["event_labels_sha256"])
    blocks = ev.assign_blocks(events)
    check("block_assignment", digest(canonical(blocks)) == pins["block_assignment_sha256"])
    sizes = [sum(1 for b in blocks.values() if b == n) for n in range(1, max(blocks.values()) + 1)]
    check("block_sizes", sizes == protocol["blocks_and_folds"]["expected_blocks"]["sizes"], str(sizes))
    recorded_pairs, derived_pairs = cs.caveated_pairs(spec), cs.caveated_pairs(spec, with_derived=True)
    pinned = pins["caveated_labels"]
    check("caveated_labels_as_recorded", digest(canonical({k: sorted(v) for k, v in sorted(recorded_pairs.items())})) == pinned["as_recorded_sha256"])
    check("caveated_labels_with_derived", digest(canonical({k: sorted(v) for k, v in sorted(derived_pairs.items())})) == pinned["with_derived_labels_sha256"])
    check("events_with_caveats", len(derived_pairs) == pinned["events_with_caveats"])
    return checks


def verify(protocol, freeze, inputs, spec, root=ROOT):
    """Every integrity check as {"check", "ok", "detail"}. Nothing is raised, so a report can list every failure at once."""
    return verify_protocol(protocol, freeze, inputs.get("policy")) + verify_inputs(protocol, inputs, spec, root)


def require_verified(checks):
    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise ProtocolMismatch("refusing to run; failed integrity checks: " + "; ".join("%s (%s)" % (c["check"], c["detail"]) for c in failed))
    return checks
