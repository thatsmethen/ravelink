Original installed observation: **overall FAIL**. The actual application capture/mix runtime failed with an attributed capture-consumer underflow. The separate basic installed-HAL loopback job passed. This is evidence publication, not a product release or production qualification.

- Source: `a4b21a393b1b1a9929d16da5d4e8ad0cea5cbfc7`.
- Automatic push run: [40048380199](https://github.com/thatsmethen/ravelink/actions/runs/40048380199), attempt 1. No manual rerun or threshold changes.
- Runtime: first fault 11 (`CaptureTransportConsumer`, Input `coreaudio:au.textual.ravelink.cable.1`, epoch 1) at Mach tick `13915888552`, 7.329696 seconds after the start event. Required later gain/mute/stop phases were not completed; runtime acceptance failed.
- Independent runtime source writer and output recorder completed their original 60-second and 32-second windows with continuous sample clocks. This does not qualify the incomplete application sequence or explain the underflow.
- Basic HAL: original 40-second writer, two 20-second readers, 756,388 identical overlapping frames, and restart silence passed the unchanged protocol. Both jobs verified owned-driver cleanup.
- Attribution identifies the reporting path, not the scheduler or clock cause. Polled native snapshots are not a complete runtime callback journal. Diagnostic instrumentation may affect scheduling.

Original GitHub artifact ZIPs, preserved without repacking:

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `original-runtime.zip` | 2,855,211 | `182d402aba8ef2141dd55b84afc5ee6b9f0267f92d338a1eccc7400f498e9478` |
| `original-hal.zip` | 10,536,082 | `520b0d57fcc2037b1e640aa28e0b5b1e42b8b09b0bde831edd60a6bd5acfee22` |

Both original ZIP digests and all 121 manifest files match GitHub's artifact metadata and the exact source revision. The repository evidence directory `research/evidence/rust-attribution-installed-40048380199` contains the frozen metadata, chronology and an independent `verify.py --archives <download-directory>` custody verifier. Custody verification is separate from runtime acceptance.
