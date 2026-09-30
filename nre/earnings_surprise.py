"""Milestone 3 Phase B: earnings surprise vs. prior period, computed from SEC's own XBRL
company-concept facts (data.sec.gov/api/xbrl/companyconcept/CIK.../us-gaap/<tag>.json) -- verified
live and free 2026-09-30. Never against consensus estimates: no free, legitimate source for those
exists anywhere this project has checked (docs/M3-NEWS-CATALYST-INTELLIGENCE-SCOPE.md sections 1
and 4), and the owner's own decision was to skip consensus rather than approximate it.

Pure computation over already-fetched facts -- this module never fetches anything itself, the same
separation nre.dataset.build() keeps from nre.event_acquire's own fetch layer. A real 10-Q or 10-K
almost always tags both the current quarter and its own prior-year comparable quarter together (the
standard GAAP comparative-statement presentation), so both halves of a year-over-year surprise are
normally available from one already-known filing with no separate lookup.

Point-in-time correctness (docs/NRE-1.0-MASTER-PROMPT.md section 16): every fact carries its own
`filed` date; `known_by` excludes any fact filed after it, so a later restatement of an earlier
quarter never leaks backward into what "was known" at the time of a given event.

Every function here is tag-generic -- nothing is EPS-specific -- confirmed 2026-09-30 by fetching
JBSS's own real us-gaap:Revenues facts and running the identical functions unchanged
(tests/test_earnings_surprise.py's own RealRevenueDataTests). Revenue surprise therefore needed no
new computation logic, only nre.cli's own already-generic `--tag`/`--unit` args on the
earnings-surprise command. A real, load-bearing finding from that same check: a single real company
can report revenue under several different XBRL tags over its own history (JBSS's own real data
uses RevenueFromContractWithCustomerIncludingAssessedTax, then ...ExcludingAssessedTax, then plain
Revenues, with real overlapping transition periods between each) -- more fragmented than EPS ever
was. "Revenues" is the correct, currently-active tag for any of this project's real 2025-2026
events; a caller reaching further back would need to check which tag was actually in use for that
period rather than assume one tag always applies. Because facts for one call are always already
filtered to a single tag (nre.ingestion.xbrl_company_concept fetches one tag at a time), a tag
transition mid-history surfaces honestly as PRIOR_PERIOD_NOT_FOUND rather than a wrong cross-tag
match -- no special-casing was needed for this.
"""
from datetime import date, timedelta

from .core import DataError

QUARTER_DAYS = (80, 100)  # a single fiscal quarter's own reporting-period length, inclusive
YOY_TOLERANCE_DAYS = 25  # how far a prior-year quarter's own end may drift from exactly 365 days earlier
                         # (a 52/53-week fiscal calendar, like JBSS's own late-June year end, does not
                         # land exactly a year apart) -- well under half a quarter, so it can't match
                         # an adjacent quarter instead.


def _duration_days(fact):
    return (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days


def _is_quarterly(fact):
    return QUARTER_DAYS[0] <= _duration_days(fact) <= QUARTER_DAYS[1]


def _validate_facts(facts):
    if not isinstance(facts, list) or not all(isinstance(f, dict) for f in facts):
        raise DataError("facts must be a list of XBRL fact dicts")
    required = ("start", "end", "val", "accn", "filed", "form")
    for fact in facts:
        if any(key not in fact for key in required):
            raise DataError("each fact needs: " + ", ".join(required))


def quarterly_actual(facts, period_end, known_by):
    """The single-quarter value first disclosed for the period ending `period_end`, using only
    facts filed on or before `known_by`. None if no quarterly fact for that period is known yet by
    then -- never estimated. When more than one filing already reports this period (a later filing
    often repeats a prior comparative quarter), the earliest-filed one is used: what the market
    actually saw first, not a later restatement."""
    _validate_facts(facts)
    candidates = [f for f in facts if f["end"] == period_end and f["filed"] <= known_by and _is_quarterly(f)]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda f: (f["filed"], f["accn"]))
    return {"value": chosen["val"], "accession": chosen["accn"], "filed": chosen["filed"],
            "form": chosen["form"], "start": chosen["start"], "end": chosen["end"]}


def year_over_year_surprise(facts, period_end, known_by):
    """Actual vs. the same fiscal quarter one year earlier -- never vs. consensus, which this
    project has no legitimate source for. The prior quarter's own end date is matched by proximity
    (roughly a year earlier), not an exact calendar date, since fiscal quarters under a 52/53-week
    calendar do not fall exactly 365 days apart. Returns a reason instead of a value, never a guess,
    when either quarter isn't known yet or the prior actual is exactly zero (surprise is undefined)."""
    current = quarterly_actual(facts, period_end, known_by)
    if current is None:
        return {"state": "CURRENT_PERIOD_NOT_YET_KNOWN", "current": None, "prior": None, "surprise_pct": None}
    target = date.fromisoformat(period_end) - timedelta(days=365)
    prior_candidates = [
        f for f in facts
        if f["filed"] <= known_by and _is_quarterly(f)
        and abs((date.fromisoformat(f["end"]) - target).days) <= YOY_TOLERANCE_DAYS
    ]
    if not prior_candidates:
        return {"state": "PRIOR_PERIOD_NOT_FOUND", "current": current, "prior": None, "surprise_pct": None}
    prior_fact = min(prior_candidates, key=lambda f: (abs((date.fromisoformat(f["end"]) - target).days), f["filed"], f["accn"]))
    prior = {"value": prior_fact["val"], "accession": prior_fact["accn"], "filed": prior_fact["filed"],
             "form": prior_fact["form"], "start": prior_fact["start"], "end": prior_fact["end"]}
    if prior["value"] == 0:
        return {"state": "PRIOR_PERIOD_ZERO", "current": current, "prior": prior, "surprise_pct": None}
    surprise = (current["value"] - prior["value"]) / abs(prior["value"]) * 100
    return {"state": "COMPUTED", "current": current, "prior": prior, "surprise_pct": round(surprise, 4)}


def surprise_for_filing(facts, accession):
    """Year-over-year surprise for whichever quarter a specific, already-identified filing (its own
    real SEC accession number -- the 10-Q or 10-K that actually carries the XBRL tag, which is
    usually a companion filing to the earnings 8-K itself, not the 8-K's own accession) reported.
    The period being reported is read from that filing's own facts, never assumed: a filing often
    carries two quarterly facts under one accession (its fresh quarter and the prior-year quarter
    repeated for comparison); the fresh one is whichever ends latest."""
    _validate_facts(facts)
    own_quarterly_facts = [f for f in facts if f["accn"] == accession and _is_quarterly(f)]
    if not own_quarterly_facts:
        return {"state": "NO_QUARTERLY_FACT_IN_THIS_FILING", "current": None, "prior": None, "surprise_pct": None}
    newest = max(own_quarterly_facts, key=lambda f: f["end"])
    return year_over_year_surprise(facts, newest["end"], newest["filed"])
