"""Milestone 3 Phase C: classifies openFDA's two medical-device regulatory datasets --
device/510k.json (Premarket Notification) and device/pma.json (Premarket Approval) -- the device
counterpart to nre.fda_approvals, for issuers (like LNSR) whose real SEC SIC code is medical
devices, not drugs, so Drugs@FDA (NDA/ANDA/BLA) does not apply to them at all. Deterministic, not
NLP/ML, same discipline as every other Phase C module: the record's own decision_code/device_class
already carries this information.

Every enum here was checked directly against openFDA's own live count-aggregation endpoint
(api.fda.gov/device/510k.json?count=<field>, .../pma.json?count=<field>), not guessed from memory
or trusted from documentation alone -- a real, load-bearing finding while doing this: openFDA's own
official field-reference PDFs (open.fda.gov/fields/deviceclearance_reference.pdf,
.../devicepma_reference.pdf) are demonstrably STALE relative to the live API for several fields.
PMA's own supplement_type is the clearest case -- the PDF documents values like "Subpart B" and
"PMA supplement (180 days)" that do not appear anywhere in live data at all; the real, live values
("30-Day Notice", "Real-Time Process", "Panel Track", etc.) are a completely different vocabulary,
so supplement_type is deliberately NOT translated through a table here, just passed through as the
already-readable raw string ClinicalTrials.gov-style clearance_type/supplement_type fields already
are elsewhere in this project.

decision_code is trickier and split evidence-by-evidence:
- 510(k): of the 11 real live decision_code values, 10 have a verified real description, either
  from the record's own decision_description field directly (SN, ST, PT, SI) or from openFDA's own
  PDF (SESE, SESK, SEKD, SESD, SESP, SESU). DENG (489 real records) has neither -- its own
  decision_description field is literally the string "Unknown" in every sampled record, and it is
  absent from the PDF too -- so it is deliberately left OUT of DECISION_CODE_510K and classifies as
  "unclassified", the same as an unrecognized value anywhere else in this project. Never guessed.
- PMA: of the 6 real live decision_code values, APPR/APRL/APWD/APCV match the PDF exactly. OK30 (a
  large, real value: 27,889 records) is NOT in the PDF at all, but a direct sample check found it
  co-occurs with supplement_type "30-Day Notice" in every record checked (and its own count,
  27,889, closely tracks that supplement_type's own count, 27,886) -- strong real evidence it is
  what the PDF calls "LE30" under a different, more current code string, recorded here as an
  observation, not an asserted official FDA definition. APCB (11 records) is also undocumented; a
  direct sample check found real ao_statement text beginning "Approval for..." in most records
  (all real companion-diagnostic devices) -- classified as approved on that direct evidence, with
  the specific meaning of "CB" left unstated since it was not found in any primary source checked.
"""
from .core import DataError

# category is one of ("cleared", "approved", "post_approval_action", "withdrawn", "unclassified").
# note cites the real source: openFDA's own decision_description field, or its own reference PDF.
DECISION_CODE_510K = {
    "SESE": {"category": "cleared", "note": "Substantially Equivalent"},
    "SN": {"category": "cleared", "note": "Substantially Equivalent for Some Indications"},
    "SESK": {"category": "cleared", "note": "Substantially Equivalent - Kit"},
    "SESU": {"category": "cleared", "note": "Substantially Equivalent - With Limitations"},
    "SEKD": {"category": "cleared", "note": "Substantially Equivalent - Kit with Drugs"},
    "ST": {"category": "cleared", "note": "Substantially Equivalent - Subject to Tracking Reg."},
    "SESD": {"category": "cleared", "note": "Substantially Equivalent with Drug"},
    "SESP": {"category": "cleared", "note": "Substantially Equivalent - Postmarket Surveillance Required"},
    "PT": {"category": "cleared", "note": "Substantially Equivalent - Subject to Tracking & PMS"},
    "SI": {"category": "cleared", "note": "Substantially Equivalent - Market after Inspection"},
    # DENG deliberately omitted -- see module docstring.
}
# Real, live-verified exhaustive set (api.fda.gov/device/510k.json?count=clearance_type.exact),
# already human-readable -- passed through raw, not translated, the same as ClinicalTrials.gov's
# own overallStatus string is kept alongside its category in nre.biotech_trials.classify_study().
CLEARANCE_TYPE_510K = frozenset({"Traditional", "Special", "Abbreviated", "Direct", "Post-NSE", "Dual Track"})

DECISION_CODE_PMA = {
    "APPR": {"category": "approved", "note": "Approval: PMA has been approved."},
    "OK30": {"category": "approved",
             "note": "Real evidence (not an official FDA definition): every sampled real record has "
                      "supplement_type '30-Day Notice'; FDA's own reference PDF documents a same-meaning "
                      "code as LE30."},
    "APRL": {"category": "post_approval_action", "note": "Reclassification after approval."},
    "APWD": {"category": "withdrawn", "note": "Withdrawal after approval."},
    "APCV": {"category": "post_approval_action", "note": "Conversion after approval."},
    "APCB": {"category": "approved",
             "note": "Real evidence (not an official FDA definition): sampled real records' own ao_statement "
                      "text begins 'Approval for...'; the specific meaning of 'CB' was not found in any "
                      "primary source checked."},
}
# Shared across both 510(k) and PMA (openFDA's own device_class classification system).
DEVICE_CLASS = {
    "1": "Class I (low to moderate risk): general controls",
    "2": "Class II (moderate to high risk): general controls and special controls",
    "3": "Class III (high risk): general controls and Premarket Approval (PMA)",
    "U": "Unclassified",
    "N": "Not classified",
    "F": "HDE",
}


def classify_510k(record):
    """A structured event record from one real 510(k) clearance
    (nre.ingestion.device_sponsor_search()'s own "510k" pathway return shape): identity, decision
    outcome, and device-class -- the parts this record's own structured fields already carry."""
    if not isinstance(record, dict):
        raise DataError("record must be a dict")
    k_number = record.get("k_number")
    if not isinstance(k_number, str) or not k_number:
        raise DataError("record missing its own k_number")
    decision_code = record.get("decision_code")
    decision_row = DECISION_CODE_510K.get(decision_code)
    device_class = (record.get("openfda") or {}).get("device_class")
    return {"k_number": k_number, "device_name": record.get("device_name"),
            "applicant": record.get("applicant"),
            "decision_code": decision_code,
            "decision_category": decision_row["category"] if decision_row else "unclassified",
            "decision_note": decision_row["note"] if decision_row else None,
            "decision_description": record.get("decision_description"),
            "clearance_type": record.get("clearance_type"),
            "date_received": record.get("date_received"), "decision_date": record.get("decision_date"),
            "device_class": device_class, "device_class_description": DEVICE_CLASS.get(device_class)}


def classify_pma(record):
    """A structured event record from one real PMA submission
    (nre.ingestion.device_sponsor_search()'s own "pma" pathway return shape). A PMA's own
    pma_number is not unique by itself -- an approved device accumulates many real supplement
    records over time (e.g. Medtronic's P060039 has supplements S013, S077, ...) -- so
    submission_id combines both, the same discipline this project already applies wherever a
    single field turns out not to be unique per real event."""
    if not isinstance(record, dict):
        raise DataError("record must be a dict")
    pma_number = record.get("pma_number")
    if not isinstance(pma_number, str) or not pma_number:
        raise DataError("record missing its own pma_number")
    supplement_number = record.get("supplement_number")
    decision_code = record.get("decision_code")
    decision_row = DECISION_CODE_PMA.get(decision_code)
    device_class = (record.get("openfda") or {}).get("device_class")
    return {"pma_number": pma_number, "supplement_number": supplement_number,
            "submission_id": pma_number + ("/" + supplement_number if supplement_number else ""),
            "trade_name": record.get("trade_name"), "applicant": record.get("applicant"),
            "decision_code": decision_code,
            "decision_category": decision_row["category"] if decision_row else "unclassified",
            "decision_note": decision_row["note"] if decision_row else None,
            "ao_statement": record.get("ao_statement"), "supplement_type": record.get("supplement_type"),
            "supplement_reason": record.get("supplement_reason"),
            "expedited_review_flag": record.get("expedited_review_flag"),
            "date_received": record.get("date_received"), "decision_date": record.get("decision_date"),
            "device_class": device_class, "device_class_description": DEVICE_CLASS.get(device_class)}
