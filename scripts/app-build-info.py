#!/usr/bin/env python3
"""Record the app's exact build inputs and reject sources changed during a build."""
import argparse
import datetime
import hashlib
import json
import plistlib
import re
import subprocess
from pathlib import Path


SINGLE_INPUTS = ('Package.swift', 'Package.resolved', 'LICENSE',
                 'scripts/build-app.sh', 'scripts/app-build-info.py', 'scripts/make-icon.swift')


def source_inputs(root):
    paths = [root / name for name in SINGLE_INPUTS if (root / name).exists()]
    for directory in ('Sources', 'Resources'):
        paths.extend(path for path in (root / directory).rglob('*') if path.is_file() or path.is_symlink())
    records = {}
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError(f'Build input must not be a symlink: {path.relative_to(root)}')
        records[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return records


def versions(version, build):
    if not re.fullmatch(r'(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})', version):
        raise ValueError('APP_VERSION must contain three numeric components of at most four digits, for example 0.1.0')
    if not re.fullmatch(r'[1-9][0-9]{0,9}', build) or int(build) > 2147483647:
        raise ValueError('APP_BUILD_NUMBER must be a positive integer no larger than 2147483647')
    return version, build


def prepare(root, version, build, configuration, architectures):
    info = plistlib.loads((root / 'Resources/Info.plist').read_bytes())
    version, build = versions(version or info['CFBundleShortVersionString'], build or info['CFBundleVersion'])
    if configuration not in ('debug', 'release') or not architectures or set(architectures) - {'arm64', 'x86_64'}:
        raise ValueError('Invalid build configuration or architecture')
    inputs = source_inputs(root)
    source_paths = list(SINGLE_INPUTS) + ['Sources', 'Resources']
    revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all', '--', *source_paths], text=True)
    return dict(schemaVersion=1, sourceRevision=revision, sourceModified=bool(status),
                sourceInputs=inputs, sourceTreeSHA256=hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                version=version, buildNumber=build, configuration=configuration, architectures=architectures,
                preparedAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                notarization='not established by this build',
                swiftVersion=subprocess.check_output(['swift', '--version'], text=True).strip())


def finish(root, record, app):
    if record['sourceInputs'] != source_inputs(root):
        raise ValueError('Build inputs changed during compilation. The previous app was preserved; build again from stable sources.')
    info_path = app / 'Contents/Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    info['CFBundleShortVersionString'], info['CFBundleVersion'] = versions(record['version'], record['buildNumber'])
    info_path.write_bytes(plistlib.dumps(info))
    resources = app / 'Contents/Resources'
    resources.mkdir(parents=True, exist_ok=True)
    (resources / 'BuildInfo.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='operation', required=True)
    start = sub.add_parser('prepare')
    start.add_argument('--version', default='')
    start.add_argument('--build-number', default='')
    start.add_argument('--configuration', required=True)
    start.add_argument('--architectures', nargs='+', required=True)
    start.add_argument('--record', type=Path, required=True)
    end = sub.add_parser('finish')
    end.add_argument('--record', type=Path, required=True)
    end.add_argument('--app', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == 'prepare':
            record = prepare(args.root, args.version, args.build_number, args.configuration, args.architectures)
            args.record.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        else:
            finish(args.root, json.loads(args.record.read_text()), args.app)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')
