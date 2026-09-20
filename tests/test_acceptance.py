"""Audit mechanics with deliberately invented inputs; no market observations."""
import copy
import json
import unittest
from pathlib import Path
from nre.acceptance import audit_cohort
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((ROOT / 'tests/fixtures/synthetic_bundle.json').read_text())
        self.protocol = json.loads((ROOT / 'config/pilot.json').read_text())
        # Artificial small contract for testing control flow only, never pilot acceptance.
        self.protocol.update(minimum_eligible_events=2, minimum_unique_issuers=1)
        self.bundle['synthetic'] = False
        for s in self.bundle['sources']:
            s['url'] = 'https://example.invalid/TEST-ONLY/' + s['source_id']
        self.bundle['securities'][0]['cik'] = '123'
        self.bundle['events'][0].update(category='earnings', subtype='results')
        other = copy.deepcopy(self.bundle['events'][0])
        other.update(event_id='e2', cluster_id='c2')
        self.bundle['events'].append(other)
        sha = digest(self.bundle['sources'][1]['text'].encode())
        self.ledger = {'frozen_at':'2026-08-01T00:00:00Z',
                       'protocol_sha256':digest(canonical(self.protocol)),
                       'candidates':[{'candidate_id':'candidate-'+e['event_id'], 'event_id':e['event_id'],
                                      'source_sha256':sha, 'disposition':'included'} for e in self.bundle['events']]}
        membership = [{k:c[k] for k in ('candidate_id','source_sha256')} for c in self.ledger['candidates']]
        self.review = {'prices_first_accessed_at':'2026-08-02T00:00:00Z',
                       'frozen_membership_sha256':digest(canonical(membership)),
                       'discovery_coverage_evidence':'TEST-ONLY', 'identity_history_evidence':'TEST-ONLY',
                       'provider_rights_evidence':'TEST-ONLY',
                       'spot_checks':[{'event_id':e['event_id'],'reviewers':['test-A','test-B'],'evidence':'TEST-ONLY'} for e in self.bundle['events']]}

    def run_audit(self):
        return audit_cohort(self.bundle, self.protocol, self.ledger, self.review)

    def test_pass_does_not_certify_real_world_evidence(self):
        r = self.run_audit()
        self.assertEqual(r['failed_gates'], [])
        self.assertFalse(r['milestone_accepted'])
        self.assertEqual(r['status'], 'STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED')

    def test_actual_pilot_minimum_not_met(self):
        self.protocol = json.loads((ROOT / 'config/pilot.json').read_text())
        r = self.run_audit()
        self.assertIn('minimum_events', r['failed_gates'])
        self.assertIn('minimum_issuers', r['failed_gates'])
        self.assertIn('protocol_hash', r['failed_gates'])

    def test_synthetic_blocked(self):
        self.bundle['synthetic'] = True
        self.assertIn('real_data', self.run_audit()['failed_gates'])

    def test_omitted_candidate_accounting(self):
        self.ledger['candidates'].pop()
        self.assertIn('candidate_accounting', self.run_audit()['failed_gates'])

    def test_duplicate_mapping_not_allowed(self):
        self.ledger['candidates'][1]['event_id'] = 'e1'
        self.assertIn('candidate_accounting', self.run_audit()['failed_gates'])

    def test_exclusion_needs_reason(self):
        self.ledger['candidates'].append({'candidate_id':'rejected', 'disposition':'excluded'})
        self.assertIn('candidate_accounting', self.run_audit()['failed_gates'])

    def test_selection_after_prices(self):
        self.review['prices_first_accessed_at'] = '2026-07-01T00:00:00Z'
        self.assertIn('selection_frozen_before_prices', self.run_audit()['failed_gates'])

    def test_company_alias_does_not_inflate_issuer_count(self):
        second = copy.deepcopy(self.bundle['securities'][0])
        second.update(security_id='SYNTH-B', company_id='different-label-same-cik')
        self.bundle['securities'].append(second)
        bars = copy.deepcopy(self.bundle['prices'])
        for b in bars:
            b['security_id'] = 'SYNTH-B'; b['price_id'] += '-B'
        self.bundle['prices'].extend(bars)
        self.bundle['events'][1]['security_id'] = 'SYNTH-B'
        self.assertEqual(self.run_audit()['counts']['unique_issuers'],1)

    def test_unknown_cik_not_counted(self):
        self.bundle['securities'][0]['cik'] = '0'
        r = self.run_audit()
        self.assertEqual(r['counts']['unique_issuers'],0)
        self.assertIn('issuer_identity',r['failed_gates'])

    def test_independent_reviewers_required(self):
        self.review['spot_checks'][0]['reviewers'] = ['same','same']
        self.assertIn('independent_timing_spot_checks',self.run_audit()['failed_gates'])

    def test_unknown_event_not_a_spot_check(self):
        self.review['spot_checks'][0]['event_id'] = 'nonexistent'
        self.assertIn('independent_timing_spot_checks',self.run_audit()['failed_gates'])

    def test_missing_earnings_taxonomy(self):
        del self.bundle['events'][0]['category']
        self.assertIn('earnings_results_only',self.run_audit()['failed_gates'])

    def test_source_not_in_archive(self):
        self.ledger['candidates'][0]['source_sha256'] = 'missing'
        self.assertIn('candidate_source_hashes',self.run_audit()['failed_gates'])

    def test_window_checked_in_exchange_timezone(self):
        # Midnight UTC Jan 5 is still Jan 4 in New York, outside the frozen window.
        self.bundle['events'][0].update(published_at='2026-01-05T00:00:00Z',timestamp_evidence='2026-01-05T00:00:00Z')
        self.bundle['sources'][1]['text'] += ' 2026-01-05T00:00:00Z'
        self.assertIn('all_events_in_window',self.run_audit()['failed_gates'])


if __name__ == '__main__': unittest.main()
