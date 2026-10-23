import array
import importlib.util
import math
from pathlib import Path
import struct
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'verify-au-loopback.py'
spec = importlib.util.spec_from_file_location('verify_au_loopback', SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class AudioUnitPCMInstrumentTests(unittest.TestCase):
    def capture(self, gains=None, dropout=False):
        rate = 8000
        gains = gains or [10**(6.0206/20), 10**(-6.0206/20), 1, 10**(12/20)]
        frames = []
        segments = [(2, 0)] + [(2, gain) for gain in gains] + [(8, 0)]
        position = 0
        for segment, (seconds, gain) in enumerate(segments):
            for local in range(seconds * rate):
                value = 10**(-18/20) * gain * math.sin(position * 2 * math.pi * 440 / rate)
                if dropout and segment == 2 and rate//2 <= local < rate//2 + rate//10:
                    value = 0
                frames.extend([value, value]); position += 1
        samples = array.array('f', frames)
        payload = samples.tobytes()
        fmt = struct.pack('<HHIIHH', 3, 2, rate, rate * 8, 8, 32)
        wave = b'RIFF' + struct.pack('<I', 36 + len(payload)) + b'WAVEfmt ' + struct.pack('<I', 16) + fmt + b'data' + struct.pack('<I', len(payload)) + payload
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / 'capture.wav'
        path.write_bytes(wave)
        return directory, path

    def test_expected_ordered_signal_is_accepted(self):
        directory, path = self.capture()
        with directory:
            result = verifier.analyze(path)
        self.assertEqual([phase['name'] for phase in result['phases']], [name for name, _ in verifier.PHASES])

    def test_wrong_restored_state_gain_is_rejected(self):
        directory, path = self.capture([10**(6.0206/20), 10**(-6.0206/20), 1, 1])
        with directory, self.assertRaises(ValueError):
            verifier.analyze(path)

    def test_mid_signal_dropout_is_rejected(self):
        directory, path = self.capture(dropout=True)
        with directory, self.assertRaises(ValueError):
            verifier.analyze(path)

    def test_swapped_live_and_bypass_phases_are_rejected(self):
        directory, path = self.capture([10**(6.0206/20), 1, 10**(-6.0206/20), 10**(12/20)])
        with directory, self.assertRaises(ValueError):
            verifier.analyze(path)


if __name__ == '__main__':
    unittest.main()
