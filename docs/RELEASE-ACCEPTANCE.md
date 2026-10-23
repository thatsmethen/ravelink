# Production acceptance ledger

The goal is a production-quality Wave Link recreation with expandable inputs/mixes and open-source virtual drivers. This ledger prevents foundational work from being mislabeled completion.

## Required gates

| Area | Required evidence | Current disposition |
|---|---|---|
| Reference fidelity | Pinned target, documented feature matrix, observed reference journeys | REA native inspection and documented matrix recorded; EULA acceptance pending for reference runtime |
| Real audio | Independent capture of routed virtual output, correct level/pan/mute/solo, source capture | Native engine rendered 48,128 silent frames to physical output; installed host BlackHole registration stalls independently; isolated installed-driver CI prepared |
| Open virtual drivers | Reproducible source build, licence/source distribution, actual installed HAL validation, removal/upgrade | Universal GPL driver build and direct interface contract pass; installed HAL validation pending |
| App routing | Permissions, process exit/relaunch, Chromium subprocesses, dedicated vs catch-all exclusions | Pending |
| Effects | Built-ins, Audio Unit chain with persistence/bypass/editor, plugin failure isolation | Built-in DSP tests pass; isolated AU discovery/probe and timeout/crash containment pass; AU rendering and rack pending |
| Reference journeys | Matrix, multiple apps per input, multiple monitors per mix, sound check, export/import | Grouped sources and outputs implemented with post-sum effects; native removal crash identified for repair; sound check pending |
| Lifecycle | Hotplug, sleep/wake, session restore, corrupt import, no unintended broadcast | Pending |
| Audio integrity | Measured latency, clock drift, dropouts, rates, format/device matrix, clipping recovery | Pending |
| Scale | Sustained real audio across increasing inputs/buses, resource/latency envelope | Session scaling and bounded expansion tests pass; machine-derived memory preflight implemented; sustained audio pending |
| Distribution | Signed app/driver installer, notarization, clean machine installation/upgrade/uninstall, CI | Private GitHub CI green at c807adf; ad-hoc app and unsigned driver installers built; distribution signing/notarization pending |
| Accessibility | Keyboard, VoiceOver names, focus, contrast, resizing, large sessions | Native inspection underway; focus/removal crash and inactive button contrast found; fixes require native recheck |
| Independence | No proprietary binaries/assets in source or distribution; full GPL corresponding driver source | Source boundaries established |

No row may be closed based solely on a simulated model or screenshot. Keep measurements and limitations with the revision they validate.

## Explicit environment boundaries

Development host: Apple silicon, macOS 27.0 beta build 26A5406e, Swift 6.2.1 command-line tools. Results here do not establish supported macOS 15/26 or Intel behavior. Administrator authentication, audio privacy permissions and distribution service credentials may require user participation. A successful build does not establish notarization or driver installation.
