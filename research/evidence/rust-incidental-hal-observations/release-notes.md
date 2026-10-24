Three independent incidental installed-HAL observations are preserved here. **All three overall results are FAIL.** No run was repeated, repaired, rescored or promoted to a pass.

| Run | Independent HAL job | Capture/mix runtime job | Overall |
| --- | --- | --- | --- |
| [40044311801](https://github.com/thatsmethen/ravelink/actions/runs/40044311801) | Pass | Activation Xrun before readiness | **FAIL** |
| [40045101519](https://github.com/thatsmethen/ravelink/actions/runs/40045101519) | Callback gaps, PCM discontinuity and reader disagreement | Recorder continuity and phase-1 PCM failed | **FAIL** |
| [40046044508](https://github.com/thatsmethen/ravelink/actions/runs/40046044508) | Pass | Xrun after phase 3; source callback gap and missing stopped event | **FAIL** |

Cleanup passed in every job; this does not alter the acceptance failures. These incidental repeats are not a controlled comparison and do not identify the cause of the observed faults.

Each run has its original workflow-log ZIP plus original HAL and runtime artifact ZIPs. All original archive bytes are preserved, including captured PCM, timestamps and frozen reports. Asset names have been made unique; ZIP contents were not rewritten. Before publication, all artifact digests and every runner custody-manifest entry were verified.

Runs 40044311801 and 40045101519 share tree `f8d559ad78bad1c89853e7196657a2455fe1cc7b`; run 40046044508 uses tree `537b4bc7c159ef791e17ace44464b96c1666be87`. The release tag at `db639ffefcb49020b9c0cea08d5ca03b8bfa2cf0` is an archive anchor, not the source revision of all runs.

Compact custody metadata and exact asset hashes are maintained at `research/evidence/rust-incidental-hal-observations/`. The run metadata there is explicitly projected from original API responses; original raw responses remain unchanged locally. This release contains evidence, not an installable application or driver release.
