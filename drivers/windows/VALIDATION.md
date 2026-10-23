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
| Native Windows Rust build and host tests | Passed | Hosted run 40039161836 built the kernel PE and passed all nine tests |
| Windows MSVC/InfVerif/Inf2Cat pipeline | Passed | Hosted run 40039161836; MSVC 14.44.35207, InfVerif `/w`, unsigned catalog for Windows 10 2004–22H2 x64; no signability errors or warnings |
| Actual Windows kernel/endpoint/audio/latency tests | Not run | Requires authorized Windows test environment |
| Production signing, HVCI/Verifier/HLK | Not run | Required before release |

The local cross-build of the subsequent lock redesign produced `dist/windows-driver/RaveLink.sys`, 26,112 bytes, SHA-256 `bd743e473d2668ef36ec5bcc00b752e044a79c3dbfa4c4fec3d82c17b071538c`. The exact PE evidence is saved beside the artifact as `pe-evidence.json`; its image is unsigned. Build-path and debug metadata can change binary hashes between hosts; each build emits a new hash rather than asserting cross-host reproducibility.

Native hosted package [40039161836](https://github.com/thatsmethen/ravelink/actions/runs/40039161836), commit `6484db8f80d3ad6d7233b5c927b11b6889c82b75`, contains the pre-redesign 20,480-byte SYS with SHA-256 `15cb6ad85aa3541b3c62f281121eea9a31152e6d899d7d134db25c237a94e314`, a 208,896-byte PDB, unsigned catalog, INF, repository license, toolchain runtime notices and both evidence JSON files. These package results do not yet validate the subsequent control/copy redesign on Windows.

The host vtable scenario injects failures at all ten PortCls startup acquisition points and checks complete cleanup. It also exercises short MDL and failed-map cleanup, actual render/capture vtable calls with bit-exact 512-frame delayed transfer, pause/D3/D0/resume, surprise removal followed by ordinary removal while stream handles remain open, final MDL cleanup, rebalance stop, and fresh restart. These mocks validate our state transitions and ownership logic; they do not prove PortCls scheduling, IRQL behavior, endpoint enumeration or fidelity under real WASAPI.

Independent source review found and corrected three defects before this checkpoint: accepting PortCls's default power capabilities, sampling QPC only after acquiring the shared lock to prevent reordered callers from moving the cursor backwards, and covering ordinary/surprise removal in addition to rebalance callbacks. Buffer detach/free sequencing and failure rollback were then checked with the host harness.

The subsequent lock redesign moves all PCM copying and STOP clearing outside the adapter spin lock. GetPosition snapshots/publishes metadata under that lock and returns the last committed position when another copy or passive control owns the data path. Passive controls disable normal kernel APCs while acquiring and holding their gate, and wait for copy quiescence before changing or unmapping buffers. Passive copy owners also defer normal kernel APCs until publishing completion; DISPATCH_LEVEL queries do not call the passive critical-region API. The threaded host scenario pauses a real PCM copy, proves a contending position query returns without waiting, and proves FreeAudioBuffer cannot unmap the buffer until copying completes. The mocks check balanced APC critical regions, simulated caller/spin-lock IRQL, and a DISPATCH_LEVEL final Release after the buffer has already been freed. KEVENT size/alignment are checked against the official SDK. PortCls's documented FreeAudioBuffer-before-destruction order is required for final Release at elevated IRQL; the outstanding-buffer destructor fallback is passive-only.

A callback can still process up to one cyclic buffer per direction (16,384 frames total) at its caller’s IRQL. Native metadata-lock and total callback timings remain unmeasured; Driver Verifier and deadline compliance remain release gates. The initial polled WaveRT path and absence of event-driven notifications also need real Windows audio-engine compatibility testing.

Initial hosted run: [40038289774](https://github.com/thatsmethen/ravelink/actions/runs/40038289774), commit `db0ae168652a4e4269b5f8b8914a1ff53da77c2f`. Rust build, nine host tests, formatting and strict Clippy succeeded on Windows. The compile-only C++ harness failed because user-mode MSVC CRT headers preceded the WDK CRT and the test used a Clang-specific type trait. The subsequent correction changes only the harness/build environment; the driver remains pure Rust.
