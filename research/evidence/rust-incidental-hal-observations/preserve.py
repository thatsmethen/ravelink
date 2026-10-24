#!/usr/bin/env python3
"""Preserve compact metadata from frozen local collections; never rerun audio.

Run from the repository root. Input ZIPs remain byte-for-byte unchanged. The
separate build staging directory is suitable for the named evidence release.
Existing outputs are never overwritten. Python standard library only.
"""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
STAGE = ROOT / 'build/incidental-hal-release-assets'
RUNS = (40044311801, 40045101519, 40046044508)
TAG = 'evidence-incidental-hal-20261024'
TARGET = 'db639ffefcb49020b9c0cea08d5ca03b8bfa2cf0'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write('\n')


def main():
    STAGE.mkdir(exist_ok=False)
    assets, runs = [], []
    for run_id in RUNS:
        src = ROOT / f'build/rust-hal-failed-{run_id}'
        destination = OUT / str(run_id)
        destination.mkdir(exist_ok=False)
        original_manifest = read(src / 'PRESERVATION-SHA256SUMS.json')
        for relative, expected in original_manifest.items():
            if digest(src / relative) != expected:
                raise ValueError(f'Frozen local evidence changed: {run_id}/{relative}')
        collection = read(src / 'collection.json')
        verification = read(src / 'custody-verification.json')
        run = read(src / 'run.json')
        jobs = read(src / 'jobs.json')
        assert collection['conclusion'] == run['conclusion'] == 'failure'
        assert verification['all_custody_manifests_verified']
        projection = {key: run[key] for key in (
            'id', 'head_sha', 'head_branch', 'event', 'status', 'conclusion',
            'run_attempt', 'workflow_id', 'html_url', 'created_at', 'updated_at')}
        projection['source_tree'] = verification['source_tree']
        projection['metadata_projection'] = True
        projection['note'] = 'Selected fields from original run API response; author/committer identity omitted. Raw original remains unchanged in local collection.'
        projection['original_api_sha256'] = {
            name: digest(src / name) for name in ('run.json', 'jobs.json', 'artifacts.json')}
        projection['jobs'] = [{
            **{key: job[key] for key in ('id', 'name', 'status', 'conclusion', 'started_at', 'completed_at', 'html_url')},
            'steps': job['steps'],
        } for job in jobs['jobs']]
        write(destination / 'run-metadata.json', projection)
        for name in ('collection.json', 'custody-verification.json', 'PRESERVATION.md'):
            target = destination / name
            with target.open('xb') as output:
                output.write((src / name).read_bytes())
        write(destination / 'original-local-files.json', {
            'local_collection': str(src.relative_to(ROOT)),
            'files_sha256': original_manifest,
            'manifest_sha256': digest(src / 'PRESERVATION-SHA256SUMS.json'),
            'note': 'Hashes of original local collection and extracted reports. The original ZIP assets contain all original artifact bytes, including WAV data.'})
        run_assets = []
        for archive in collection['archives']:
            kind = 'workflow-logs' if archive['name'] == 'logs' else ('runtime-evidence' if 'runtime' in archive['name'] else 'hal-evidence')
            asset_name = f'run-{run_id}-{kind}.zip'
            source = src / archive['archive']
            assert source.stat().st_size == archive['bytes']
            assert digest(source) == archive['sha256']
            shutil.copyfile(source, STAGE / asset_name)
            assert digest(STAGE / asset_name) == archive['sha256']
            item = {
                'name': asset_name, 'run_id': run_id, 'kind': kind,
                'bytes': archive['bytes'], 'sha256': archive['sha256'],
                'original_local_archive': str(source.relative_to(ROOT)),
                'original_artifact_name': archive['name'],
                'original_github_digest': archive['github_digest'],
                'url': f'https://github.com/thatsmethen/ravelink/releases/download/{TAG}/{asset_name}',
                'original_bytes_unchanged': True,
            }
            assets.append(item)
            run_assets.append(asset_name)
        runs.append({'run_id': run_id, 'conclusion': 'FAIL',
                     'source_revision': run['head_sha'], 'source_tree': verification['source_tree'],
                     'url': run['html_url'], 'assets': run_assets})
    write(OUT / 'release-plan.json', {
        'schema': 1, 'repository': 'thatsmethen/ravelink', 'tag': TAG,
        'target_commit': TARGET, 'prerelease': True,
        'runs': runs, 'assets': assets,
        'note': 'Independent incidental failed observations. Release target is an archive anchor, not a claim that all runs used that revision. No rerun, rescore, threshold change or causal attribution.'})
    print(f'Prepared {len(assets)} original ZIP assets; {sum(a["bytes"] for a in assets)} bytes total.')


if __name__ == '__main__':
    main()
