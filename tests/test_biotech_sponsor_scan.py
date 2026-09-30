import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nre import cli
from nre.biotech_sponsor_scan import scan_all, scan_issuer, sponsor_matches
from nre.core import DataError, canonical, digest
from nre.ingestion import SourceUnavailable


class FakeClient:
    """Mirrors tests/test_depth_cohort.py's own FakeClient exactly: url -> (body_bytes, metadata),
    no network."""
    def __init__(self, documents=None, errors=None):
        self.documents, self.errors, self.calls = documents or {}, errors or {}, []

    def fetch(self, url, output):
        self.calls.append(url)
        if url in self.errors:
            raise self.errors[url]
        if url not in self.documents:
            raise AssertionError("unexpected fetch: " + url)
        body = canonical(self.documents[url])
        return body, {"url": url, "sha256": digest(body), "size": len(body),
                     "retrieved_at": "2026-09-30T12:00:00Z", "raw_file": digest(body) + ".raw"}


NEUROCRINE_CT_URL = 'https://clinicaltrials.gov/api/v2/studies?query.spons=Neurocrine+Biosciences&pageSize=20'
# Real, trimmed 2026-09-30: one genuine Neurocrine-sponsored study, one that only matched the
# broad query.spons search on a shared "Bioscience(s)" token (a real Yale University trial).
NEUROCRINE_CT_DOCUMENT = {
    "studies": [
        {"protocolSection": {
            "identificationModule": {"nctId": "NCT06911112", "briefTitle": "NBI-1065845-MDD3025"},
            "statusModule": {"overallStatus": "RECRUITING"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Neurocrine Biosciences"}},
            "designModule": {"phases": ["PHASE3"]},
        }},
        {"protocolSection": {
            "identificationModule": {"nctId": "NCT05207085", "briefTitle": "Valbenazine for Trichotillomania"},
            "statusModule": {"overallStatus": "COMPLETED"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Yale University"}},
            "designModule": {"phases": ["PHASE2"]},
        }},
    ]
}
NEUROCRINE_FDA_URL = 'https://api.fda.gov/drug/drugsfda.json?search=sponsor_name%3ANEUROCRINE%2A&limit=20'
NEUROCRINE_FDA_DOCUMENT = {"results": [
    {"application_number": "NDA209241", "sponsor_name": "NEUROCRINE", "products": [{"brand_name": "INGREZZA"}],
     "submissions": [{"submission_type": "ORIG", "submission_number": "1", "submission_status": "AP",
                      "submission_status_date": "20170411"}]},
]}
LNSR_CT_URL = 'https://clinicaltrials.gov/api/v2/studies?query.spons=LENSAR&pageSize=20'
LNSR_CT_DOCUMENT = {"studies": [
    {"protocolSection": {
        "identificationModule": {"nctId": "NCT01014702", "briefTitle": "Prospective Clinical Trial of the LensAR Laser System"},
        "statusModule": {"overallStatus": "COMPLETED"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "LensAR Incorporated"}},
        "designModule": {},
    }},
]}

NBIX_ENTRY = {"ticker": "NBIX", "cik": "0000914475", "sic": "2836", "legal_name": "NEUROCRINE BIOSCIENCES INC",
              "clinical_trials_sponsor_query": "Neurocrine Biosciences", "fda_sponsor_prefix": "NEUROCRINE",
              "providers": ["clinical_trials", "fda_drugs"]}
LNSR_ENTRY = {"ticker": "LNSR", "cik": "0001320350", "sic": "3841", "legal_name": "LENSAR, Inc.",
              "clinical_trials_sponsor_query": "LENSAR", "fda_sponsor_prefix": None,
              "providers": ["clinical_trials"], "note": "Medical device, not a drug company."}


class SponsorMatchesTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(sponsor_matches("Neurocrine Biosciences", "Neurocrine Biosciences"))

    def test_real_suffix_and_case_variant_still_matches(self):
        # Real: ClinicalTrials.gov's own leadSponsor.name for LENSAR's trials is "LensAR
        # Incorporated", not "LENSAR" -- must still count as the same company.
        self.assertTrue(sponsor_matches("LensAR Incorporated", "LENSAR"))

    def test_real_unrelated_collaborator_does_not_match(self):
        self.assertFalse(sponsor_matches("Yale University", "Neurocrine Biosciences"))

    def test_none_or_empty_does_not_match(self):
        self.assertFalse(sponsor_matches(None, "Neurocrine Biosciences"))
        self.assertFalse(sponsor_matches("", "Neurocrine Biosciences"))


class ScanIssuerTests(unittest.TestCase):
    def test_drug_company_scans_both_providers_and_tags_matches(self):
        client = FakeClient({NEUROCRINE_CT_URL: NEUROCRINE_CT_DOCUMENT, NEUROCRINE_FDA_URL: NEUROCRINE_FDA_DOCUMENT})
        result = scan_issuer(client, NBIX_ENTRY, "/tmp/out")
        self.assertEqual(result["clinical_trials"]["result_count"], 2)
        self.assertEqual(result["clinical_trials"]["matched_count"], 1)
        self.assertTrue(result["clinical_trials"]["studies"][0]["lead_sponsor_match"])
        self.assertFalse(result["clinical_trials"]["studies"][1]["lead_sponsor_match"])
        self.assertEqual(result["clinical_trials"]["studies"][0]["classification"]["status_category"], "ongoing")
        self.assertEqual(result["fda_drugs"]["result_count"], 1)
        self.assertEqual(result["fda_drugs"]["matched_count"], 1)
        self.assertEqual(result["fda_drugs"]["applications"][0]["classification"]["pathway"], "new_drug_application")

    def test_device_company_skips_fda_drugs_search_entirely(self):
        client = FakeClient({LNSR_CT_URL: LNSR_CT_DOCUMENT})
        result = scan_issuer(client, LNSR_ENTRY, "/tmp/out")
        self.assertEqual(result["fda_drugs"], {"applicable": False, "reason": "Medical device, not a drug company."})
        self.assertEqual(result["clinical_trials"]["matched_count"], 1)
        # No FDA URL was ever called for a device-only issuer.
        self.assertTrue(all("clinicaltrials.gov" in u for u in client.calls))

    def test_missing_required_field_rejected(self):
        with self.assertRaises(DataError):
            scan_issuer(FakeClient(), {"ticker": "NBIX"}, "/tmp/out")


class ScanAllTests(unittest.TestCase):
    def test_scans_every_issuer_in_order(self):
        client = FakeClient({NEUROCRINE_CT_URL: NEUROCRINE_CT_DOCUMENT, NEUROCRINE_FDA_URL: NEUROCRINE_FDA_DOCUMENT,
                             LNSR_CT_URL: LNSR_CT_DOCUMENT})
        result = scan_all(client, {"issuers": [NBIX_ENTRY, LNSR_ENTRY]}, "/tmp/out")
        self.assertEqual([i["ticker"] for i in result["issuers"]], ["NBIX", "LNSR"])

    def test_missing_issuers_list_rejected(self):
        with self.assertRaises(DataError):
            scan_all(FakeClient(), {}, "/tmp/out")


class RealCommittedConfigTests(unittest.TestCase):
    """Structural checks against the real, committed config/m3-biotech-sponsor-map.json -- no
    network. Mirrors tests/test_corporate_events.py's own RealDataTests discipline: the project's
    own real data must actually satisfy what the code requires, not just the fixtures."""
    def setUp(self):
        self.spec = json.loads(Path("config/m3-biotech-sponsor-map.json").read_text(encoding="utf-8"))

    def test_exactly_six_issuers_with_required_fields(self):
        issuers = self.spec["issuers"]
        self.assertEqual(len(issuers), 6)
        for entry in issuers:
            for key in ("ticker", "cik", "sic", "legal_name", "clinical_trials_sponsor_query", "providers"):
                self.assertIn(key, entry)
            self.assertTrue(entry["cik"].isdigit())
            self.assertEqual(len(entry["cik"]), 10)

    def test_every_fda_drugs_provider_has_a_real_sponsor_prefix(self):
        for entry in self.spec["issuers"]:
            if "fda_drugs" in entry["providers"]:
                self.assertIsInstance(entry["fda_sponsor_prefix"], str)
                self.assertTrue(entry["fda_sponsor_prefix"])

    def test_device_only_issuer_has_no_fda_drugs_provider(self):
        lnsr = next(e for e in self.spec["issuers"] if e["ticker"] == "LNSR")
        self.assertNotIn("fda_drugs", lnsr["providers"])
        self.assertIsNone(lnsr["fda_sponsor_prefix"])


class CliBiotechSponsorScanTests(unittest.TestCase):
    def test_two_issuer_spec_classified_through_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "spec.json"
            spec_path.write_text(json.dumps({"issuers": [NBIX_ENTRY, LNSR_ENTRY]}), encoding="utf-8")
            client = FakeClient({NEUROCRINE_CT_URL: NEUROCRINE_CT_DOCUMENT, NEUROCRINE_FDA_URL: NEUROCRINE_FDA_DOCUMENT,
                                 LNSR_CT_URL: LNSR_CT_DOCUMENT})
            with patch("nre.ingestion.PublicClient", return_value=client), patch("builtins.print") as output:
                code = cli.main(["biotech-sponsor-scan", "--spec", str(spec_path), "--output", tmp])
                self.assertEqual(code, 0)
                summary = json.loads(output.call_args_list[0].args[0])
                self.assertEqual(summary["issuer_count"], 2)
                self.assertEqual(summary["clinical_trials_matched_total"], 2)
                self.assertEqual(summary["fda_drugs_matched_total"], 1)
                saved = json.loads((Path(tmp) / "biotech-sponsor-scan.json").read_text(encoding="utf-8"))
                self.assertEqual(len(saved["issuers"]), 2)


if __name__ == "__main__":
    unittest.main()
