"""Synthetic instrument controls. No device enumeration, installation or audio."""
import array
import csv
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import analyze_runtime as analysis
import run_runtime
import run_system


def signal(frames=96000, gain=-6, ppm=lambda _: 0.0):
    result, position = array.array("f"), 0.371
    amplitude = 0.125 * 10 ** (gain / 20)
    for frame in range(frames):
        result.extend(amplitude * math.sin(2 * math.pi * hz * position / 48000) for hz in (440, 997))
        position += 1 + ppm(frame / 48000) / 1e6
    return result


def write_wav(path, samples):
    payload = samples.tobytes()
    path.write_bytes(b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVEfmt "
                     + struct.pack("<IHHIIHH", 16, 3, 2, 48000, 384000, 8, 32)
                     + b"data" + struct.pack("<I", len(payload)) + payload)


class SignalControls(unittest.TestCase):
    def test_fixed_and_valid_continuous_asrc_drift_pass(self):
        for label, drift in [("fixed", lambda _: 0), ("positive", lambda _: 2000),
                             ("negative", lambda _: -2000), ("smooth", lambda t: 2000 * math.sin(t))]:
            with self.subTest(label=label):
                data = signal(ppm=drift)
                result = analysis.tone_metrics(data, 0, len(data) // 2, -6)
                self.assertTrue(result["pass"], result)

    def test_wrong_gain_channels_silence_and_single_sample_skip_fail(self):
        baseline = signal()
        cases = {}
        cases["wrong_gain"] = array.array("f", (value * 0.5 for value in baseline))
        swapped = array.array("f", baseline)
        for index in range(0, len(swapped), 2):
            swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
        cases["swapped"] = swapped
        for count in (8, 512):
            data = array.array("f", baseline)
            data[48000:48000 + count * 2] = array.array("f", [0] * count * 2)
            cases[f"hole{count}"] = data
        skipped = array.array("f", baseline)
        skipped[48000:-2] = baseline[48002:]
        cases["single_sample_skip"] = skipped
        for label, data in cases.items():
            with self.subTest(label=label):
                self.assertFalse(analysis.tone_metrics(data, 0, len(data) // 2, -6)["pass"])

    def test_outside_declared_drift_fails_frequency_bound(self):
        result = analysis.tone_metrics(signal(ppm=lambda _: 5000), 0, 96000, -6)
        self.assertFalse(result["pass"])
        self.assertGreater(result["channels"][0]["frequency_error_ppm"], 2500)

    def test_timeline_uses_actual_callback_clock_without_whole_capture_drift(self):
        events = [{"host_time": 1_000_000_000 + round(frame / 47950 * 1e9), "stored_frames": 480}
                  for frame in range(0, 48000, 480)]
        timeline = analysis.CaptureTimeline(events, 1e-9, 48000)
        tick = 1_000_000_000 + round(24000 / 47950 * 1e9)
        self.assertEqual(timeline.frame(tick), 24000)
        self.assertAlmostEqual(timeline.response_seconds(24000, tick), 0, places=8)


class ProtocolControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory()
        cls.root = Path(cls.storage.name)
        cls.phases, requested = [], 0.5
        for index, (gain, muted, seconds) in enumerate(analysis.PHASES):
            acknowledged = requested + 0.01
            cls.phases.append(dict(event="phase", phase=index, gain_db=gain, muted=muted,
                requested_host_time=cls.tick(requested), acknowledged_host_time=cls.tick(acknowledged),
                version=2 * (index + 1), rendered_frames=round(acknowledged * 48000),
                callback_count=round(acknowledged * 48000 / 256)))
            requested = acknowledged + seconds
        cls.stop_seconds = requested
        records = [dict(event="started", input_id="coreaudio:au.textual.ravelink.cable.1",
            output_id="coreaudio:au.textual.ravelink.cable.2", sample_rate=48000)] + cls.phases + [
            dict(event="stopped", requested_host_time=cls.tick(requested), returned_host_time=cls.tick(requested + 0.02))]
        (cls.root / "runtime-events.jsonl").write_text("".join(json.dumps(item) + "\n" for item in records))
        (cls.root / "runtime-result.json").write_text('{"pass":true}')
        cls.samples = array.array("f")
        for frame in range(26 * 48000):
            time = frame / 48000
            gain, muted = -6, False
            for phase in cls.phases:
                if cls.seconds(phase["requested_host_time"]) + 0.03 <= time:
                    gain, muted = phase["gain_db"], phase["muted"]
            if time >= requested + 0.03:
                muted = True
            amplitude = 0 if muted else 0.125 * 10 ** (gain / 20)
            cls.samples.extend(amplitude * math.sin(2 * math.pi * hz * (frame + 0.37) / 48000) for hz in (440, 997))
        write_wav(cls.root / "runtime-reader.wav", cls.samples)
        frames, period = len(cls.samples) // 2, 256
        with (cls.root / "runtime-reader.csv").open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["sample_time", "host_time", "observed_host_time", "flags", "frames", "stored_frames"])
            for frame in range(0, frames, period):
                writer.writerow([100000 + frame, cls.tick(frame / 48000), cls.tick(frame / 48000) + 1000,
                    3, period, min(period, frames - frame)])
        (cls.root / "runtime-reader.json").write_text(json.dumps(dict(status=0, stop_status=0,
            destroy_status=0, fault=0, complete=True, ready=True, uid="au.textual.ravelink.cable.2",
            matches=1, sample_rate=48000, channels=2, frames=frames, target_frames=frames,
            events=math.ceil(frames / period), host_time_numer=1, host_time_denom=1)))
        with (cls.root / "runtime-telemetry.csv").open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["host_time", "rendered_frames", "callback_count", "applied_control_version",
                "captured_frames", "buffered_frames", "clock_correction_ppm", "fault", "running"])
            for step in range(10, math.floor(requested * 50)):
                tick = cls.tick(step / 50)
                version = max([phase["version"] for phase in cls.phases if phase["acknowledged_host_time"] <= tick] or [0])
                count = step * 960
                writer.writerow([tick, count, count // 256, version, count + 2048, 2048, 0, 0, 1])

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    @staticmethod
    def tick(seconds):
        return 1_000_000_000 + round(seconds * 1e9)

    @staticmethod
    def seconds(tick):
        return (tick - 1_000_000_000) / 1e9

    def fixture(self, directory, mutate=None):
        output = Path(directory)
        for path in self.root.iterdir():
            shutil.copyfile(path, output / path.name)
        if mutate:
            samples = array.array("f", self.samples)
            mutate(samples)
            write_wav(output / "runtime-reader.wav", samples)
        return output

    def test_complete_fixed_sequence_passes(self):
        result = analysis.analyze(self.root)
        self.assertTrue(result["pass"], result)
        self.assertLess(result["stop_response_seconds"], 0.06)
        self.assertEqual(result["unmuted_zero_runs"], [0, 0])

    def test_gain_handoff_margin_cannot_hide_silent_packet(self):
        def mutate(samples):
            index = round((self.seconds(self.phases[1]["requested_host_time"]) + 0.1) * 48000) * 2
            samples[index:index + 1024] = array.array("f", [0] * 1024)
        with tempfile.TemporaryDirectory() as directory:
            result = analysis.analyze(self.fixture(directory, mutate))
            self.assertFalse(result["pass"])
            self.assertIn(512, result["unmuted_zero_runs"])

    def test_delayed_restore_is_measured_and_fails(self):
        def mutate(samples):
            begin = round(self.seconds(self.phases[3]["requested_host_time"]) * 48000) * 2
            end = begin + round(0.4 * 48000) * 2
            samples[begin:end] = array.array("f", [0] * (end - begin))
        with tempfile.TemporaryDirectory() as directory:
            result = analysis.analyze(self.fixture(directory, mutate))
            self.assertFalse(result["pass"])
            self.assertIsNone(result["phases"][3]["detected_response_seconds"])

    def test_delayed_mute_is_measured_and_fails(self):
        def mutate(samples):
            begin = round(self.seconds(self.phases[2]["requested_host_time"]) * 48000)
            for frame in range(begin, begin + round(0.4 * 48000)):
                for side, hz in enumerate((440, 997)):
                    samples[frame * 2 + side] = 0.125 * 10 ** (-12 / 20) * math.sin(2 * math.pi * hz * frame / 48000)
        with tempfile.TemporaryDirectory() as directory:
            result = analysis.analyze(self.fixture(directory, mutate))
            self.assertFalse(result["pass"])
            self.assertIsNone(result["phases"][2]["detected_response_seconds"])

    def test_delayed_stop_and_stale_tail_fail(self):
        def mutate(samples):
            begin = round((self.stop_seconds + 0.3) * 48000) * 2
            samples[begin:begin + 1024] = array.array("f", [0.01] * 1024)
        with tempfile.TemporaryDirectory() as directory:
            result = analysis.analyze(self.fixture(directory, mutate))
            self.assertFalse(result["pass"])
            self.assertGreater(result["stopped_tail_peak"], 0)

    def test_report_cannot_redefine_expected_gain_or_ack_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.fixture(directory)
            records = [json.loads(line) for line in (output / "runtime-events.jsonl").read_text().splitlines()]
            records[2]["gain_db"] = -6
            records[2]["acknowledged_host_time"] += 300_000_000
            (output / "runtime-events.jsonl").write_text("".join(json.dumps(item) + "\n" for item in records))
            result = analysis.analyze(output)
            self.assertFalse(result["pass"])
            self.assertTrue(any("controls differ" in error for error in result["failures"]))
            self.assertTrue(any("acknowledgement exceeded" in error for error in result["failures"]))

    def test_late_valid_ack_does_not_extend_output_response_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.fixture(directory)
            records = [json.loads(line) for line in (output / "runtime-events.jsonl").read_text().splitlines()]
            # Keep every phase duration valid: gain acknowledgement takes 200ms,
            # and subsequent phases move by the extra190ms. PCM reaches -12dB
            # 400ms after its request, before ack+250ms but after request+250ms.
            records[2]["acknowledged_host_time"] += 190_000_000
            for record in records[3:]:
                for key in ("requested_host_time", "acknowledged_host_time", "returned_host_time"):
                    if key in record:
                        record[key] += 190_000_000
            (output / "runtime-events.jsonl").write_text("".join(json.dumps(item) + "\n" for item in records))
            samples = array.array("f")
            for frame in range(len(self.samples) // 2):
                time, gain, muted = frame / 48000, -6, False
                for record in records[1:5]:
                    delay = 0.4 if record["phase"] == 1 else 0.03
                    if time >= self.seconds(record["requested_host_time"]) + delay:
                        gain, muted = record["gain_db"], record["muted"]
                if time >= self.seconds(records[-1]["requested_host_time"]) + 0.03:
                    muted = True
                amplitude = 0 if muted else 0.125 * 10 ** (gain / 20)
                samples.extend(amplitude * math.sin(2 * math.pi * hz * (frame + 0.37) / 48000) for hz in (440, 997))
            write_wav(output / "runtime-reader.wav", samples)
            result = analysis.analyze(output)
            self.assertFalse(result["pass"])
            self.assertAlmostEqual(result["phases"][1]["acknowledgement_seconds"], 0.2)
            self.assertIsNone(result["phases"][1]["detected_response_seconds"])
            self.assertFalse(any("duration differs" in error for error in result["failures"]))
            self.assertFalse(any("acknowledgement exceeded" in error for error in result["failures"]))


class OwnershipControls(unittest.TestCase):
    def test_existing_second_uid_prevents_install(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch.object(run_system, "DESTINATION", output / "absent.driver"), \
                 mock.patch.object(run_system, "guard_environment"), \
                 mock.patch.object(run_system, "discover", side_effect=[{"matches": 0}, {"matches": 1}]), \
                 mock.patch.object(run_system, "bounded") as command:
                with self.assertRaisesRegex(RuntimeError, "UID already exists"):
                    run_system.run(output, Path("unused"), Path("unused"))
                command.assert_not_called()
            self.assertFalse((output / "installation-owner.json").exists())

    def test_runtime_evidence_is_not_overwritten_or_launched(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "runtime-result.json").write_text('{"pass":false}')
            with mock.patch.object(run_runtime.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(RuntimeError, "overwrite"):
                    run_runtime.RuntimeProcess(Path("unused"), output)
                launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
