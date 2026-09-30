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
submission_type has exactly two (ORIG, SUPPL).

submission_class_code's own real enum is far larger and more fragmented (27 distinct values,
confirmed exhaustive via the same live count aggregation), including combination codes like
"TYPE 1/4" (a submission that is simultaneously Type 1 and Type 4). Each real submission carries
its own submission_class_code_description field -- unlike decision_code in
nre.device_clearances' own 510(k) taxonomy, no separate glossary lookup was needed; each of the 24
values below was read directly from that field on real records. Three real values (489+ real
occurrences combined) have no description on any sampled record (checked up to 50 samples each) --
UNKNOWN, BIOSIMILAR, TYPE 10- BLA -- and are deliberately left OUT of SUBMISSION_CLASS_CODE rather
than guessed, even though "BIOSIMILAR" reads as self-evident English: this module's own discipline
throughout has been to classify only from verified real data, never a plausible-looking guess.
"""
from .core import DataError

SUBMISSION_STATUS = {"AP": "approved", "TA": "tentative_approval"}
SUBMISSION_TYPE = {"ORIG": "original_application", "SUPPL": "supplement"}
# Every value read directly from real submissions' own submission_class_code_description field
# (api.fda.gov/drug/drugsfda.json?search=submissions.submission_class_code:"<code>"), 2026-09-30.
SUBMISSION_CLASS_CODE = {
    "LABELING": "labeling", "MANUF (CMC)": "manufacturing_cmc", "EFFICACY": "efficacy",
    "TYPE 1": "new_molecular_entity", "TYPE 2": "new_active_ingredient", "TYPE 3": "new_dosage_form",
    "TYPE 4": "new_combination", "TYPE 5": "new_formulation_or_new_manufacturer",
    "TYPE 6": "new_indication_no_longer_used", "TYPE 7": "already_marketed_without_approved_nda",
    "TYPE 8": "partial_rx_to_otc_switch", "TYPE 9": "new_indication_distinct_nda_consolidated",
    "TYPE 9- BLA": "new_indication_distinct_bla_consolidated",
    "TYPE 10": "new_indication_distinct_nda_not_consolidated",
    "REMS": "rems", "N/A": "not_applicable", "BIOEQUIV": "bioequivalence", "S": "supplement",
    "MEDGAS": "medical_gas",
    "TYPE 1/4": "new_molecular_entity_and_new_combination",
    "TYPE 3/4": "new_dosage_form_and_new_combination",
    "TYPE 2/3": "new_active_ingredient_and_new_dosage_form",
    "TYPE 2/4": "new_active_ingredient_and_new_combination",
    "TYPE 4/5": "new_combination_and_new_formulation_or_manufacturer",
}
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
    "submissions" list nre.ingestion.drugsfda_application()'s own return shape carries): status,
    type, and submission_class_code, each read from openFDA's own real enums."""
    if not isinstance(submission, dict):
        raise DataError("submission must be a dict")
    status, sub_type = submission.get("submission_status"), submission.get("submission_type")
    class_code = submission.get("submission_class_code")
    return {"submission_number": submission.get("submission_number"),
            "submission_type": sub_type, "submission_type_category": SUBMISSION_TYPE.get(sub_type, "unclassified"),
            "submission_class_code": class_code,
            "submission_class_code_category": SUBMISSION_CLASS_CODE.get(class_code, "unclassified"),
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
