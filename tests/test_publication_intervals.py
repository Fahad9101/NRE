import json
import unittest
from pathlib import Path
from nre.core import DataError, iso, publication_bounds
from nre.dataset import build


class PublicationIntervalTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((Path(__file__).parent / 'fixtures/synthetic_bundle.json').read_text())
        self.event = self.bundle['events'][0]
        self.event['precision'] = 'minute'

    def row(self):
        return build(self.bundle)[0][0]

    def test_verified_premarket_minute_maps_without_invented_seconds(self):
        r = self.row()
        self.assertEqual(r['state'], 'MAPPED')
        self.assertEqual(r['publication_interval'], {'start_inclusive': '2026-01-05T12:00:00Z',
                                                    'end_exclusive': '2026-01-05T12:01:00Z'})
        self.assertAlmostEqual(r['labels']['day1_open_return']['value'], .1)

    def test_cutoff_inside_minute_rejected_in_both_modes(self):
        self.event['cutoff'] = '2026-01-05T12:00:30Z'
        for mode in ('historical_reconstruction', 'forward_observed'):
            with self.subTest(mode=mode):
                self.bundle['availability_mode'] = mode
                self.assertIn('NEWS_NOT_AVAILABLE_AT_CUTOFF', self.row()['reasons'])

    def test_first_public_verification_still_required(self):
        self.event['first_public_verified'] = False
        self.assertIn('FIRST_PUBLIC_TIME_UNVERIFIED', self.row()['reasons'])

    def test_evidence_still_required(self):
        self.event['timestamp_evidence'] = 'missing'
        with self.assertRaises(DataError):
            self.row()

    def test_non_aligned_minute_rejected(self):
        self.event['published_at'] = '2026-01-05T12:00:10Z'
        with self.assertRaises(DataError):
            self.row()

    def test_identity_must_hold_for_whole_minute(self):
        self.bundle['securities'][0]['valid_to'] = '2026-01-05T12:00:30Z'
        self.assertIn('IDENTITY_EXPIRED', self.row()['reasons'])

    def test_opening_and_closing_bell_minutes_rejected(self):
        for t in ('14:30', '21:00'):
            with self.subTest(t=t):
                pub = f'2026-01-05T{t}:00Z'
                self.event.update(published_at=pub, timestamp_evidence=pub)
                # Use a later cutoff so this tests classification, not availability.
                self.event['cutoff'] = '2026-01-05T22:00:00Z'
                self.bundle['sources'][1]['text'] += ' ' + pub
                self.assertIn('PUBLICATION_INTERVAL_CROSSES_SESSION_BOUNDARY', self.row()['reasons'])

    def test_minute_before_open_cannot_forecast_open_at_its_cutoff(self):
        self.event.update(published_at='2026-01-05T14:29:00Z', cutoff='2026-01-05T14:30:00Z',
                          timestamp_evidence='2026-01-05T14:29:00Z')
        self.bundle['sources'][1]['text'] += ' 2026-01-05T14:29:00Z'
        self.assertIn('CUTOFF_NOT_BEFORE_REACTION_OPEN', self.row()['reasons'])

    def test_offset_timestamp_normalizes(self):
        self.event['published_at'] = '2026-01-05T07:00:00-05:00'
        first, last, available = publication_bounds(self.event)
        self.assertEqual(iso(first), '2026-01-05T12:00:00Z')
        self.assertEqual(iso(available), '2026-01-05T12:01:00Z')
        self.assertLess(last, available)


if __name__ == '__main__':
    unittest.main()
