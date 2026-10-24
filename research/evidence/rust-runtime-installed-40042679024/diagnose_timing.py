"""Read-only derivation from the frozen original runtime artifact."""
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parent
artifact = root / "runtime-artifact"
records = [json.loads(line) for line in (artifact / "runtime-events.jsonl").read_text().splitlines()]
origin = next(record["host_time"] for record in records if record["event"] == "started")
report = json.loads((artifact / "runtime-reader.json").read_text())
scale = report["host_time_numer"] / report["host_time_denom"] / 1e9
stop = next(record for record in records if record["event"] == "stopped")
derived = {"schema": 1, "source_run": 40042679024,
    "source_revision": "4fad7fca69415bc86aae17caa5cab2641576a26e",
    "acceptance": "FAIL; derived timing does not repair original observations",
    "origin": "Runtime started event, after start() returned",
    "stop_requested_seconds": (stop["requested_host_time"] - origin) * scale,
    "stop_returned_seconds": (stop["returned_host_time"] - origin) * scale,
    "gap_observations": []}
for name in ("source-writer", "runtime-reader"):
    with (artifact / f"{name}.csv").open(newline="") as file:
        events = list(csv.DictReader(file))
    for index in range(1, len(events)):
        previous, current = events[index - 1], events[index]
        missing = float(current["sample_time"]) - float(previous["sample_time"]) - int(previous["frames"])
        if missing == 0:
            continue
        context = []
        for event in events[max(0, index - 2):index + 2]:
            context.append({"sample_time": float(event["sample_time"]),
                "callback_frames": int(event["frames"]),
                "native_host_seconds": (int(event["host_time"]) - origin) * scale,
                "observed_after_pcm_seconds": (int(event["observed_host_time"]) - origin) * scale,
                "observed_minus_native_seconds": (int(event["observed_host_time"]) - int(event["host_time"])) * scale})
        derived["gap_observations"].append({"process": name, "event_index_zero_based": index,
            "missing_sample_frames": missing, "context": context})
print(json.dumps(derived, indent=2, allow_nan=False))
