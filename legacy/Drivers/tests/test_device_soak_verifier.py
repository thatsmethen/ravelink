"""Synthetic instrument controls only; these do not exercise installed HAL devices."""
import array
import importlib.util
import math
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('soak_verifier', ROOT / 'scripts/verify-device-soak.py')
verifier = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(verifier)


class DeviceSoakVerifierTests(unittest.TestCase):
    rate = 8000

    def test_shared_capture_counts_preserve_logical_graph_and_strict_counter_gates(self):
        report = dict(visibleInputGroups=12, logicalCaptureSources=24, physicalCaptureSources=2,
                      mixBuses=8, physicalOutputs=2, parentRoutes=96, expandedRoutes=192,
                      droppedFrames=0, underrunFrames=0, oversizedBlocks=0,
                      counterSamples=[dict(physicalCaptureSources=2)])
        verifier.checked_engine(report)
        for field, value in [('logicalCaptureSources', 2), ('physicalCaptureSources', 24),
                             ('physicalCaptureSources', 1), ('droppedFrames', 1), ('underrunFrames', 1),
                             ('oversizedBlocks', 1), ('counterSamples', [dict(physicalCaptureSources=1)])]:
            with self.assertRaises(ValueError): verifier.checked_engine({**report, field: value})

    def capture(self, first_bus=0, change=None, duration=1.2):
        samples = array.array('f')
        for phase, seconds in enumerate((.5, duration, 1)):
            for frame in range(round(self.rate * seconds)):
                wave = .01 * (math.cos(2 * math.pi * 400 * frame / self.rate) + math.cos(2 * math.pi * 1000 * frame / self.rate)) if phase == 1 else 0
                values = [wave * 10 ** (-3 * (first_bus + channel // 2) / 20) for channel in range(8)]
                if change: values = change(phase, frame, values)
                samples.extend(values)
        return samples

    def inspect(self, change=None, pair=0, bus=0, duration=1.2):
        return verifier.inspect_pair(self.rate, self.capture(bus - pair, change, duration), pair, bus, minimum_seconds=1)

    def test_all_eight_separate_bus_levels_pass(self):
        for first_bus in (0, 4):
            samples = self.capture(first_bus)
            for pair in range(4):
                result = verifier.inspect_pair(self.rate, samples, pair, first_bus + pair, minimum_seconds=1)
                self.assertAlmostEqual(result['settledSeconds'], 1.2)
                self.assertLess(result['maxStereoError'], 1e-8)
                self.assertAlmostEqual(result['componentClock'][0]['averageHz'], 400, places=4)

    def test_default_envelope_rejects_short_run(self):
        with self.assertRaises(ValueError): verifier.inspect_pair(self.rate, self.capture(), 0, 0)

    def test_wrong_gain_rejected(self):
        with self.assertRaises(ValueError): self.inspect(lambda phase, frame, pair: [v * .9 for v in pair])

    def test_wrong_bus_pair_assignment_rejected(self):
        samples = self.capture()
        with self.assertRaises(ValueError): verifier.inspect_pair(self.rate, samples, 1, 0, minimum_seconds=1)

    def test_missing_second_input_tone_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(lambda phase, frame, values: [.01 * math.cos(2 * math.pi * 400 * frame / self.rate)] * 8 if phase == 1 else values)

    def test_mislabeled_frequency_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(lambda phase, frame, values: [.01 * (math.cos(2 * math.pi * 400 * frame / self.rate) + math.cos(2 * math.pi * 1100 * frame / self.rate))] * 8 if phase == 1 else values)

    def test_stereo_polarity_error_rejected(self):
        with self.assertRaises(ValueError): self.inspect(lambda phase, frame, values: [(-v if i % 2 else v) for i, v in enumerate(values)])

    def test_midrun_dropout_rejected(self):
        with self.assertRaises(ValueError): self.inspect(lambda phase, frame, values: [0] * 8 if phase == 1 and 4000 <= frame < 4800 else values)

    def test_phase_jump_rejected(self):
        with self.assertRaises(ValueError): self.inspect(lambda phase, frame, values: [-v for v in values] if phase == 1 and frame >= 4000 else values)

    def test_signal_return_after_final_mute_rejected(self):
        with self.assertRaises(ValueError): self.inspect(lambda phase, frame, values: [.002] * 8 if phase == 2 and frame > 4000 else values)

    def test_partial_tail_is_not_discarded(self):
        samples = self.capture(); samples.extend([.005] * (8 * 7))
        with self.assertRaises(ValueError): verifier.inspect_pair(self.rate, samples, 0, 0, minimum_seconds=1)

    def test_clipping_residual_rejected(self):
        with self.assertRaises(ValueError): self.inspect(lambda phase, frame, values: [max(-.012, min(.012, v)) for v in values])

    def test_riff_frame_length_and_nonfinite_rejected(self):
        def wav(values):
            data = array.array('f', values).tobytes()
            return b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 3, 8, 8000, 256000, 32, 32) + b'data' + struct.pack('<I', len(data)) + data
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'raw.wav'
            for values in ([0] * 9, [float('nan')] * 8):
                p.write_bytes(wav(values))
                with self.assertRaises(ValueError): verifier.load(p)


if __name__ == '__main__': unittest.main()
