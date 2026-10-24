#!/usr/bin/env python3
"""Verify original release archives without extracting or changing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archives', type=Path, default=ROOT)
args = parser.parse_args()
custody = json.loads((ROOT / 'custody-verification.json').read_text(encoding='utf-8'))
for record in custody['records']:
    archive = args.archives / record['archive']
    raw = archive.read_bytes()
    assert len(raw) == record['bytes'], (archive.name, 'archive length')
    assert hashlib.sha256(raw).hexdigest() == record['sha256'], (archive.name, 'archive hash')
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        assert len(names) == len(set(names)) == record['zip_members'], 'duplicate or missing ZIP members'
        manifest = json.loads(z.read('custody-manifest.json'))
        assert manifest['source_revision'] == custody['source_revision']
        assert manifest['run_id'] == str(custody['run_id'])
        files = manifest['files']
        expected = [item['path'] for item in files] + ['custody-manifest.json']
        assert len(expected) == len(set(expected)) and set(expected) == set(names)
        for item in files:
            data = z.read(item['path'])
            assert len(data) == item['bytes'], item['path']
            assert hashlib.sha256(data).hexdigest() == item['sha256'], item['path']
        print(f'{archive.name}: SHA-256 and all {len(files)} custody files verified')
print('Custody verified. The runtime acceptance result remains FAIL.')
