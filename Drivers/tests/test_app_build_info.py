import importlib.util
import hashlib
import json
from pathlib import Path
import plistlib
import tempfile
import tarfile
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
            archive = app / 'Contents/Resources/CorrespondingSource.tar.gz'
            result = json.loads((app / 'Contents/Resources/BuildInfo.json').read_text())
            self.assertEqual(result.pop('correspondingSourceSHA256'), hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(result, record)

    def test_archive_contains_exact_inputs_and_can_identify_extracted_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'input'; root.mkdir()
            (root / 'Sources').mkdir(); (root / 'scripts').mkdir()
            source = root / 'Sources/Main.swift'; source.write_text('source')
            script = root / 'scripts/build-app.sh'; script.write_text('#!/bin/bash\n'); script.chmod(0o755)
            (root / 'private-recording.wav').write_bytes(b'do not package')
            record = {'schemaVersion': 1, 'sourceInputs': module.source_inputs(root),
                      'sourceRevision': '1' * 40, 'sourceModified': False}
            archive = Path(directory) / 'source.tar.gz'
            digest = module.source_archive(root, record, archive)
            self.assertEqual(digest, hashlib.sha256(archive.read_bytes()).hexdigest())
            extracted = Path(directory) / 'extracted'
            with tarfile.open(archive) as tar:
                self.assertEqual(set(tar.getnames()), {'RaveLink-source/SourceManifest.json', 'RaveLink-source/Sources/Main.swift', 'RaveLink-source/scripts/build-app.sh'})
                self.assertEqual(tar.getmember('RaveLink-source/scripts/build-app.sh').mode, 0o755)
                for item in tar.getmembers():
                    path = extracted / item.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(tar.extractfile(item).read())
            restored = extracted / 'RaveLink-source'
            self.assertEqual(module.source_identity(restored, module.source_inputs(restored)),
                             ('1' * 40, False, 'source archive manifest (declared origin)'))
            (restored / 'Sources/Main.swift').write_text('changed')
            self.assertTrue(module.source_identity(restored, module.source_inputs(restored))[1])

    def test_archive_refuses_changed_input_and_unversioned_origin_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'Sources').mkdir()
            source = root / 'Sources/Main.swift'; source.write_text('original')
            inputs = module.source_inputs(root)
            self.assertEqual(module.source_identity(root, inputs), (None, True, 'unversioned source directory'))
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'changed while packaging'):
                module.source_archive(root, {'sourceInputs': inputs}, root / 'archive.tar.gz')

    def test_external_source_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'Sources').mkdir()
            outside = root / 'outside'; outside.write_text('external source')
            (root / 'Sources/Main.swift').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                module.source_inputs(root)
