import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nre import cli
from nre.core import DataError, canonical, digest
from nre.ingestion import clinical_trials_study


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


REAL_NBIX_URL = "https://clinicaltrials.gov/api/v2/studies/NCT03325010"
# A trimmed but real response for NBIX (Neurocrine Biosciences)'s own trial, fetched directly on
# 2026-09-30 -- the same study tests/test_biotech_trials.py already classifies.
REAL_NBIX_DOCUMENT = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT03325010",
                                 "briefTitle": "Safety, Tolerability, and Efficacy of NBI-98854 for the Treatment of Pediatric Subjects With Tourette Syndrome"},
        "statusModule": {"overallStatus": "COMPLETED"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Neurocrine Biosciences"}},
        "conditionsModule": {"conditions": ["Tourette Syndrome"]},
        "designModule": {"phases": ["PHASE2"]},
    }
}


class ClinicalTrialsStudyTests(unittest.TestCase):
    def test_real_response_shape_parses_cleanly(self):
        client = FakeClient({REAL_NBIX_URL: REAL_NBIX_DOCUMENT})
        protocol, meta = clinical_trials_study(client, "NCT03325010", "/tmp/out")
        self.assertEqual(protocol["identificationModule"]["nctId"], "NCT03325010")
        self.assertEqual(client.calls, [REAL_NBIX_URL])
        self.assertEqual(meta["url"], REAL_NBIX_URL)

    def test_invalid_nct_id_format_rejected(self):
        with self.assertRaises(DataError):
            clinical_trials_study(FakeClient(), "not-an-nct-id", "/tmp/out")
        with self.assertRaises(DataError):
            clinical_trials_study(FakeClient(), "NCT123", "/tmp/out")  # too few digits

    def test_response_nct_id_must_match_the_request(self):
        wrong = {"protocolSection": {"identificationModule": {"nctId": "NCT99999999"}}}
        client = FakeClient({REAL_NBIX_URL: wrong})
        with self.assertRaises(DataError):
            clinical_trials_study(client, "NCT03325010", "/tmp/out")

    def test_missing_protocol_section_rejected(self):
        client = FakeClient({REAL_NBIX_URL: {"no_protocol": True}})
        with self.assertRaises(DataError):
            clinical_trials_study(client, "NCT03325010", "/tmp/out")


class CliClinicalTrialTests(unittest.TestCase):
    """cli.py's own "clinical-trial" command, end to end, with a faked PublicClient standing in for
    the real network the same way test_xbrl_ingestion.py's own CLI test fakes it for earnings-surprise."""

    def test_real_nbix_trial_classified_through_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("nre.ingestion.PublicClient", return_value=FakeClient({REAL_NBIX_URL: REAL_NBIX_DOCUMENT})), \
             patch("builtins.print") as output:
            code = cli.main(["clinical-trial", "--nct-id", "NCT03325010", "--output", tmp])
            self.assertEqual(code, 0)
            printed = json.loads(output.call_args_list[0].args[0])
            self.assertEqual(printed["status_category"], "completed")
            self.assertEqual(printed["sponsor"], "Neurocrine Biosciences")
            saved = json.loads((Path(tmp) / "clinical-trial.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["nct_id"], "NCT03325010")
            self.assertEqual(saved["result"]["status_category"], printed["status_category"])


if __name__ == "__main__":
    unittest.main()
