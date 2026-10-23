import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'run-driver-lifecycle.py'
spec = importlib.util.spec_from_file_location('lifecycle_acceptance', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LifecycleHarnessTests(unittest.TestCase):
    def test_workstation_and_self_hosted_are_refused(self):
        valid = dict(RAVELINK_TEST_DRIVER_LIFECYCLE='1', GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted')
        self.assertTrue(module.authorized(valid))
        for key in valid:
            changed = dict(valid); del changed[key]
            self.assertFalse(module.authorized(changed))
        self.assertFalse(module.authorized({**valid, 'RUNNER_ENVIRONMENT': 'self-hosted'}))
        with tempfile.TemporaryDirectory() as folder, patch.object(module, 'OUT', Path(folder) / 'absent'), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(module.main(), 2)
            self.assertFalse(module.OUT.exists())

    def test_payload_identity_detects_changed_names_and_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);(root / 'a').write_bytes(b'original')
            original = module.tree_hash(root)
            (root / 'a').write_bytes(b'tampered')
            self.assertNotEqual(module.tree_hash(root), original)
            (root / 'a').write_bytes(b'original');(root / 'a').rename(root / 'b')
            self.assertNotEqual(module.tree_hash(root), original)
            (root / 'link').symlink_to(root / 'b')
            with self.assertRaisesRegex(ValueError, 'symlink'): module.tree_hash(root)

    def test_failed_command_preserves_log_and_outcome(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(module, 'OUT', Path(folder)):
            harness = module.Acceptance()
            with self.assertRaisesRegex(AssertionError, 'unexpected exit 7'):
                harness.command('expected-failure', [sys.executable, '-c', 'print("failure evidence"); raise SystemExit(7)'])
            report = json.loads((module.OUT / 'report.json').read_text())
            self.assertFalse(report['completed'])
            self.assertEqual(report['events'][0]['exitCode'], 7)
            self.assertIn('failure evidence', (module.OUT / report['events'][0]['log']).read_text())

    def test_rejection_case_cannot_pass_with_successful_command(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(module, 'OUT', Path(folder)):
            harness = module.Acceptance()
            with self.assertRaisesRegex(AssertionError, 'unexpected exit 0'):
                harness.command('false-rejection', [sys.executable, '-c', 'pass'], success=False)
            harness.command('actual-rejection', [sys.executable, '-c', 'raise SystemExit(1)'], success=False)
            self.assertEqual([e['exitCode'] for e in harness.events], [0, 1])

    def test_cleanup_never_adopts_preexisting_devices(self):
        harness = module.Acceptance()
        with patch.object(harness, 'command', side_effect=AssertionError('mutation attempted')):
            harness.cleanup()

    def test_cleanup_rejects_another_run_ownership(self):
        environment = dict(RAVELINK_TEST_DRIVER_LIFECYCLE='1', GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted', GITHUB_RUN_ID='current')
        with tempfile.TemporaryDirectory() as folder, patch.object(module, 'OUT', Path(folder)), patch.dict(os.environ, environment, clear=True), patch.object(sys, 'argv', [str(SCRIPT), '--cleanup']):
            (module.OUT / 'owned-fixtures.json').write_text(json.dumps({'ids': list(module.IDS), 'runID': 'other'}))
            with patch.object(module.Acceptance, 'command', side_effect=AssertionError('mutation attempted')):
                with self.assertRaisesRegex(ValueError, 'ownership'): module.main()

    def test_timeout_and_unrelated_failure_cannot_satisfy_policy_rejection(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(module, 'OUT', Path(folder)):
            harness = module.Acceptance()
            with self.assertRaisesRegex(AssertionError, 'unexpected exit 124'):
                harness.command('timeout', [sys.executable, '-c', 'raise SystemExit(124)'], success=False)
            with self.assertRaisesRegex(AssertionError, 'policy refusal was not observed'):
                harness.command('unrelated', [sys.executable, '-c', 'print("disk failure"); raise SystemExit(1)'],
                                success=False, expected_refusal='Refusing downgrade')

    def test_receipt_query_errors_are_not_absence(self):
        harness = module.Acceptance()
        with patch.object(subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pkgutil')):
            with self.assertRaises(subprocess.CalledProcessError): harness.receipt('ci-lifecycle-a')

    def test_service_already_absent_requires_specific_exit_and_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(module, 'OUT', Path(folder)):
            harness = module.Acceptance();allowed = {1: 'No matching processes were found'}
            harness.command('absent-service', [sys.executable, '-c', 'print("No matching processes were found"); raise SystemExit(1)'], allowed_failures=allowed)
            with self.assertRaisesRegex(AssertionError, 'unexpected exit 1'):
                harness.command('other-error', [sys.executable, '-c', 'print("permission denied"); raise SystemExit(1)'], allowed_failures=allowed)
            with self.assertRaisesRegex(AssertionError, 'unexpected exit 124'):
                harness.command('timeout', [sys.executable, '-c', 'print("No matching processes were found"); raise SystemExit(124)'], allowed_failures=allowed)


if __name__ == '__main__': unittest.main()
