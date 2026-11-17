import gzip
import unittest

from nre import m6_guidance_screen as screen
from nre.core import DataError, digest


CIK = "0001234567"
ACCESSION = "0001104659-25-012345"
FILING = {
    "cik": CIK,
    "accession": ACCESSION,
    "source_url": f"{screen.SEC_ARCHIVE}/1234567/000110465925012345/{ACCESSION}.txt",
}
MAIN_DOCUMENT = "<DOCUMENT>\n<TYPE>8-K\n<FILENAME>main.htm\n<TEXT>Current report</TEXT>\n</DOCUMENT>"
RELEASE_DOCUMENT = """<DOCUMENT>
<TYPE>EX-99.1
<FILENAME>earnings-release.htm
<TEXT>
<html><body>
<h2>Full fiscal year 2025 financial outlook</h2>
<table>
  <tr><th>Metric (USD millions)</th><th>Prior</th><th>Current</th></tr>
  <tr><td>Total&nbsp;revenue</td><td>$410 to $440</td><td>$420 to $450</td></tr>
</table>
<script>hidden script reference</script><style>hidden style reference</style>
<ix:hidden>hidden XBRL reference</ix:hidden>
</body></html>
</TEXT>
</DOCUMENT>"""


def submission(*documents, count=None):
    listed_count = len(documents) if count is None else count
    return "\n".join((
        "<SEC-DOCUMENT>", "<SEC-HEADER>", f"ACCESSION NUMBER: {ACCESSION}",
        f"PUBLIC DOCUMENT COUNT: {listed_count}", f"CENTRAL INDEX KEY: {CIK}",
        "</SEC-HEADER>", *documents, "</SEC-DOCUMENT>",
    )).encode()


class GuidanceScreenTests(unittest.TestCase):
    def test_item_202_earnings_and_interim_guidance_selection(self):
        def row(number, form, items, filed):
            return (f"0001104659-25-{number:06d}", f"{filed}T21:02:03Z", filed,
                    form, items, "main.htm")

        rows = [
            row(6, "8-K", "2.02,9.01", "2025-06-30"),
            row(7, "8-K", "7.01,9.01", "2025-04-03"),
            row(8, "8-K", "8.01,9.01", "2025-02-05"),
            row(9, "8-K", "1.01,9.01", "2025-03-04"),
            row(10, "8-K/A", "2.02", "2025-03-04"),
            row(11, "8-K", "2.02", "2025-07-01"),
            row(12, "8-K", "Item 2.02; Item 9.01", "2025-01-01"),
        ]
        recent = dict(zip(screen.FILING_FIELDS, zip(*rows)))
        earnings = screen.current_reports(recent, CIK, "2025-01-01", "2025-06-30")
        guidance = screen.current_reports(recent, CIK, "2025-01-01", "2025-06-30",
                                          guidance_updates=True)
        self.assertEqual([entry["accession"] for entry in earnings], [rows[6][0], rows[0][0]])
        self.assertEqual([entry["accession"] for entry in guidance],
                         [rows[index][0] for index in (6, 2, 1, 0)])
        self.assertEqual(earnings[0]["items"], ["2.02", "9.01"])
        accession = rows[6][0]
        archive_path = f"1234567/{accession.replace('-', '')}/{accession}.txt"
        self.assertEqual(earnings[0]["cik"], CIK)
        self.assertEqual(earnings[0]["source_url"], f"{screen.SEC_ARCHIVE}/{archive_path}")
        self.assertEqual(earnings[0]["mirror_url"], f"{screen.PUBLIC_MIRROR}/{archive_path}")

    def test_archive_requires_matching_cik_and_accession(self):
        payload = submission(MAIN_DOCUMENT, RELEASE_DOCUMENT)
        for identity in ({"cik": "0001234568"}, {"accession": "0001104659-25-012346"}):
            with self.subTest(identity=identity), self.assertRaisesRegex(DataError, "identity"):
                screen.exhibits(payload, {**FILING, **identity})

    def test_compressed_archive_keeps_forecast_table_and_source(self):
        payload = gzip.compress(submission(MAIN_DOCUMENT, RELEASE_DOCUMENT), mtime=0)
        review = screen.archive_review(payload, FILING)
        self.assertEqual(review["archive_sha256"], digest(payload))
        self.assertEqual(review["listed_document_count"], 2)
        self.assertEqual(review["available_document_count"], 2)
        self.assertEqual(review["exhibit_formats"], {"htm": 1})
        release, = review["exhibits"]
        self.assertEqual(release["form_type"], "EX-99.1")
        self.assertEqual(release["source_url"], FILING["source_url"].rsplit("/", 1)[0]
                         + "/earnings-release.htm")
        self.assertEqual(release["lines"], [
            "Full fiscal year 2025 financial outlook",
            "Metric (USD millions) | Prior | Current",
            "Total revenue | $410 to $440 | $420 to $450",
        ])
        self.assertEqual(release["review_excerpt"], [{"line": 2, "excerpt": release["lines"]}])

    def test_complete_envelope_preserves_reported_and_available_counts(self):
        release, counts = screen.exhibits(submission(MAIN_DOCUMENT, RELEASE_DOCUMENT, count=5), FILING)
        self.assertEqual(counts, {"listed_document_count": 5, "available_document_count": 2})
        self.assertEqual([exhibit["filename"] for exhibit in release], ["earnings-release.htm"])

    def test_error_page_or_truncated_archive_fails(self):
        payload = submission(MAIN_DOCUMENT, RELEASE_DOCUMENT)
        cases = [
            (b"<html><title>Request blocked</title></html>", "identity"),
            (payload.removesuffix(b"</SEC-DOCUMENT>"), "Incomplete SEC submission"),
            (payload.replace(b"</DOCUMENT>\n</SEC-DOCUMENT>", b"</SEC-DOCUMENT>"),
             "Incomplete SEC submission"),
            (payload.replace(b"</TEXT>\n</DOCUMENT>", b"</DOCUMENT>"), "Incomplete exhibit"),
        ]
        for raw, description in cases:
            with self.subTest(error=description), self.assertRaisesRegex(DataError, description):
                screen.archive_review(raw, FILING)
