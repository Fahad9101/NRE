"""Milestone 3: connects Phase C's classifiers (nre.biotech_trials, nre.fda_approvals) to this
project's own 23 accepted issuers, for the subset in drug/medical-device development
(config/m3-biotech-sponsor-map.json). Discovery only -- classifies whatever a real sponsor search
finds, tags each result with whether it actually matches the issuer's own name (a search matches
broadly, sometimes by a shared token with an unrelated sponsor -- verified real examples in
nre.ingestion's own docstrings), and never drops a non-matching result silently, the same
discipline this project already applies to same-day-catalyst caveats: flagged, not excluded."""
import re
from .core import DataError
from .biotech_trials import classify_study
from .fda_approvals import classify_application
from .ingestion import clinical_trials_sponsor_search, drugsfda_sponsor_search

_SUFFIX = re.compile(r"[,.]?\s*(inc|incorporated|corp|corporation|co|ltd|llc)\.?\s*$", re.I)


def _normalize(name):
    return _SUFFIX.sub("", name.strip().lower()).strip() if isinstance(name, str) else ""


def sponsor_matches(candidate_name, query):
    """Whether a search result's own sponsor name plausibly IS the queried company, not just a
    broadly-matched collaborator -- a normalized (case/common-suffix-insensitive) substring check
    either direction, since real registered names vary in casing and suffix (e.g. "LensAR
    Incorporated" for a "LENSAR" query)."""
    a, b = _normalize(candidate_name), _normalize(query)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def scan_issuer(client, entry, output):
    """One issuer's own real discovery scan: every study clinical_trials_sponsor_search() finds,
    classified and tagged with sponsor_matches(); every application drugsfda_sponsor_search()
    finds, the same way, but only when "fda_drugs" is one of the issuer's own listed providers
    (a medical-device issuer like LNSR has no Drugs@FDA presence to search -- recorded as
    inapplicable, not fabricated as an empty drug search)."""
    for key in ("ticker", "cik", "sic", "legal_name", "clinical_trials_sponsor_query", "providers"):
        if key not in entry:
            raise DataError("issuer entry missing its own " + key)
    providers = entry["providers"]
    result = {"ticker": entry["ticker"], "cik": entry["cik"], "sic": entry["sic"],
              "legal_name": entry["legal_name"]}

    protocols, ct_meta = clinical_trials_sponsor_search(client, entry["clinical_trials_sponsor_query"], output)
    trials = []
    for protocol in protocols:
        lead = protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name")
        trials.append({"nct_id": protocol.get("identificationModule", {}).get("nctId"),
                       "lead_sponsor_name": lead,
                       "lead_sponsor_match": sponsor_matches(lead, entry["clinical_trials_sponsor_query"]),
                       "classification": classify_study(protocol)})
    result["clinical_trials"] = {"query": entry["clinical_trials_sponsor_query"], "result_count": len(trials),
                                  "matched_count": sum(1 for t in trials if t["lead_sponsor_match"]),
                                  "studies": trials, "fetch_metadata": ct_meta}

    if "fda_drugs" in providers:
        applications, fda_meta = drugsfda_sponsor_search(client, entry["fda_sponsor_prefix"], output)
        apps = []
        for application in applications:
            name = application.get("sponsor_name")
            apps.append({"application_number": application.get("application_number"), "sponsor_name": name,
                        "sponsor_match": sponsor_matches(name, entry["fda_sponsor_prefix"]),
                        "classification": classify_application(application)})
        result["fda_drugs"] = {"sponsor_prefix": entry["fda_sponsor_prefix"], "result_count": len(apps),
                               "matched_count": sum(1 for a in apps if a["sponsor_match"]),
                               "applications": apps, "fetch_metadata": fda_meta}
    else:
        result["fda_drugs"] = {"applicable": False, "reason": entry.get("note", "not a drug company")}
    return result


def scan_all(client, spec, output):
    """Every issuer in the spec, in order -- one failure fails the whole scan rather than silently
    skipping an issuer (mirrors nre.event_acquire's own all-or-nothing batch discipline)."""
    issuers = spec.get("issuers")
    if not isinstance(issuers, list) or not issuers:
        raise DataError("spec missing its own issuers list")
    return {"schema_version": 1, "issuers": [scan_issuer(client, entry, output) for entry in issuers]}
