"""Shared builders for the Milestone 2 tests: synthetic accepted events over the real 2026 session calendar."""
import copy

from nre import fingerprints as fp
from nre.calendar import Calendar
from nre.core import timestamp

CAL = Calendar()
POLICY, POLICY_SHA = fp.load_policy()
SESSIONS = [d for d in CAL.days if "2026-02-02" <= d <= "2026-03-27"]
LATE = timestamp("2026-06-01T00:00:00Z")  # after every label of every synthetic event has matured


def event(n, session=None, timing="after_hours", sic="7372", cluster=None, values=None, absent=()):
    """An accepted-event stand-in: its own issuer and cluster, deterministic label values, and a reaction session from the calendar."""
    session = session or SESSIONS[n]
    anchor = CAL.offset(session, -1)
    labels = {}
    for name in fp.LABELS:
        if name in absent:
            labels[name] = {"value": None, "reason": "TEST_ABSENT"}
        elif fp.label_kind(name) == "boolean":
            labels[name] = {"value": n % 2 == 0, "reason": None}
        else:
            labels[name] = {"value": round(0.01 * (n + 1), 6), "reason": None}
    for name, value in (values or {}).items():
        labels[name] = {"value": value, "reason": None}
    when = (anchor + "T21:30:00Z", anchor + "T21:35:00Z") if timing == "after_hours" else (session + "T11:00:00Z", session + "T11:05:00Z")
    return fp.make_event(CAL, "e%d" % n, cluster or "c%d" % n, "T%d" % n, "%010d" % (1000 + n), timing, when[0], when[1], session,
                         fp.sector_from_sic(sic), labels)


def policy_with(**changes):
    """A validated copy of the repository policy; keys are dotted paths such as 'analogues.min_members'."""
    policy = copy.deepcopy(POLICY)
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        node = policy
        for key in parents:
            node = node[key]
        node[leaf] = value
    fp.validate_policy(policy)
    return policy


def inputs_for(events, policy=None):
    return {"events": sorted(events, key=fp.event_order), "policy": policy or POLICY, "policy_sha256": "0" * 64, "sectors": {},
            "sector_map_sha256": "0" * 64, "sector_read_on": "2026-09-26", "calendar": CAL}


def poisoned(events):
    """The same events with every existing label value replaced by junk; which labels exist is left alone."""
    changed = copy.deepcopy(events)
    for e in changed:
        for name, label in e["labels"].items():
            if label["value"] is not None:
                label["value"] = (not label["value"]) if isinstance(label["value"], bool) else 999.0
    return changed
