# ACK checkpoint: one complete installed runtime and basic HAL PASS

The automatic push run [40050165081](https://github.com/thatsmethen/ravelink/actions/runs/40050165081), attempt 1, observed exact source `db052e4fb790801c6692fc0caba82f0545e2055e`. Both installed jobs finished **PASS**. This is one original observation on disposable arm64 macOS 15.7.9 GitHub runners, using Rust 1.91.1. There was no manual rerun, protocol adjustment or threshold change. Earlier failed observations remain separate evidence; this run does not establish that their causes were repaired.

## Original application runtime outcome

The actual `AudioRuntime` received the independent C writer through Cable 1, mixed into Cable 2 and was recorded independently. The original result and full PCM analyzer both passed. Output still uses CPAL; this does not qualify the proposed native output adapters or multiple outputs.

| Phase | Selected control | Original callback ACK | Original detected response | Original phase result |
|---|---|---:|---:|---|
| 0 | −6 dB, unmuted | 11.120 ms | Already present at initial compiled gain | PASS |
| 1 | −12 dB, unmuted | 24.657 ms | 30.010 ms | PASS |
| 2 | Muted | 24.258 ms | 29.997 ms | PASS |
| 3 | −6 dB, unmuted | 8.885 ms | 25.008 ms | PASS |
| Stop | Explicit stop | Separate stop event | 35.010 ms | PASS |

The fixed detector's first-phase response value is −0.050001 seconds because the initial compiled mix already has that gain; it is **not** a measured negative response latency. Later estimates use the unchanged envelope detector and are not acoustic latency measurements. All requested control ACKs and changing-control/stop responses satisfied the original request-based 250 ms bounds.

All unmuted steady windows passed amplitude, frequency, mean and sine-recurrence checks. Reported relative amplitude errors were at most `2.014313e-5`, and measured frequency error was at most 26.889 ppm. The original analyzer found no unmuted stereo zero runs; mute and stopped-tail peaks were exactly zero. The source writer completed 60 seconds (5,625 callbacks) and the independent output recorder 32 seconds (3,000 callbacks), with continuous sample clocks at 48 kHz. The runtime completed the full protocol and exited successfully after approximately 23.78 seconds of process lifetime.

Every polled runtime fault code was zero and coupled `first_fault` remained null. Final native capture state reported `OwnerCompleted`, zero callbacks in flight, and successful stop, destroy and listener removal. These are polled telemetry/lifecycle observations, not a full journal of every runtime callback. Both UIDs were verified absent after owned-driver cleanup.

## Separate basic HAL outcome

The original 40-second writer, two 20-second readers and restart-silence sequence all passed the unchanged protocol. The two readers' 759,516 overlapping frames were identical, with maximum difference zero. Both steady recordings had no stereo zero runs and passed channel/amplitude/residual checks; restarted silence had peak zero. The writer and reader sample clocks were continuous. Owned-driver removal and absence of both cable UIDs were verified.

## Source and scope

This checkpoint changes control acknowledgment timing and adds offline prerequisites. Relative to the preceding `a4b21a393b1b1a9929d16da5d4e8ad0cea5cbfc7` observation, the committed `drivers/macos/tests` tree is unchanged. Capture transport changes only expose the existing correction constant and add read-only kernel accessors for offline fanout; the existing capture consumer thresholds, arithmetic and priming policy remain unchanged. A later native-output implementation must receive its own installed qualification.

The prior ambiguous Xrun and attributed capture-underflow failures were not rerun or reclassified. This short successful run is not long-duration reliability evidence, Windows installed acceptance, acoustic latency measurement, plugin-host qualification, multi-output qualification or production completion.

## Custody and reproduction

Original archives are published without repacking at the [evidence prerelease](https://github.com/thatsmethen/ravelink/releases/tag/evidence-ack-runtime-40050165081). Exact public URLs and anonymous readback results are in `publication.json`.

| Original archive | GitHub artifact ID | Bytes | SHA-256 |
|---|---:|---:|---|
| `original-runtime.zip` | 12542474990 | 6,838,012 | `245d1b455888aba8f51272431f618beba928ff3914c7ee5a9e162f8d29f4f596` |
| `original-hal.zip` | 12542922152 | 10,535,621 | `8d1f11c66d2cf16f31cfd2bd71a1309d1834bafdf5afca1d983f86e7030c2f4b` |

The first in-progress API snapshots, final GitHub metadata and original job log are retained. Both ZIP digests match GitHub artifact metadata. All 121 manifest files (56 runtime, 65 HAL) match their byte counts and SHA-256; including both manifests, there are 123 ZIP members. Public readback compares the complete ZIPs and every member. Archives and extracted files are excluded from Git only after successful public verification.

Download both assets into a directory, then run:

```sh
python3 research/evidence/rust-ack-installed-40050165081/verify.py --archives /absolute/download/directory
python3 research/evidence/rust-ack-installed-40050165081/summarize.py --archives /absolute/download/directory
```

`summarize.py` reproduces `derived-summary.json` from verified original reports and telemetry without altering their criteria or reclassifying them. Custody verification and acceptance remain separate claims. No local driver, audio-device or default-setting operations were performed for this observation review.
