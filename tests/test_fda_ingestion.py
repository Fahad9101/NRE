import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nre import cli
from nre.core import DataError, canonical, digest
from nre.ingestion import (
    SourceUnavailable, drugsfda_application, drugsfda_sponsor_search, clinical_trials_sponsor_search,
)


class FakeClient:
    """A fetch() double matching PublicClient's interface: url -> (body_bytes, metadata), no
    network. Mirrors tests/test_depth_cohort.py's own FakeClient exactly."""
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


REAL_CAFCIT_URL = 'https://api.fda.gov/drug/drugsfda.json?search=application_number:%22NDA020793%22&limit=1'
# A trimmed but real response for NDA020793 (CAFCIT, sponsor HIKMA), fetched directly on 2026-09-30
# -- the same application tests/test_fda_approvals.py already classifies.
REAL_CAFCIT_DOCUMENT = {
    "meta": {"results": {"total": 1}},
    "results": [{
        "application_number": "NDA020793", "sponsor_name": "HIKMA",
        "products": [{"brand_name": "CAFCIT"}],
        "submissions": [{"submission_type": "ORIG", "submission_number": "1", "submission_status": "AP",
                         "submission_status_date": "19990921"}],
    }],
}
NOT_FOUND_DOCUMENT = {"error": {"code": "NOT_FOUND", "message": "No matches found!"}}
NOT_FOUND_URL = 'https://api.fda.gov/drug/drugsfda.json?search=application_number:%22NDA999999999%22&limit=1'

# Real, trimmed sponsor-search responses fetched directly on 2026-09-30, used to prove
# clinical_trials_sponsor_search()/drugsfda_sponsor_search()'s own real, verified behavior:
# query.spons matches broadly (collaborators too), and openFDA's sponsor_name is a short registered
# name, not a company's full public name.
REAL_NEUROCRINE_CT_SEARCH_URL = 'https://clinicaltrials.gov/api/v2/studies?query.spons=Neurocrine+Biosciences&pageSize=5'
REAL_NEUROCRINE_CT_SEARCH_DOCUMENT = {
    "studies": [
        {"protocolSection": {"identificationModule": {"nctId": "NCT06911112", "briefTitle": "NBI-1065845-MDD3025"},
                              "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Neurocrine Biosciences"}}}},
        {"protocolSection": {"identificationModule": {"nctId": "NCT05207085", "briefTitle": "Valbenazine for Trichotillomania"},
                              "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Yale University"}}}},
    ]
}
REAL_ASSEMBLY_FDA_SEARCH_URL = 'https://api.fda.gov/drug/drugsfda.json?search=sponsor_name%3AASSEMBLY%2A&limit=20'


class DrugsfdaApplicationTests(unittest.TestCase):
    def test_real_response_shape_parses_cleanly(self):
        client = FakeClient({REAL_CAFCIT_URL: REAL_CAFCIT_DOCUMENT})
        result, meta = drugsfda_application(client, "NDA020793", "/tmp/out")
        self.assertEqual(result["sponsor_name"], "HIKMA")
        self.assertEqual(client.calls, [REAL_CAFCIT_URL])
        self.assertEqual(meta["url"], REAL_CAFCIT_URL)

    def test_openfda_200_error_body_becomes_a_data_error(self):
        # Defensive: if openFDA ever returns 200 with an {"error": {...}} body (not the real 404
        # behavior verified for a not-found search, but a distinct shape this function also guards
        # against), it must not be treated as a successful empty result.
        client = FakeClient({REAL_CAFCIT_URL: NOT_FOUND_DOCUMENT})
        with self.assertRaises(DataError):
            drugsfda_application(client, "NDA020793", "/tmp/out")

    def test_openfda_real_404_not_found_becomes_a_data_error(self):
        # Verified directly against the real API 2026-09-30: a well-formed but nonexistent
        # application_number gets a real HTTP 404 (not a 200), with an {"error": {...}} body.
        client = FakeClient(errors={NOT_FOUND_URL: SourceUnavailable("HTTP_404")})
        with self.assertRaises(DataError):
            drugsfda_application(client, "NDA999999999", "/tmp/out")

    def test_invalid_application_number_format_rejected(self):
        for bad in ("IND012345", "NDA", "020793", "nda020793"):
            with self.assertRaises(DataError):
                drugsfda_application(FakeClient(), bad, "/tmp/out")

    def test_response_application_number_must_match_the_request(self):
        wrong = {"results": [{"application_number": "NDA999999", "submissions": []}]}
        client = FakeClient({REAL_CAFCIT_URL: wrong})
        with self.assertRaises(DataError):
            drugsfda_application(client, "NDA020793", "/tmp/out")


class ClinicalTrialsSponsorSearchTests(unittest.TestCase):
    def test_real_response_shape_returns_every_protocol_unfiltered(self):
        # Broad match by design (collaborators too) -- filtering to the real sponsor is the
        # caller's job, matching what a real check against "Assembly Biosciences" found (an
        # unrelated sponsor matched on the shared "Bioscience(s)" token).
        client = FakeClient({REAL_NEUROCRINE_CT_SEARCH_URL: REAL_NEUROCRINE_CT_SEARCH_DOCUMENT})
        protocols, meta = clinical_trials_sponsor_search(client, "Neurocrine Biosciences", "/tmp/out", page_size=5)
        self.assertEqual(len(protocols), 2)
        self.assertEqual(protocols[0]["identificationModule"]["nctId"], "NCT06911112")
        self.assertEqual(meta["url"], REAL_NEUROCRINE_CT_SEARCH_URL)

    def test_real_zero_result_search_returns_empty_list_not_an_error(self):
        # Verified directly: a genuinely zero-match sponsor search returns HTTP 200 with an empty
        # studies list -- a normal outcome, unlike openFDA's exact/prefix lookup below.
        url = 'https://clinicaltrials.gov/api/v2/studies?query.spons=Zzzznonexistentsponsorxyz123&pageSize=5'
        client = FakeClient({url: {"studies": []}})
        protocols, meta = clinical_trials_sponsor_search(client, "Zzzznonexistentsponsorxyz123", "/tmp/out", page_size=5)
        self.assertEqual(protocols, [])

    def test_empty_sponsor_rejected(self):
        with self.assertRaises(DataError):
            clinical_trials_sponsor_search(FakeClient(), "", "/tmp/out")


class DrugsfdaSponsorSearchTests(unittest.TestCase):
    def test_real_zero_result_prefix_search_returns_empty_list_not_an_error(self):
        # Verified directly against the real API 2026-09-30: Assembly Biosciences (clinical-stage,
        # nothing FDA-approved yet) gets a real HTTP 404 for this prefix search -- a normal, valid
        # outcome for a discovery search, never raised as an error.
        client = FakeClient(errors={REAL_ASSEMBLY_FDA_SEARCH_URL: SourceUnavailable("HTTP_404")})
        results, meta = drugsfda_sponsor_search(client, "ASSEMBLY", "/tmp/out")
        self.assertEqual(results, [])

    def test_real_nonzero_result_prefix_search(self):
        url = 'https://api.fda.gov/drug/drugsfda.json?search=sponsor_name%3ANEUROCRINE%2A&limit=20'
        document = {"results": [
            {"application_number": "NDA209241", "sponsor_name": "NEUROCRINE",
             "products": [{"brand_name": "INGREZZA"}], "submissions": []},
        ]}
        client = FakeClient({url: document})
        results, meta = drugsfda_sponsor_search(client, "NEUROCRINE", "/tmp/out")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["sponsor_name"], "NEUROCRINE")

    def test_empty_sponsor_prefix_rejected(self):
        with self.assertRaises(DataError):
            drugsfda_sponsor_search(FakeClient(), "", "/tmp/out")


class CliFdaApprovalTests(unittest.TestCase):
    """cli.py's own "fda-approval" command, end to end, with a faked PublicClient standing in for
    the real network the same way test_clinical_trials_ingestion.py's own CLI test fakes it."""

    def test_real_cafcit_application_classified_through_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("nre.ingestion.PublicClient", return_value=FakeClient({REAL_CAFCIT_URL: REAL_CAFCIT_DOCUMENT})), \
             patch("builtins.print") as output:
            code = cli.main(["fda-approval", "--application-number", "NDA020793", "--output", tmp])
            self.assertEqual(code, 0)
            printed = json.loads(output.call_args_list[0].args[0])
            self.assertEqual(printed["pathway"], "new_drug_application")
            self.assertEqual(printed["sponsor_name"], "HIKMA")
            saved = json.loads((Path(tmp) / "fda-approval.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["application_number"], "NDA020793")
            self.assertEqual(saved["result"]["pathway"], printed["pathway"])


if __name__ == "__main__":
    unittest.main()
