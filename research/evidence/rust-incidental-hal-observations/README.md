# Three incidental installed-HAL failures, preserved independently

These are three separate **FAIL** observations triggered by intervening pushes,
including release-tag and contribution-identity work. They are not a controlled
experiment, a replacement for any earlier result, or evidence of improvement.
No run was restarted, repaired or rescored for this preservation work.

| Run | Overall | Independent HAL job | Capture/mix runtime job |
| --- | --- | --- | --- |
| [40044311801](https://github.com/thatsmethen/ravelink/actions/runs/40044311801) | **FAIL** | Pass | Activation Xrun before readiness; recorder never started |
| [40045101519](https://github.com/thatsmethen/ravelink/actions/runs/40045101519) | **FAIL** | Callback gaps, PCM discontinuity and reader disagreement | Independent recorder gap and phase-1 PCM failure; executable-local success does not override acceptance |
| [40046044508](https://github.com/thatsmethen/ravelink/actions/runs/40046044508) | **FAIL** | Pass | Xrun after phase 3; source callback gap and missing stopped event |

Every job's cleanup report passed. Cleanup success does not change acceptance.
The recorded faults and gaps do not establish their cause.

The first two runs have identical source tree
`f8d559ad78bad1c89853e7196657a2455fe1cc7b`, despite different original commit
identities. The third uses tree `537b4bc7c159ef791e17ace44464b96c1666be87`.
Each source revision, tree and exact failed step is retained in its run directory.

## Evidence custody

[The evidence release](https://github.com/thatsmethen/ravelink/releases/tag/evidence-incidental-hal-20261024)
contains nine original ZIP byte streams: one workflow-log archive and two
artifact archives per run. The six artifact archives retain all reports,
timestamps, captured WAVs and original runner custody manifests. Asset filenames
were made unique; archive contents were not rewritten. `release-plan.json`
records their byte lengths, SHA-256 hashes, original artifact names and URLs.
The tag targets `db639ffefcb49020b9c0cea08d5ca03b8bfa2cf0` as an archive anchor;
it does not assert that all three runs used that revision.

Before staging, every local preservation-manifest file was rehashed. Each
artifact archive matches its original GitHub artifact digest, and every file in
each runner-created custody manifest matches the archived bytes. Workflow-log
ZIPs have locally recorded hashes because their download API supplies no digest.
The retained source tree checks and archive verification are independent of the
frozen acceptance outcomes.

`run-metadata.json` files are explicitly labelled **metadata projections** of
selected original API fields, not original API responses. They omit historical
author/committer identity fields. Raw original API responses, original ZIPs and
extracted reports remain unchanged in the corresponding `build/rust-hal-failed-*`
collections; their hashes are retained in `original-local-files.json`. Public
metadata does not include those omitted identity values.

`PRESERVATION.md`, `collection.json` and `custody-verification.json` are copies of
the previously appended local preservation records. They are not original
runner reports. The original reports remain inside the byte-identical assets.
The script `preserve.py` prepares this bounded metadata and the asset staging
directory from the frozen local collections, refusing existing outputs.

`published-release.json` and `release-download-verification.json` record the
publication and independent redownload check once completed. The latter verifies
the published ZIP bytes, CRCs and runner custody manifests; it never executes a
contained program or reruns an audio analysis. No large archive or extracted WAV
is committed in this metadata directory.

For a later custody-only replay, select fresh destinations so the original
verification is not overwritten:

```sh
python3 research/evidence/rust-incidental-hal-observations/verify-release.py \
  --record-directory build/incidental-hal-replay-records \
  --download-directory build/incidental-hal-replay-downloads
```

This uses the GitHub CLI for public release retrieval and Python's standard
library for hashing and ZIP inspection. It does not change a frozen outcome.
