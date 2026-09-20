"""Reproduce the exploratory review from privately retained connector exports.

Run from repository root. This records quarantine outcomes, never accepted labels.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nre.alpaca import audit_daily
from nre.calendar import Calendar
from nre.core import canonical, digest
from nre.dataset import build, verify_snapshot, write_snapshot


def run(root, observed):
    root = Path(root)
    prices = json.loads((root / 'prices.json').read_text())
    actions = json.loads((root / 'actions.json').read_text())
    audit = audit_daily(prices, observed)
    discovery = json.loads(Path('reports/discovery-progress.json').read_text())
    candidates = [c for c in discovery['pilot_filing_date_screen']
                  if c['state'] == 'EARNINGS_CANDIDATE']
    specs = {
        '0000320193': ('AAPL', 'NASDAQ', '2026-01-29', 'date',
            'https://www.apple.com/newsroom/2026/01/apple-reports-first-quarter-results/',
            'Review note: issuer page provides a release date; earliest release time is unverified.'),
        '0000789019': ('MSFT', 'NASDAQ', '2026-01-28T21:08:16Z', 'second',
            'https://news.microsoft.com/source/2026/01/28/microsoft-cloud-and-ai-strength-drives-second-quarter-results/',
            'Review note: article:published_time is 2026-01-28T21:08:16+00:00. '
            'This is later than SEC acceptance at 21:04:38 UTC, so it cannot establish earliest publication.'),
        '0000051143': ('IBM', 'NYSE', '2026-01-28T21:08:00Z', 'minute',
            'https://www.prnewswire.com/news-releases/ibm-releases-fourth-quarter-results-302673165.html',
            'Review note: wire page displays Jan 28, 2026, 16:08 ET. Seconds and earliest dissemination are unverified.'),
        '0001045810': ('NVDA', 'NASDAQ', '2026-02-25', 'date',
            'https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-2026',
            'Review note: issuer page provides February 25, 2026; earliest release time is unverified.')}
    bundle = dict(schema_version=1, synthetic=False, as_of=observed,
                  availability_mode='historical_reconstruction', sources=[],
                  securities=[], providers=[], events=[], prices=[], corporate_actions=[])
    cal = Calendar()
    reviews = []
    for c in candidates:
        symbol, exchange, published, precision, url, note = specs[c['cik']]
        sid = symbol + '-release-review'
        bundle['sources'].append(dict(source_id=sid, url=url, text=note,
            first_seen_at=observed, retrieved_at=observed, source_kind='analyst_review_note'))
        bundle['securities'].append(dict(security_id=symbol, company_id=c['cik'],
            cik=c['cik'], ticker=symbol, exchange=exchange, security_type='common_stock',
            source_id=sid, valid_from=c['filing_date']+'T00:00:00Z', valid_to=None,
            available_at=observed, identity_review_required=True))
        bundle['events'].append(dict(event_id=c['candidate_id'], cluster_id=c['candidate_id'],
            security_id=symbol, source_id=sid, published_at=published, precision=precision,
            first_public_verified=False, cutoff=c['acceptance_at'], category='earnings',
            subtype='results', cutoff_role='filing_acceptance_reference_not_verified_decision_time'))
        # Conditional date mapping only: no claim that first news was after-hours.
        day = cal.offset(c['filing_date'], 1)
        anchor = cal.offset(day, -1)
        dividends = [a for a in actions['announcements'].get('cash_dividends', [])
                     if a['symbol'] == symbol]
        windows = {}
        for n in (1, 2, 5, 10, 20):
            end = cal.offset(day, n-1)
            windows[str(n)] = {'end': end, 'dividend_ex_dates': [a['ex_date'] for a in dividends
                              if anchor < a['ex_date'] <= end]}
        reviews.append({'symbol': symbol, 'event_id': c['candidate_id'],
            'publication_precision': precision, 'first_public_verified': False,
            'price_coverage': audit['coverage'][symbol],
            'conditional_reaction_session': day,
            'condition': 'If first-public release was after the close on the stated release date.',
            'conditional_windows': windows,
            'additional_blockers': audit['blockers'],
            'raw_prices_admitted_to_label_builder': False})
    # Unknown adjustment/session semantics are not converted into raw/regular flags.
    # Prices are audited separately and intentionally not admitted to the builder.
    path, pipeline = write_snapshot(bundle, root / 'snapshots')
    manifest = verify_snapshot(path)
    outcomes, replay = build(bundle)
    assert digest(canonical(outcomes)) == manifest['output_sha256']
    assert digest(canonical(replay)) == manifest['report_sha256']
    report = {'reviewed_at': observed, 'scope': 'four exploratory candidates; not frozen cohort',
        'accepted_events': 0, 'price_audit': audit, 'event_reviews': reviews,
        'pipeline_report': pipeline, 'pipeline_outcomes': outcomes,
        'snapshot_id': manifest['snapshot_id'], 'replay_verified': True,
        'pipeline_scope': 'Source-review-only quarantine snapshot; no price-derived labels. '
            'The builder reports the first blocking reason; the independent intake audit lists additional blockers.',
        'corporate_actions_payload_sha256': digest(canonical(actions)),
        'corporate_action_limit': 'Observed dividends are positive evidence of action windows; '
            'absence of other actions is not a complete action audit. IBM acquirer-role merger not applied as a share adjustment.'}
    for name, value in [('four-candidate-review.json', report),
                        ('four-candidate-quarantine-input.json', bundle)]:
        Path('reports', name).write_text(json.dumps(value, indent=2)+'\n')
    print(json.dumps({'snapshot': str(path), 'accepted_events': 0,
                      'outcomes': [(o['security_id'], o['reasons']) for o in outcomes]}))


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
