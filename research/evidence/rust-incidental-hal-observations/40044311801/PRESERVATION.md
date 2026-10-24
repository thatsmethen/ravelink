# Preserved incidental run 40044311801

Run: https://github.com/thatsmethen/ravelink/actions/runs/40044311801
Source: `4fad7fca69415bc86aae17caa5cab2641576a26e`
Tree: `f8d559ad78bad1c89853e7196657a2455fe1cc7b`
Conclusion: **failure**

The independent HAL acceptance passed. The runtime capture/mix job failed during activation before readiness: `Audio stream activation failed for RaveLink 2: The device reported a buffer underrun or overrun. Output stopped; reduce audio load before restarting.` Runtime exited 1 and published no protocol events. The orchestrator reported `runtime did not publish real capture/mix readiness`; the recorder never started and its analysis records the missing `runtime-reader.json`. Source writer exited 0 without recorded sample gaps. Both cleanup reports passed with both cable UIDs absent.

Original API responses, logs ZIP and artifact ZIPs remain unchanged. Every artifact matches its GitHub SHA-256 digest and CRC, and every runner custody-manifest entry matches the archived bytes, including retained WAV files. The logs ZIP has a locally recorded hash because the logs API supplies no digest. See collection.json and custody-verification.json.

These incidental repeats are not a controlled experiment. The recorded gaps and faults do not establish their cause. No run was repeated, repaired or rescored during collection. Initial runs 40044311801 and 40045101519 have the same source tree; run 40046044508 uses a later tree. Cleanup success does not turn acceptance failure into success.

## Original archive hashes

- `logs.zip` (logs, 31185 bytes): `c9a6c22672ae8bb6df7be9147d1e7707f651e5776b0433be682c1b7abcc220f0`
- `artifact-12540533344.zip` (original-rust-runtime-40044311801-1, 90162 bytes): `50fdb800f8c5c019f9a0866254628a58af69880e45d9192c749948136d3c6983`
- `artifact-12540423242.zip` (original-rust-hal-40044311801-1, 10304066 bytes): `8213d7e4e3316fe6b6a71f8568bed779b7ba489f097e3e188ceeadaa5dcc3d3c`
