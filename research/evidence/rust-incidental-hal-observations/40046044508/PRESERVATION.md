# Preserved incidental run 40046044508

Run: https://github.com/thatsmethen/ravelink/actions/runs/40046044508
Source: `03ff13a4f3b38fd4568ffdf96d893f7c05564f17`
Tree: `537b4bc7c159ef791e17ace44464b96c1666be87`
Conclusion: **failure**

The independent HAL acceptance passed, including equal overlapping readers, no sample gaps, and restarted silence peak 0. Runtime capture/mix failed with `runtime stopped: fault=Xrun, error=None` (exit 1). Its event log contains started and phases 0, 1, 2 and 3, but no stopped event. Source writer recorded a 2648-frame callback gap after sample 908868. The independent output analysis failed with `missing or repeated runtime protocol events`, so it did not produce a completed phase acceptance result. Recorder exited 0 and completed its requested frame count; this does not establish PCM acceptance. Both cleanup reports passed.

Original API responses, logs ZIP and artifact ZIPs remain unchanged. Every artifact matches its GitHub SHA-256 digest and CRC, and every runner custody-manifest entry matches the archived bytes, including retained WAV files. The logs ZIP has a locally recorded hash because the logs API supplies no digest. See collection.json and custody-verification.json.

These incidental repeats are not a controlled experiment. The recorded gaps and faults do not establish their cause. No run was repeated, repaired or rescored during collection. Initial runs 40044311801 and 40045101519 have the same source tree; run 40046044508 uses a later tree. Cleanup success does not turn acceptance failure into success.

## Original archive hashes

- `logs.zip` (logs, 31081 bytes): `3216f87ccaf2fc43bac2876893dc6774a743fc9fa9b5a64247a28e1e8d3c8b4c`
- `artifact-12540974278.zip` (original-rust-hal-40046044508-1, 10299518 bytes): `92868147abc0dce11b3a2ec32871de9d6928aa5a27d96f4ece79bc8feba75b36`
- `artifact-12540564349.zip` (original-rust-runtime-40046044508-1, 4916944 bytes): `62ce393faa55dd6e2576e51030237cb7ac32ac797584e59ee74ff946a0f7672d`
