#!/usr/bin/env python3
"""Reassemble immutable evidence parts, verifying compressed and raw PCM hashes."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def filename(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', value):
        raise ValueError('Invalid evidence filename')
    return value


def digest(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Invalid SHA-256')
    return value


def restore(manifest_path, output_directory):
    manifest_path, output_directory = Path(manifest_path), Path(output_directory)
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError('Manifest is too large')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('version') != 1 or not 1 <= len(manifest.get('files', [])) <= 32:
        raise ValueError('Unsupported evidence manifest')
    output_directory.mkdir(parents=True, exist_ok=True)
    restored = []
    for record in manifest['files']:
        name = filename(record['name'])
        expected = digest(record['sha256'])
        raw_expected = digest(record['rawSHA256'])
        length, raw_length = record['bytes'], record['rawBytes']
        parts = record['parts']
        if not isinstance(length, int) or not isinstance(raw_length, int) or not 0 < length <= 512 * 1024 * 1024 or not 0 < raw_length <= 512 * 1024 * 1024:
            raise ValueError('Invalid evidence length')
        if not isinstance(parts, list) or not 1 <= len(parts) <= 1024:
            raise ValueError('Invalid part count')
        final = output_directory / name
        if final.exists() or final.is_symlink():
            raise FileExistsError(f'Refusing to replace {final}')
        descriptor, temporary_name = tempfile.mkstemp(prefix='.restore-', dir=output_directory)
        temporary = Path(temporary_name)
        try:
            total = 0
            compressed_hash = hashlib.sha256()
            with os.fdopen(descriptor, 'wb') as output:
                for part in parts:
                    part_path = manifest_path.parent / filename(part['name'])
                    if part_path.is_symlink() or not part_path.is_file():
                        raise ValueError(f'Missing or redirected evidence part: {part_path.name}')
                    size = part['bytes']
                    if not isinstance(size, int) or not 0 < size <= 1024 * 1024 or part_path.stat().st_size != size:
                        raise ValueError(f'Wrong size: {part_path.name}')
                    data = part_path.read_bytes()
                    if hashlib.sha256(data).hexdigest() != digest(part['sha256']):
                        raise ValueError(f'Wrong SHA-256: {part_path.name}')
                    total += len(data)
                    if total > length:
                        raise ValueError('Parts exceed declared archive length')
                    compressed_hash.update(data); output.write(data)
            if total != length or compressed_hash.hexdigest() != expected:
                raise ValueError('Reassembled archive does not match the original')
            raw_hash, raw_total = hashlib.sha256(), 0
            with gzip.open(temporary, 'rb') as stream:
                while data := stream.read(1024 * 1024):
                    raw_total += len(data)
                    if raw_total > raw_length:
                        raise ValueError('Uncompressed evidence exceeds declared length')
                    raw_hash.update(data)
            if raw_total != raw_length or raw_hash.hexdigest() != raw_expected:
                raise ValueError('Uncompressed recording does not match original PCM')
            # Exclusive hard-link publication never replaces an existing result.
            os.link(temporary, final)
            restored.append(str(final))
        finally:
            temporary.unlink(missing_ok=True)
    return restored


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    for result in restore(args.manifest, args.output_directory):
        print(result)
