# Wave Link reference and evidence

Reference selected on 23 October 2026: **Elgato Wave Link for macOS 3.4.0, build 3281**. The vendor's [official update feed](https://gc-updates.elgato.com/mac/ewlm-update/final/feed.xml) selected that build at acquisition. Its published date is 8 October 2026; this is distinct from the acquisition date. The [official DMG](https://edge.elgato.com/egc/macos/ewlm/release/ElgatoWaveLink-3.4.0.3281.dmg) is 100,762,225 bytes, SHA-256 `49f15d4a6565885631485b69f0c7f4bbdc8856d11af479a18555d30a1e548a1f`.

The app was mounted read-only, not installed. `codesign --verify --deep --strict` succeeded. Its signing identity is Corsair Memory, Inc., team `Y93VXCB8Q5`. The bundle identifies `com.elgato.WaveLink3`, version `3.4.0`, build `3281`, minimum macOS `15.0`. Host: macOS 27.0 build 26A5406e, arm64. The executable contains arm64 and x86_64 slices; inspected native slice is arm64. These are identity and static inspection facts, not audio compatibility results.

## Sources and design boundary

The [current product specifications](https://www.elgato.com/us/en/s/wave-link-app) describe eight software/non-Wave channels plus four Wave inputs, unlimited apps per channel, five virtual mixes, multiple playback devices, 48 kHz stereo processing, mono duplication, and AU effects on macOS. RaveLink's removal of channel/mix count caps is a deliberate extension; actual simultaneous capacity must be measured on a particular machine.

The [official software overview](https://www.elgato.com/us/en/explorer/products/wave/wave-link-3-0-software-overview/) supplies the workflow reference: inputs at left, mix columns at top, monitor selector above, independent route levels, channel creation from devices/apps, named virtual channels, and input effect configuration. Its screenshots show Windows and are documentation evidence, not observed macOS UI.

Selected visual references inspected through a browser:

- [Mix matrix](https://d32bbxx72p2025.cloudfront.net/images/Wave_Link_3_Unmuted.width-1000.format-webp.webp)
- [Channel picker](https://d32bbxx72p2025.cloudfront.net/images/Wave_Link_3_Create_Channel.width-1000.format-webp.webp)
- [Virtual channel choices](https://d32bbxx72p2025.cloudfront.net/images/Wave_Link_3_Add_Empty_Channel.width-1000.format-webp.webp)

The [streaming workflow](https://www.elgato.com/us/en/explorer/products/wave/wave-link-how-to-use-it-for-streaming/) establishes the practical scenario: the audience and headphone balances can differ while input effects carry into mixes. The [official Stream Deck plugin](https://marketplace.elgato.com/product/wave-link-aa41150f-9645-4275-b064-7642ba6a17ae) is a further integration surface, not implemented merely by supporting a local mixer UI. Elgato hardware DSP, firmware, Marketplace and hardware-controller integration remain distinct subsystems.

No Elgato executable code, assets, fonts, branding, or driver are incorporated into RaveLink. Full reference artifacts and raw analysis stay under ignored `.tools/`. `evidence/manifest.json` records selected facts, exact artifact digests, REA Evidence IDs and raw-record digests. A filtered manifest is not a substitute for its original full REA records.

## REA actually exercised

Toolchain: `rea-agents@6.7.0`, `node@24.22.1`, both installed from npm into `.tools/rea-cli`; exact package integrities are in the manifest. The user-named repository `morluto/rea` was checked out at `5d6b8a0ab693c03ab85cf0807d40bedf021e76d8`. Its `reverse-engineer-anything` skill and native/artifact guide were read. Repository-main documentation advertises flags not accepted by the npm release; a rejected `--detail` call is retained, and supported CLI help was used for subsequent calls.

| Target | REA evidence | Observed fact |
| --- | --- | --- |
| Installed older driver | `ev_53ec3f16d17e1df129ff7fb0088908bbf99e3b823bf435dc1292affc850fb8f3` | Mach-O digest `3af3dec4dc7499e2ab84034f0239cccc022c0a99ee6a89987e7677135fa360b4` |
| Installed driver plist | `ev_0e85b015016e51c6830918a79c4f9d5e11b9412eb4c5870c64fc48b2096b2661` | `com.elgato.WaveLinkVirtualAudio`, version 1.1 build 5 |
| Current app executable | `ev_67dff9e8207fb0eb0861ca01cd7759ca1fe738de9b620706682c247cef7328c9` | Digest `42aac08bd1f25968cfd28efebb80810deb141de7bec740aef4594c31c0713694`; CoreAudio/AVFAudio and vendor framework dependencies |
| Current app plist | `ev_ae648cfea85327b4c16f32b7d65a68ce50a2abf2ae5e67fdc3c320b89fc88279` | Exact app identity and minimum OS above |
| Bundled driver package | `ev_82aa198e489168699852cba1147c5ddc5cf4db34c13d9119e7cce0298d2c4e43` | Package digest `e75d4af1394f96c60ff9cb221b3417d5ff420bd5c30107eae1170ade928c8e98` |
| Extracted current driver | `ev_dfa91980b93ae89066f23852f1f85702996760b4a178b13def78042ec3fbde1c` | Mach-O digest `83fa62e0b4e4e1aae887c1da029760d0f22e84a10c9573ddff8a5ab2146b1bf1` |
| Current driver plist | `ev_50d6506c00ed67674af1a6e3609591eb8dbd3c99c50c53d851c55b4211ad94db` | `com.elgato.WaveLink3VirtualAudio`, version 1.6 build 10 |

The newer driver was expanded with `pkgutil --expand-full`; no package scripts were executed. Its exports include an AudioServerPlugIn factory and create/destroy device, I/O operation, sample-rate and zero-timestamp entry points. This supports an inference that a HAL AudioServerPlugIn is the relevant virtual-device architecture. Exported names alone do not prove implementation details, dynamic endpoint capacity, timing behavior, mix math, latency, or error recovery.

REA's built-in `native-macos` provider works. Ghidra is unconfigured, Hopper is absent, and IDA/Kuna are unconfigured; no decompilation claim is made. Imports/exports can omit stripped/toolchain-hidden symbols. Original full records retain the tool's limitations and provenance.

## Runtime boundary

The downloaded app was launched through CUA from its read-only mount. It displayed an EULA acceptance gate before onboarding. Acceptance requires a user decision, so inspection stopped there; Cancel and Quit closed the inspection process. `.tools/evidence/reference-eula-gate.png` records the actual UI boundary. No driver installation, audio permission approval, default audio change, or main-mixer action occurred. The documentation screenshot is saved separately as `.tools/evidence/reference-documented-matrix.png`.

Consequently, routing, fader curves, mute/solo semantics, effects order, capture, restore behavior, device recovery and audio quality have **not** been observed in the reference runtime. They remain acceptance work. Compilation or synthetic DSP checks in RaveLink cannot close those reference comparisons.

## Reproduce static inspection

Use the pinned Node executable explicitly; do not silently substitute the host Node version. Acquire the official DMG at the URL above and verify its size/hash before mounting. Never install the reference driver as part of inspection.

```sh
npm install --prefix .tools/rea-cli --save-exact node@24.22.1 rea-agents@6.7.0
shasum -a 256 .tools/reference/ElgatoWaveLink-3.4.0.3281.dmg
hdiutil attach -readonly -nobrowse -mountpoint .tools/reference/wavelink-mount .tools/reference/ElgatoWaveLink-3.4.0.3281.dmg
.tools/rea-cli/node_modules/node/bin/node .tools/rea-cli/node_modules/rea-agents/scripts/rea.mjs inspect-macho '.tools/reference/wavelink-mount/Elgato Wave Link.app' --json > .tools/evidence/reference-macho.json
.tools/rea-cli/node_modules/node/bin/node .tools/rea-cli/node_modules/rea-agents/scripts/rea.mjs inspect-plist '.tools/reference/wavelink-mount/Elgato Wave Link.app' --json > .tools/evidence/reference-plist.json
.tools/rea-cli/node_modules/node/bin/node .tools/rea-cli/node_modules/rea-agents/scripts/rea.mjs inspect-artifact '.tools/reference/wavelink-mount/Elgato Wave Link.app/Contents/Resources/WaveLink3VirtualAudioDriverInstaller.pkg' --json > .tools/evidence/reference-driver-package.json
pkgutil --expand-full '.tools/reference/wavelink-mount/Elgato Wave Link.app/Contents/Resources/WaveLink3VirtualAudioDriverInstaller.pkg' .tools/reference/driver-package
hdiutil detach .tools/reference/wavelink-mount
```

The extraction destination must be fresh. For each driver, pass its `Contents/MacOS/…` executable to `inspect-macho` and `inspect-plist`; the CLI rejects a `.driver` directory target. Preserve each full JSON record before extracting selected metadata. Read-only filesystem inspection does not establish reference audio behavior.
