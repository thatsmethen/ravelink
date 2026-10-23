# RaveLink

A proprietary Rust audio mixer and routing application under development for **Windows and macOS**, with independently authored virtual-device drivers. Reference research uses pinned Elgato Wave Link artifacts and [morluto/rea](https://github.com/morluto/rea). No Elgato code or artwork is packaged.

**Not a production release.** The original Swift/GPL prototype is archived under [`legacy/`](legacy/) and at tag `legacy-swift-gpl-freeze`. Its original licensing remains in force. New shipping targets do not depend on it.

The [current requirements and acceptance gates](research/RUST-MIGRATION.md) supersede the original prototype scope. Inputs and mix buses are dynamic; practical capacity is constrained by verified CPU, memory, devices and OS behavior, rather than a product-imposed channel count.

## Rust workspace

- `ravelink-core`: validated sessions, routing, stereo mixing, meters and built-in DSP.
- `ravelink-audio`: CoreAudio/WASAPI device I/O, explicit output selection and runtime state.
- `ravelink-app`: Rust-native desktop interface using eframe/egui with AccessKit.
- `ravelink-hal`: original macOS AudioServerPlugIn through Apple's C ABI.

Windows virtual-driver development and platform qualification are required parts of the project. A portable desktop build is not evidence of a working Windows virtual device. See [platform research](docs/rust-platform-research.md).

```sh
cargo test --workspace
cargo run -p ravelink-app
```

Rust is pinned in `rust-toolchain.toml`. Current development targets are macOS and Windows; native builds and installed-driver acceptance are tracked separately. Audio starts stopped and requires an explicitly selected output. No system default audio device is changed.

New studios use `RaveLinkRust/session.json` in the user's application-data directory, separate from the archived prototype's studio. Permissively licensed dependencies retain their licenses. ASIO and GPL audio drivers are excluded from the shipping dependency graph.

See [LICENSE](LICENSE) for the new first-party proprietary notice and [legacy/LICENSE](legacy/LICENSE) for archived-code terms. Private repository visibility does not change previously distributed licensing.
