import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('app_build_info', Path(__file__).parents[2] / 'scripts/app-build-info.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AppBuildInfoTests(unittest.TestCase):
    def test_versions_reject_ambiguous_or_invalid_values(self):
        self.assertEqual(module.versions('0.1.0', '1'), ('0.1.0', '1'))
        for version, build in [('1.0-beta', '1'), ('01.0.0', '1'), ('1.0.0', '0'), ('1.0.0', '2147483648'), ('1.0.0', '1.2')]:
            with self.subTest(version=version, build=build), self.assertRaises(ValueError):
                module.versions(version, build)

    def test_source_change_refuses_bundle_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Sources').mkdir(); (root / 'Resources').mkdir()
            source = root / 'Sources/Main.swift'; source.write_text('original')
            app = root / 'Staged.app'; (app / 'Contents').mkdir(parents=True)
            info_path = app / 'Contents/Info.plist'
            original = plistlib.dumps({'CFBundleVersion': '1', 'CFBundleShortVersionString': '0.1.0'})
            info_path.write_bytes(original)
            record = {'sourceInputs': module.source_inputs(root), 'version': '0.2.0', 'buildNumber': '2'}
            source.write_text('changed during build')
            with self.assertRaisesRegex(ValueError, 'changed during compilation'):
                module.finish(root, record, app)
            self.assertEqual(info_path.read_bytes(), original)
            self.assertFalse((app / 'Contents/Resources/BuildInfo.json').exists())
            source.write_text('original')
            module.finish(root, record, app)
            self.assertEqual(plistlib.loads(info_path.read_bytes())['CFBundleVersion'], '2')
            self.assertEqual(json.loads((app / 'Contents/Resources/BuildInfo.json').read_text()), record)

    def test_external_source_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'Sources').mkdir()
            outside = root / 'outside'; outside.write_text('external source')
            (root / 'Sources/Main.swift').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                module.source_inputs(root)
