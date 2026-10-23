# Production acceptance ledger

The goal is a production-quality Wave Link recreation with expandable inputs/mixes and open-source virtual drivers. This ledger prevents foundational work from being mislabeled completion.

## Required gates

| Area | Required evidence | Current disposition |
|---|---|---|
| Reference fidelity | Pinned target, documented feature matrix, observed reference journeys | REA inspection in progress; EULA acceptance pending for reference runtime |
| Real audio | Independent capture of routed virtual output, correct level/pan/mute/solo, source capture | Engine implementation in progress |
| Open virtual drivers | Reproducible source build, licence/source distribution, actual installed HAL validation, removal/upgrade | Build and direct interface tests in progress |
| App routing | Permissions, process exit/relaunch, Chromium subprocesses, dedicated vs catch-all exclusions | Pending |
| Effects | Built-ins, Audio Unit chain with persistence/bypass/editor, plugin failure isolation | Built-ins being implemented; AU hosting pending |
| Reference journeys | Matrix, multiple apps per input, multiple monitors per mix, sound check, export/import | Partial implementation |
| Lifecycle | Hotplug, sleep/wake, session restore, corrupt import, no unintended broadcast | Pending |
| Audio integrity | Measured latency, clock drift, dropouts, rates, format/device matrix, clipping recovery | Pending |
| Scale | Sustained real audio across increasing inputs/buses, resource/latency envelope | Session model scaling is a separate check |
| Distribution | Signed app/driver installer, notarization, clean machine installation/upgrade/uninstall, CI | Developer build pipeline prepared |
| Accessibility | Keyboard, VoiceOver names, focus, contrast, resizing, large sessions | Pending native UI inspection |
| Independence | No proprietary binaries/assets in source or distribution; full GPL corresponding driver source | Source boundaries established |

No row may be closed based solely on a simulated model or screenshot. Keep measurements and limitations with the revision they validate.

## Explicit environment boundaries

Development host: Apple silicon, macOS 27.0 beta build 26A5406e, Swift 6.2.1 command-line tools. Results here do not establish supported macOS 15/26 or Intel behavior. Administrator authentication, audio privacy permissions and distribution service credentials may require user participation. A successful build does not establish notarization or driver installation.
