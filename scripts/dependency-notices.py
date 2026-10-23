#!/usr/bin/env python3
"""Produce source-bound notices for the locked macOS/Windows desktop graph."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ['aarch64-apple-darwin', 'x86_64-pc-windows-msvc']

def generate():
    runtime = ROOT/'docs/third-party-licenses/rust-1.91.1'
    runtime_record = json.loads((runtime/'sources.json').read_text(encoding='utf-8'))
    pinned = tomllib.loads((ROOT/'rust-toolchain.toml').read_text(encoding='utf-8'))['toolchain']['channel']
    if runtime_record['toolchain'] != pinned:
        raise RuntimeError('Rust runtime notices do not match the pinned toolchain')
    for record in runtime_record['files']:
        if hashlib.sha256((runtime/record['file']).read_bytes()).hexdigest() != record['sha256']:
            raise RuntimeError('Rust runtime notice hash mismatch: '+record['file'])
    packages = {}
    for target in TARGETS:
        metadata = json.loads(subprocess.check_output([
            'cargo', 'metadata', '--locked', '--format-version', '1', '--filter-platform', target,
        ], cwd=ROOT))
        active = {n['id']: n for n in metadata['resolve']['nodes']}
        for package in metadata['packages']:
            if package['id'] not in active or package['source'] is None:
                continue
            record = packages.setdefault(package['id'], dict(package, target_features={}))
            record['target_features'][target] = sorted(active[package['id']]['features'])
    checksums = {(p['name'], p['version']): p.get('checksum') for p in tomllib.loads((ROOT/'Cargo.lock').read_text(encoding="utf-8"))['package']}
    notes = [
        'RaveLink third-party software and font notices',
        'Generated from Cargo.lock and Cargo metadata for the listed targets.',
        'First-party RaveLink code is proprietary. These dependencies retain their own licenses.',
        'Targets: '+', '.join(TARGETS),
        'All bundled license alternatives are reproduced; no third-party ownership is claimed.',
    ]
    inventory = []
    missing = []
    for package in sorted(packages.values(), key=lambda p:(p['name'],p['version'])):
        base = Path(package['manifest_path']).parent
        files = []
        for file in base.rglob('*'):
            if not file.is_file():
                continue
            name = file.name.lower()
            rel = file.relative_to(base).as_posix()
            if name.startswith(('license','licence','copying','notice','unlicense')) or (package['name']=='epaint_default_fonts' and rel.startswith('fonts/') and file.suffix=='.txt'):
                if file.stat().st_size > 256*1024:
                    raise RuntimeError(f'Unexpectedly large license: {package["name"]}/{rel}')
                try:
                    text = file.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    continue
                files.append((rel,text))
        if not files:
            cached = ROOT/'docs/third-party-licenses'/f'{package["name"]}-{package["version"]}'
            manifest = cached/'sources.json'
            if manifest.exists():
                for record in json.loads(manifest.read_text(encoding="utf-8")):
                    payload = (cached/record['file']).read_bytes()
                    if hashlib.sha256(payload).hexdigest() != record['sha256']:
                        raise RuntimeError(f'Cached license hash mismatch: {cached.name}')
                    files.append((record['url'], payload.decode('utf-8')))
        if not files and package['license'] in ['MIT', 'CC0-1.0']:
            standard = ROOT/'docs/third-party-licenses/standard'
            record = next(r for r in json.loads((standard/'sources.json').read_text(encoding="utf-8")) if r['file']==package['license']+'.txt')
            payload = (standard/record['file']).read_bytes()
            if hashlib.sha256(payload).hexdigest() != record['sha256']:
                raise RuntimeError('Standard license hash mismatch')
            files.append(('Standard SPDX text; package declares this license but ships no license file: '+record['url'],payload.decode()))
        if not files:
            missing.append(f'{package["name"]} {package["version"]}')
        notes.extend(['\n'+'='*72, f'{package["name"]} {package["version"]}',
                      f'Declared license: {package["license"]}', 'Declared authors: '+', '.join(package['authors']), f'Source: {package["repository"] or package["source"]}'])
        for rel,text in sorted(files):
            notes.extend(['\n--- '+rel+' ---',text.rstrip()])
        inventory.append({
            'name':package['name'],'version':package['version'], 'license':package['license'],
            'source':package['source'], 'repository':package['repository'], 'declared_authors':package['authors'],
            'registry_checksum':checksums[(package['name'],package['version'])],
            'target_features':package['target_features'],
            'notice_files':[{'path':rel,'sha256':hashlib.sha256(text.encode()).hexdigest()} for rel,text in sorted(files)],
        })
    if missing:
        raise RuntimeError('Missing source license text: '+', '.join(missing))
    # Some upstream license notices link to the standard grant rather than
    # reproducing it. Include the standard MIT text alongside those notices.
    notes.extend(['\nStandard MIT license text', (ROOT/'docs/third-party-licenses/standard/MIT.txt').read_text(encoding="utf-8")])
    return '\n'.join(notes)+'\n', json.dumps({'schema_version':1,'targets':TARGETS,'dependencies':inventory},indent=2)+'\n'

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    notices,inventory=generate()
    for path,content in [(ROOT/'THIRD-PARTY-NOTICES.txt',notices),(ROOT/'docs/dependencies.json',inventory)]:
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8")!=content:
                print(f'Outdated dependency record: {path.name}',file=sys.stderr); return 1
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    print('Dependency notices verified' if args.check else 'Dependency notices generated')
    return 0
if __name__=='__main__':
    sys.exit(main())
