#!/usr/bin/env python3
"""Download published evidence and verify original bytes, without running them."""
import argparse
import datetime
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-directory', type=Path, default=OUT,
                        help='New verification records; existing records are never overwritten')
    parser.add_argument('--download-directory', type=Path,
                        default=ROOT / 'build/incidental-hal-release-redownload',
                        help='New directory for unmodified downloads and original API responses')
    args = parser.parse_args()
    records = args.record_directory.resolve()
    downloads = args.download_directory.resolve()
    records.mkdir(parents=True, exist_ok=True)
    for name in ('published-release.json', 'release-download-verification.json'):
        if (records / name).exists():
            parser.error('Existing verification is frozen; choose a new --record-directory')
    plan = json.loads((OUT / 'release-plan.json').read_text(encoding='utf-8'))
    downloads.mkdir(parents=True, exist_ok=False)
    commands = []

    def command(args, output_name, timeout=60):
        with (downloads / output_name).open('xb') as output:
            result = subprocess.run(args, cwd=ROOT, stdout=output, stderr=subprocess.PIPE, timeout=timeout)
        commands.append({'command': args, 'exit_code': result.returncode,
                         'stdout': output_name, 'stderr': result.stderr.decode('utf-8', errors='strict')})
        with (downloads / 'commands.json').open('w', encoding='utf-8') as file:
            json.dump(commands, file, indent=2, sort_keys=True)
            file.write('\n')
        if result.returncode:
            raise RuntimeError(f'Command failed; original response retained: {args[:3]}')

    command(['gh', 'api', f'repos/{plan["repository"]}/releases/tags/{plan["tag"]}'], 'original-release-api.json')
    release = json.loads((downloads / 'original-release-api.json').read_text(encoding='utf-8'))
    assert release['tag_name'] == plan['tag'] and not release['draft'] and release['prerelease']
    assert release['target_commitish'] == plan['target_commit']
    remote = {asset['name']: asset for asset in release['assets']}
    expected = {asset['name']: asset for asset in plan['assets']}
    assert set(remote) == set(expected) | {'ASSET-SHA256SUMS.txt'}
    command(['gh', 'api', f'repos/{plan["repository"]}/git/ref/tags/{plan["tag"]}'], 'original-tag-api.json')
    tag = json.loads((downloads / 'original-tag-api.json').read_text(encoding='utf-8'))
    assert tag['object']['type'] == 'commit' and tag['object']['sha'] == plan['target_commit']
    command(['gh', 'release', 'download', plan['tag'], '--repo', plan['repository'], '--dir', str(downloads)],
            'download.stdout', timeout=300)
    assert (downloads / 'ASSET-SHA256SUMS.txt').read_bytes() == (OUT / 'ASSET-SHA256SUMS.txt').read_bytes()
    results = []
    revisions = {run['run_id']: run['source_revision'] for run in plan['runs']}
    for name, expected_asset in expected.items():
        path = downloads / name
        actual = digest(path)
        assert path.stat().st_size == expected_asset['bytes'] == remote[name]['size']
        assert actual == expected_asset['sha256']
        assert remote[name]['digest'] == 'sha256:' + actual
        assert remote[name]['browser_download_url'] == expected_asset['url']
        result = {'name': name, 'bytes': path.stat().st_size, 'sha256': actual,
                  'release_asset_id': remote[name]['id'], 'release_digest_matches': True,
                  'original_archive_digest_matches': True}
        with zipfile.ZipFile(path) as bundle:
            assert bundle.testzip() is None
            result['zip_crc_verified'] = True
            if expected_asset['kind'] != 'workflow-logs':
                manifest = json.loads(bundle.read('custody-manifest.json'))
                assert str(manifest['run_id']) == str(expected_asset['run_id'])
                assert manifest['source_revision'] == revisions[expected_asset['run_id']]
                entries = manifest['files']
                names = [entry['path'] for entry in entries]
                assert len(names) == len(set(names))
                assert set(names) == {info.filename for info in bundle.infolist() if not info.is_dir()} - {'custody-manifest.json'}
                for entry in entries:
                    payload = bundle.read(entry['path'])
                    assert len(payload) == entry['bytes']
                    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
                result['runner_custody_entries_verified'] = len(entries)
        results.append(result)
    write(records / 'published-release.json', {
        **{key: release[key] for key in ('id', 'tag_name', 'target_commitish', 'name', 'html_url', 'draft', 'prerelease', 'created_at', 'published_at')},
        'metadata_projection': True,
        'note': 'Selected public release fields; raw API response remains unchanged in local redownload directory.',
        'original_release_api_sha256': digest(downloads / 'original-release-api.json'),
        'original_tag_api_sha256': digest(downloads / 'original-tag-api.json'),
        'resolved_tag_commit': tag['object']['sha'],
        'assets': [{key: asset[key] for key in ('id', 'name', 'size', 'digest', 'browser_download_url', 'state')}
                   for asset in release['assets']],
    })
    write(records / 'release-download-verification.json', {
        'schema': 1, 'verified_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'verified', 'release_url': release['html_url'], 'target_commit': plan['target_commit'],
        'assets': results, 'asset_checksum_file_matches': True,
        'verifier_sha256': digest(Path(__file__)),
        'plan_sha256': digest(OUT / 'release-plan.json'),
        'commands_sha256': digest(downloads / 'commands.json'),
        'programs_executed_from_archives': False, 'audio_analyses_rerun': False,
        'note': 'Custody verification only. All three original overall acceptance results remain FAIL.',
    })
    write(downloads / 'SHA256SUMS.json', {
        str(path.relative_to(downloads)): digest(path) for path in sorted(downloads.rglob('*')) if path.is_file()})
    print(f'Verified {len(results)} published original ZIPs and all runner custody-manifest entries.')


if __name__ == '__main__':
    main()
