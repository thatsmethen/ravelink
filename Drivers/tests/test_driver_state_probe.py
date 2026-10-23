from pathlib import Path
import subprocess
import tempfile
import unittest


class DriverStateProbeTests(unittest.TestCase):
    def test_query_errors_and_invalid_format_do_not_pass_as_absence(self):
        source = Path(__file__).with_name('driver_state_contract.c')
        with tempfile.TemporaryDirectory() as folder:
            executable = str(Path(folder) / 'contract')
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', str(source),
                            '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-o', executable], check=True, timeout=30)
            output = subprocess.run([executable], capture_output=True, text=True, check=True, timeout=10)
            self.assertIn('controls passed', output.stdout)
            self.assertIn('Device enumeration failed OSStatus=7331', output.stderr)


if __name__ == '__main__': unittest.main()
