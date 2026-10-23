# Proprietary Rust architecture for Windows and macOS

Research date: 2026-10-24. This is a proposed replacement architecture, not an implemented or qualified product. It follows the user's explicit requirements for original proprietary drivers, Rust, and Windows plus macOS. Only platform documentation and maintainer sources informed this investigation; no GPL driver source was inspected for the new design. Earlier prototype results remain historical evidence and do not establish Rust compatibility or correctness.

## Recommended structure

Use a fresh Rust workspace for the owned application, engine and platform drivers. Keep any permitted third-party dependencies under their own licenses and preserve notices; a proprietary product does not make those dependencies proprietary. Do not translate the former GPL driver or relabel its license. Record exact dependency versions, feature flags, origins and licenses before packaging.

| Component | Proposed responsibility |
| --- | --- |
| `session-core` | Shared validated model, stable identifiers, persistence, routing and resource estimates. No OS or UI dependency. |
| `engine` | Supervised user process containing the real-time graph, mixing, DSP, resampling, clock reconciliation and telemetry. Compile graphs and allocate buffers away from callbacks. |
| `desktop` | Rust interface using eframe/egui; bounded control IPC and meter updates. Virtualize large route matrices and repaint only when needed. |
| `platform-macos` | Core Audio device I/O, process taps and permissions through SDK interfaces; an independent, original AudioServerPlugIn driver crate. |
| `platform-windows` | WASAPI and process capture through Windows API bindings; an independent, original kernel audio driver crate. |
| `plugin-worker` | Platform effect hosting outside the UI, with explicit deadlines, crash reporting, state limits and fail-closed routing. |

These process and module boundaries are design recommendations. Drivers should implement endpoint transport, timing and required OS contracts; effects and session parsing belong in the user engine. Logical channel counts can be dynamic, but memory, CPU, OS endpoint limits and driver resources remain finite and must be checked before activation.

## macOS driver and capture path

Choose **AudioServerPlugIn**, not AudioDriverKit, for the virtual devices. Apple explicitly directs virtual-device developers to AudioServerPlugIn and states that AudioDriverKit supports physical devices. Apple's virtual-device documentation describes a standard C interface and `.driver` installation in the HAL directory. [Apple driver guidance](https://developer.apple.com/documentation/audiodriverkit/creating-an-audio-device-driver), [AudioServerPlugIn](https://developer.apple.com/documentation/CoreAudio/creating-an-audio-server-driver-plug-in)

An original Rust implementation can expose the factory and SDK-defined callback tables through the C ABI. It needs exact structure layouts, reference counting, property-size validation, stable object lifetime and callback synchronization. Qualify the Mach-O bundle/link mode with the actual host; an ordinary Rust `cdylib` build alone is not proof of a working HAL plug-in. Rust permits C ABI interoperability, but unsafe boundary mistakes remain unsafe. A panic must never unwind through a non-unwinding foreign ABI; aborting inside the audio server is also a host-audio failure, not acceptable recovery. [Rust FFI](https://doc.rust-lang.org/nomicon/ffi.html)

Use Core Audio taps for process/group capture where available, with the documented usage description and actual user privacy approval. Apple's API also supports muting captured playback. Installed-device transport and process capture are separate features; neither substitutes for validating the other. [Core Audio taps](https://developer.apple.com/documentation/CoreAudio/capturing-system-audio-with-core-audio-taps)

## Windows driver choice and qualification

The initial feasibility target should be an **original Rust WDM/WaveRT virtual render/capture driver using PortCls**. Microsoft documents this virtual-device architecture through SysVAD and defines the miniport interface publicly. This recommendation uses the documented contract, not copied sample implementation. Exact COM-style vtables, stream and buffer ownership, PnP/power transitions, position reporting and kernel execution constraints need independent implementation and testing. [Virtual audio architecture](https://learn.microsoft.com/en-us/samples/microsoft/windows-driver-samples/sysvad-virtual-audio-device-driver-sample/), [IMiniportWaveRT](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nn-portcls-iminiportwavert)

**ACX/KMDF is the alternative to evaluate before committing to the driver implementation.** ACX models audio streams/formats as WDF objects and simplifies parts of PnP and power handling. It is kernel-mode, not UMDF, and currently supports WaveRT streaming. Its Rust binding and linking path has not been demonstrated here. Prefer it if a bounded feasibility experiment proves the required virtual endpoints and toolchain support; do not assume ACX means a user-mode driver. [Microsoft ACX overview](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/acx-audio-class-extensions-overview)

The principal risk is tool maturity. Microsoft's `windows-drivers-rs` explicitly says it is not yet recommended for production. It supports WDM/WDF development goals, but documents narrower tested configurations and crates.io binding configurations than the full WDK ecosystem. Pin Rust, LLVM/libclang, WDK/SDK and MSVC together; generate missing SDK bindings intentionally. There is no evidence yet that this project builds or loads a Rust audio miniport. A C/C++ fallback would be a language-scope decision, not a silent substitute. [Microsoft Rust driver framework](https://github.com/microsoft/windows-drivers-rs), [WDK requirements](https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk)

Use WASAPI and documented process loopback for application capture. Microsoft supports including or excluding one process tree, with a minimum build of 20348 for that API. Capturing a stream does not itself reroute or silence its original playback, nor does it create a system endpoint. Define the supported Windows baseline and routing policy explicitly. [Process loopback](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/)

Build CI must be followed by installed-driver tests on a rebootable Windows target: independent PCM capture, simultaneous clients, clock drift, sleep/resume, device changes, upgrade/removal, Driver Verifier and HVCI/Memory Integrity. Use the target-OS-appropriate HLK. Microsoft's current guidance restricts attestation to testing scenarios; plan production distribution around WHCP/HLK dashboard signing, publisher enrollment and signing credentials. Do not make disabling system protections a shipping requirement. [Signing options](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/driver-signing-offerings), [HLK](https://learn.microsoft.com/en-us/windows-hardware/test/hlk/), [HVCI qualification](https://learn.microsoft.com/en-us/windows-hardware/test/hlk/testref/driver-compatibility-with-device-guard)

## Rust interface and library options

| Option | License and fit | Main tradeoff |
| --- | --- | --- |
| **eframe/egui — recommended** | MIT/Apache-2.0; Rust-native desktop framework. AccessKit is enabled by default in eframe on supported native platforms. | Custom controls need deliberate styling, semantics and focus behavior. VoiceOver/NVDA and large-matrix performance still require actual testing. [Project](https://github.com/emilk/egui), [accessibility](https://github.com/emilk/egui/blob/main/docs/accessibility.md) |
| Tauri with a Rust/WASM frontend | MIT/Apache-2.0 core; permits a Rust-owned application with web rendering. | System webview variation and an extra IPC/security boundary. A TypeScript-only UI would not satisfy a strict Rust UI requirement. [Project](https://github.com/tauri-apps/tauri), [security model](https://v2.tauri.app/security/) |
| Dioxus desktop | MIT; Rust component UI using a system webview. | Retains webview/runtime variation; audio must remain outside the UI renderer. [Maintainer desktop documentation](https://github.com/DioxusLabs/dioxus/blob/main/packages/desktop/README.md) |

Framework license labels are not a completed transitive dependency or bundled-font audit. Prefer direct platform APIs where clock, capture or routing semantics matter. CPAL is Apache-2.0 and offers CoreAudio/WASAPI I/O, but does not replace an original virtual endpoint driver. Keep its optional ASIO feature disabled unless its separate SDK terms are deliberately resolved: that feature can download the ASIO SDK during build. [CPAL](https://github.com/RustAudio/cpal)

## First acceptance milestones

1. Create an independently authored workspace and dependency/license manifest. Keep historical GPL artifacts out of the new product's source and package dependency graph.
2. Prove the original macOS factory/property/lifetime contract in a private harness, then test installed render/capture PCM on an authorized disposable target.
3. Prove a pinned Rust Windows toolchain can build, load and stream through original virtual render/capture endpoints. Resolve PortCls versus ACX using that result before promising driver production readiness.
4. Run the same independent routing, DSP, timing, failure and persistence acceptance scenarios on both platforms. Recreate reference journeys from observed behavior without importing proprietary assets.
5. Qualify signed/notarized macOS packages and Windows WHCP/HLK submissions, including installation, privacy attribution, updates and removal. Build success, simulation and signing each remain narrower evidence than production qualification.

Required environments and credentials are Windows driver build/runtime targets, HLK facilities and publisher signing enrollment, plus macOS installation/privacy consent and notarization access. They are identified gates, not approvals obtained by this research. No driver installation, SDK installation, new implementation or vendor agreement action was performed for this report.
