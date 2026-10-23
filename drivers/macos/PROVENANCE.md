# RaveLink macOS HAL source provenance

This implementation was authored independently for RaveLink on 24 October 2026.
It is proprietary RaveLink source under the repository LICENSE. No existing
third-party virtual audio driver implementation was consulted, copied, translated,
ported, or linked in writing this implementation. In particular, the historical
BlackHole source, patches, and application sources were excluded from inspection.

The implementation references below are public platform interface contracts, not
third-party driver implementations:

- Apple's installed macOS SDK `CoreAudio.framework/Headers/AudioServerPlugIn.h`:
  factory/interface UUIDs, vtable order and argument types, host lifecycle,
  realtime restrictions, IO operation selectors, timestamp period minimum.
- Apple's installed `CoreAudio.framework/Headers/AudioHardwareBase.h`: object,
  device and stream properties, errors, object classes, ASBD range structures.
- Apple's installed `CoreAudioTypes.framework/Headers/CoreAudioBaseTypes.h`:
  ASBD, timestamps, SMPTE, Float32 PCM flags and sample-time validity.
- Apple's installed `CoreFoundation.framework/Headers/CFPlugInCOM.h`:
  IUnknown layout, macOS HRESULT/ULONG sizes, interface UUID and error values.
- Apple's installed `usr/include/mach/mach_time.h`: monotonic tick function
  and timebase conversion structure/function declarations.
- [Apple AudioServerPlugInDriverInterface documentation](https://developer.apple.com/documentation/coreaudio/audioserverplugindriverinterface).

SDK version: **26.1**. SDK root:
`/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk`.
The native C conformance host includes Apple's installed headers directly. Rust
ABI declarations contain the minimal required type and constant definitions.
The factory UUID in Info.plist is RaveLink-specific; the type/interface UUIDs
are Apple's required standard values. No external Rust crates are dependencies
of `ravelink-hal`; the Rust standard library and Apple platform frameworks apply
their own terms. This record describes the actual source inputs and is not a
legal clearance opinion.

SHA-256 of the consulted SDK headers at implementation time:

| Header | SHA-256 |
| --- | --- |
| AudioServerPlugIn.h | `255f6e4a7b8620cff4c634bb175a304a2fea29d4e637928846793893151b6aa0` |
| AudioHardwareBase.h | `7784442bb6e53b95c820bf9d66b738e25b91c376bffeb596df023a67941184c8` |
| CoreAudioBaseTypes.h | `f58c4e2bccc86193afa89160bba76ab57989138e8885bed1c068d41ebe2b5c86` |
| CFPlugInCOM.h | `b55e8944691eaae29ee56de475f29d91d5dafefb13e3e95ee240763f892d3d7c` |
| mach_time.h | `d690e304ea595ca216ed51e20aa9747e0b3bcb07446d996abe0080a231c7065f` |
