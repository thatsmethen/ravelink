Original installed observation: **PASS for both application runtime and basic HAL jobs**, limited to this single macOS run. This is evidence publication, not a product release or production qualification. Earlier failed observations remain unchanged and are not explained away by this success.

- Source: `db052e4fb790801c6692fc0caba82f0545e2055e`.
- Automatic push [run 40050165081](https://github.com/thatsmethen/ravelink/actions/runs/40050165081), attempt 1. No manual rerun or threshold change.
- Actual runtime: independent writer → Cable 1 → `AudioRuntime` capture/mix → Cable 2 → independent recorder. The full −6 dB, −12 dB, mute, unmute/−6 dB and explicit Stop sequence passed the unchanged PCM, clock and control criteria.
- Changing controls were detected at approximately 25–30 ms; Stop at 35 ms, within the fixed request-based 250 ms bounds. Initial −6 dB was already compiled and is not a response-latency measurement. No unmuted stereo zero runs; mute and stopped tail exactly silent.
- Independent runtime writer/recorder completed 60/32 seconds with continuous sample clocks. Polled fault codes remained zero; native capture teardown reported successful completion.
- Basic HAL: original 40-second writer, two 20-second readers, 759,516 identical overlapping frames and restart silence passed. Both jobs verified owned-driver cleanup and both cable UIDs absent.
- This does not establish long-duration reliability, causes of earlier failures, Windows installed operation, proposed native output ownership, multiple outputs or production completion. Runtime output still uses CPAL.

Original GitHub artifact ZIPs, preserved without repacking:

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `original-runtime.zip` | 6,838,012 | `245d1b455888aba8f51272431f618beba928ff3914c7ee5a9e162f8d29f4f596` |
| `original-hal.zip` | 10,535,621 | `8d1f11c66d2cf16f31cfd2bd71a1309d1834bafdf5afca1d983f86e7030c2f4b` |

Both ZIP digests and all 121 manifest files match GitHub artifact metadata and the exact source. The repository evidence directory `research/evidence/rust-ack-installed-40050165081` retains metadata, original outcomes and portable `verify.py --archives <download-directory>` / `summarize.py` tools. Custody checks are separate from acceptance.
