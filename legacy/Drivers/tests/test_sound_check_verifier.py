"""Synthetic instrument controls; these do not establish installed-HAL behavior."""
import array
import importlib.util
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('sound_check_verifier', ROOT / 'scripts/verify-sound-check.py')
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
RATE = 8000
CLIP_FRAMES = 9063  # Deliberately leaves a large unfaded discontinuity at the seam.


def write_wav(path, stereo):
    data = array.array('f', stereo).tobytes()
    fmt = struct.pack('<HHIIHH', 3, 2, RATE, RATE * 8, 8, 32)
    payload = b'WAVEfmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    path.write_bytes(b'RIFF' + struct.pack('<I', len(payload)) + payload)


def playback(seconds, gain, frequency=440, faded=True):
    result = array.array('f')
    for frame in range(round(seconds * RATE)):
        position = frame % CLIP_FRAMES
        envelope = min(1, position / 40, (CLIP_FRAMES - 1 - position) / 40) if faded else 1
        value = math.sin(2 * math.pi * frequency * position / RATE + .7) * verifier.TONE * gain * envelope
        result.extend((value, value))
    return result


def capture(frequency=440, faded=True, unity_gain=1, attenuated_gain=verifier.ATTENUATION):
    return (array.array('f', [0]) * (RATE * 2 * 3)
            + playback(3.2, unity_gain, frequency, faded)
            + playback(3.2, attenuated_gain, frequency, faded)
            + array.array('f', [0]) * (RATE * 2 * 8))


class SoundCheckVerifierTests(unittest.TestCase):
    def analyze(self, samples=None, guard_signal=False, **report_changes):
        samples = capture() if samples is None else samples
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_wav(root / 'sound-check-output.wav', samples)
            guard = array.array('f', [0]) * len(samples)
            if guard_signal:
                guard[RATE * 8] = .01
            write_wav(root / 'sound-check-guard.wav', guard)
            report = dict(completed=True, helperReaped=True, initialGainDB=-12,
                          finalMode='empty', finalFrames=0, visibleInputGroups=1, mixBuses=1,
                          recordedFrames=CLIP_FRAMES, sampleRate=RATE)
            report.update(report_changes)
            (root / 'sound-check-engine.json').write_text(json.dumps(report))
            return verifier.analyze(root)

    def test_valid_dry_clip_repeats_with_edge_fades_and_live_gain(self):
        report = self.analyze()
        self.assertEqual([p['phase'] for p in report['output']['phases']], ['unity', 'minus12dB', 'silence'])

    def test_post_effect_instead_of_dry_recording_is_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze(capture(unity_gain=verifier.ATTENUATION))

    def test_wrong_playback_frequency_is_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze(capture(frequency=480))

    def test_wrong_live_effect_gain_is_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze(capture(attenuated_gain=.5))

    def test_a_hard_loop_seam_is_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze(capture(faded=False))

    def test_recording_leak_before_play_is_rejected(self):
        samples = capture()
        samples[RATE * 2:RATE * 4] = playback(1, verifier.ATTENUATION)
        with self.assertRaises(ValueError):
            self.analyze(samples)

    def test_dropout_in_loop_playback_is_rejected(self):
        samples = capture()
        samples[RATE * 8:RATE * 8 + 800] = array.array('f', [0]) * 800
        with self.assertRaises(ValueError):
            self.analyze(samples)

    def test_stereo_polarity_error_is_rejected(self):
        samples = capture()
        for frame in range(1, len(samples), 2):
            samples[frame] *= -1
        with self.assertRaises(ValueError):
            self.analyze(samples)

    def test_signal_in_partial_tail_is_rejected(self):
        samples = capture()
        samples.extend((.01, .01))
        with self.assertRaises(ValueError):
            self.analyze(samples)

    def test_guard_output_leak_is_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze(guard_signal=True)

    def test_unreaped_helper_or_retained_clip_does_not_pass(self):
        for changes in [dict(helperReaped=False), dict(finalFrames=100), dict(completed=False)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.analyze(**changes)

    def test_truncated_capture_is_rejected(self):
        with self.assertRaises(ValueError):
            self.analyze(capture()[:RATE * 2 * 8])


if __name__ == '__main__':
    unittest.main()
