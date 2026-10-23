# Release baseline evidence — failed soak retained

Source: `b7872630d29c8fd1a0864fbb93599c5bf576d873`.
Original [CI run 39998798881](https://github.com/thatsmethen/ravelink/actions/runs/39998798881)
failed the device-input soak and separate deterministic tests. Loopback, matrix,
Audio Unit and Sound Check acceptance passed. The original reports, logs,
provenance and post-run diagnostic results remain distinct in this folder.

The two 60-second, eight-channel soak recordings are preserved losslessly as
numbered 512 KiB parts in the private
[draft evidence release](https://github.com/thatsmethen/ravelink/releases/tag/untagged-126e3fe9c151ee7af29a),
tag `evidence-b787263`, release ID `422198169`. Repository/release access is
required. The parts split the original gzip bytes; they do not transform PCM.
`parts-manifest.json` records every part, reconstructed gzip and raw WAV hash.
`verified-upload.json` records GitHub asset identities/digests. Use the numbered
parts only: two failed whole-file upload entries have no verified digest.

From the repository root, download into a fresh directory and restore:

```sh
gh release download evidence-b787263 --repo thatsmethen/ravelink \
  --pattern 'soak-*.wav.gz.part*' --pattern parts-manifest.json \
  --dir build/b787263-downloaded-parts
shasum -a 256 build/b787263-downloaded-parts/parts-manifest.json
python3 scripts/restore-evidence.py \
  build/b787263-downloaded-parts/parts-manifest.json \
  --output-directory build/b787263-restored
```

The manifest SHA-256 must be
`c7b09c872512df42b0855ea3b821864bc47d63a93e5902e4215b28a4a60c357e`.
The restoration script verifies each part, the complete gzip length/hash, and
the decompressed WAV length/hash before publishing either restored archive.
It refuses to overwrite existing output. Each raw WAV is 92,160,044 bytes.

| Recording | Original WAV SHA-256 |
| --- | --- |
| `soak-a.wav` | `5eea5ccf5afc7a803b8e4e0a54bae5279eacf2990f2f847f0511ee0e9111eab9` |
| `soak-b.wav` | `cc688c0774bd0c351fe953fb61094eaa054343210bc46ea90ec4ab28a044272d` |

Upload digests and local reconstruction were verified. The parent task then
downloaded all 96 parts and the manifest from the private release and restored
both archives. `verified-remote-retrieval.json` records an independent recheck of
those downloaded part bytes, the exact manifest digest, both restored gzip hashes
and both decompressed WAV hashes, with a UTC verification time. To replay the original analyzer, use
the source revision above: later analyzers describe the changed physical-capture
accounting and must not overwrite this baseline's outcome.
