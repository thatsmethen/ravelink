#!/usr/bin/env python3
"""Derived chronology only; never repairs PCM or changes frozen acceptance."""
import argparse
import csv
import io
import json
from pathlib import Path
import zipfile

from verify import ROOT, SOURCE, verify


def fourcc(value):
    return value.to_bytes(4, "big").decode("ascii", errors="replace")


def analyze(archives):
    verify(archives)
    with zipfile.ZipFile(archives / "original-runtime.zip") as runtime, zipfile.ZipFile(archives / "original-hal.zip") as hal:
        def document(archive, name):
            return json.loads(archive.read(name))
        def rows(archive, name):
            return list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        records = [json.loads(line) for line in runtime.read("runtime-native-timing.jsonl").splitlines()]
        failure_index = next(i for i, row in enumerate(records) if row["fault"])
        first = records[failure_index]
        previous = records[failure_index - 1]
        native = first["captures"][0]["native_timing"]
        packet, completed = native["last_packet"], native["last_completed_callback"]
        anchor = completed["entry_host_time"]
        report = document(runtime, "source-writer.json")
        scale = report["host_time_numer"] / report["host_time_denom"] / 1e9
        def event_context(event, timing):
            return {"index": timing["index"], "sample_time": float(event["sample_time"]),
                "native_host_time": int(event["host_time"]), **timing,
                "entry_minus_native_ms": (timing["entry_host_time"] - int(event["host_time"])) * scale * 1000,
                "work_us": (timing["exit_host_time"] - timing["entry_host_time"]) * scale * 1e6,
                "entry_minus_os_now_ms": (timing["entry_host_time"] - timing["current_host_time"]) * scale * 1000}
        neighbors = {}
        for name in ("source-writer", "runtime-reader"):
            diag = document(runtime, name + "-diagnostics.json")
            events = rows(runtime, name + ".csv")
            index = min(range(len(diag["timings"])), key=lambda i: abs(diag["timings"][i]["entry_host_time"] - anchor))
            nearby = [event_context(events[i], diag["timings"][i]) for i in range(max(0, index - 2), min(len(events), index + 3))]
            for event in nearby:
                event["entry_relative_to_last_native_ms"] = (event["entry_host_time"] - anchor) * scale * 1000
            neighbors[name] = {"nearby_callbacks": nearby,
                "notifications": [{**n, "selector_fourcc": fourcc(n["selector"])} for n in diag["notifications"]]}
        diag = document(hal, "tone-writer-diagnostics.json")
        events = rows(hal, "tone-writer.csv")
        hal_report = document(hal, "tone-writer.json")
        if (report["host_time_numer"], report["host_time_denom"]) != (hal_report["host_time_numer"], hal_report["host_time_denom"]):
            raise ValueError("Independent jobs have different Mach timebases")
        gaps = []
        for i in range(1, len(events)):
            delta = float(events[i]["sample_time"]) - float(events[i-1]["sample_time"]) - int(events[i-1]["frames"])
            if abs(delta) <= .001:
                continue
            before = event_context(events[i-1], diag["timings"][i-1])
            after = event_context(events[i], diag["timings"][i])
            notifications = [{**n, "selector_fourcc": fourcc(n["selector"]),
                "ms_after_previous_entry": (n["host_time"] - before["entry_host_time"]) * scale * 1000}
                for n in diag["notifications"] if n["selector"] == int.from_bytes(b"over", "big")]
            stopped = {name: (before["entry_host_time"] - document(hal, name + "-diagnostics.json")["lifecycle"]["stop_return"]) * scale
                for name in ("reader-a", "reader-b")}
            gaps.append({"delta_frames": delta, "previous": before, "current": after,
                         "overload_notifications": notifications, "seconds_after_reader_stop": stopped})
        return {"schema": 1, "source_revision": SOURCE, "overall_result": "FAIL",
            "runtime": {"first_fault_code": first["fault"],
                "last_good_observation_host_time": previous["observed_host_time"],
                "first_bad_observation_host_time": first["observed_host_time"],
                "fault_observation_bracket_ms": (first["observed_host_time"] - previous["observed_host_time"]) * scale * 1000,
                "last_native_packet": packet, "last_native_completed_callback": completed,
                "last_native_entry_minus_input_ms": (anchor - packet["host_time"]) * scale * 1000,
                "last_native_callback_work_us": (completed["completion_host_time"] - anchor) * scale * 1e6,
                "last_native_completion_before_first_bad_ms": (first["observed_host_time"] - completed["completion_host_time"]) * scale * 1000,
                "first_packet_fault": native["first_fault"], "independent_observers": neighbors,
                "terminal_native_snapshot": records[-1]},
            "basic_hal_writer_gaps": gaps,
            "limits": ["Native snapshots are polled, not a full callback journal.",
                "Xrun code 5 has three possible origins: native input reentry, native input overload, CPAL output overload.",
                "No exact first-fault source/timestamp or output callback duration was recorded.",
                "Late independent callback entry supports a scheduling-disturbance hypothesis but does not identify its cause.",
                "Diagnostic instrumentation can perturb scheduling. No original failure or threshold is changed."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, default=ROOT)
    print(json.dumps(analyze(parser.parse_args().archives), indent=2, allow_nan=False))
