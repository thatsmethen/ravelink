#!/usr/bin/env python3
"""Build/package/install independently named GPL RaveLink Core Audio HAL devices.

No command restarts coreaudiod. Installation/removal requires an explicit root invocation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'Drivers' / 'BlackHole'
PATCHES = ROOT / 'Drivers' / 'patches'
HAL = Path('/Library/Audio/Plug-Ins/HAL')
PREFIX = 'au.textual.ravelink.audio.'
PLUGIN_TYPE = '443ABAB8-E7B3-491A-B985-BEB9187030DB'
VERSION = '0.1.0'
BUILD_NUMBER = 1
DEFAULT_DEVICES = ['stream:Stream Mix', 'voice:Voice', 'music:Music', 'browser:Browser', 'game:Game']


def run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE)
    return result.stdout.strip()


def parse_device(value: str) -> tuple[str, str]:
    slug, sep, label = value.partition(':')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', slug):
        raise ValueError('Device ID must start with a lowercase letter, use a-z/0-9/hyphen, and be at most 48 characters')
    label = label if sep else slug.replace('-', ' ').title()
    # CFStringCreateWithFormat interprets percent signs; disallow them, newlines and control codes.
    if not label or len(label) > 80 or '%' in label or any(ord(c) < 32 or ord(c) == 127 for c in label):
        raise ValueError('Device label must contain 1–80 printable characters without percent signs')
    return slug, label


def release_version(version: str, build_number: int) -> tuple[str, int]:
    if not isinstance(version, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('Release version must be three canonical integers, e.g. 0.2.0')
    # CFBundleVersion's first component is limited to four digits. Keep package
    # receipts and bundle comparison on the same monotonic numeric scale.
    if type(build_number) is not int or not 1 <= build_number <= 9999:
        raise ValueError('Build number must be an increasing integer from 1 through 9999')
    return version, build_number


def receipt_id(slug: str) -> str:
    return PREFIX + 'package.' + parse_device(slug)[0]


def verify_upstream() -> dict:
    manifest = json.loads((UPSTREAM / 'upstream.json').read_text())
    for name, digest in manifest['files'].items():
        if hashlib.sha256((UPSTREAM / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Pinned upstream checksum mismatch: {name}')
    return manifest


def prepare_patched_source(source_dir: Path) -> dict:
    """Keep pristine corresponding source and apply only exact, hashed local patches."""
    manifest = json.loads((PATCHES / 'manifest.json').read_text())
    original = (UPSTREAM / 'BlackHole.c').read_bytes()
    if hashlib.sha256(original).hexdigest() != manifest['upstreamSourceSHA256']:
        raise ValueError('Patch input checksum mismatch')
    (source_dir / 'BlackHole.c').write_bytes(original)
    generated = source_dir / 'RaveLinkAudio.c'
    generated.write_bytes(original)
    for entry in manifest['patches']:
        name = entry['file']
        if Path(name).name != name or not name.endswith('.patch'):
            raise ValueError('Invalid patch filename')
        patch = (PATCHES / name).read_bytes()
        if hashlib.sha256(patch).hexdigest() != entry['sha256']:
            raise ValueError(f'Local patch checksum mismatch: {name}')
        (source_dir / name).write_bytes(patch)
        subprocess.run(['/usr/bin/patch', '--batch', '--fuzz=0', str(generated)],
                       input=patch, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if hashlib.sha256(generated.read_bytes()).hexdigest() != manifest['patchedSourceSHA256']:
        raise ValueError('Patched source checksum mismatch')
    (source_dir / 'patches.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def icon() -> bytes:
    """Original 256px icon: three pale faders on a dark teal field, in an ICNS PNG entry."""
    size = 256
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            color = (17, 35, 42, 255)
            for column, handle in ((64, 92), (128, 160), (192, 116)):
                if abs(x - column) < 4 and 44 < y < 212:
                    color = (96, 155, 166, 255)
                if abs(x - column) < 20 and abs(y - handle) < 12:
                    color = (126, 231, 202, 255)
            pixels.extend(color)
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(pixels), 9)) + chunk(b'IEND', b'')
    return b'icns' + struct.pack('>I', len(png) + 16) + b'ic08' + struct.pack('>I', len(png) + 8) + png


def build_one(destination: Path, device: tuple[str, str], channels: int, archs: list[str], identity: str,
              manifest: dict, version: str = VERSION, build_number: int = BUILD_NUMBER) -> dict:
    release_version(version, build_number)
    slug, label = device
    bundle_id = PREFIX + slug
    driver_name = 'RaveLink.' + slug
    factory = str(uuid.uuid5(uuid.NAMESPACE_DNS, bundle_id)).upper()
    bundle_name = f'RaveLink-{slug}.driver'
    final = destination / bundle_name
    if final.exists() or final.is_symlink():
        raise ValueError(f'Output exists, choose a fresh output directory: {final}')
    with tempfile.TemporaryDirectory(prefix='.ravelink-', dir=destination) as scratch:
        scratch = Path(scratch)
        bundle = scratch / bundle_name
        contents = bundle / 'Contents'
        executable = contents / 'MacOS' / 'RaveLinkAudio'
        resources = contents / 'Resources'
        source_dir = resources / 'Source'
        executable.parent.mkdir(parents=True)
        source_dir.mkdir(parents=True)
        config = {
            'BlackHole_Create': 'RaveLink_Create',
            'kDriver_Name': json.dumps(driver_name),
            'kDevice_Name': json.dumps('RaveLink ' + label, ensure_ascii=False),
            'kDevice2_Name': json.dumps('RaveLink ' + label + ' (hidden)', ensure_ascii=False),
            'kPlugIn_BundleID': json.dumps(bundle_id),
            'kPlugIn_Icon': '"RaveLink.icns"',
            'kManufacturer_Name': '"RaveLink project"',
            'kHas_Driver_Name_Format': '0',
            'kNumber_Of_Channels': str(channels),
            'kDevice2_IsHidden': '1',
            'kDevice2_HasInput': '0',
            'kDevice2_HasOutput': '0',
            # All gain/mute belongs to the app, avoiding accidental double attenuation.
            'kEnableVolumeControl': '0',
            'kCanBeDefaultSystemDevice': '0',
        }
        header = ''.join(f'#define {key} {value}\n' for key, value in config.items())
        (source_dir / 'config.h').write_text(header)
        patches = prepare_patched_source(source_dir)
        shutil.copy2(UPSTREAM / 'LICENSE', resources / 'LICENSE-BlackHole.txt')
        shutil.copy2(UPSTREAM / 'upstream.json', source_dir / 'upstream.json')
        plist = {
            'CFBundleDevelopmentRegion': 'en',
            'CFBundleExecutable': 'RaveLinkAudio',
            'CFBundleIdentifier': bundle_id,
            'CFBundleInfoDictionaryVersion': '6.0',
            'CFBundleName': 'RaveLink ' + label,
            'CFBundlePackageType': 'BNDL',
            'CFBundleShortVersionString': version,
            'CFBundleVersion': str(build_number),
            'CFBundleSupportedPlatforms': ['MacOSX'],
            'CFBundleIconFile': 'RaveLink.icns',
            'LSMinimumSystemVersion': '12.0',
            'CFPlugInFactories': {factory: 'RaveLink_Create'},
            'CFPlugInTypes': {PLUGIN_TYPE: [factory]},
        }
        (contents / 'Info.plist').write_bytes(plistlib.dumps(plist, sort_keys=True))
        (resources / 'RaveLink.icns').write_bytes(icon())
        compile_args = ['xcrun', 'clang', '-bundle', '-O2', '-fblocks', '-Wno-format-extra-args', '-mmacosx-version-min=12.0']
        for arch in archs:
            compile_args += ['-arch', arch]
        compile_args += ['-include', str(source_dir / 'config.h'), str(source_dir / 'RaveLinkAudio.c'), '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-framework', 'Accelerate', '-o', str(executable)]
        run(compile_args)
        metadata = {
            'id': slug, 'name': plist['CFBundleName'], 'bundle': bundle_name,
            'bundleID': bundle_id, 'deviceUID': driver_name + '_UID',
            'factoryUUID': factory, 'channels': channels, 'architectures': archs,
            'minimumMacOS': '12.0', 'upstream': manifest, 'localPatches': patches,
            'codeSigning': 'ad-hoc' if identity == '-' else identity,
            'notarized': False, 'version': version, 'buildNumber': build_number,
        }
        (resources / 'build-info.json').write_text(json.dumps(metadata, indent=2) + '\n')
        (source_dir / 'BUILD.txt').write_text(
            'RaveLink virtual device, GPL-3.0-only. Derived from BlackHole by Existential Audio.\n'
            'Full corresponding C source and configuration are included here.\n'
            'From this directory, build with Apple Command Line Tools:\n'
            'xcrun clang -bundle -O2 -fblocks -Wno-format-extra-args -mmacosx-version-min=12.0 '
            + ' '.join('-arch ' + arch for arch in archs)
            + ' -include config.h RaveLinkAudio.c -framework CoreAudio -framework CoreFoundation -framework Accelerate -o RaveLinkAudio\n'
            'Place output at Contents/MacOS/RaveLinkAudio, preserving the included Info.plist and resources,\n'
            'then codesign --force --sign - /path/to/RaveLink-ID.driver\n'
            'Changes: independent name, UID, factory, bundle ID; original icon; hidden mirror disabled;\n'
            'device gain disabled; system-alert default eligibility disabled; box name follows driver name.\n'
            'Hashed local patch also validates each ring frame against its timeline/generation;\n'
            'missing, overwritten or concurrent in-flight frames are silent. See patches.json.\n'
            'Pristine BlackHole.c, exact patch, and patched RaveLinkAudio.c are all included.\n'
        )
        sign = ['/usr/bin/codesign', '--force', '--sign', identity]
        if identity != '-':
            sign += ['--timestamp', '--options', 'runtime']
        run(sign + [str(bundle)])
        validate_bundle(bundle)
        bundle.rename(final)
        metadata['path'] = str(final)
        return metadata


def validate_bundle(bundle: Path) -> dict:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError(f'Not a driver directory: {bundle}')
    if any(p.is_symlink() for p in bundle.rglob('*')):
        raise ValueError('Driver bundles must not contain symbolic links')
    info = plistlib.loads((bundle / 'Contents' / 'Info.plist').read_bytes())
    data = json.loads((bundle / 'Contents' / 'Resources' / 'build-info.json').read_text())
    slug, _ = parse_device(data['id'])
    if bundle.name != f'RaveLink-{slug}.driver' or info['CFBundleIdentifier'] != PREFIX + slug or data['bundleID'] != PREFIX + slug:
        raise ValueError('Driver identity mismatch')
    if info['CFBundleExecutable'] != 'RaveLinkAudio' or info['CFBundlePackageType'] != 'BNDL':
        raise ValueError('Unexpected driver structure')
    # Initial development bundles omitted buildNumber but used CFBundleVersion1.
    version, build_number = release_version(data['version'], data.get('buildNumber', int(str(info['CFBundleVersion']))))
    if info['CFBundleShortVersionString'] != version or info['CFBundleVersion'] != str(build_number):
        raise ValueError('Driver release version mismatch')
    data['buildNumber'] = build_number
    factory = str(uuid.uuid5(uuid.NAMESPACE_DNS, PREFIX + slug)).upper()
    if info['CFPlugInFactories'] != {factory: 'RaveLink_Create'} or info['CFPlugInTypes'] != {PLUGIN_TYPE: [factory]}:
        raise ValueError('Driver factory identity mismatch')
    executable = bundle / 'Contents' / 'MacOS' / 'RaveLinkAudio'
    actual_archs = run(['xcrun', 'lipo', '-archs', str(executable)]).split()
    if sorted(actual_archs) != sorted(data['architectures']):
        raise ValueError('Architecture mismatch')
    if '_RaveLink_Create' not in run(['xcrun', 'nm', '-gU', str(executable)]):
        raise ValueError('Missing audio plug-in factory')
    run(['/usr/bin/codesign', '--verify', '--strict', str(bundle)])
    return data


def require_root() -> None:
    if os.geteuid() != 0:
        raise ValueError('This command requires an explicit administrator invocation using sudo. No changes made.')
    if HAL.is_symlink() or HAL.resolve() != HAL:
        raise ValueError('HAL install directory must not be a symbolic link')


def install(bundles: list[Path]) -> None:
    require_root()
    if len({bundle.name for bundle in bundles}) != len(bundles):
        raise ValueError('Duplicate install destinations')
    for bundle in bundles:
        validate_bundle(bundle)
        target = HAL / bundle.name
        if target.exists() or target.is_symlink():
            raise ValueError(f'Refusing to replace existing driver {target}; explicitly uninstall it first')
    HAL.mkdir(parents=True, exist_ok=True)
    for bundle in bundles:
        with tempfile.TemporaryDirectory(prefix='.ravelink-install-', dir=HAL) as staging:
            stage = Path(staging) / bundle.name
            shutil.copytree(bundle, stage)
            validate_bundle(stage)
            for path in [stage, *stage.rglob('*')]:
                os.chown(path, 0, 0)
                path.chmod(0o755 if path.is_dir() or path.name == 'RaveLinkAudio' else 0o644)
            stage.rename(HAL / bundle.name)
        print(f'Installed {HAL / bundle.name}')
    print('Restart macOS after closing audio apps to activate these devices. Audio services were not restarted.')


def uninstall(ids: list[str]) -> None:
    slugs = [parse_device(value)[0] for value in ids]
    if len(set(slugs)) != len(slugs):
        raise ValueError('Duplicate uninstall device IDs; no devices removed')
    require_root()
    targets = []
    for slug in slugs:
        target = HAL / f'RaveLink-{slug}.driver'
        if not target.exists():
            raise ValueError(f'Not installed: {target}')
        validate_bundle(target)
        targets.append(target)
    for target in targets:
        shutil.rmtree(target)
        print(f'Removed {target}')
    for slug in slugs:
        receipt = receipt_id(slug)
        present = subprocess.run(['/usr/sbin/pkgutil', '--pkg-info', receipt],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if present.returncode == 0:
            run(['/usr/sbin/pkgutil', '--forget', receipt])
    print('Restart macOS after closing audio apps. Audio services were not restarted.')


def preinstall_script(releases: list[tuple[str, int]]) -> str:
    """Every component checks the entire proposed set before any payload changes."""
    checks = []
    for slug, build_number in releases:
        slug = parse_device(slug)[0]
        release_version(VERSION, build_number)
        checks.append(f"check_device '{slug}' '{build_number}'")
    return '''#!/bin/bash
set -euo pipefail
volume="${3:-/}"
case "$volume" in /*) ;; *) echo 'Invalid Installer target volume' >&2; exit 1 ;; esac
volume=$(cd "$volume" && pwd -P)
ancestor="${volume%/}"
for component in Library Audio Plug-Ins HAL; do
  ancestor="$ancestor/$component"
  if [[ -L "$ancestor" || ( -e "$ancestor" && ! -d "$ancestor" ) ]]; then
    echo "Refusing unexpected HAL parent path: $ancestor" >&2; exit 1
  fi
done
hal="${volume%/}/Library/Audio/Plug-Ins/HAL"
check_device() {
  local slug="$1" incoming="$2" target="$hal/RaveLink-$1.driver" identity installed
  if [[ -L "$target" ]]; then echo "Refusing symbolic-link driver: $target" >&2; exit 1; fi
  if [[ ! -e "$target" ]]; then return; fi
  if [[ ! -d "$target" || -L "$target/Contents" || -L "$target/Contents/Info.plist" ]]; then
    echo "Refusing unexpected installed driver structure: $target" >&2; exit 1
  fi
  identity=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$target/Contents/Info.plist")
  if [[ "$identity" != "au.textual.ravelink.audio.$slug" ]]; then
    echo "Refusing to replace another bundle at $target" >&2; exit 1
  fi
  installed=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$target/Contents/Info.plist")
  if [[ ! "$installed" =~ ^[1-9][0-9]{0,3}$ ]]; then
    echo "Unsupported installed build number at $target; inspect it before replacing it" >&2; exit 1
  fi
  if (( installed > incoming )); then
    echo "Refusing driver downgrade: $slug installed build $installed, package build $incoming. Explicitly uninstall first for an intentional downgrade." >&2
    exit 1
  fi
}
''' + '\n'.join(checks) + '\n'


def package(bundles: list[Path], output: Path, identity: str | None) -> None:
    if not bundles:
        raise ValueError('Specify at least one driver bundle')
    if output.exists() or output.is_symlink():
        raise ValueError('Package output already exists')
    metadata = [validate_bundle(bundle) for bundle in bundles]
    ids = [data['id'] for data in metadata]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate devices')
    architectures = set.intersection(*(set(data['architectures']) for data in metadata))
    if not architectures:
        raise ValueError('Packaged devices must support at least one common architecture')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ravelink-package-') as staging:
        staging = Path(staging)
        components = staging / 'components'
        components.mkdir()
        scripts = staging / 'scripts'
        scripts.mkdir()
        releases = [(data['id'], data.get('buildNumber', 1)) for data in metadata]
        (scripts / 'preinstall').write_text(preinstall_script(releases))
        (scripts / 'preinstall').chmod(0o755)
        run(['/usr/bin/xattr', '-rc', str(scripts)])
        packages = []
        for bundle, data in zip(bundles, metadata):
            payload = staging / ('payload-' + data['id'])
            payload.mkdir()
            shutil.copytree(bundle, payload / bundle.name)
            # Avoid host-specific extended attributes and AppleDouble sidecars.
            run(['/usr/bin/xattr', '-rc', str(payload)])
            component_plist = staging / (data['id'] + '.plist')
            run(['/usr/bin/pkgbuild', '--analyze', '--root', str(payload), str(component_plist)])
            definitions = plistlib.loads(component_plist.read_bytes())
            for component in definitions:
                # Installer compares the marketing version before CFBundleVersion,
                # which can silently skip a newer build and still advance receipts.
                # The mandatory full-set preinstall owns monotonic build ordering.
                component.update(BundleIsRelocatable=False, BundleHasStrictIdentifier=True,
                                 BundleIsVersionChecked=False, BundleOverwriteAction='upgrade')
            component_plist.write_bytes(plistlib.dumps(definitions))
            component_package = components / (data['id'] + '.pkg')
            run(['/usr/bin/pkgbuild', '--root', str(payload), '--component-plist', str(component_plist),
                 '--scripts', str(scripts), '--ownership', 'recommended', '--install-location', str(HAL),
                 '--identifier', receipt_id(data['id']), '--version', str(data.get('buildNumber', 1)), str(component_package)])
            packages.append(component_package)
        distribution = staging / 'Distribution'
        synthesize = ['/usr/bin/productbuild', '--synthesize']
        for component_package in packages:
            synthesize += ['--package', str(component_package)]
        run(synthesize + [str(distribution)])
        tree = ET.parse(distribution)
        root = tree.getroot()
        title = root.find('title')
        if title is None:
            title = ET.SubElement(root, 'title')
        title.text = 'RaveLink virtual devices'
        options = root.find('options')
        if options is None:
            options = ET.SubElement(root, 'options')
        options.set('customize', 'never')
        options.set('rootVolumeOnly', 'true')
        options.set('hostArchitectures', ','.join(sorted(architectures)))
        domains = root.find('domains')
        if domains is None:
            domains = ET.SubElement(root, 'domains')
        domains.attrib.update(enable_localSystem='true', enable_currentUserHome='false', enable_anywhere='false')
        minimum_os = max((data['minimumMacOS'] for data in metadata), key=lambda value: tuple(map(int, value.split('.'))))
        volume_check = root.find('volume-check')
        if volume_check is None:
            volume_check = ET.SubElement(root, 'volume-check', script='true')
        allowed_os = volume_check.find('allowed-os-versions')
        if allowed_os is None:
            allowed_os = ET.SubElement(volume_check, 'allowed-os-versions')
        else:
            allowed_os.clear()
        ET.SubElement(allowed_os, 'os-version', min=minimum_os)
        for reference in root.findall('pkg-ref'):
            if reference.text and reference.text.strip():
                reference.set('onConclusion', 'RequireRestart')
        tree.write(distribution, encoding='utf-8', xml_declaration=True)
        args = ['/usr/bin/productbuild', '--distribution', str(distribution), '--package-path', str(components)]
        if identity:
            args += ['--sign', identity, '--timestamp']
        run(args + [str(output)])
        # Check the archived bytes, not only the staging folder.
        expanded = staging / 'expanded'
        run(['/usr/sbin/pkgutil', '--expand-full', str(output), str(expanded)])
        archived = sorted(expanded.rglob('*.driver'))
        if len(archived) != len(bundles) or {bundle.name for bundle in archived} != {bundle.name for bundle in bundles}:
            raise ValueError('Package is missing driver bundles')
        for bundle in archived:
            validate_bundle(bundle)
        receipts = {ET.parse(path).getroot().get('identifier'): ET.parse(path).getroot().get('version')
                    for path in expanded.rglob('PackageInfo')}
        if receipts != {receipt_id(slug): str(build_number) for slug, build_number in releases}:
            raise ValueError('Package receipt identity or version mismatch')
        if identity:
            run(['/usr/sbin/pkgutil', '--check-signature', str(output)])
    print(f'Created {output}. macOS restart required after installation; package never restarts audio services.')
    print('Package is unsigned.' if identity is None else 'Package signed; notarization is a separate release step.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build', help='Build unique named virtual devices; never installs them')
    build.add_argument('--device', action='append', metavar='ID:LABEL', help='Repeat to add devices; default stream, voice, music, browser, game')
    build.add_argument('--channels', type=int, default=2)
    build.add_argument('--arch', choices=['arm64', 'x86_64'], action='append')
    build.add_argument('--output', type=Path, default=ROOT / 'build' / 'virtual-devices')
    build.add_argument('--sign', default='-', help='Signing identity; default ad-hoc')
    build.add_argument('--version', default=VERSION, help='Release version, e.g. 0.2.0')
    build.add_argument('--build-number', type=int, default=BUILD_NUMBER, help='Increasing CFBundleVersion and package receipt version (1–9999)')
    for name in ['validate', 'install', 'package']:
        cmd = commands.add_parser(name)
        cmd.add_argument('bundles', nargs='+', type=Path)
        if name == 'package':
            cmd.add_argument('--output', required=True, type=Path)
            cmd.add_argument('--sign', help='Developer ID Installer identity')
    remove = commands.add_parser('uninstall')
    remove.add_argument('ids', nargs='+', help='Only RaveLink device IDs, e.g. stream music')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            release_version(args.version, args.build_number)
            if not 2 <= args.channels <= 256 or args.channels % 2:
                raise ValueError('Channels must be an even integer from 2–256; create additional device IDs for more buses')
            devices = [parse_device(value) for value in (args.device or DEFAULT_DEVICES)]
            if len({device[0] for device in devices}) != len(devices):
                raise ValueError('Duplicate device IDs')
            manifest = verify_upstream()
            args.output = args.output.resolve()
            args.output.mkdir(parents=True, exist_ok=True)
            if any((args.output / f'RaveLink-{slug}.driver').exists() for slug, _ in devices):
                raise ValueError('An output driver already exists; choose a fresh output directory')
            archs = list(dict.fromkeys(args.arch or ['arm64', 'x86_64']))
            result = [build_one(args.output, device, args.channels, archs, args.sign, manifest,
                                args.version, args.build_number) for device in devices]
            (args.output / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result, indent=2))
        elif args.command == 'validate':
            print(json.dumps([validate_bundle(path) for path in args.bundles], indent=2))
        elif args.command == 'install':
            install(args.bundles)
        elif args.command == 'uninstall':
            uninstall(args.ids)
        elif args.command == 'package':
            package(args.bundles, args.output.resolve(), args.sign)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
