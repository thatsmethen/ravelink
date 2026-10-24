#!/usr/bin/env python3
"""Derived first-fault chronology; no PCM repair or acceptance changes."""
import argparse
import csv
import io
import json
from pathlib import Path
import zipfile

from verify import ROOT, SOURCE, verify


def analyze(archives):
    verify(archives)
    with zipfile.ZipFile(archives / "original-runtime.zip") as archive:
        def document(name):
            return json.loads(archive.read(name))

        records = [json.loads(line) for line in archive.read("runtime-native-timing.jsonl").splitlines()]
        first = next(row for row in records if row["fault"])
        fault = first["first_fault"]
        if fault["metadata_pending"] or fault["metadata"] is None:
            raise ValueError("First fault metadata is incomplete")
        anchor = fault["metadata"]["observed_mach_host_time"]
        report = document("source-writer.json")
        scale = report["host_time_numer"] / report["host_time_denom"] / 1e9
        native = first["captures"][0]["native_timing"]
        completed = native["last_completed_callback"]
        packet = native["last_packet"]
        events = [json.loads(line) for line in archive.read("runtime-events.jsonl").splitlines()]
        nearby = {}
        for name in ("source-writer", "runtime-reader"):
            diag = document(name + "-diagnostics.json")
            pcm = list(csv.DictReader(io.StringIO(archive.read(name + ".csv").decode())))
            index = min(range(len(diag["timings"])), key=lambda i: abs(diag["timings"][i]["entry_host_time"] - anchor))
            rows = []
            for i in range(max(0, index - 2), min(len(pcm), index + 3)):
                timing = diag["timings"][i]
                rows.append({**timing, "native_sample_time": float(pcm[i]["sample_time"]),
                    "native_host_time": int(pcm[i]["host_time"]),
                    "entry_relative_to_fault_ms": (timing["entry_host_time"] - anchor) * scale * 1000,
                    "entry_minus_native_ms": (timing["entry_host_time"] - int(pcm[i]["host_time"])) * scale * 1000,
                    "callback_work_us": (timing["exit_host_time"] - timing["entry_host_time"]) * scale * 1e6})
            nearby[name] = {"callbacks": rows, "notifications": diag["notifications"]}
        return {"schema": 1, "source_revision": SOURCE, "overall_result": "FAIL",
            "runtime_first_fault": fault,
            "seconds_from_started_to_fault": (anchor - events[0]["host_time"]) * scale,
            "phases": [{**event,
                "acknowledgment_ms": (event["acknowledged_host_time"] - event["requested_host_time"]) * scale * 1000,
                "fault_ms_after_request": (anchor - event["requested_host_time"]) * scale * 1000,
                "fault_ms_after_acknowledgment": (anchor - event["acknowledged_host_time"]) * scale * 1000}
                for event in events if event["event"] == "phase"],
            "last_native_packet": packet, "last_native_completed_callback": completed,
            "native_packet_fault": native["first_fault"],
            "last_native_entry_minus_input_ms": (completed["entry_host_time"] - packet["host_time"]) * scale * 1000,
            "last_native_callback_work_us": (completed["completion_host_time"] - completed["entry_host_time"]) * scale * 1e6,
            "last_native_completion_before_fault_ms": (anchor - completed["completion_host_time"]) * scale * 1000,
            "independent_observers": nearby,
            "terminal_native_snapshot": records[-1],
            "limits": [
                "Attribution identifies the capture consumer underflow report, not the scheduler or clock cause.",
                "Native snapshots are polled; no complete native-input or runtime-output callback journal exists.",
                "Final buffered_frames is the previous successful prepare occupancy, not the underflow-time cursor.",
                "Missing required protocol phases keep runtime acceptance failed; completed phases are not a replacement test.",
                "Diagnostic instrumentation may perturb scheduling. Frozen PCM, reports and limits are unchanged."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, default=ROOT)
    print(json.dumps(analyze(parser.parse_args().archives), indent=2, allow_nan=False))
