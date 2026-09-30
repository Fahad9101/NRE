import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nre import cli
from nre.core import DataError, canonical, digest
from nre.ingestion import drugsfda_application


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


class DrugsfdaApplicationTests(unittest.TestCase):
    def test_real_response_shape_parses_cleanly(self):
        client = FakeClient({REAL_CAFCIT_URL: REAL_CAFCIT_DOCUMENT})
        result, meta = drugsfda_application(client, "NDA020793", "/tmp/out")
        self.assertEqual(result["sponsor_name"], "HIKMA")
        self.assertEqual(client.calls, [REAL_CAFCIT_URL])
        self.assertEqual(meta["url"], REAL_CAFCIT_URL)

    def test_openfda_no_match_body_becomes_a_data_error(self):
        # openFDA returns HTTP 200 with an {"error": {...}} body for a zero-result search, unlike a
        # real HTTP error status -- must not be treated as a successful empty result.
        client = FakeClient({REAL_CAFCIT_URL: NOT_FOUND_DOCUMENT})
        with self.assertRaises(DataError):
            drugsfda_application(client, "NDA020793", "/tmp/out")

    def test_invalid_application_number_format_rejected(self):
        for bad in ("IND012345", "NDA", "020793", "nda020793"):
            with self.assertRaises(DataError):
                drugsfda_application(FakeClient(), bad, "/tmp/out")

    def test_response_application_number_must_match_the_request(self):
        wrong = {"results": [{"application_number": "NDA999999", "submissions": []}]}
        client = FakeClient({REAL_CAFCIT_URL: wrong})
        with self.assertRaises(DataError):
            drugsfda_application(client, "NDA020793", "/tmp/out")


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
