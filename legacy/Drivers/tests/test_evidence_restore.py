import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('evidence_restore', Path(__file__).parents[2] / 'scripts/restore-evidence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.raw = b'original immutable PCM\0' * 1000
        self.archive = gzip.compress(self.raw, mtime=0)
        self.parts = []
        for index, start in enumerate(range(0, len(self.archive), 23)):
            data = self.archive[start:start + 23]
            name = f'recording.gz.part{index:04d}'
            (self.directory / name).write_bytes(data)
            self.parts.append(dict(name=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        self.record = dict(name='recording.gz', bytes=len(self.archive), sha256=hashlib.sha256(self.archive).hexdigest(),
                           rawBytes=len(self.raw), rawSHA256=hashlib.sha256(self.raw).hexdigest(), parts=self.parts)
        self.manifest = self.directory / 'parts-manifest.json'

    def save(self):
        self.manifest.write_text(json.dumps(dict(version=1, files=[self.record])))

    def test_restores_exact_original_and_refuses_replacement(self):
        self.save()
        output = self.directory / 'restored'
        module.restore(self.manifest, output)
        self.assertEqual((output / 'recording.gz').read_bytes(), self.archive)
        self.assertEqual(gzip.decompress((output / 'recording.gz').read_bytes()), self.raw)
        with self.assertRaises(FileExistsError): module.restore(self.manifest, output)

    def test_corrupt_part_fails_without_publishing(self):
        self.save()
        path = self.directory / self.parts[0]['name']
        path.write_bytes(b'x' * path.stat().st_size)
        with self.assertRaises(ValueError): module.restore(self.manifest, self.directory / 'restored')
        self.assertEqual(list((self.directory / 'restored').iterdir()), [])

    def test_wrong_raw_digest_fails_without_publishing(self):
        self.record['rawSHA256'] = '0' * 64
        self.save()
        with self.assertRaises(ValueError): module.restore(self.manifest, self.directory / 'restored')
        self.assertEqual(list((self.directory / 'restored').iterdir()), [])

    def test_paths_and_redirected_parts_are_rejected(self):
        self.record['name'] = '../outside.gz'
        self.save()
        with self.assertRaises(ValueError): module.restore(self.manifest, self.directory / 'restored')
        self.record['name'] = 'recording.gz'
        original = self.directory / self.parts[0]['name']
        alternate = self.directory / 'alternate'
        original.rename(alternate); original.symlink_to(alternate)
        self.save()
        with self.assertRaises(ValueError): module.restore(self.manifest, self.directory / 'restored')
