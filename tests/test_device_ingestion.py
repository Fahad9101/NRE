import unittest

from nre.core import DataError, canonical, digest
from nre.ingestion import SourceUnavailable, device_sponsor_search


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


LENSAR_510K_URL = 'https://api.fda.gov/device/510k.json?search=applicant%3ALENSAR%2A&limit=20'
LENSAR_PMA_URL = 'https://api.fda.gov/device/pma.json?search=applicant%3ALENSAR%2A&limit=20'
REAL_LENSAR_510K_DOCUMENT = {"results": [
    {"k_number": "K090633", "applicant": "Lensar, Inc.", "device_name": "LENSAR LASER SYSTEM",
     "decision_code": "SESE", "openfda": {"device_class": "2"}},
]}


class DeviceSponsorSearchTests(unittest.TestCase):
    def test_real_510k_response_shape_parses_cleanly(self):
        client = FakeClient({LENSAR_510K_URL: REAL_LENSAR_510K_DOCUMENT})
        results, meta = device_sponsor_search(client, "510k", "LENSAR", "/tmp/out")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["k_number"], "K090633")
        self.assertEqual(client.calls, [LENSAR_510K_URL])

    def test_real_zero_result_pma_search_returns_empty_list_not_an_error(self):
        # Verified directly against the real API 2026-09-30: LNSR genuinely has zero PMA records
        # (only 510(k) ones), which gets a real HTTP 404 -- a normal, valid outcome, not an error.
        client = FakeClient(errors={LENSAR_PMA_URL: SourceUnavailable("HTTP_404")})
        results, meta = device_sponsor_search(client, "pma", "LENSAR", "/tmp/out")
        self.assertEqual(results, [])

    def test_invalid_pathway_rejected(self):
        with self.assertRaises(DataError):
            device_sponsor_search(FakeClient(), "pma510k", "LENSAR", "/tmp/out")

    def test_empty_applicant_prefix_rejected(self):
        with self.assertRaises(DataError):
            device_sponsor_search(FakeClient(), "510k", "", "/tmp/out")


if __name__ == "__main__":
    unittest.main()
