"""Offline parser, concurrent storage and real subprocess deadline controls."""
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from analyze_diagnostics import summarize
from run_system import ManagedProcess


class DiagnosticControls(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        events, timings = [], []
        for index, sample in enumerate((1000, 1512, 2600)):
            host = sample * 1000
            events.append(dict(sample_time=sample, host_time=host, observed_host_time=host + 150,
                               flags=3, frames=512, stored_frames=512))
            timings.append(dict(index=index, entry_host_time=host + 100, after_pcm_host_time=host + 150,
                exit_host_time=host + 170, current_present=True, current_host_time=host + 50,
                current_sample_time=sample, current_flags=3))
        with (root / "events.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, events[0].keys())
            writer.writeheader()
            writer.writerows(events)
        (root / "report.json").write_text('{"host_time_numer":1,"host_time_denom":1}')
        data = dict(schema=1, complete=True, io_quiescent=True, listener_quiescent=True,
            host_time_numer=1, host_time_denom=1, event_count=3, notification_reservations=1,
            dropped_notifications=0, lifecycle=dict(start_request=10, start_return=20, stop_request=30,
                stop_return=40, destroy_request=50, destroy_return=60), timings=timings,
            listeners=[dict(object=100, selector=123, scope=456, element=0, available=True, added=True,
                add_status=0, remove_status=0)],
            notifications=[dict(index=0, host_time=25, object=100, selector=123, scope=456, element=0)])
        self.save(root, data)
        return data

    @staticmethod
    def save(root, data):
        (Path(root) / "diagnostics.json").write_text(json.dumps(data))

    @staticmethod
    def analyze(root):
        root = Path(root)
        return summarize(root / "diagnostics.json", root / "events.csv", root / "report.json")

    def test_gap_timing_and_callback_work_are_separate_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            self.fixture(directory)
            result = self.analyze(directory)
            self.assertTrue(result["pass"])
            self.assertAlmostEqual(result["max_callback_work_seconds"], 70e-9)
            self.assertAlmostEqual(result["max_entry_minus_native_seconds"], 100e-9)
            self.assertEqual(result["sample_gap_context"][0]["delta_frames"], 576)
            self.assertEqual(result["sample_gap_context"][0]["previous"]["index"], 1)

    def test_malformed_timing_or_original_csv_mismatch_is_rejected(self):
        for mutate in (lambda d: d["timings"][0].update(entry_host_time=2_000_000),
                       lambda d: d["timings"][0].update(after_pcm_host_time=1_000_151),
                       lambda d: d["timings"][1].update(index=0),
                       lambda d: d["timings"][1].update(current_sample_time=None),
                       lambda d: d.update(host_time_numer=2)):
            with tempfile.TemporaryDirectory() as directory:
                data = self.fixture(directory)
                mutate(data)
                self.save(directory, data)
                with self.assertRaises(ValueError):
                    self.analyze(directory)

    def test_missing_current_timestamp_is_preserved_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            data = self.fixture(directory)
            data["timings"][0].update(current_present=False, current_flags=0, current_host_time=0,
                                       current_sample_time=None)
            self.save(directory, data)
            self.assertTrue(self.analyze(directory)["pass"])

    def test_overflow_uncommitted_and_listener_failures_remain_failures(self):
        for mutate in (lambda d: d.update(dropped_notifications=2),
                       lambda d: d.update(notification_reservations=2),
                       lambda d: d.update(listener_quiescent=False),
                       lambda d: d["listeners"][0].update(remove_status=-50)):
            with tempfile.TemporaryDirectory() as directory:
                data = self.fixture(directory)
                mutate(data)
                self.save(directory, data)
                self.assertFalse(self.analyze(directory)["pass"])

    def test_repeated_notification_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = self.fixture(directory)
            data["notifications"].append(dict(data["notifications"][0]))
            data["notification_reservations"] = 2
            self.save(directory, data)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.analyze(directory)

    @unittest.skipUnless(sys.platform == "darwin", "Apple SDK type declarations required")
    def test_native_notification_storage_is_bounded_and_concurrent(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "diagnostics-contract")
            subprocess.run(["xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                str(Path(__file__).with_name("diagnostics-contract.c")), "-framework", "CoreAudio",
                "-framework", "CoreFoundation", "-o", binary], check=True, timeout=30)
            root = Path(directory)
            subprocess.run([binary, str(root / "diagnostics.json"), str(root / "events.csv"),
                            str(root / "report.json")], check=True, timeout=10)
            result = self.analyze(root)
            self.assertTrue(result["pass"], result)
            self.assertEqual(result["accepted_pcm_callbacks"], 3)
            self.assertEqual(result["sample_gap_context"][0]["delta_frames"], 576)
            data = json.loads((root / "diagnostics.json").read_text())
            self.assertIsNone(data["timings"][2]["current_sample_time"])
            self.assertEqual(len(result["notifications"]), 1)


class DeadlineControls(unittest.TestCase):
    def child(self, root, name, code, timeout):
        process = ManagedProcess()
        process.name, process.mode = name, "offline-test"
        process._spawn([sys.executable, "-c", code, str(root)], Path(root) / f"{name}.log", timeout)
        return process

    def test_short_child_deadline_is_enforced_while_waiting_for_long_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            long = self.child(directory, "long", "import time; time.sleep(0.8)", 3)
            short = self.child(directory, "short",
                "import time,pathlib,sys; time.sleep(.5); pathlib.Path(sys.argv[1],'deadline-was-missed').write_text('late')", .15)
            self.assertEqual(long.finish()["exit_code"], 0)
            result = short.finish()
            self.assertTrue(result["timed_out"], result)
            self.assertTrue(result["term_sent"])
            self.assertIsNotNone(short.process.poll())
            self.assertFalse((Path(directory) / "deadline-was-missed").exists())

    def test_failed_child_does_not_cancel_other_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            failing = self.child(directory, "failing", "raise SystemExit(7)", 2)
            observer = self.child(directory, "observer",
                "import time,pathlib,sys; time.sleep(.2); pathlib.Path(sys.argv[1],'preserved').write_text('done')", 2)
            self.assertEqual(failing.finish()["exit_code"], 7)
            self.assertEqual(observer.finish()["exit_code"], 0)
            self.assertEqual((Path(directory) / "preserved").read_text(), "done")

    @unittest.skipUnless(os.name == "posix", "process-group signal control")
    def test_sigterm_ignoring_child_is_killed_and_reaped(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(ManagedProcess, "TERM_GRACE_SECONDS", 0.1):
            process = self.child(directory, "ignore",
                "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)", 1)
            result = process.finish()
            self.assertTrue(result["timed_out"] and result["term_sent"] and result["kill_sent"], result)
            self.assertEqual(result["exit_code"], -signal.SIGKILL)
            self.assertIsNotNone(process.process.poll())

    @unittest.skipUnless(os.name == "posix", "process-group signal control")
    def test_descendant_cannot_outlive_timed_out_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            code = """import subprocess,sys,time
subprocess.Popen([sys.executable, '-c', "import signal,time,pathlib,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(1.5); pathlib.Path(sys.argv[1],'escaped').write_text('late')", sys.argv[1]])
time.sleep(20)
"""
            process = self.child(directory, "descendant", code, .7)
            result = process.finish()
            self.assertTrue(result["timed_out"] and result["kill_sent"], result)
            time.sleep(1)
            self.assertFalse((Path(directory) / "escaped").exists())

    def test_prior_log_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "prior.log").write_text("original")
            with mock.patch("run_system.subprocess.Popen") as launch:
                with self.assertRaises(FileExistsError):
                    self.child(directory, "prior", "raise SystemExit(0)", 1)
                launch.assert_not_called()
            self.assertEqual((Path(directory) / "prior.log").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
