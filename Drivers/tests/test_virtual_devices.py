# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'virtual-devices.py'
spec = importlib.util.spec_from_file_location('virtual_devices', SCRIPT)
virtual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(virtual)


class DriverConfigurationTests(unittest.TestCase):
    def test_pinned_source_hashes(self):
        self.assertEqual(virtual.verify_upstream()['commit'], '561d934c77a1fa64987e01ccabe890fed30e181f')

    def test_exact_local_patch_and_corresponding_source(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            manifest = virtual.prepare_patched_source(source)
            self.assertEqual((source / 'BlackHole.c').read_bytes(), (virtual.UPSTREAM / 'BlackHole.c').read_bytes())
            self.assertEqual(hashlib.sha256((source / 'RaveLinkAudio.c').read_bytes()).hexdigest(), manifest['patchedSourceSHA256'])
            self.assertTrue((source / 'patches.json').is_file())
            for entry in manifest['patches']:
                self.assertEqual(hashlib.sha256((source / entry['file']).read_bytes()).hexdigest(), entry['sha256'])

    def test_modified_patch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(virtual.PATCHES, root / 'patches')
            source = root / 'source'; source.mkdir()
            with (root / 'patches/0001-frame-validity.patch').open('a') as file:
                file.write('\n')
            with patch.object(virtual, 'PATCHES', root / 'patches'), self.assertRaisesRegex(ValueError, 'patch checksum'):
                virtual.prepare_patched_source(source)

    def test_stable_id_and_editable_label(self):
        self.assertEqual(virtual.parse_device('podcast:My Show'), ('podcast', 'My Show'))
        self.assertEqual(virtual.parse_device('podcast'), ('podcast', 'Podcast'))

    def test_bad_ids_are_rejected(self):
        for value in ['../BlackHole2ch', 'foo/bar', 'Foo', '0a', 'x' * 49, '', 'foo;echo']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                virtual.parse_device(value)

    def test_format_injection_and_controls_are_rejected(self):
        for value in ['music:%s', 'music:', 'music:bad\nlabel', 'music:bad\x00label', 'music:' + 'x' * 81]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                virtual.parse_device(value)

    def test_invalid_channel_counts_fail_before_build(self):
        for count in ['0', '-2', '3', '258', '4294967296']:
            result = subprocess.run([str(SCRIPT), 'build', '--channels', count], text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn('Channels must', result.stderr)

    def test_duplicate_id_fails_before_build(self):
        result = subprocess.run([str(SCRIPT), 'build', '--device', 'same:One', '--device', 'same:Two'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Duplicate device IDs', result.stderr)

    def test_no_admin_install(self):
        if virtual.os.geteuid() == 0:
            self.skipTest('Root process; do not execute installation as a test')
        result = subprocess.run([str(SCRIPT), 'install', '/does-not-exist'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('explicit administrator invocation', result.stderr)

    def test_built_bundles_and_isolation(self):
        with tempfile.TemporaryDirectory(prefix='ravelink-driver-test-') as directory:
            directory = Path(directory)
            output = directory / 'devices'
            subprocess.run([str(SCRIPT), 'build', '--device', 'test-one:Test "One" 🎵', '--device', 'test-two:Test Two', '--output', str(output)], stdout=subprocess.DEVNULL, check=True)
            bundles = sorted(output.glob('*.driver'))
            self.assertEqual(len(bundles), 2)
            metadata = [virtual.validate_bundle(bundle) for bundle in bundles]
            self.assertNotEqual(metadata[0]['factoryUUID'], metadata[1]['factoryUUID'])
            self.assertNotEqual(metadata[0]['deviceUID'], metadata[1]['deviceUID'])
            self.assertEqual(metadata[0]['architectures'], ['arm64', 'x86_64'])
            self.assertEqual(metadata[0]['name'], 'RaveLink Test "One" 🎵')
            executable = directory / 'driver-contract'
            subprocess.run(['xcrun', 'clang', '-O2', '-Wall', '-Wextra', str(ROOT / 'Drivers/tests/driver_contract.c'), '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-o', str(executable)], check=True)
            args = [str(executable)]
            for bundle, info in zip(bundles, metadata):
                args += [str(bundle / 'Contents/MacOS/RaveLinkAudio'), info['deviceUID'], str(info['channels'])]
            subprocess.run(args, check=True)
            validity = directory / 'driver-validity-contract'
            subprocess.run(['xcrun', 'clang', '-O2', '-Wall', '-Wextra', str(ROOT / 'Drivers/tests/driver_validity_contract.c'), '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-o', str(validity)], check=True)
            for bundle, info in zip(bundles, metadata):
                self.assertEqual(info['localPatches'], json.loads((virtual.PATCHES / 'manifest.json').read_text()))
                subprocess.run([str(validity), str(bundle / 'Contents/MacOS/RaveLinkAudio'), info['deviceUID'], str(info['channels'])], check=True, timeout=30)
            # Signed bundle tampering must fail validation before install.
            with (bundles[0] / 'Contents/Resources/build-info.json').open('a') as file:
                file.write(' ')
            with self.assertRaises(subprocess.CalledProcessError):
                virtual.validate_bundle(bundles[0])
            # Refuse symlink payloads, even when the target is otherwise valid.
            (bundles[1] / 'Contents/Resources/unexpected').symlink_to('/tmp')
            with self.assertRaises(ValueError):
                virtual.validate_bundle(bundles[1])


if __name__ == '__main__':
    unittest.main()
