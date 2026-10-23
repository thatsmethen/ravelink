# RaveLink

A proprietary Rust audio mixer and routing application under development for **Windows and macOS**, with independently authored virtual-device drivers. Reference research uses pinned Elgato Wave Link artifacts and [morluto/rea](https://github.com/morluto/rea). No Elgato code or artwork is packaged.

**Not a production release.** The original Swift/GPL prototype is archived under [`legacy/`](legacy/) and at tag `legacy-swift-gpl-freeze`. Its original licensing remains in force. New shipping targets do not depend on it.

The [current requirements and acceptance gates](research/RUST-MIGRATION.md) supersede the original prototype scope. Inputs and mix buses are dynamic; practical capacity is constrained by verified CPU, memory, devices and OS behavior, rather than a product-imposed channel count.

## Rust workspace

- `ravelink-core`: validated sessions, routing, stereo mixing, meters and built-in DSP.
- `ravelink-audio`: CoreAudio/WASAPI device I/O, explicit output selection and runtime state.
- `ravelink-app`: Rust-native desktop interface using eframe/egui with AccessKit.
- `ravelink-hal`: original macOS AudioServerPlugIn through Apple's C ABI.
- `ravelink-windows-driver`: original Rust PortCls/WaveRT driver, built separately with its pinned kernel toolchain.

Both virtual drivers are implemented. Their qualification remains separate: independent clients have measured the installed macOS HAL, while the Windows driver has passed a native build, SDK ABI checks and unsigned package validation. Windows kernel installation, audio operation and signing remain unverified. See [platform research](docs/rust-platform-research.md).

```sh
cargo test --workspace
cargo run -p ravelink-app
```

Rust is pinned in `rust-toolchain.toml`. Current development targets are macOS and Windows; native builds and installed-driver acceptance are tracked separately. Audio starts stopped and requires an explicitly selected output. No system default audio device is changed.

The current runtime mixes explicitly selected device inputs and test tones into one selected output. Input, route and mix gain/mute/solo controls can update during playback without rebuilding the graph; callback acknowledgements track applied versions. Stop also cancels a start still queued by the interface. Device capture includes a bounded stereo queue and clock compensation; [capture evidence and backend limits](crates/ravelink-audio/CAPTURE.md) distinguish offline tests from native qualification. Application capture, simultaneous outputs, gain smoothing and complete installed-runtime qualification remain required work.

Desktop CI at `01a2222` built release artifacts and passed deterministic tests on Windows Server 2022 and macOS 15 ([run evidence](research/evidence/rust-ci-40034960508/run.json)). The stopped native macOS interface was exercised with 128 sources, 32 mixes and 4,096 routes ([observations](research/evidence/rust-ui-scale/observation.json)); this does not establish audio capacity or Windows interaction quality.

At `6484db8`, the installed macOS HAL delivered two independently recorded stereo sine signals continuously, with bit-identical overlap between readers and silence after all clients restarted ([preserved PCM and measurements](research/evidence/rust-hal-installed-40039161891/)). The corresponding [Windows build evidence](research/evidence/rust-windows-native-40039161836/README.md) retains the original unsigned driver package. These checkpoints do not establish the full application's capture/mix/output path. Windows capture now uses an original event-driven WASAPI adapter with explicit silent-packet and packet-lifetime handling; native capture qualification remains pending.

New studios use `RaveLinkRust/session.json` in the user's application-data directory, separate from the archived prototype's studio. Permissively licensed dependencies retain their licenses. ASIO and GPL audio drivers are excluded from the shipping dependency graph.

See [LICENSE](LICENSE) for the new first-party proprietary notice and [legacy/LICENSE](legacy/LICENSE) for archived-code terms. Private repository visibility does not change previously distributed licensing.
