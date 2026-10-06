"""The features the frozen Milestone 4 protocol allows, computed so that no outcome from the future or from the test block can reach them.

Only the pieces whose correctness is a leakage question live here: the release timing and sector indicators, and the issuer-history rate with its group
prior. Standardization, the design matrices and the models that use them are not part of this module.

An event's history is the fold's TRAINING events that reacted on an earlier session and whose labels for the target were already available at the event's
cutoff. The group prior is built from the same events, so every number a feature uses was knowable when the event's cutoff passed.
"""
from . import m4_protocol as pr
from .m4_data import ProtocolGap

FEATURE_VERSION = "m4-features-v1"
OTHER_DIVISIONS = ("B", "E", "F", "G")


def sector_group(event):
    """D (manufacturing), I (services) or other (divisions B, E, F and G). A division the protocol does not name is a gap, not a guess."""
    division = event["sic_division"]
    if division in ("D", "I"):
        return division
    if division in OTHER_DIVISIONS:
        return "other"
    raise ProtocolGap("event %s has SIC division %s, which the protocol's sector grouping does not name (D, I, or B, E, F, G)" % (event["event_id"], division))


def indicators(event):
    """after_hours, is_I and is_other (D is the reference)."""
    group = sector_group(event)
    return {"after_hours": 1 if event["release_timing"] == "after_hours" else 0, "is_I": 1 if group == "I" else 0, "is_other": 1 if group == "other" else 0}


def history(event, train_events, target):
    """The training events an `event` may learn from: those that reacted on an earlier session and whose `target` labels were available at its cutoff."""
    return [e for e in train_events
            if e["event_id"] != event["event_id"] and e["reaction_session"] < event["reaction_session"]
            and all(e["available_at"][name] <= event["cutoff"] for name in target.source_labels)]


def _defined(events, target):
    pairs = [(e, target.function(e["labels"])) for e in events]
    return [(e, v) for e, v in pairs if v is not None]


def _group(event, defined):
    """The same-SIC-major-group members of `defined` when there are enough of them, else all of it; and which one was used."""
    members = [(e, v) for e, v in defined if e["sic_major_group"] == event["sic_major_group"]]
    if len(members) >= pr.GROUP_PRIOR_MINIMUM:
        return members, "sic_major_group"
    return defined, "all_earlier_events"


def issuer_history_rate(event, train_events, target, prior_strength=pr.PRIOR_STRENGTH):
    """(k + m p) / (n + m): the issuer's own earlier outcomes on a binary target, shrunk toward the group prior p (0.5 if there is no earlier event)."""
    defined = _defined(history(event, train_events, target), target)
    own = [v for e, v in defined if e["cik"] == event["cik"]]
    k, n = sum(1 for v in own if v), len(own)
    if defined:
        pool, source = _group(event, defined)
        prior = sum(1 for _, v in pool if v) / len(pool)
    else:
        pool, source, prior = [], "none_available", pr.GROUP_PRIOR_DEFAULT
    return {"rate": (k + prior_strength * prior) / (n + prior_strength), "k": k, "n": n, "prior": prior, "prior_source": source, "prior_n": len(pool),
            "history_event_ids": sorted(e["event_id"] for e, _ in defined)}


def issuer_history_mean(event, train_events, target, prior_strength=pr.PRIOR_STRENGTH):
    """The regression analogue: (sum of y + m mu) / (n + m), mu the group (else pooled) mean of y, used as is.

    With no earlier event at all the protocol gives no mu (the binary rate has the default 0.5), so this raises rather than choose one.
    """
    defined = _defined(history(event, train_events, target), target)
    if not defined:
        raise ProtocolGap("event %s has no earlier training event with %s defined, and the protocol gives the regression history mean no default for that"
                          % (event["event_id"], target.id))
    own = [v for e, v in defined if e["cik"] == event["cik"]]
    pool, source = _group(event, defined)
    mu = sum(v for _, v in pool) / len(pool)
    return {"mean": (sum(own) + prior_strength * mu) / (len(own) + prior_strength), "n": len(own), "prior": mu, "prior_source": source, "prior_n": len(pool),
            "history_event_ids": sorted(e["event_id"] for e, _ in defined)}
