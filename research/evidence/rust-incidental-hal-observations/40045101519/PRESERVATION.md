# Preserved incidental run 40045101519

Run: https://github.com/thatsmethen/ravelink/actions/runs/40045101519
Source: `eebc08b19ba04f6b7d22d8593211532957633d5a`
Tree: `f8d559ad78bad1c89853e7196657a2455fe1cc7b`
Conclusion: **failure**

Both installed jobs failed. The HAL job recorded sample callback gaps of 868 frames for the writer, 812 for reader A and 808 for reader B; each reader contained a 1380-frame stereo zero run. Reader overlap covered 752636 frames with maximum difference 0.19753236323595047 and 37664 samples differing by more than 1e-6. Restarted silence passed at peak 0. The runtime executable itself returned pass/exit 0, but independent acceptance failed: its recorder had a 772-frame sample gap, and gain phase 1 failed the PCM recurrence thresholds (left/right relative peak 0.3581903670/0.2201936920, relative RMS 0.0009392753/0.0005896318, thresholds 0.005/0.0005). Other gain/mute phases passed. Stopped tail peak was 0 and observed stop response was 0.0249922083 seconds. Both cleanup reports passed. Runtime-local success does not override independent acceptance failure.

Original API responses, logs ZIP and artifact ZIPs remain unchanged. Every artifact matches its GitHub SHA-256 digest and CRC, and every runner custody-manifest entry matches the archived bytes, including retained WAV files. The logs ZIP has a locally recorded hash because the logs API supplies no digest. See collection.json and custody-verification.json.

These incidental repeats are not a controlled experiment. The recorded gaps and faults do not establish their cause. No run was repeated, repaired or rescored during collection. Initial runs 40044311801 and 40045101519 have the same source tree; run 40046044508 uses a later tree. Cleanup success does not turn acceptance failure into success.

## Original archive hashes

- `logs.zip` (logs, 31239 bytes): `6d32afaff92d69142cfc6a6d3606d93dd62632a58b5e34d661f7bcff0c3324c9`
- `artifact-12540634166.zip` (original-rust-runtime-40045101519-1, 6346598 bytes): `5a6366f0a55bf7b488030ea8f223d67034ff051c8dd93014f64abe97077a974f`
- `artifact-12540149104.zip` (original-rust-hal-40045101519-1, 10289792 bytes): `c5bbaf5b3517e2919b8d67addf38678a502a6d0cfb75a45f2f60dc5eb96a5e8e`
