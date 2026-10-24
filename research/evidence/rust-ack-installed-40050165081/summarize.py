#!/usr/bin/env python3
"""Summarize verified original reports without changing their acceptance criteria."""
import argparse
import json
from pathlib import Path
import zipfile

from verify import ROOT, SOURCE, verify


def summarize(archives):
    custody = verify(archives)
    run = json.loads((ROOT / "original-run.json").read_text())
    jobs = json.loads((ROOT / "original-jobs.json").read_text())
    if run["head_sha"] != SOURCE or run["run_attempt"] != 1:
        raise ValueError("Unexpected source or attempt")
    with zipfile.ZipFile(archives / "original-runtime.zip") as runtime, zipfile.ZipFile(archives / "original-hal.zip") as hal:
        def doc(archive, name):
            return json.loads(archive.read(name))

        pcm = doc(runtime, "runtime-output-analysis.json")
        events = [json.loads(line) for line in runtime.read("runtime-events.jsonl").splitlines()]
        native = [json.loads(line) for line in runtime.read("runtime-native-timing.jsonl").splitlines()]
        phases = []
        for phase in pcm["phases"]:
            event = next(e for e in events if e["event"] == "phase" and e["phase"] == phase["phase"])
            phases.append({"phase": phase["phase"], "gain_db": event["gain_db"],
                "muted": event["muted"], "version": event["version"],
                "pass": phase["pass"], "acknowledgment_seconds": phase["acknowledgement_seconds"],
                "detected_response_seconds": phase["detected_response_seconds"],
                "channels": phase.get("channels"), "mute_peak": phase.get("peak"),
                "longest_stereo_zero_run": phase.get("longest_stereo_zero_run")})
        basic = doc(hal, "acceptance.json")
        pair = next(o for o in basic["observations"] if "overlap_frames" in o)
        return {"schema": 1, "source_revision": SOURCE, "run_id": run["id"],
            "run_attempt": run["run_attempt"], "run_conclusion": run["conclusion"],
            "jobs": [{"name": j["name"], "conclusion": j["conclusion"]} for j in jobs["jobs"]],
            "runtime": {"acceptance_pass": doc(runtime, "runtime-acceptance.json")["pass"],
                "client_result": doc(runtime, "runtime-result.json"), "pcm_pass": pcm["pass"],
                "criteria": pcm["criteria"], "phases": phases, "clock": pcm["clock"],
                "unmuted_zero_runs": pcm["unmuted_zero_runs"],
                "stopped_tail_peak": pcm["stopped_tail_peak"],
                "stop_response_seconds": pcm["stop_response_seconds"],
                "source_writer": doc(runtime, "source-writer-analysis.json"),
                "events": events, "fault_codes_in_polled_records": sorted({r["fault"] for r in native}),
                "terminal_native_snapshot": native[-1], "cleanup": doc(runtime, "cleanup.json")},
            "basic_hal": {"acceptance_pass": basic["pass"], "reader_pair": pair,
                "observations": [{k: o[k] for k in ("source_report", "pass", "clock", "frames", "mode", "peak", "longest_stereo_zero_run") if k in o}
                    for o in basic["observations"]], "cleanup": doc(hal, "cleanup.json")},
            "custody": custody,
            "limits": ["One original automatic run; no retry or threshold changes.",
                "Phase zero already matches the initial compiled gain; its negative response offset is not measured response latency.",
                "Subsequent response estimates use the fixed envelope detector and are not acoustic latency measurements.",
                "Native and runtime telemetry are polled, while independent recorder timestamps cover each observer callback.",
                "Earlier failed observations remain valid; this does not prove their root causes repaired.",
                "The output remains CPAL. Native output adapters, multiple outputs, Windows installed operation and production qualification are not established."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, default=ROOT)
    print(json.dumps(summarize(parser.parse_args().archives), indent=2, allow_nan=False))
