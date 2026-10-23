# Superseding product requirements — 2026-10-24

The user explicitly changed the product requirements to independently authored proprietary application and virtual-device drivers, implemented in Rust, for Windows and macOS. This supersedes the original open-source-driver request and the Swift/macOS prototype. The autonomous goal remains active; its original tool summary predates this requirement change.

New shipping implementation lives in `crates/` and `drivers/`. First-party new code is proprietary. Permissively licensed Rust libraries and platform SDK interfaces are allowed dependencies; no GPL implementation is copied, translated, linked or packaged into the new shipping targets. All former GPL notices and rights remain in force for the archived prototype. Private visibility does not revoke any previously granted rights.

The user subsequently requested public GitHub visibility and continued incremental pushes. The repository is now public; first-party proprietary licensing and the archived prototype's existing licence are unchanged. `scripts/push-public.sh` checks the requested visibility before and after publication.

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

## Current evidence checkpoints

- `6484db8`: native macOS and Windows desktop CI passed. The original macOS HAL passed a disposable-host installation, two independent 20-second stereo recordings, bit-identical reader overlap, fresh-client silence and owned-driver removal. Original PCM and observer records are preserved under `research/evidence/rust-hal-installed-40039161891/`. This measured the driver, not the complete Rust application runtime.
- `6484db8`: the original Windows driver built on Windows Server 2022 and passed nine user-mode host tests, SDK ABI assertions, PE checks, INF validation and unsigned catalog generation. The original artifact and logs are preserved under `research/evidence/rust-windows-native-40039161836/`. No installed-kernel, endpoint, audio, Verifier, HLK or signing result is claimed.
- `b30dea6`: explicit hardware/virtual-device input capture, a bounded clock-compensating transport and native input selection were added. The stopped macOS picker was exercised and the original studio restored byte-for-byte. Offline clock, spectral and allocation controls passed; physical input, permission and runtime audio evidence remained pending.
- `4aa6394`: Windows capture was replaced with an original Rust WASAPI owner thread and portable packet decoder. Independent source review corrected failed-construction event lifetime and an exact-drain-budget error. The 34 audio tests pass locally, including silent-packet, release, timestamp, cancellation and transport controls; Windows-target checks pass. Native execution remains a distinct gate.
- Repeated driver observation `40041055533` at `b30dea6` failed: one reader omitted 568 frames early in capture, despite clean later sine measurements. Original PCM, timestamps and failed analysis are retained under `research/evidence/rust-hal-failed-40041055533/`. Separately triggered run `40041275322` passed. The intermittent continuity risk remains unresolved; a passing repeat does not replace the failure.

Upcoming work includes installed capture-to-mixer-to-output observation, gain transition quality, simultaneous independent outputs, application/process capture, complete effects and Sound Check workflows, recovery and sustained resource measurements, native Windows interaction/audio tests, and distributable signed installers. Reference mixer fidelity remains unverified because the pinned Elgato reference stops at its separate vendor-driver installation gate.
