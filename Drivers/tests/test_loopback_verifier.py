"""Synthetic controls for the verifier instrument, never evidence of HAL behavior."""
import array
import importlib.util
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('loopback_verifier', ROOT / 'scripts/verify-loopback.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

RATE = 8000
UNITY = 0.12589254
ATTENUATED = UNITY * 10 ** (-12 / 20)


def wave_bytes(phases=None, frequency=440, gain=1, stereo_delta=0):
    if phases is None:
        phases = [(0.5, 0), (1.5, UNITY), (1.0, ATTENUATED), (1.0, 0)]
    samples = array.array('f')
    frame = 0
    for phase in phases:
        seconds, amplitude = phase[:2]
        phase_frequency = phase[2] if len(phase) == 3 else frequency
        for _ in range(round(seconds * RATE)):
            sample = gain * amplitude * math.sin(2 * math.pi * phase_frequency * frame / RATE)
            samples.extend([sample, sample + stereo_delta])
            frame += 1
    if sys.byteorder != 'little':
        samples.byteswap()
    raw = samples.tobytes()
    fmt = struct.pack('<HHIIHH', 3, 2, RATE, RATE * 8, 8, 32)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(raw)) + raw
    return b'RIFF' + struct.pack('<I', len(body)) + body


class LoopbackVerifierControls(unittest.TestCase):
    def verify(self, payload):
        with tempfile.TemporaryDirectory(prefix='ravelink-verifier-control-') as directory:
            path = Path(directory) / 'synthetic.wav'
            path.write_bytes(payload)
            return verifier.verify(path)

    def test_known_signal_is_accepted_without_claiming_capture_provenance(self):
        result = self.verify(wave_bytes())
        self.assertAlmostEqual(result['frequencyHz'], 440, delta=1)
        self.assertAlmostEqual(result['peak'], UNITY, delta=0.0001)
        self.assertEqual(result['orderedPhaseStartsSeconds'], {'unity': 0.5, 'minus12dB': 2.0, 'muted': 3.0})
        self.assertEqual(result['stereoDifference'], 0)
        self.assertIn('caller supplies capture provenance', result['evidence'])

    def test_wrong_frequency_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'frequency'):
            self.verify(wave_bytes(frequency=880))

    def test_wrong_frequency_in_attenuated_phase_is_rejected(self):
        phases = [(0.5, 0), (1.5, UNITY), (1.0, ATTENUATED, 880), (1.0, 0)]
        with self.assertRaisesRegex(ValueError, 'frequency'):
            self.verify(wave_bytes(phases))

    def test_analysis_read_is_bounded(self):
        with mock.patch.object(verifier, 'MAX_CAPTURE_BYTES', 1024):
            with self.assertRaisesRegex(ValueError, 'analysis limit'):
                self.verify(wave_bytes())

    def test_wrong_gain_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(wave_bytes(gain=0.5))

    def test_wrong_attenuation_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(wave_bytes([(0.5, 0), (1.5, UNITY), (1.0, UNITY * 10 ** (-6 / 20)), (1.0, 0)]))

    def test_missing_mute_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'silence'):
            self.verify(wave_bytes([(0.5, 0), (1.5, UNITY), (1.0, ATTENUATED), (1.0, ATTENUATED)]))

    def test_truncated_payload_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'RIFF length'):
            self.verify(wave_bytes()[:-1])

    def test_incomplete_stereo_frame_is_rejected_even_with_correct_riff_length(self):
        payload = bytearray(wave_bytes()[:-1])
        struct.pack_into('<I', payload, 4, len(payload) - 8)
        struct.pack_into('<I', payload, 40, len(payload) - 44)
        with self.assertRaises(ValueError):
            self.verify(bytes(payload))

    def test_wrong_phase_order_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(wave_bytes([(0.5, 0), (1.0, ATTENUATED), (1.5, UNITY), (1.0, 0)]))

    def test_fragmented_signal_does_not_accumulate_into_a_settled_phase(self):
        phases = [(0.5, 0)] + [(0.1, UNITY), (0.1, 0)] * 10 + [(1.0, ATTENUATED), (1.0, 0)]
        with self.assertRaises(ValueError):
            self.verify(wave_bytes(phases))

    def test_dropout_between_settled_phases_is_rejected(self):
        phases = [(0.5, 0), (1.0, UNITY), (0.1, 0), (0.5, UNITY), (1.0, ATTENUATED), (1.0, 0)]
        with self.assertRaisesRegex(ValueError, 'Discontinuous'):
            self.verify(wave_bytes(phases))

    def test_signal_after_mute_is_rejected(self):
        phases = [(0.5, 0), (1.5, UNITY), (1.0, ATTENUATED), (0.5, 0), (0.5, ATTENUATED)]
        with self.assertRaisesRegex(ValueError, 'returned after'):
            self.verify(wave_bytes(phases))

    def test_nonfinite_and_stereo_mismatch_are_rejected(self):
        payload = bytearray(wave_bytes())
        struct.pack_into('<f', payload, 44, math.nan)
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            self.verify(payload)
        with self.assertRaises(ValueError):
            self.verify(wave_bytes(stereo_delta=0.001))

    def test_duplicate_chunks_are_rejected(self):
        payload = bytearray(wave_bytes())
        payload += b'fmt ' + struct.pack('<I', 16) + struct.pack('<HHIIHH', 3, 2, RATE, RATE * 8, 8, 32)
        struct.pack_into('<I', payload, 4, len(payload) - 8)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.verify(payload)


if __name__ == '__main__':
    unittest.main()
