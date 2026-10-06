"""The Milestone 4 harness's data layer: events with the holdout sealed, the two caveat versions, targets, folds and the checks that make a fold sound.

Nothing here fits, predicts or scores. What it does decide is which events a fold may use and what it may know about them, because every leakage rule in
the frozen protocol (config/m4-protocol.json) is a rule about that:

  * the holdout block's labels are never read when the events are loaded: those events are built from the spec alone and carry a SealedLabels, which
    raises on any access. The only way to the labels is HoldoutGate.unseal, which the harness calls only after the access has been logged;
  * a fold's training events are whole blocks, so no reaction session or cluster is split between training and test;
  * every training event's labels have matured before the fold's first test cutoff, asserted for every fold and every target.
"""
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import caveat_sensitivity as cs
from . import event_acquire as ea
from . import fingerprints as fp
from . import m4_protocol as pr
from . import m4_scoping_evidence as ev
from .core import DataError

VERSIONS = ("all_event", "clean_window")
SEALED_REASON = "SEALED_HOLDOUT"  # the reason on the placeholder labels a sealed event is built with; no caller ever sees them
EVALUABLE, INSUFFICIENT_DATA, COUNTS_ONLY = "EVALUABLE", "INSUFFICIENT_DATA", "COUNTS_ONLY"


class HoldoutSealed(DataError):
    """A holdout label was read outside the logged look."""


class HoldoutNotAuthorized(DataError):
    """The holdout look has not been authorized in this version of the harness."""


class MaturityViolation(DataError):
    """A training event's label would not yet have been known at a test event's cutoff."""


class ProtocolGap(DataError):
    """The frozen protocol does not say what to do here, and any choice could move a result: the harness stops instead of choosing."""


class SealedLabels(Mapping):
    """Stands in for a holdout event's labels. Every way of reading it raises; there is nothing behind it to read."""

    def __init__(self, event_id, gate):
        self._event_id, self._gate = event_id, gate

    def _deny(self, what):
        self._gate.denied.append((self._event_id, what))
        raise HoldoutSealed("the labels of holdout event %s are sealed (%s); the only way to them is the logged look" % (self._event_id, what))

    def __getitem__(self, key):
        self._deny("read of " + repr(key))

    def __iter__(self):
        self._deny("iteration")

    def __len__(self):
        self._deny("length")

    def __repr__(self):
        return "<sealed labels of %s>" % self._event_id


class HoldoutGate:
    """Holds what is needed to unseal the holdout events, and counts the attempts to read them any other way."""

    def __init__(self, loader, pairs):
        self._loader, self._pairs = loader, pairs
        self.denied = []  # every refused read: (event_id, what)
        self.unsealed = 0  # how many times labels were actually loaded

    def unseal(self, events, version):
        """The events with their real labels, as `version` sees them. Called only after the access has been logged (Harness.look)."""
        if version not in VERSIONS:
            raise DataError("unknown version " + str(version))
        out = []
        for event in events:
            labels = self._loader(event["event_id"])
            names = self._pairs.get(event["event_id"]) if version == "clean_window" else None
            out.append({**event, "labels": mask_labels(labels, names) if names else labels})
            self.unsealed += 1
        return out


def mask_labels(labels, names):
    """Labels with the named ones absent, as the clean-window version treats a caveated pair (caveat_sensitivity's CAVEAT reason)."""
    return {n: ({"value": None, "reason": cs.CAVEAT_REASON} if n in names else label) for n, label in labels.items()}


def is_sealed(event):
    return isinstance(event["labels"], SealedLabels)


@dataclass(frozen=True)
class Target:
    id: str
    role: str  # primary | descriptive_only | insufficient_data_by_rule
    kind: str  # binary | regression
    clock: str  # B | C0 for the primaries, None otherwise
    source_labels: tuple
    definition: str
    function: Callable  # an event's labels -> True/False (binary) or a float (regression); None when the target is absent for the event


@dataclass(frozen=True)
class Fold:
    name: str
    role: str  # development | holdout
    train_blocks: tuple
    test_block: int


# the labels each target reads; the primaries' own lists are in the protocol and are checked against these
SOURCES = {"gap_ge_%dpct" % t: ("gap_ge_%dpct" % t,) for t in fp.GAP_THRESHOLDS}
SOURCES.update({"day1_high_ge_%dpct" % t: ("day1_high_return",) for t in (10, 20, 30)})
SOURCES.update({"day1_close_ge_%dpct" % t: ("day1_close_return",) for t in (10, 20)})
SOURCES.update({"extension_after_open_ge_%dpct" % t: ("day1_open_return", "day1_high_return") for t in (5, 10)})
SOURCES.update({"session5_close_ge_%dpct" % t: ("session_5_close_return",) for t in (10, 20)})
SOURCES.update({"loses_half_of_gap": ("positive_gap_retained_half",), "full_gap_fill": ("positive_gap_filled",),
                "closes_below_open": ("day1_open_return", "day1_close_return")})


def _label_value(name):
    return lambda labels: labels[name]["value"]


def targets(protocol):
    """Every target the protocol names, by id: the five primaries, the descriptive-only ones and those that are INSUFFICIENT_DATA by rule."""
    functions = {t[0]: t[3] for t in ev.TARGETS}
    groups, out = protocol["targets"], {}
    for item in groups["primary"]:
        function = functions[item["id"]] if item["kind"] == "binary" else _label_value(item["source_labels"][0])
        out[item["id"]] = Target(item["id"], "primary", item["kind"], item["clock"], tuple(item["source_labels"]), item["definition"], function)
    for role in ("descriptive_only", "insufficient_data_by_rule"):
        for item in groups[role]:
            out[item["id"]] = Target(item["id"], role, "binary", None, SOURCES[item["id"]], item["definition"], functions[item["id"]])
    return out


def folds(protocol):
    plan = protocol["blocks_and_folds"]
    out = [Fold("dev_test_block_%d" % f["test_block"], "development", tuple(f["train_blocks"]), f["test_block"]) for f in plan["development_folds"]]
    held = plan["final_holdout_fold"]
    return out + [Fold("holdout_test_block_%d" % held["test_block"], "holdout", tuple(held["train_blocks"]), held["test_block"])]


def split(events, blocks, fold):
    """The fold's training and test events, each in the order of fp.event_order: whole blocks only."""
    train = [e for e in events if blocks[e["event_id"]] in fold.train_blocks]
    test = [e for e in events if blocks[e["event_id"]] == fold.test_block]
    return sorted(train, key=fp.event_order), sorted(test, key=fp.event_order)


def counts(values):
    """Defined, positive and negative events among values that are True, False or None (absent)."""
    defined = [v for v in values if v is not None]
    positives = sum(1 for v in defined if v)
    return {"defined": len(defined), "positives": positives, "negatives": len(defined) - positives}


def enough(c):
    """The protocol's 'at least 10 positives and 10 negatives'."""
    return c["positives"] >= pr.MIN_POSITIVES and c["negatives"] >= pr.MIN_NEGATIVES


def shortfall(c):
    if c["positives"] < pr.MIN_POSITIVES:
        return "%d positives among %d defined events (at least %d needed)" % (c["positives"], c["defined"], pr.MIN_POSITIVES)
    if c["negatives"] < pr.MIN_NEGATIVES:
        return "%d negatives among %d defined events (at least %d needed)" % (c["negatives"], c["defined"], pr.MIN_NEGATIVES)
    return None


def target_values(target, events):
    return [target.function(e["labels"]) for e in events]


def fold_state(target, train_events, train_values):
    """The fold-level rule, on the training events with the target defined in the version being run: {"state", "reason", "train"}."""
    if len(train_events) < pr.MIN_TRAIN_EVENTS:
        return {"state": INSUFFICIENT_DATA, "reason": "%d training events, fewer than the %d needed to fit anything" % (len(train_events), pr.MIN_TRAIN_EVENTS),
                "train": {"defined": sum(v is not None for v in train_values)}}
    if target.kind == "regression":
        n = sum(v is not None for v in train_values)
        reason = None if n >= pr.MIN_TRAIN_EVENTS else "%d training events with the target defined (at least %d needed)" % (n, pr.MIN_TRAIN_EVENTS)
        return {"state": EVALUABLE if reason is None else INSUFFICIENT_DATA, "reason": reason, "train": {"defined": n}}
    c = counts(train_values)
    reason = shortfall(c)
    return {"state": EVALUABLE if reason is None else INSUFFICIENT_DATA, "reason": reason, "train": c}


def pooled_state(target, fitted_test_values):
    """The pooled-development-test rule over the test events of the folds that were not INSUFFICIENT_DATA: {"state", "reason", "test"}."""
    if target.kind == "regression":
        n = sum(v is not None for v in fitted_test_values)
        reason = None if n >= pr.MIN_REGRESSION_TEST_EVENTS else "%d test events with the target defined (at least %d needed)" % (n, pr.MIN_REGRESSION_TEST_EVENTS)
        return {"state": EVALUABLE if reason is None else INSUFFICIENT_DATA, "reason": reason, "test": {"defined": n}}
    c = counts(fitted_test_values)
    reason = shortfall(c)
    return {"state": EVALUABLE if reason is None else INSUFFICIENT_DATA, "reason": reason, "test": c}


def holdout_state(target, test_values):
    """The holdout's own rule: EVALUABLE or COUNTS_ONLY. Needs the holdout's outcomes, so it is applied only inside the logged look."""
    if target.kind == "regression":
        n = sum(v is not None for v in test_values)
        return {"state": EVALUABLE if n >= pr.MIN_REGRESSION_TEST_EVENTS else COUNTS_ONLY, "test": {"defined": n}}
    c = counts(test_values)
    return {"state": EVALUABLE if enough(c) else COUNTS_ONLY, "test": c}


def assert_clusters_whole(train, test, blocks):
    """No reaction session, cluster or block is split between a fold's training and test events."""
    for key, label in (("reaction_session", "reaction session"), ("cluster_id", "cluster")):
        shared = {e[key] for e in train} & {e[key] for e in test}
        if shared:
            raise DataError("%s split between training and test: %s" % (label, ", ".join(sorted(shared))))
    shared = {blocks[e["event_id"]] for e in train} & {blocks[e["event_id"]] for e in test}
    if shared:
        raise DataError("block split between training and test: %s" % sorted(shared))


def assert_label_maturity(train, test, labels, fold_name=""):
    """Every training event's `labels` are available at or before the first test cutoff. Returns the smallest slack, in days."""
    first = min(e["cutoff"] for e in test)
    smallest = None
    for event in train:
        for name in labels:
            slack = (first - event["available_at"][name]).total_seconds() / 86400
            if slack < 0:
                raise MaturityViolation("%s: label %s of training event %s is available %.2f days after the first test cutoff %s"
                                        % (fold_name, name, event["event_id"], -slack, first.isoformat()))
            smallest = slack if smallest is None else min(smallest, slack)
    return smallest


def sources_of(events, root=pr.ROOT):
    """Which of the three accepted-event specs each event came from (the protocol reports every metric by source)."""
    source_of = {}
    for name, rel in ev.SOURCES:
        for entry in json.loads((Path(root) / rel).read_text(encoding="utf-8"))["events"]:
            if "recorded_result" in entry:
                source_of[entry["event_id"]] = name
    if set(source_of) != {e["event_id"] for e in events}:
        raise DataError("every event must come from exactly one source spec")
    return source_of


def _sector(sectors, cik):
    return {k: sectors[cik][k] for k in ("sic", "sic_division", "sic_division_name", "sic_major_group", "sic_description")}


def _event(entry, calendar, sectors, labels):
    window = ea.event_window(entry, calendar)
    security = entry["security"]
    return fp.make_event(calendar, entry["event_id"], entry["cluster_id"], security["ticker"], security["cik"], window["release_timing"],
                         entry["published_at"], entry["cutoff"], window["reaction_session"], _sector(sectors, security["cik"]), labels,
                         entry["source"]["source_id"], entry["source"]["url"], entry["recorded_result"]["labels_sha256"])


def load_inputs(protocol, root=pr.ROOT):
    """What fp.load_inputs returns for the protocol's pinned inputs, except that the holdout block's labels are never read.

    The holdout events are built from the spec alone (identity, timing, sector and the pinned labels digest) and carry a SealedLabels. Their record
    files are opened only by the loader the gate holds, which verifies them against the pinned digest, and only when the harness unseals them.
    """
    root, pins = Path(root), protocol["inputs"]
    calendar = fp.Calendar(spec=pr.load_json(root / pins["calendar"]["path"]))
    spec = pr.load_json(root / pins["events_spec"]["path"])
    scope_note = fp.spec_scope_note(spec)
    sectors, sector_sha, sector_read_on = fp.load_sector_map(root / pins["sector_map"]["path"])
    policy, policy_sha = fp.load_policy(root / pins["fingerprint_policy"]["path"])
    ea.validate_spec(spec, calendar, root)
    entries = [e for e in spec["events"] if "recorded_result" in e]
    for entry in entries:
        if entry["security"]["cik"] not in sectors:
            raise DataError("%s: no SIC entry for CIK %s" % (entry["event_id"], entry["security"]["cik"]))
    blocks = ev.assign_blocks([{"event_id": e["event_id"], "reaction_session": ea.event_window(e, calendar)["reaction_session"]} for e in entries])
    holdout_block = protocol["holdout"]["block"]
    if holdout_block != max(blocks.values()):
        raise DataError("the holdout must be the last block")
    by_id = {e["event_id"]: e for e in entries}

    def load_labels(event_id):
        entry = by_id[event_id]
        record = pr.load_json(root / entry["recorded_result"]["recorded_in"])
        return fp.event_from_record(entry, record, _sector(sectors, entry["security"]["cik"]), calendar)["labels"]

    gate = HoldoutGate(load_labels, cs.caveated_pairs(spec, with_derived=True))
    placeholder = {name: {"value": None, "reason": SEALED_REASON} for name in fp.LABELS}
    events = []
    for entry in entries:
        if blocks[entry["event_id"]] == holdout_block:
            event = _event(entry, calendar, sectors, placeholder)
            event["labels"] = SealedLabels(entry["event_id"], gate)
        else:
            record = pr.load_json(root / entry["recorded_result"]["recorded_in"])
            event = fp.event_from_record(entry, record, _sector(sectors, entry["security"]["cik"]), calendar)
        events.append(event)
    if len({e["event_id"] for e in events}) != len(events):
        raise DataError("duplicate event_id")
    return {"events": sorted(events, key=fp.event_order), "policy": policy, "policy_sha256": policy_sha, "sectors": sectors,
            "sector_map_sha256": sector_sha, "sector_read_on": sector_read_on, "calendar": calendar, "scope_note": scope_note,
            "spec": spec, "blocks": blocks, "gate": gate, "holdout_block": holdout_block}


def seal_events(events, blocks, holdout_block, spec):
    """The sealing load_inputs does, for events that already carry their labels (synthetic ones in the tests). Returns (events, gate)."""
    held = {e["event_id"]: e["labels"] for e in events if blocks[e["event_id"]] == holdout_block}
    gate = HoldoutGate(lambda event_id: held[event_id], cs.caveated_pairs(spec, with_derived=True))
    return [{**e, "labels": SealedLabels(e["event_id"], gate)} if e["event_id"] in held else e for e in events], gate


def versions(inputs):
    """{"all_event": events, "clean_window": events}. In the clean-window version the caveated pairs, derived labels included, are absent.

    The holdout events are shared between the versions: their labels are sealed, and the gate applies the version's mask when it unseals them.
    """
    pairs = cs.caveated_pairs(inputs["spec"], with_derived=True)
    clean = []
    for event in inputs["events"]:
        names = pairs.get(event["event_id"])
        clean.append(event if not names or is_sealed(event) else {**event, "labels": mask_labels(event["labels"], names)})
    return {"all_event": inputs["events"], "clean_window": clean}
