# Local HAL validation — 24 October 2026

Environment: macOS arm64, Apple SDK 26.1, Rust 1.91.1. This record covers the
initial fixed-format independently authored driver candidate, not an installed
system audio device.

| Check | Result |
| --- | --- |
| `cargo test -p ravelink-hal` | 7 passed, 0 failed |
| `cargo clippy -p ravelink-hal --all-targets -- -D warnings` | Passed |
| `cargo fmt -p ravelink-hal --check` | Passed |
| `sh drivers/macos/tests/run-native-host.sh` | Passed against debug dylib |
| `sh drivers/macos/build-bundle.sh` | Built arm64 driver bundle |
| Native host against bundled release executable | Passed |
| `codesign --verify --strict dist/macos/RaveLink.driver` | Passed; ad-hoc signature |
| `nm -gU` on bundle executable | Exports `RaveLinkHALFactory` |

The Rust tests cover ABI layout, property validation, malformed formats and
buffer sizes, independent ring readers, concurrent ring writers/readers,
wraparound and overwritten frames, independent device storage, balanced clients,
monotonic period-quantized clock arithmetic, and direct-vtable loopback. An
instrumented allocator observed zero allocations across tested write, capture
and timestamp callback calls.

The separate C host is compiled directly against Apple's SDK headers. It loads
the library with `dlopen`, checks factory and COM behavior, enumerates the device,
queries/validates properties and Float32 ASBDs, runs start/stop and audio callbacks,
and checks timestamps. It covers 1, 127, 512, 4096 and 8192-frame calls, reads before
writes, ring wraparound, and repeated stop/start clearing. The same executable
passed against both the debug dylib and packaged release binary.

An independent source review checked the ABI, atomics, realtime callback paths,
properties, client lifecycle, clock arithmetic and bundle metadata against the
installed Apple SDK. It found no confirmed blocking defect in that scope. Its
specific validation-gap finding prompted the varied-size/order/restart native
host cases above. Review is not evidence of real-host operation.

The C host supplies synthetic timestamps with input time equal to output time
plus 512 frames. Therefore these checks do **not** establish actual Core Audio
latency compensation, host scheduling, independent-process capture, CFPlugIn
discovery, macOS audio-host loading, audio continuity under load, sleep/wake,
aggregate operation, or cross-architecture behavior. These remain unverified.
No driver installation, host-service restart or external audio routing was done.

Produced artifact: `dist/macos/RaveLink.driver`, ad-hoc signed for local arm64 use.
SHA-256 of `Contents/MacOS/RaveLinkHAL`:
`8abd3ff7866a39bbf92d6bc79eb4e28f62695c39b55c7e4edd586c90aa1c4a6a`.
Rebuilding or re-signing may change that hash. The bundle has no Developer ID
signature or notarization and is not a universal release artifact.
