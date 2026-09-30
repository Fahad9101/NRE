"""Milestone 3: catalyst-strength features, scoped to Phase A + Phase B only per the owner's own
2026-09-30 decision (docs/M3-CATALYST-STRENGTH-SCOPE.md section 2's own open question). Combines
Phase A's already-computed corporate-event classification (nre.corporate_events.classify_filing())
with Phase B's already-computed earnings-surprise result (nre.earnings_surprise's own
year_over_year_surprise()/surprise_for_filing()) into one structured feature record per real
earnings event -- never a combined score. Every field here is an individually real, auditable
signal (an SEC item's own category, a real computed surprise percentage and its sign); nothing is
synthesized or weighted into anything resembling the master prompt section 13's own eventual
"Catalyst strength: 92/100" model-output display, which is a later, calibrated model's job, not
this phase's (see the scope doc's own section 1 for that distinction).

Pure computation over already-computed inputs -- this module never fetches or classifies anything
itself, the same separation nre.earnings_surprise itself keeps from nre.ingestion's fetch layer.

surprise_magnitude_band (small/medium/large) is deliberately not built here: the scope doc's own
section 3 explains why -- too few real surprise_pct values exist yet (Phase B's live-fetch stays
blocked from GitHub Actions) to set a defensible, data-driven bucket boundary from.
"""
from .core import DataError

SURPRISE_NOT_COMPUTED = "NOT_COMPUTED"  # no earnings_surprise_result was available to combine at all


def catalyst_features(corporate_event_rows, earnings_surprise_result=None):
    """One real earnings event's own catalyst-strength features: its corporate-event category and
    subtype (from the filing's own earnings/item-2.02 row in corporate_event_rows --
    nre.corporate_events.classify_filing()'s own return shape for that filing's real item list),
    any other real item the same filing also carries (never collapsed into the earnings row, the
    same discipline classify_filing() itself already applies), and its earnings-surprise magnitude
    and direction when a real, already-computed surprise result is available.
    earnings_surprise_result is optional: most real events have none yet, since Phase B's live
    fetch is blocked -- that is recorded honestly as SURPRISE_NOT_COMPUTED, never guessed."""
    if not isinstance(corporate_event_rows, list) or not corporate_event_rows:
        raise DataError("corporate_event_rows must be a non-empty list")
    earnings_rows = [row for row in corporate_event_rows if row.get("category") == "earnings"]
    if len(earnings_rows) != 1:
        raise DataError("corporate_event_rows must include exactly one earnings (item 2.02) row")
    primary = earnings_rows[0]
    co_filed_items = [row.get("item") for row in corporate_event_rows if row is not primary]

    surprise_pct = surprise_direction = None
    if earnings_surprise_result is None:
        surprise_state = SURPRISE_NOT_COMPUTED
    else:
        surprise_state = earnings_surprise_result.get("state")
        surprise_pct = earnings_surprise_result.get("surprise_pct")
        if surprise_pct is not None:
            surprise_direction = "positive" if surprise_pct > 0 else "negative" if surprise_pct < 0 else "flat"

    return {"corporate_event_category": primary["category"], "corporate_event_subtype": primary["subtype"],
            "co_filed_items": co_filed_items,
            "earnings_surprise_state": surprise_state, "earnings_surprise_pct": surprise_pct,
            "surprise_direction": surprise_direction}
