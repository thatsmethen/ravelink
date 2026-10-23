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
import zlib

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'Drivers' / 'BlackHole'
HAL = Path('/Library/Audio/Plug-Ins/HAL')
PREFIX = 'au.textual.ravelink.audio.'
PLUGIN_TYPE = '443ABAB8-E7B3-491A-B985-BEB9187030DB'
VERSION = '0.1.0'
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


def verify_upstream() -> dict:
    manifest = json.loads((UPSTREAM / 'upstream.json').read_text())
    for name, digest in manifest['files'].items():
        if hashlib.sha256((UPSTREAM / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Pinned upstream checksum mismatch: {name}')
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


def build_one(destination: Path, device: tuple[str, str], channels: int, archs: list[str], identity: str, manifest: dict) -> dict:
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
            'kDevice_Name': json.dumps('RaveLink ' + label),
            'kDevice2_Name': json.dumps('RaveLink ' + label + ' (hidden)'),
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
        source = (UPSTREAM / 'BlackHole.c').read_text()
        # The only source modification removes the upstream box branding; public symbols are renamed via config.
        needle = 'CFSTR("BlackHole Box")'
        if source.count(needle) != 1:
            raise ValueError('Unexpected upstream box definition')
        source = source.replace(needle, 'CFSTR(kDriver_Name " Box")')
        (source_dir / 'RaveLinkAudio.c').write_text(source)
        shutil.copy2(UPSTREAM / 'BlackHole.c', source_dir / 'BlackHole.c')
        shutil.copy2(UPSTREAM / 'LICENSE', resources / 'LICENSE-BlackHole.txt')
        shutil.copy2(UPSTREAM / 'upstream.json', source_dir / 'upstream.json')
        plist = {
            'CFBundleDevelopmentRegion': 'en',
            'CFBundleExecutable': 'RaveLinkAudio',
            'CFBundleIdentifier': bundle_id,
            'CFBundleInfoDictionaryVersion': '6.0',
            'CFBundleName': 'RaveLink ' + label,
            'CFBundlePackageType': 'BNDL',
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': '1',
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
            'minimumMacOS': '12.0', 'upstream': manifest,
            'codeSigning': 'ad-hoc' if identity == '-' else identity,
            'notarized': False, 'version': VERSION,
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
    require_root()
    targets = []
    for value in ids:
        slug, _ = parse_device(value)
        target = HAL / f'RaveLink-{slug}.driver'
        if not target.exists():
            raise ValueError(f'Not installed: {target}')
        validate_bundle(target)
        targets.append(target)
    for target in targets:
        shutil.rmtree(target)
        print(f'Removed {target}')
    print('Restart macOS after closing audio apps. Audio services were not restarted.')


def package(bundles: list[Path], output: Path, identity: str | None) -> None:
    if output.exists():
        raise ValueError('Package output already exists')
    ids = [validate_bundle(bundle)['id'] for bundle in bundles]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate devices')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ravelink-package-') as staging:
        staging = Path(staging)
        payload = staging / 'payload'
        payload.mkdir()
        for bundle in bundles:
            shutil.copytree(bundle, payload / bundle.name)
        # Generated build provenance is host-specific and causes pkgbuild AppleDouble sidecars.
        run(['/usr/bin/xattr', '-rc', str(payload)])
        # Use component property list to stop Installer relocating bundles outside HAL.
        components = staging / 'components.plist'
        run(['/usr/bin/pkgbuild', '--analyze', '--root', str(payload), str(components)])
        definitions = plistlib.loads(components.read_bytes())
        for component in definitions:
            component['BundleIsRelocatable'] = False
            component['BundleHasStrictIdentifier'] = True
        components.write_bytes(plistlib.dumps(definitions))
        args = ['/usr/bin/pkgbuild', '--root', str(payload), '--component-plist', str(components), '--ownership', 'recommended', '--install-location', str(HAL), '--identifier', PREFIX + 'package', '--version', VERSION]
        if identity:
            args += ['--sign', identity]
        run(args + [str(output)])
        # Check the archived bytes, not only the staging folder.
        expanded = staging / 'expanded'
        run(['/usr/sbin/pkgutil', '--expand-full', str(output), str(expanded)])
        archived = sorted((expanded / 'Payload').glob('*.driver'))
        if {bundle.name for bundle in archived} != {bundle.name for bundle in bundles}:
            raise ValueError('Package is missing driver bundles')
        for bundle in archived:
            validate_bundle(bundle)
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
            result = [build_one(args.output, device, args.channels, archs, args.sign, manifest) for device in devices]
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
