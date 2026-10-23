# Fidelity and release acceptance queue

This is an evidence queue, not a completion declaration. Reference identity and limitations are in [REFERENCE.md](REFERENCE.md). Rows distinguish reference documentation, static evidence, candidate implementation and required runtime observation. No reference main-mixer journey has yet been exercised.

| Priority / workflow | Reference basis | Required acceptance evidence |
| --- | --- | --- |
| P0: microphone to headphones and stream | Documented independent mixes | Record known input through two destinations; change one route and prove the other PCM is unchanged; verify real device selection and no accidental duplicate monitoring. |
| P0: app audio with system remainder | Documented app grouping and system input | Two independent test apps plus system source; prove each signal appears once in assigned routes, excluded apps are absent, and denied capture is actionable. |
| P0: virtual devices | REA observes HAL plugin factory/entry points | Install open-source driver on intended OS, enumerate in an independent recorder, send and capture PCM, then verify stop/restart/uninstall. Build success alone is insufficient. |
| P0: dynamic scale | Requested extension beyond reference limits | No arbitrary schema count cap; add/remove more than eight input channels and five mixes while active; document measured CPU, underruns and usable capacity. Never promise infinite simultaneous hardware. |
| P0: mute and level changes | Documented mix controls | Separate source mute, route mute and master mute tests; silence criteria, exact gain factors and transitions; avoid clicks during live changes. |
| P0: device loss/recovery | Required production behavior | Unplug/replug input/output; switching rate/buffer size; sleep/wake; disconnected status; recovery without crash, feedback or silent failure. |
| P0: persistence | Required production behavior | Kill/relaunch, corrupt file, future schema, duplicate IDs, import replacement, missing device and recovery; preserve original damaged file. |
| P1: grouped sources | Documented multiple apps per channel | Group two apps, independently stop/restart either, and prove common processing/routing without unintended duplication. |
| P1: multiple outputs per mix | Documented multiple monitor/playback devices | Same mix on two devices, including independent clocks; demonstrate drift handling and device loss isolation. |
| P1: AU effect rack | Documented macOS effects | Discover, add, order, bypass, remove and restore Audio Units; exercise at least one independent third-party AU and a failing AU; determine effects latency and state preservation. |
| P1: source and channel management | Documented matrix/channel controls | Rebind a disconnected source, rename, reorder, scroll large sessions, and navigate entirely with keyboard/VoiceOver. |
| P1: installer/release | Required production behavior | Signed app/driver installer, notarization when credentials available, clean-machine install/uninstall, license notice, verified release checksums and rollback. |
| P2: hardware / controller integrations | Vendor docs; not inferred from mixer | Separate acceptance for Stream Deck, firmware controls, vendor hardware DSP, Sound Check, compact mode, shortcuts, updates and other agreed parity surfaces. |

## Initial candidate source review

This review inspected `StudioView.swift`, `SourceSheets.swift` and `StudioModel.swift` as present during initial implementation. It is source-only evidence and can become stale as the agents edit the app.

Present in UI source: a scrollable inputs-by-mixes matrix, individual route enable/level/pan, input and master mute, solo, meters, input/mix creation, basic effects, source labels, missing output labels, session import/export and a first-input empty state. These still need native runtime and audio validation.

Important parity gaps to recheck before any fidelity claim:

1. A channel currently selects one source, while the reference groups multiple applications. A bus selects one output device, while the reference allows several.
2. Basic built-in high-pass/gate/compressor controls do not implement an AU rack. There is no plugin discovery, chain order, plugin UI, bypass or state restore in the reviewed source.
3. Source selection is available at creation only. The settings panel offers channel offset but no input device/app rebinding. A disconnected microphone therefore requires replacing the channel, losing route/effect setup.
4. There is no channel reorder interaction in the inspected UI. Index-based view identity and bindings must be revisited when reorder/removal is added.
5. The reference's documented compact controls and visible monitoring selection are absent. RaveLink's larger cells, persistent right inspector and branded header are deliberate visual differences, so the result should be described as an independent interpretation until native comparison is available.
6. Save/update is debounced 100 ms and the pending task is cancelled on every mutation. Sustained slider dragging could postpone audio parameter updates until release. Verify the runtime behavior and ensure control delivery is independent from persistence debounce.
7. The current `db` formatter displays minus infinity at -60 dB. Confirm the engine applies actual silence at that UI state or display -60 dB instead. A 0.001 linear gain is quiet, not silence.
8. The system-source explanatory text promises exclusion of dedicated app channels and the app's own output. That must be backed by capture membership and live recording evidence, including source changes while running.

### Follow-up source review, 24 October 2026

The implementation now delivers audio parameter updates immediately and debounces only disk saves; the -60 dB label is also corrected. Failed startup loads now preserve an unreadable copy, and backup failure disables overwrite. These fixes were verified in source; startup recovery still needs native UI exercise.

`SessionStore` now preflights the file size, bounds the actual read against concurrent growth, and enforces the same 32 MB limit on save before replacing an existing file. Regression tests cover a 2 GB sparse input, rejected oversized output, unchanged malformed input, and route isolation after persistence/removal.

Remaining concrete source concerns reported to the implementation owner:

- A temporary empty name during inline rename reaches full session validation on immediate audio update, whose failure handler stops the engine. A live rename must not interrupt routing; defer the display-name edit or decouple metadata validity from audio control updates.
- Sparse imported `sends` arrays currently validate but produce invisible/uneditable route cells. Either reject incomplete matrices or normalize absent routes to muted entries during intake, with explicit tests.

The second issue is now fixed: validation requires the complete matrix using checked count multiplication, alongside unique identifiers and referential checks. Grouped inputs validate every source offset and reject duplicate sources. Multi-output mixes validate every offset and reject overlapping stereo pairs on the same device. The updated core suites passed **12 tests**, including these regressions; [the test record](evidence/core-review.json) pins the tested source hashes. This is core validation evidence, not runtime routing or release acceptance.

## Release promotion rule

Each acceptance result needs the tested commit, app/driver hashes, OS/build, device identifiers, sample rate, buffer size, exact setup, measurements and retained output artifacts. Mark a row passed only for the exercised scope. Synthetic controls validate the test instruments and DSP functions; they do not demonstrate installed driver operation, reference fidelity, clean-machine installation, or production reliability.

Before promotion, run an extended routing soak with independent recorded output and dropout accounting, then test sleep/wake and device recovery. Keep driver installation, reference EULA acceptance, OS capture permissions and notarization credentials as explicit boundaries. Do not replace missing evidence with a polished UI or a successful build.
