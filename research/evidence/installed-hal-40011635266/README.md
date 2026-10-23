# Installed-driver observation — failed soak retained

Source: `784e38f30a7b51f2fc8d40d58413780ae11e9944`.
Original [CI run 40011635266](https://github.com/thatsmethen/ravelink/actions/runs/40011635266)
failed the strict device-input soak and driver lifecycle acceptance. Deterministic
macOS tests, basic loopback, matrix routing, Audio Unit and Sound Check acceptance
passed. Original reports and logs remain unchanged; post-run diagnosis is separate.

The soak used 12 visible input groups, 24 logical sources, two unique capture
sources, eight mix buses on two output devices, 48 kHz and 512-frame buffers.
It recorded 296 engine underrun frames, zero dropped/oversized frames, two feeder
timestamp discontinuities and one recorder-A discontinuity. Mean measured engine
CPU was 0.0894114 core equivalents, peak resident memory 30,457,856 bytes. Sparse
post-run signal windows show the repeated-source cancellation defect no longer
occurs, but the uninterrupted routing gate still fails. These measurements do
not establish a generally supported scale or latency envelope.

The lifecycle run caught Installer reporting success but skipping the payload
when a higher build number had a lower marketing version. The report's payload
hash assertion correctly failed. Later code changes are not part of this run.

Both original 60-second, eight-channel soak recordings are preserved losslessly
as numbered 512 KiB parts in the private
[draft evidence release](https://github.com/thatsmethen/ravelink/releases/tag/untagged-4914eee7527f412d2aa9),
tag `evidence-784e38f`, release ID `422248488`. Access to the private repository is
required. This is an evidence archive, not a product release. All 100 assets
(98 parts, manifest and original provenance) were checked against GitHub's
uploaded state, byte length and SHA-256 digest. The original local gzip archives
remain preserved but are intentionally excluded from Git due to transfer limits.

From the repository root, download into a fresh directory and restore:

```sh
gh release download evidence-784e38f --repo thatsmethen/ravelink \
  --pattern 'soak-*.wav.gz.part*' --pattern parts-manifest.json \
  --dir build/784e38f-downloaded-parts
shasum -a 256 build/784e38f-downloaded-parts/parts-manifest.json
python3 scripts/restore-evidence.py \
  build/784e38f-downloaded-parts/parts-manifest.json \
  --output-directory build/784e38f-restored
```

The manifest SHA-256 must be
`694f5f4d794f113e3dbbaf0fe1e7f1cdc846b81f94f8105c44e1d1963d3e1588`.
Restoration checks every part, the full gzip and decompressed raw WAV before
publishing output; existing output is not overwritten. Each raw WAV is
92,160,044 bytes. `verified-remote-retrieval.json` records the successful download
and reconstruction of both archives with original raw hashes on 23 October 2026
UTC. `verified-upload.json` retains the GitHub asset IDs and digests.

| Recording | Original WAV SHA-256 |
| --- | --- |
| `soak-a.wav` | `b2feb0e79d489da25fd947aa86de46d44c6905ac44d4fb5a7ef3db062a093c62` |
| `soak-b.wav` | `2c7fa6cf7107d49a2cd4a5e2592666b6712873f6d1235d2c98a0675f0aa6a9f3` |

Use the exact source revision above to replay the original verifier. A later
in-process probe reproduced stale audio after an intentionally skipped write in
the pinned upstream ring; that is separate evidence and does not establish why
macOS skipped callbacks during this run. Neither that diagnosis nor subsequent
clock-controller changes repair or replace this failed observation.
