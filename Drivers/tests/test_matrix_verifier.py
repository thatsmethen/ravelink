"""Synthetic controls validate the analyzer, not RaveLink audio routing."""
import array
import importlib.util
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('matrix_verifier', ROOT / 'scripts/verify-matrix.py')
verifier = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(verifier)


class MatrixVerifierTests(unittest.TestCase):
    def capture(self, output, change=None):
        rate = 8000
        phases = [(0, 0)] + [a if output == 'A' else b for _, a, b in verifier.PHASES] + [(0, 0)]
        samples = array.array('f')
        for phase, coefficients in enumerate(phases):
            for frame in range(round(rate * 1.2)):
                wave = verifier.TONE * math.sin(2 * math.pi * 440 * frame / rate)
                pair = [wave * coefficients[0], wave * coefficients[1]]
                if change: pair = change(phase, frame, pair)
                samples.extend(pair)
        if sys.byteorder != 'little': samples.byteswap()
        data = samples.tobytes()
        return (b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt '
                + struct.pack('<IHHIIHH', 16, 3, 2, rate, rate * 8, 8, 32)
                + b'data' + struct.pack('<I', len(data)) + data)

    def analyze(self, output='A', change=None, payload=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.wav'
            path.write_bytes(payload if payload is not None else self.capture(output, change))
            return verifier.analyze(path, output)

    def test_correct_ordered_control_sequence(self):
        for output in ('A', 'B'):
            result = self.analyze(output)
            self.assertEqual(result['output'], output)
            self.assertEqual(result['sampleRate'], 8000)

    def test_unrelated_mix_level_change_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('B', lambda phase, frame, pair: [v * .25 for v in pair] if phase == 2 else pair)

    def test_pan_on_wrong_channel_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('A', lambda phase, frame, pair: pair[::-1] if phase == 3 else pair)

    def test_midphase_dropout_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('A', lambda phase, frame, pair: [0, 0] if phase == 1 and 3000 <= frame < 5000 else pair)

    def test_signal_after_mute_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('A', lambda phase, frame, pair: [.05, .05] if phase == 13 else pair)

    def test_nonfinite_samples_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('B', lambda phase, frame, pair: [float('nan'), 0] if phase == 4 and frame == 300 else pair)

    def test_silent_capture_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('A', lambda phase, frame, pair: [0, 0])

    def test_partial_tail_signal_after_final_mute_rejected(self):
        payload = bytearray(self.capture('A'))
        tail = struct.pack('<ff', .1, -.1) * 13
        payload.extend(tail)
        struct.pack_into('<I', payload, 4, len(payload) - 8)
        struct.pack_into('<I', payload, 40, len(payload) - 44)
        with self.assertRaises(ValueError): self.analyze(payload=bytes(payload))

    def test_partial_silent_tail_is_still_measured(self):
        payload = bytearray(self.capture('B'))
        payload.extend(struct.pack('<ff', 0, 0) * 13)
        struct.pack_into('<I', payload, 4, len(payload) - 8)
        struct.pack_into('<I', payload, 40, len(payload) - 44)
        result = self.analyze('B', payload=bytes(payload))
        self.assertAlmostEqual(result['phases'][-1]['durationSeconds'], 2.4 + 13 / 8000)

    def test_right_channel_polarity_inversion_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('B', lambda phase, frame, pair: [pair[0], -pair[1]])

    def test_later_source_gain_is_not_skipped(self):
        with self.assertRaises(ValueError):
            self.analyze('A', lambda phase, frame, pair: [v * 2 for v in pair] if phase == 10 else pair)

    def test_later_master_level_is_not_skipped(self):
        with self.assertRaises(ValueError):
            self.analyze('B', lambda phase, frame, pair: [v / verifier.QUARTER for v in pair] if phase == 11 else pair)

    def test_later_frequency_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('B', lambda phase, frame, pair: [verifier.TONE * verifier.QUARTER * math.sin(2 * math.pi * 880 * frame / 8000)] * 2 if phase == 8 else pair)

    def test_truncated_riff_rejected(self):
        with self.assertRaises(ValueError): self.analyze(payload=self.capture('A')[:-8])

    def test_square_wave_with_same_peak_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('A', lambda phase, frame, pair: [math.copysign(verifier.TONE, v) for v in pair] if phase == 1 else pair)

    def test_wrong_frequency_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze('A', lambda phase, frame, pair: [verifier.TONE * math.sin(2 * math.pi * 880 * frame / 8000)] * 2 if phase == 1 else pair)


if __name__ == '__main__': unittest.main()
