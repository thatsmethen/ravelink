"""Failure custody in the shell harness, using inert stand-ins instead of HAL."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SoakOrchestrationTests(unittest.TestCase):
    def run_harness(self, engine_status=0, failed_probe=''):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / 'scripts'
            scripts.mkdir()
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            shutil.copy(ROOT / 'scripts/run-device-soak.sh', scripts)
            (scripts / 'test.sh').write_text(
                '#!/bin/bash\n'
                'touch "$RAVELINK_SOAK_GO_FILE"\n'
                'echo engine-complete\n'
                'exit "$FAKE_ENGINE_STATUS"\n')
            (scripts / 'test.sh').chmod(0o755)
            fake_python = bin_dir / 'python3'
            fake_python.write_text('''#!/bin/bash
set -eu
script="$1"; shift
if [[ "$script" == scripts/verify-device-soak.py ]]; then
  for name in a b feeder; do test -f "$1/soak-$name.finished"; done
  echo '{"observationsFinished":true}'
  exit 0
fi
ready=''; report=''
while (( $# )); do
  case "$1" in
    --ready-file) ready="$2"; shift 2 ;;
    --report) report="$2"; shift 2 ;;
    *) shift ;;
  esac
done
touch "$ready"
while [[ ! -f "${report%/*}/soak-go" ]]; do sleep 0.01; done
# A later completion distinguishes waiting from the old early EXIT trap.
sleep 0.1
touch "${report%.json}.finished"
if [[ "${report##*/}" == "soak-$FAKE_FAILED_PROBE.json" ]]; then exit 7; fi
''')
            fake_python.chmod(0o755)
            environment = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}',
                               RAVELINK_TEST_DEVICE_SOAK='1', RAVELINK_SOAK_OUTPUT=str(root / 'build'),
                               FAKE_ENGINE_STATUS=str(engine_status), FAKE_FAILED_PROBE=failed_probe)
            result = subprocess.run(['bash', str(scripts / 'run-device-soak.sh')], env=environment,
                                    capture_output=True, text=True, timeout=10)
            statuses = json.loads((root / 'build/soak-exit-status.json').read_text())
            observation = json.loads((root / 'build/soak-analysis.json').read_text())
            return result, statuses, observation

    def test_failed_engine_still_preserves_complete_independent_observation(self):
        result, statuses, observation = self.run_harness(engine_status=9)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(statuses, dict(engine=9, feeder=0, receiverA=0, receiverB=0, analysis=0))
        self.assertTrue(observation['observationsFinished'])

    def test_failed_recorder_does_not_skip_remaining_probe_or_hide_failure(self):
        result, statuses, observation = self.run_harness(failed_probe='a')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(statuses, dict(engine=0, feeder=0, receiverA=7, receiverB=0, analysis=0))
        self.assertTrue(observation['observationsFinished'])

    def test_all_successful_components_are_required_for_success(self):
        result, statuses, observation = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(value == 0 for value in statuses.values()))
        self.assertTrue(observation['observationsFinished'])


if __name__ == '__main__':
    unittest.main()
