"""The instrument callback is tested with synthetic buffers, without HAL startup."""
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest


@unittest.skipUnless(platform.system() == 'Darwin', 'CoreAudio headers require macOS')
class SoakProbeTests(unittest.TestCase):
    def contract(self, sanitizer=False):
        source = Path(__file__).with_name('soak_probe_contract.c')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'contract'
            flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'] if sanitizer else []
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O1', '-g', '-Wall', '-Wextra',
                            *flags, str(source), '-framework', 'CoreAudio',
                            '-framework', 'CoreFoundation', '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], check=True, text=True, capture_output=True, timeout=20 if sanitizer else 10)
            self.assertIn('no HAL I/O performed', result.stdout)

    def test_eight_channel_capture_feed_bounds_and_timestamp_health(self):
        self.contract()

    @unittest.skipUnless(os.environ.get('RAVELINK_TEST_PROBE_SANITIZER') == '1',
                         'ASan instrumentation is opt-in; unavailable on some macOS beta hosts')
    def test_callback_contract_under_sanitizers(self):
        self.contract(sanitizer=True)


if __name__ == '__main__': unittest.main()
