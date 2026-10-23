# Production acceptance ledger

The goal is a production-quality Wave Link recreation with expandable inputs/mixes and open-source virtual drivers. This ledger prevents foundational work from being mislabeled completion.

## Required gates

| Area | Required evidence | Current disposition |
|---|---|---|
| Reference fidelity | Pinned target, documented feature matrix, observed reference journeys | REA native inspection and documented matrix recorded; EULA acceptance pending for reference runtime |
| Real audio | Independent capture of routed virtual output, correct level/pan/mute/solo, source capture | Installed HAL CI passed independent loopback and simultaneous two-output level/pan/mute/solo/summing controls on macOS 15.7.9 arm64. Actual grouped device-input soak failed its debug-build throughput gate; app capture pending |
| Open virtual drivers | Reproducible source build, licence/source distribution, actual installed HAL validation, removal/upgrade | Universal GPL driver build and direct interface contract pass; actual install/loopback/restart/uninstall passed on disposable macOS 15.7.9 runner; upgrade and clean user-machine installer pending |
| App routing | Permissions, process exit/relaunch, Chromium subprocesses, dedicated vs catch-all exclusions | Pending |
| Effects | Built-ins, Audio Unit chain with persistence/bypass/editor, plugin failure isolation | Independent installed-HAL Apple effect gain/live parameter/bypass/restored-state/mute recording passes (run 39968280263). Native master_me and bounded reported-latency alignment tests pass; generic rack persistence verified in packaged UI. Full third-party compatibility and physical end-to-end latency pending |
| Reference journeys | Matrix, multiple apps per input, multiple monitors per mix, sound check, export/import | Grouped sources and outputs implemented with post-sum effects; native removal/reorder checks pass. Sound Check dry recording/looping and isolated routing implemented; packaged UI record/cap/clear/close checked, independent installed-HAL audition acceptance prepared |
| Lifecycle | Hotplug, sleep/wake, session restore, corrupt import, no unintended broadcast | Pending |
| Audio integrity | Measured latency, clock drift, dropouts, rates, format/device matrix, clipping recovery | Pending |
| Scale | Sustained real audio across increasing inputs/buses, resource/latency envelope | Memory preflight and session scaling tests pass. Two actual debug-build 24-capture/8-mix runs rendered 82–84% of expected frames with millions of dropped frames; failed runs preserved. Release-build measurement prepared with identical capture semantics, no threshold relaxation |
| Distribution | Signed app/driver installer, notarization, clean machine installation/upgrade/uninstall, CI | Private GitHub checkpoints published; latest CI retains successful loopback/matrix/AU recordings but fails the scale gate and a subsequently repaired process fixture. Ad-hoc app and unsigned driver installers built; distribution signing/notarization pending |
| Accessibility | Keyboard, VoiceOver names, focus, contrast, resizing, large sessions | Native removal, reorder and effect-rack journeys rechecked; inactive button contrast fixed and inspected. Full keyboard/VoiceOver and large-session checks pending |
| Independence | No proprietary binaries/assets in source or distribution; full GPL corresponding driver source | Source boundaries established |

No row may be closed based solely on a simulated model or screenshot. Keep measurements and limitations with the revision they validate.

## Explicit environment boundaries

Development host: Apple silicon, macOS 27.0 beta build 26A5406e, Swift 6.2.1 command-line tools. Results here do not establish supported macOS 15/26 or Intel behavior. Administrator authentication, audio privacy permissions and distribution service credentials may require user participation. A successful build does not establish notarization or driver installation.

The first independent installed-HAL record is retained in [installed-hal-39961789278/provenance.json](../research/evidence/installed-hal-39961789278/provenance.json), together with the original WAV compressed losslessly and its SHA-256. This short result covers macOS 15.7.9 build 24G830 on arm64 and the stated control sequence only. It does not resolve the separately reproduced installed BlackHole 0.5.0 hang on the development host.
