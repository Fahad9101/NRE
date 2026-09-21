"""Build an evidence-review queue without changing frozen membership or eligibility."""
import argparse
import json
from collections import Counter
from pathlib import Path

from nre.core import DataError, canonical, digest


def build_queue(ledger, notes):
    candidates = ledger['candidates']
    ids = [r['candidate_id'] for r in candidates]
    if len(ids) != len(set(ids)):
        raise DataError('duplicate frozen candidate')
    membership = [{k: r[k] for k in ('candidate_id', 'source_sha256')}
                  for r in sorted(candidates, key=lambda r: r['candidate_id'])]
    if digest(canonical(membership)) != ledger['membership_sha256']:
        raise DataError('frozen membership hash differs')
    by_id = {r['candidate_id']: r for r in candidates}
    reviewed = {}
    for note in notes['notes']:
        key = note['candidate_id']
        if key not in by_id or key in reviewed:
            raise DataError('unknown or duplicate reviewed candidate')
        if note['primary_url'] != by_id[key]['primary_url']:
            raise DataError('review URL does not match frozen accession')
        if note.get('first_public_verified') is not False or note.get('release_time') is not None:
            raise DataError('primary screening cannot certify release time')
        if not note.get('summary') or not note.get('evidence_locator'):
            raise DataError('review evidence required')
        reviewed[key] = note
    issuer_counts = Counter(r['cik'] for r in candidates)
    queue = []
    for row in sorted(candidates, key=lambda r: r['candidate_id']):
        note = reviewed.get(row['candidate_id'])
        flags = list(note['review_flags']) if note else []
        if row['form'] == '8-K/A':
            flags.append('AMENDMENT_REVIEW_REQUIRED')
        if issuer_counts[row['cik']] > 1:
            flags.append('MULTIPLE_FILINGS_FOR_ISSUER_REVIEW_REQUIRED')
        queue.append({
            'candidate_id': row['candidate_id'], 'cik': row['cik'],
            'primary_url': row['primary_url'],
            'status': 'PRIMARY_SCREENED_REVIEW_REQUIRED' if note else 'PRIMARY_REVIEW_PENDING',
            'flags': sorted(set(flags)),
        })
    return {
        'schema_version': 1, 'membership_sha256': ledger['membership_sha256'],
        'frozen_at': ledger['frozen_at'], 'candidate_count': len(queue),
        'primary_screened': len(reviewed), 'primary_pending': len(queue) - len(reviewed),
        'accepted_events': 0, 'price_acquisition_authorized_by_this_report': False,
        'flag_counts': dict(sorted(Counter(f for r in queue for f in r['flags']).items())),
        'limitations': [
            'Primary screening is not complete eligibility, source archival or independent review.',
            'Dates and identities in a filing do not establish availability before the release.',
            'No automatic exclusions or duplicate-event merges follow from flags.',
        ],
        'candidates': queue,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', default='config/m1-frozen-candidate-ledger.json')
    parser.add_argument('--notes', default='reports/m1-primary-source-notes.json')
    parser.add_argument('--output', default='reports/m1-primary-review-queue.json')
    args = parser.parse_args()
    report = build_queue(json.loads(Path(args.ledger).read_text()), json.loads(Path(args.notes).read_text()))
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'candidates'}, sort_keys=True))
