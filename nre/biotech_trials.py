"""Milestone 3 Phase C: classifies ClinicalTrials.gov study status/phase into structured,
auditable categories matching docs/NRE-1.0-MASTER-PROMPT.md section 6's Biotechnology/
Pharmaceuticals taxonomy (trial phase, regulatory status, discontinuations) and section 29's
biotech-specific handling. Deterministic, not NLP/ML -- ClinicalTrials.gov's own status/phase enums
already carry this information; no free text needs reading to get this far, the same discipline
nre.corporate_events already applies to SEC 8-K items.

Every enum value is sourced from ClinicalTrials.gov's own live field-values statistics endpoint
(clinicaltrials.gov/api/v2/stats/field/values?fields=OverallStatus,Phase), read directly 2026-09-30 --
not guessed from memory. All 14 real overallStatus values and all 6 real phase values are covered;
an unrecognized value (a future addition to their own schema) classifies as unclassified, never
guessed, matching nre.corporate_events.classify_item()'s own handling of an unknown SEC item.

Clinical success is not scored as economic significance here or anywhere in this module (master
prompt section 6: "Clinical success must not automatically be scored as economically
transformational... Separate scientific success from economic significance."). Whether a completed
trial's own primary endpoint was actually met needs that trial's separate results data, which this
module does not fetch or interpret -- COMPLETED means only that the study finished enrolling and
following its participants, nothing about the outcome.
"""
from .core import DataError

# category is one of CATEGORIES. note explains a real ambiguity the bare status doesn't resolve --
# in particular, COMPLETED says nothing about whether the trial's own primary endpoint was met.
STATUS_TAXONOMY = {
    "COMPLETED": {"category": "completed",
                  "note": "Finished; whether the primary endpoint was met needs the trial's own separate results data, not this status alone."},
    "TERMINATED": {"category": "discontinued", "note": "Stopped early after already starting."},
    "WITHDRAWN": {"category": "discontinued", "note": "Stopped before enrolling any participant."},
    "SUSPENDED": {"category": "discontinued", "note": "Halted; not necessarily permanently."},
    "RECRUITING": {"category": "ongoing", "note": None},
    "NOT_YET_RECRUITING": {"category": "ongoing", "note": None},
    "ACTIVE_NOT_RECRUITING": {"category": "ongoing", "note": None},
    "ENROLLING_BY_INVITATION": {"category": "ongoing", "note": None},
    "APPROVED_FOR_MARKETING": {"category": "regulatory_milestone", "note": "The intervention itself reached market."},
    "UNKNOWN": {"category": "administrative",
                "note": "Status not verified within ClinicalTrials.gov's own required window -- a reporting gap, not a scientific or regulatory outcome."},
    "WITHHELD": {"category": "administrative", "note": None},
    "NO_LONGER_AVAILABLE": {"category": "administrative", "note": None},
    "AVAILABLE": {"category": "administrative", "note": None},
    "TEMPORARILY_NOT_AVAILABLE": {"category": "administrative", "note": None},
}
PHASES = frozenset({"NA", "EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4"})
CATEGORIES = ("completed", "discontinued", "ongoing", "regulatory_milestone", "administrative", "unclassified")


def classify_status(overall_status):
    """The structured category for one real ClinicalTrials.gov overallStatus value. None if this
    table doesn't cover it -- never guessed (their own schema could add a new value later)."""
    entry = STATUS_TAXONOMY.get(overall_status)
    return dict(entry, status=overall_status) if entry else None


def classify_phases(phases):
    """Every phase value validated against ClinicalTrials.gov's own real enum; raises rather than
    silently accepting one this table doesn't recognize."""
    if not isinstance(phases, list):
        raise DataError("phases must be a list")
    unknown = [p for p in phases if p not in PHASES]
    if unknown:
        raise DataError("unrecognized phase value(s): %s" % unknown)
    return list(phases)


def classify_study(protocol):
    """A structured event record from one real study's own protocolSection
    (nre.ingestion.clinical_trials_study()'s own return shape): identity, phase(s), status category,
    condition(s), and sponsor -- the parts of section 6's Biotechnology/Pharmaceuticals taxonomy a
    study record's own structured fields already carry, without reading any free text."""
    if not isinstance(protocol, dict):
        raise DataError("protocol must be a dict")
    identification = protocol.get("identificationModule") or {}
    nct_id = identification.get("nctId")
    if not isinstance(nct_id, str) or not nct_id:
        raise DataError("protocol missing its own nctId")
    status = (protocol.get("statusModule") or {}).get("overallStatus")
    status_row = classify_status(status)
    phases = classify_phases((protocol.get("designModule") or {}).get("phases") or [])
    conditions = (protocol.get("conditionsModule") or {}).get("conditions")
    sponsor = ((protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name")
    return {"nct_id": nct_id, "brief_title": identification.get("briefTitle"),
            "status": status, "status_category": status_row["category"] if status_row else "unclassified",
            "status_note": status_row["note"] if status_row else None,
            "phases": phases, "conditions": list(conditions) if isinstance(conditions, list) else [],
            "sponsor": sponsor}
