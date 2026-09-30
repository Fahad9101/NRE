"""Milestone 3 Phase C: classifies openFDA Drugs@FDA submission records into structured,
auditable regulatory-pathway and approval-status categories matching
docs/NRE-1.0-MASTER-PROMPT.md section 6's Biotechnology/Pharmaceuticals taxonomy (regulatory
status, approval, PDUFA-adjacent milestones) and section 29's biotech-specific handling.
Deterministic, not NLP/ML -- submission_status, submission_type, and an application_number's own
prefix already carry this information, the same discipline nre.corporate_events and
nre.biotech_trials already apply to SEC 8-K items and ClinicalTrials.gov studies.

submission_status and submission_type are both sourced from openFDA's own live count aggregation
(api.fda.gov/drug/drugsfda.json?count=submissions.<field>), read directly 2026-09-30 -- not guessed
from memory: submission_status has exactly two real values across the whole database (AP, TA);
submission_type has exactly two (ORIG, SUPPL). submission_class_code's own real enum is far larger
and more fragmented (27 distinct values, including combination codes like "TYPE 1/4") and is
deliberately NOT classified here yet -- a later, separate pass, the same way
nre.earnings_surprise started with EPS before revenue rather than everything at once.
"""
from .core import DataError

SUBMISSION_STATUS = {"AP": "approved", "TA": "tentative_approval"}
SUBMISSION_TYPE = {"ORIG": "original_application", "SUPPL": "supplement"}
APPLICATION_PREFIXES = (
    ("ANDA", "abbreviated_new_drug_application"),
    ("NDA", "new_drug_application"),
    ("BLA", "biologics_license_application"),
)


def classify_application_number(application_number):
    """The regulatory pathway an application number's own prefix indicates. None if it starts with
    none of the three real prefixes this table covers -- never guessed."""
    if not isinstance(application_number, str):
        raise DataError("application_number must be a string")
    for prefix, pathway in APPLICATION_PREFIXES:
        if application_number.startswith(prefix):
            return {"prefix": prefix, "pathway": pathway}
    return None


def classify_submission(submission):
    """One structured record from a real Drugs@FDA submission entry (a member of the
    "submissions" list nre.ingestion.drugsfda_application()'s own return shape carries): status and
    type, both read from openFDA's own real, small enums -- never the far larger, more fragmented
    submission_class_code, which this module deliberately does not classify yet."""
    if not isinstance(submission, dict):
        raise DataError("submission must be a dict")
    status, sub_type = submission.get("submission_status"), submission.get("submission_type")
    return {"submission_number": submission.get("submission_number"),
            "submission_type": sub_type, "submission_type_category": SUBMISSION_TYPE.get(sub_type, "unclassified"),
            "submission_status": status, "submission_status_category": SUBMISSION_STATUS.get(status, "unclassified"),
            "submission_status_date": submission.get("submission_status_date")}


def classify_application(application):
    """A structured event record from one real Drugs@FDA application
    (nre.ingestion.drugsfda_application()'s own return shape): identity, regulatory pathway, and
    every one of its own submissions classified, in the order openFDA itself returned them (not
    necessarily chronological -- callers needing order should sort on submission_status_date)."""
    if not isinstance(application, dict):
        raise DataError("application must be a dict")
    application_number = application.get("application_number")
    if not isinstance(application_number, str) or not application_number:
        raise DataError("application missing its own application_number")
    pathway = classify_application_number(application_number)
    submissions = application.get("submissions")
    if not isinstance(submissions, list):
        raise DataError("application missing its own submissions list")
    products = application.get("products") or []
    brand_names = sorted({p.get("brand_name") for p in products if isinstance(p, dict) and p.get("brand_name")})
    return {"application_number": application_number,
            "pathway": pathway["pathway"] if pathway else "unclassified",
            "sponsor_name": application.get("sponsor_name"), "brand_names": brand_names,
            "submissions": [classify_submission(s) for s in submissions]}
