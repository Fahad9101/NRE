"""Offline verification of the original SEC discovery artifact; no downloads."""
import argparse
import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from nre.core import DataError, canonical, digest, timestamp
from nre.cohort import freeze_sec_cohort
from nre.ingestion import SecRelayClient


def require(condition, message):
    if not condition:
        raise DataError(message)


def audit(archive, root):
    root = Path(root)
    read = lambda name: json.loads((root / name).read_text())
    spec = read('config/sec-cohort-spec.json')
    protocol = read('config/pilot.json')
    frozen_ledger = read('config/m1-frozen-candidate-ledger.json')
    frozen_cohort = read('config/m1-frozen-issuer-cohort.json')
    frozen_report = read('reports/m1-sec-cohort-freeze.json')
    observed = {}
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), 'duplicate archive member')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names), 'unsafe archive member')
        require(z.testzip() is None, 'archive CRC failed')
        frame = json.loads(z.read('nre-historical-frame.json'))
        require(digest(canonical(frame)) == frozen_ledger['historical_frame_sha256'], 'frame hash mismatch')
        require(digest(z.read('nre-sec-master-2026.parquet')) == spec['historical_frame']['parquet_sha256'], 'parquet hash mismatch')
        for name in names:
            if not name.startswith('nre-sec-freeze/raw/') or not name.endswith('.json'):
                continue
            meta = json.loads(z.read(name))
            require(PurePosixPath(name).stem == digest(canonical(meta)), 'observation hash mismatch')
            for key in ('payload_file', 'raw_file'):
                require(PurePosixPath(meta[key]).name == meta[key], 'unsafe referenced member')
            payload = z.read('nre-sec-freeze/raw/' + meta['payload_file'])
            transport = z.read('nre-sec-freeze/raw/' + meta['raw_file'])
            require(digest(payload) == meta['sha256'] and len(payload) == meta['size'], 'payload integrity failed')
            require(digest(transport) == meta['transport_sha256'] and len(transport) == meta['transport_size'], 'transport integrity failed')
            extracted, representation = SecRelayClient.payload(transport, meta['url'])
            require(extracted == payload and representation == meta['source_representation'], 'relay extraction differs')
            require(timestamp(meta['retrieved_at']) <= timestamp(frozen_ledger['frozen_at']), 'source observed after freeze')
            require(meta['url'] not in observed, 'duplicate observation URL')
            observed[meta['url']] = (payload, meta)

    class ArchivedClient:
        def __init__(self):
            self.used = set()

        def fetch(self, url, output):
            require(url in observed, 'required archived source missing')
            self.used.add(url)
            return observed[url]

    client = ArchivedClient()
    with tempfile.TemporaryDirectory() as destination:
        with patch('nre.cohort._client', return_value=(client, spec['sec_transport'])):
            cohort, ledger, report = freeze_sec_cohort(spec, protocol, destination, 'offline-audit', frame)
    # Only execution time changes. Compare every other published field, including
    # ordering, source hashes, stopping rule, and each accession reconciliation.
    for actual, expected in ((cohort, frozen_cohort), (ledger, frozen_ledger), (report, frozen_report)):
        require({k: v for k, v in actual.items() if k != 'frozen_at'} ==
                {k: v for k, v in expected.items() if k != 'frozen_at'}, 'frozen output replay differs')
    require(client.used == set(observed), 'unused archived observations')
    return {
        'state': 'ARCHIVE_INTEGRITY_AND_DISCOVERY_REPLAY_VERIFIED',
        'archive_sha256': digest(Path(archive).read_bytes()),
        'archive_members': len(names), 'verified_observations': len(observed),
        'candidate_count': report['candidate_count'],
        'processed_issuers': report['processed_issuers'],
        'membership_sha256': report['membership_sha256'],
        'accepted_events': 0, 'market_prices_accessed': False,
        'limitations': [
            'Integrity and deterministic replay do not authenticate SEC origin or first-public time.',
            'Archived relay payloads remain transformed representations, not raw SEC bytes.',
            'The parquet checksum is verified; parquet-to-frame transformation is not rerun here.',
            'Primary-document eligibility, timing, provider permissions and independent reviews remain required.'
        ]
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--root', default='.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.archive, args.root)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, sort_keys=True))
