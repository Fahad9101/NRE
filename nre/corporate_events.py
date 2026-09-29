"""Milestone 3, Phase A: classifies SEC Form 8-K Item numbers into the structured event taxonomy
docs/NRE-1.0-MASTER-PROMPT.md section 6 names (Earnings / General Corporate Events / Capital
Markets Events). Deterministic and auditable, not NLP/ML -- an 8-K's own Item number already
tells you its regulatory category; no text needs reading or scoring to get this far.

Every title, and the item-number set itself, is sourced from SEC's own Exchange Act Form 8-K
Compliance & Disclosure Interpretations (sec.gov/rules-regulations/staff-guidance/compliance-
disclosure-interpretations/exchange-act-form-8-k, read 2026-09-29), with Item 5.08's own title
("Shareholder Director Nominations") independently confirmed against a real 8-K cover page
(accession 0001193125-25-245196) since that C&DI page carries no interpretation for it. No
category/subtype invented beyond what section 6's own taxonomy names -- an item number not in
ITEM_TAXONOMY classifies as unclassified, never guessed.

Item 2.02 (Results of Operations and Financial Condition) is the earnings item; its category and
subtype match nre.event_acquire.EVENT_CATEGORY/EVENT_SUBTYPE exactly, since it is the same event
this project's own M1/M2 pipeline already keys everything on.
"""
from .core import DataError

# category is one of "earnings", "general_corporate", "capital_markets", or "administrative" (9.01
# only -- an exhibit-attachment marker, not itself an event). subtype is this module's own, more
# specific grouping within a category; it is not an SEC-defined term.
ITEM_TAXONOMY = {
    "1.01": {"title": "Entry into a Material Definitive Agreement", "category": "general_corporate", "subtype": "material_agreement"},
    "1.02": {"title": "Termination of a Material Definitive Agreement", "category": "general_corporate", "subtype": "material_agreement"},
    "1.03": {"title": "Bankruptcy or Receivership", "category": "general_corporate", "subtype": "bankruptcy_or_restructuring"},
    "1.04": {"title": "Mine Safety – Reporting of Shutdowns and Patterns of Violations", "category": "general_corporate", "subtype": "regulatory_disclosure"},
    "1.05": {"title": "Material Cybersecurity Incidents", "category": "general_corporate", "subtype": "cybersecurity_incident"},
    "2.01": {"title": "Completion of Acquisition or Disposition of Assets", "category": "general_corporate", "subtype": "acquisition_or_divestiture"},
    "2.02": {"title": "Results of Operations and Financial Condition", "category": "earnings", "subtype": "results"},
    "2.03": {"title": "Creation of a Direct Financial Obligation under an Off-Balance Sheet Arrangement of a Registrant", "category": "capital_markets", "subtype": "debt_or_financial_obligation"},
    "2.04": {"title": "Triggering Events That Accelerate or Increase a Direct Financial Obligation or an Obligation under an Off-Balance Sheet Arrangement", "category": "capital_markets", "subtype": "debt_or_financial_obligation"},
    "2.05": {"title": "Costs Associated with Exit or Disposal Activities", "category": "general_corporate", "subtype": "restructuring"},
    "2.06": {"title": "Material Impairments", "category": "general_corporate", "subtype": "impairment"},
    "3.01": {"title": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing", "category": "general_corporate", "subtype": "listing_status"},
    "3.02": {"title": "Unregistered Sales of Equity Securities", "category": "capital_markets", "subtype": "equity_issuance"},
    "3.03": {"title": "Material Modification to Rights of Security Holders", "category": "capital_markets", "subtype": "security_holder_rights"},
    "4.01": {"title": "Changes in Registrant's Certifying Accountant", "category": "general_corporate", "subtype": "accountant_change"},
    "4.02": {"title": "Non-Reliance on Previously Issued Financial Statements or a Related Audit Report or Completed Interim Review", "category": "general_corporate", "subtype": "financial_restatement"},
    "5.01": {"title": "Changes in Control of Registrant", "category": "general_corporate", "subtype": "control_change"},
    "5.02": {"title": "Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; Compensatory Arrangements of Certain Officers", "category": "general_corporate", "subtype": "officer_or_director_change"},
    "5.03": {"title": "Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year", "category": "general_corporate", "subtype": "governance_amendment"},
    "5.04": {"title": "Temporary Suspension of Trading Under Registrant's Employee Benefit Plans", "category": "general_corporate", "subtype": "benefit_plan_suspension"},
    "5.05": {"title": "Amendments to the Registrant's Code of Ethics, or Waiver of a Provision of the Code of Ethics", "category": "general_corporate", "subtype": "governance_amendment"},
    "5.06": {"title": "Change in Shell Company Status", "category": "general_corporate", "subtype": "shell_company_status"},
    "5.07": {"title": "Submission of Matters to a Vote of Security Holders", "category": "general_corporate", "subtype": "shareholder_vote"},
    "5.08": {"title": "Shareholder Director Nominations", "category": "general_corporate", "subtype": "shareholder_vote"},
    "6.01": {"title": "ABS Informational and Computational Material", "category": "capital_markets", "subtype": "asset_backed_securities"},
    "6.02": {"title": "Change of Servicer or Trustee", "category": "capital_markets", "subtype": "asset_backed_securities"},
    "6.03": {"title": "Change in Credit Enhancement or Other External Support", "category": "capital_markets", "subtype": "asset_backed_securities"},
    "6.04": {"title": "Failure to Make a Required Distribution", "category": "capital_markets", "subtype": "asset_backed_securities"},
    "6.05": {"title": "Securities Act Updating Disclosure", "category": "capital_markets", "subtype": "asset_backed_securities"},
    "7.01": {"title": "Regulation FD Disclosure", "category": "general_corporate", "subtype": "reg_fd_disclosure"},
    "8.01": {"title": "Other Events", "category": "general_corporate", "subtype": "other"},
    "9.01": {"title": "Financial Statements and Exhibits", "category": "administrative", "subtype": "exhibits_only"},
}
CATEGORIES = ("earnings", "general_corporate", "capital_markets", "administrative")


def classify_item(item):
    """The official title, category and subtype for one 8-K item number, or None if this table
    doesn't cover it -- never guessed. `item` must already be a real item-number string such as
    the ones nre.ingestion.sec_candidates() extracts (e.g. "2.02"), not free text."""
    if not isinstance(item, str) or item not in ITEM_TAXONOMY:
        return None
    return dict(ITEM_TAXONOMY[item])


def classify_filing(items):
    """Every item's own classification for one filing's real Item list, in the given order. A
    filing commonly carries several genuinely distinct items (e.g. an earnings release alongside a
    dividend declaration); each classifies independently rather than collapsing into one label, the
    same discipline docs/SAME-DAY-COMPETING-CATALYST-POLICY.md already applies by hand. An item
    number this table doesn't cover classifies as {"category": "unclassified", ...}, not fabricated."""
    if not isinstance(items, list) or not items:
        raise DataError("items must be a non-empty list")
    rows = []
    for item in items:
        found = classify_item(item)
        rows.append({"item": item, **(found or {"title": None, "category": "unclassified", "subtype": None})})
    return rows
