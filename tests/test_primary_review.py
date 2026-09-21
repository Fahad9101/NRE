import copy
import unittest

from nre.core import DataError, canonical, digest
from scripts.review_frozen_candidates import build_queue


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(candidate_id='one', source_sha256='a' * 64, cik='1', primary_url='https://example.test/one', form='8-K'),
                     dict(candidate_id='two', source_sha256='b' * 64, cik='1', primary_url='https://example.test/two', form='8-K/A')]
        membership = [{k: r[k] for k in ('candidate_id', 'source_sha256')} for r in self.rows]
        self.ledger = dict(candidates=self.rows, membership_sha256=digest(canonical(membership)), frozen_at='2026-09-20T00:00:00Z')
        self.note = dict(candidate_id='one', primary_url=self.rows[0]['primary_url'], first_public_verified=False, release_time=None, summary='Results announced.', evidence_locator='Item 2.02', review_flags=[])

    def test_full_accounting_keeps_unreviewed_amendment(self):
        report = build_queue(self.ledger, {'notes': [self.note]})
        self.assertEqual((report['primary_screened'], report['primary_pending'], report['accepted_events']), (1, 1, 0))
        self.assertIn('AMENDMENT_REVIEW_REQUIRED', report['candidates'][1]['flags'])
        self.assertFalse(report['price_acquisition_authorized_by_this_report'])

    def test_tampered_membership_rejected(self):
        self.rows[0]['source_sha256'] = 'c' * 64
        with self.assertRaises(DataError):
            build_queue(self.ledger, {'notes': []})

    def test_wrong_source_and_duplicate_review_rejected(self):
        changed = copy.deepcopy(self.note)
        changed['primary_url'] = 'https://example.test/other'
        for notes in ([changed], [self.note, self.note]):
            with self.assertRaises(DataError):
                build_queue(self.ledger, {'notes': notes})

    def test_screen_cannot_promote_publication_truth(self):
        self.note['first_public_verified'] = True
        with self.assertRaises(DataError):
            build_queue(self.ledger, {'notes': [self.note]})
