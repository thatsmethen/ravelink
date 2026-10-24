# Attribution checkpoint: installed runtime FAIL; separate basic HAL PASS

The one automatic push run [40048380199](https://github.com/thatsmethen/ravelink/actions/runs/40048380199), attempt 1, observed exact source `a4b21a393b1b1a9929d16da5d4e8ad0cea5cbfc7` on disposable GitHub macOS runners. The original run finished overall **FAIL**. No manual rerun, PCM repair, protocol change or threshold adjustment was made. Prior failed observations remain independent evidence.

## Original outcome

The application runtime exited with `CaptureUnderflow`. Its coupled first-fault record identifies `CaptureTransportConsumer`, direction `Input`, endpoint `coreaudio:au.textual.ravelink.cable.1`, epoch 1, fault 11, Mach observation tick `13915888552`, with complete metadata. This is 7.329696125 seconds after its start event and 192.125917 ms after the second phase's −12 dB request (143.022375 ms after its callback acknowledgment). The first −6 dB phase and second request exist; required subsequent protocol events do not. The original analyzer therefore reports `missing or repeated runtime protocol events`, and the complete runtime qualification fails.

The last polled native packet, index 688, was published. Its callback took 6.708333 µs and completed 15.598167 ms before the attributed fault. Its entry was 10.904 ms after its native input timestamp. Packet-level `first_fault` is null; this is consistent with a consumer underflow rather than a rejected native packet. Final native lifecycle reports successful stop, destroy and listener removal, zero callbacks in flight and `OwnerCompleted`. The independent source writer completed 60 seconds and the output recorder 32 seconds with continuous sample clocks; neither observer recorded an overload notification. These facts identify the failure-reporting path without establishing the scheduling or clock cause. Final `buffered_frames=1056` is the last successful prepare occupancy, not the underflow-time cursor. There is no full runtime output callback journal or full native input callback journal.

The separate basic installed-HAL job passed its unchanged protocol: a 40-second source writer, two 20-second independent recordings, steady stereo amplitude/channel/continuity checks, 756,388 overlapping frames identical between readers, and exact restart silence. Both jobs verified removal of their owned driver; runtime cleanup verified both cable UIDs absent. A passing basic driver observation does not replace application runtime acceptance or erase earlier intermittent failures.

## Custody and reproduction

Original archives are published without repacking at the [evidence prerelease](https://github.com/thatsmethen/ravelink/releases/tag/evidence-attribution-runtime-40048380199). Exact asset URLs, publication readback and tag verification are in `publication.json`. Large archives and extracted files are intentionally excluded from Git after public download verification.

| Original archive | GitHub artifact ID | Bytes | SHA-256 |
|---|---:|---:|---|
| `original-runtime.zip` | 12542521354 | 2,855,211 | `182d402aba8ef2141dd55b84afc5ee6b9f0267f92d338a1eccc7400f498e9478` |
| `original-hal.zip` | 12541364444 | 10,536,082 | `520b0d57fcc2037b1e640aa28e0b5b1e42b8b09b0bde831edd60a6bd5acfee22` |

`first-*-snapshot.json` retains the initial in-progress observation. `original-*.json` and `original-run.log` preserve final GitHub responses. Each ZIP's digest matches GitHub metadata. Its manifest identifies the exact source; all 121 manifest members (56 runtime, 65 basic HAL) verify byte lengths and SHA-256. The two manifests are additional ZIP members, for 123 total members. `*-custody-verification.json` records this check; it does not change the acceptance outcome.

Download both original ZIP assets into a directory, then run:

```sh
python3 research/evidence/rust-attribution-installed-40048380199/verify.py --archives /absolute/download/directory
python3 research/evidence/rust-attribution-installed-40048380199/diagnose_timing.py --archives /absolute/download/directory
```

The second command recreates `derived-timing.json` from verified original archives. It preserves full first-fault and terminal snapshots and adjacent independent observer timings; it does not reclassify the failed sequence. Native callback state is polled and diagnostics can perturb scheduling. No local audio devices, driver installation or default audio settings were accessed for this evidence review.
