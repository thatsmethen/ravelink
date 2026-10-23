# Superseding product requirements — 2026-10-24

The user explicitly changed the product requirements to independently authored proprietary application and virtual-device drivers, implemented in Rust, for Windows and macOS. This supersedes the original open-source-driver request and the Swift/macOS prototype. The autonomous goal remains active; its original tool summary predates this requirement change.

New shipping implementation lives in `crates/` and `drivers/`. First-party new code is proprietary. Permissively licensed Rust libraries and platform SDK interfaces are allowed dependencies; no GPL implementation is copied, translated, linked or packaged into the new shipping targets. All former GPL notices and rights remain in force for the archived prototype. Private visibility does not revoke any previously granted rights.

The previous prototype is frozen under `legacy/`. It is retained to preserve history, failed experiments and test evidence. Native code, old driver patches and GPL build scripts are not a shipping foundation for the Rust rewrite. Fresh driver work uses official SDK ABI contracts and independently authored implementation. This is a provenance boundary, not a claim of an independently audited clean-room process.

## Frozen results

- Source f733a8c: macOS signed universal prototype built; not notarized.
- Installed CI 40022691623: driver lifecycle passed; audio loopback/continuous PCM failed. Original raw WAVs and hashes are retained. No successful production capacity claim.
- Native 128-input/32-mix interface stalled even with indexed routes. Later publication deduplication passed deterministic tests but received no repeated native scale acceptance.
- Helper resolution and bounded diagnostic/source-archive work remained experimental at freeze. None changes the failed installed-audio result.
- User's original studio was restored byte-for-byte and checked natively with audio stopped.
- No old test driver or Elgato reference driver was installed on this host during the migration.

## New acceptance gates

1. Rust shared graph, session persistence, bounded realtime audio processing and a native desktop application on both platforms.
2. Original macOS HAL and Windows virtual audio devices, actual installed capture/render loopback and independent PCM verification.
3. Dynamic input and bus counts limited by measured resources rather than product licensing. Scalable UI, accessibility, topology changes and routing clarity.
4. Device/app capture, independent monitor/stream/voice mixes, effects, Sound Check and recoverable session workflows measured against pinned reference behavior.
5. Device loss, restarts, suspend/resume, rate changes, clock drift, long-run stability and security/permission behavior.
6. Signed/notarized macOS distribution and Windows driver qualification/signing, clean install/upgrade/uninstall and native OS/architecture verification.

A compiling Rust prototype or passing generated-audio test does not satisfy installed-driver, native Windows, reference-fidelity or production acceptance.
