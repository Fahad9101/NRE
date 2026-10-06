"""Synthetic events for the Milestone 4 harness tests: five blocks over the real 2026 session calendar, with labels from a seeded generator.

The shape follows the real data (five blocks more than 28 days apart, the last the holdout; a dozen issuers in several SIC divisions; a few events sharing a
reaction session; some caveats) so that the harness's folds, thresholds and leakage checks are exercised the way they are on the real events.
"""
import copy
import random

from nre import fingerprints as fp
from nre.calendar import Calendar

CAL = Calendar()
BLOCK_RANGES = (("2026-01-05", "2026-01-23"), ("2026-02-23", "2026-03-13"), ("2026-04-14", "2026-05-01"), ("2026-06-02", "2026-06-18"), ("2026-07-21", "2026-08-07"))
SIZES = (14, 30, 22, 24, 20)
SICS = ("2834", "7372", "1311", "4813", "5065", "5812", "3674", "8742", "2836", "7370", "4911", "5411")


def labels_for(rng):
    """Sixteen labels that agree with one another the way the dataset engine's do."""
    opened = rng.gauss(0.012, 0.05)
    high = max(opened, 0) + abs(rng.gauss(0.01, 0.03))
    low = min(opened, 0) - abs(rng.gauss(0.01, 0.03))
    close = low + (high - low) * rng.random()
    labels = {"day1_open_return": opened, "day1_high_return": high, "day1_low_return": low, "day1_close_return": close}
    walk = close
    for n in fp.HORIZONS:
        walk += rng.gauss(0, 0.03)
        labels["session_%d_close_return" % n] = walk
    for t in fp.GAP_THRESHOLDS:
        labels["gap_ge_%dpct" % t] = opened >= t / 100
    positive = opened >= 0.005
    labels["positive_gap_retained_half"] = close >= opened / 2 if positive else None
    labels["positive_gap_filled"] = low <= 0 if positive else None
    out = {}
    for name in fp.LABELS:
        value = labels[name]
        out[name] = {"value": None if value is None else (round(value, 6) if not isinstance(value, bool) else value),
                     "reason": "NOT_POSITIVE_GAP_GE_0_5PCT" if value is None else None}
    return out


def build_event(n, session, timing, cik, sic, cluster, labels):
    anchor = CAL.offset(session, -1)
    when = (anchor + "T21:30:00Z", anchor + "T21:35:00Z") if timing == "after_hours" else (session + "T11:00:00Z", session + "T11:05:00Z")
    return fp.make_event(CAL, "s%03d" % n, cluster, "T%02d" % int(cik[-2:]), cik, timing, when[0], when[1], session, fp.sector_from_sic(sic), labels,
                         labels_sha256="%064x" % n)


def dataset(seed=7, sizes=SIZES, shared_sessions=True):
    """(events, spec): events in blocks 1..5 and a spec naming some caveats. Reproducible from the seed."""
    rng = random.Random(seed)
    events, number = [], 0
    for (first, last), size in zip(BLOCK_RANGES, sizes):
        days = [s for s in CAL.days if first <= s <= last]
        for i in range(size):
            session = days[(i * len(days)) // size] if not (shared_sessions and i % 9 == 8) else events[-1]["reaction_session"]
            issuer = rng.randrange(12)
            cluster = "c%03d" % number
            if shared_sessions and i % 9 == 8:
                cluster = events[-1]["cluster_id"]  # a second release in the same cluster, on the same session
            events.append(build_event(number, session, rng.choice(("after_hours", "premarket")), "%010d" % (1000 + issuer), SICS[issuer], cluster, labels_for(rng)))
            number += 1
    spec = {"events": [{"event_id": e["event_id"], "recorded_result": {}} for e in events]}
    for i, entry in enumerate(spec["events"]):
        if i % 6 == 0:
            entry["caveats"] = [{"labels": ["day1_open_return"], "note": "synthetic"}]
        elif i % 17 == 0:
            entry["caveats"] = [{"labels": ["all"], "note": "synthetic"}]
        elif i % 11 == 0:
            entry["caveats"] = [{"labels": ["session_5_close_return"], "note": "synthetic"}]
    return events, spec


def with_labels_changed(events, change):
    """A deep copy of the events in which change(event) has altered the labels of the events it chooses."""
    out = copy.deepcopy(events)
    for event in out:
        change(event)
    return out
