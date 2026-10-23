"""Package and temporary-volume policy tests. Never mutates the host HAL or receipts."""
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/virtual-devices.py'
SPEC = importlib.util.spec_from_file_location('virtual_lifecycle', SCRIPT)
virtual = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(virtual)


class VirtualLifecycleTests(unittest.TestCase):
    def test_duplicate_uninstall_aliases_fail_before_root_or_filesystem_work(self):
        with mock.patch.object(virtual, 'require_root') as root, mock.patch.object(virtual, 'validate_bundle') as validate:
            with self.assertRaisesRegex(ValueError, 'Duplicate uninstall'):
                virtual.uninstall(['voice', 'voice:Different label'])
            root.assert_not_called()
            validate.assert_not_called()

    def test_release_identifiers_and_build_numbers_are_explicit(self):
        self.assertEqual(virtual.release_version('0.2.3', 17), ('0.2.3', 17))
        self.assertNotEqual(virtual.receipt_id('voice'), virtual.receipt_id('music'))
        for version, number in [('01.2.3', 1), ('1.2', 1), ('1.2.3-beta', 1), ('0.2.3', 0), ('0.2.3', 10000), ('0.2.3', True)]:
            with self.subTest(version=version, number=number), self.assertRaises(ValueError):
                virtual.release_version(version, number)

    def test_invalid_release_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'absent'
            result = subprocess.run([str(SCRIPT), 'build', '--build-number', '0', '--output', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_uninstall_preflights_all_bundles_and_forgets_only_owned_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            hal = Path(directory)
            for name in ['voice', 'music', 'unrelated']:
                (hal / f'RaveLink-{name}.driver').mkdir()
            with mock.patch.object(virtual, 'HAL', hal), mock.patch.object(virtual, 'require_root'), \
                 mock.patch.object(virtual, 'validate_bundle') as validate, \
                 mock.patch.object(virtual.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                 mock.patch.object(virtual, 'run') as run:
                validate.side_effect = [None, ValueError('damaged signature')]
                with self.assertRaisesRegex(ValueError, 'damaged signature'):
                    virtual.uninstall(['voice', 'music'])
                self.assertTrue((hal / 'RaveLink-voice.driver').exists())
                self.assertTrue((hal / 'RaveLink-music.driver').exists())
                run.assert_not_called()
                validate.side_effect = None
                virtual.uninstall(['voice', 'music'])
                self.assertFalse((hal / 'RaveLink-voice.driver').exists())
                self.assertFalse((hal / 'RaveLink-music.driver').exists())
                self.assertTrue((hal / 'RaveLink-unrelated.driver').exists())
                self.assertEqual(run.call_args_list, [
                    mock.call(['/usr/sbin/pkgutil', '--forget', 'au.textual.ravelink.audio.package.voice']),
                    mock.call(['/usr/sbin/pkgutil', '--forget', 'au.textual.ravelink.audio.package.music'])])

    def preflight(self, installed, incoming):
        with tempfile.TemporaryDirectory() as directory:
            volume = Path(directory)
            before = {}
            for slug, build, identity in installed:
                path = volume / 'Library/Audio/Plug-Ins/HAL' / f'RaveLink-{slug}.driver/Contents/Info.plist'
                path.parent.mkdir(parents=True)
                path.write_bytes(plistlib.dumps(dict(CFBundleIdentifier=identity, CFBundleVersion=build)))
                before[path] = path.read_bytes()
            script = volume / 'preinstall'
            script.write_text(virtual.preinstall_script(incoming))
            result = subprocess.run(['bash', str(script), 'package', '/', str(volume)], capture_output=True, text=True)
            for path, original in before.items():
                self.assertEqual(path.read_bytes(), original, 'Policy preflight must never rewrite installed metadata')
            return result

    def test_preinstall_allows_fresh_upgrade_and_same_build_repair(self):
        identity = 'au.textual.ravelink.audio.voice'
        for installed in [[], [('voice', '1', identity)], [('voice', '3', identity)]]:
            with self.subTest(installed=installed):
                result = self.preflight(installed, [('voice', 3)])
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_preinstall_rejects_downgrade_identity_mismatch_and_unknown_build(self):
        identity = 'au.textual.ravelink.audio.voice'
        for build, bundle_id in [('4', identity), ('1', 'foreign.bundle'), ('broken', identity), ('01', identity)]:
            with self.subTest(build=build, bundle_id=bundle_id):
                result = self.preflight([('voice', build, bundle_id)], [('voice', 3)])
                self.assertNotEqual(result.returncode, 0)

    def test_every_component_checks_later_downgrade_before_any_payload(self):
        result = self.preflight([('voice', '1', 'au.textual.ravelink.audio.voice'),
                                 ('music', '5', 'au.textual.ravelink.audio.music')], [('voice', 2), ('music', 2)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('music installed build 5, package build 2', result.stderr)

    def test_preinstall_refuses_symlink_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            volume = Path(directory)
            hal = volume / 'Library/Audio/Plug-Ins/HAL'
            hal.mkdir(parents=True)
            (hal / 'RaveLink-voice.driver').symlink_to('/does-not-exist')
            script = volume / 'preinstall'
            script.write_text(virtual.preinstall_script([('voice', 2)]))
            result = subprocess.run(['bash', str(script), 'package', '/', str(volume)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('symbolic-link driver', result.stderr)

    def test_preinstall_refuses_redirected_parent_without_following_it(self):
        with tempfile.TemporaryDirectory() as directory:
            volume = Path(directory)
            (volume / 'Library').mkdir()
            (volume / 'outside').mkdir()
            (volume / 'Library/Audio').symlink_to(volume / 'outside')
            script = volume / 'preinstall'
            script.write_text(virtual.preinstall_script([('voice', 2)]))
            result = subprocess.run(['bash', str(script), 'package', '/', str(volume)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unexpected HAL parent path', result.stderr)
            self.assertEqual(list((volume / 'outside').iterdir()), [])

    def test_real_product_archive_has_per_device_receipts_and_versioned_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            devices = directory / 'devices'
            subprocess.run([str(SCRIPT), 'build', '--device', 'receipt-a:Receipt A', '--device', 'receipt-b:Receipt B',
                            '--version', '0.2.3', '--build-number', '17', '--arch', 'arm64', '--output', str(devices)],
                           check=True, stdout=subprocess.DEVNULL)
            bundles = sorted(devices.glob('*.driver'))
            # Older metadata omitted buildNumber. The signed Info.plist still
            # determines the receipt version rather than an implicit build1.
            metadata_path = bundles[0] / 'Contents/Resources/build-info.json'
            legacy = json.loads(metadata_path.read_text())
            del legacy['buildNumber']
            metadata_path.write_text(json.dumps(legacy))
            subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(bundles[0])], check=True)
            archive = directory / 'devices.pkg'
            virtual.package(bundles, archive, None)
            expanded = directory / 'expanded'
            subprocess.run(['/usr/sbin/pkgutil', '--expand-full', str(archive), str(expanded)], check=True)
            receipts = {ET.parse(path).getroot().get('identifier'): ET.parse(path).getroot().get('version')
                        for path in expanded.rglob('PackageInfo')}
            self.assertEqual(receipts, {'au.textual.ravelink.audio.package.receipt-a': '17',
                                        'au.textual.ravelink.audio.package.receipt-b': '17'})
            archived = sorted(expanded.rglob('*.driver'))
            self.assertEqual(len(archived), 2)
            for bundle in archived:
                data = virtual.validate_bundle(bundle)
                self.assertEqual((data['version'], data['buildNumber']), ('0.2.3', 17))
                script = bundle.parent.parent / 'Scripts/preinstall'
                self.assertTrue(script.is_file())
                self.assertIn("check_device 'receipt-a' '17'", script.read_text())
                self.assertIn("check_device 'receipt-b' '17'", script.read_text())
            distribution = ET.parse(expanded / 'Distribution').getroot()
            self.assertEqual(distribution.find('options').get('hostArchitectures'), 'arm64')
            self.assertEqual(distribution.find('options').get('rootVolumeOnly'), 'true')
            self.assertEqual(distribution.find('volume-check/allowed-os-versions/os-version').get('min'), '12.0')
            self.assertTrue(all(p.get('onConclusion') == 'RequireRestart'
                                for p in distribution.findall('pkg-ref') if p.get('version')))


if __name__ == '__main__':
    unittest.main()
