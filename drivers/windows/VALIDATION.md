# Windows driver validation record

Checkpoint: 2026-10-24, macOS arm64 development host. No Windows driver installation, kernel load, signing-policy change, or local audio-service change occurred.

| Check | Result | Scope |
| --- | --- | --- |
| Rust host tests | 9 passed | ABI layout, descriptors, malformed formats, integer timing, buffer bounds, mocked PortCls vtable/lifetime scenario |
| Rust formatting | Passed | `cargo fmt --manifest-path crates/ravelink-windows-driver/Cargo.toml -- --check` |
| Strict host Clippy | Passed | `cargo clippy --manifest-path crates/ravelink-windows-driver/Cargo.toml --all-targets -- -D warnings` |
| Official SDK ABI compile | Passed | Apple Clang 17, Windows x64 target, exact Microsoft 26100.6584 header packages; sizes, offsets, constants, signatures and inheritance |
| Native Windows kernel PE cross-build | Passed | Pinned nightly/core, bundled LLVM linker, official kernel import libraries |
| PE structure check | Passed | Native AMD64 entry, checksum, relocations, ASLR/NX/integrity flags, kernel-only imports, no TLS or writable executable sections |
| Windows MSVC/InfVerif/Inf2Cat pipeline | Pending hosted run | Implemented in dedicated workflow; no successful Windows packaging result claimed by this record |
| Actual Windows kernel/endpoint/audio/latency tests | Not run | Requires authorized Windows test environment |
| Production signing, HVCI/Verifier/HLK | Not run | Required before release |

The local cross-build produced `dist/windows-driver/RaveLink.sys`, 20,480 bytes, SHA-256 `77320cfbf74c08b9b9016abc0bf1a2eca17f5980e21c46de6ff2c205f713e290`. The exact PE evidence is saved beside the artifact as `pe-evidence.json`; its image is unsigned. Build-path and debug metadata can change binary hashes between hosts; each build emits a new hash rather than asserting cross-host reproducibility.

The host vtable scenario injects failures at all ten PortCls startup acquisition points and checks complete cleanup. It also exercises short MDL and failed-map cleanup, actual render/capture vtable calls with bit-exact 512-frame delayed transfer, pause/D3/D0/resume, surprise removal followed by ordinary removal while stream handles remain open, final MDL cleanup, rebalance stop, and fresh restart. These mocks validate our state transitions and ownership logic; they do not prove PortCls scheduling, IRQL behavior, endpoint enumeration or fidelity under real WASAPI.

Independent source review found and corrected three defects before this checkpoint: accepting PortCls's default power capabilities, sampling QPC only after acquiring the shared lock to prevent reordered callers from moving the cursor backwards, and covering ordinary/surprise removal in addition to rebalance callbacks. Buffer detach/free sequencing and failure rollback were then checked with the host harness.

The implementation holds a kernel spin lock while processing at most one cyclic buffer per direction (up to 16,384 frames total), and can clear up to 64 KiB on STOP. This is bounded but has no measured native hold-time evidence. Microsoft's guidance is less than 25 microseconds; meeting that bound, including under contention, is a release qualification gate. The initial polled WaveRT path and absence of event-driven notifications also need real Windows audio-engine compatibility testing.
