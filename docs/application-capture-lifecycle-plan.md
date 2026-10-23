# Application capture and device lifecycle: next qualification work

This is an implementation/qualification plan, not a claim that the runtime cases
below already pass. The present engine matches CoreAudio's reported bundle ID
exactly, stops when a captured or explicitly excluded application's process membership changes, and
checks device availability/rates periodically. Application capture permission has
not been granted or exercised on the development host during this work.
Inclusion and exclusion taps share one initial process snapshot. Empty exclusion
memberships remain watched, so a previously absent excluded app becoming active
is detected too. Current periodic detection has an observation interval; the pure
membership tests do not establish zero leakage during an actual process transition.

## Process identity

CoreAudio exposes a process-object list and a PID for each process. The current
exact-ID match does not adequately group Chromium's nested helper applications.
Build a process inventory that retains both the reported bundle ID and the owning
application identity. Resolve an executable's enclosing application from actual
bundle ancestry, including nested helper `.app` bundles within an outer `.app`.
Use `NSRunningApplication` metadata where available and a bounded executable-path
lookup otherwise. Do not infer ownership from a bundle-ID prefix: two unrelated
applications can share that text. Unresolved shared system/XPC processes must stay
unattributed until there is an authoritative owner mapping.

The picker, dedicated capture selection, and catch-all exclusions must consume
the same inventory and identity resolver. Tests should cover nested Chromium
helpers, helpers with no reported ID, unrelated prefix collisions, two instances
of the same app, process exits/PID reuse, missing metadata, and legacy saved helper
identities. Those tests establish selection logic; authorized playback/capture
with actual Chromium processes is a separate acceptance case.

## Updating tap membership

The installed SDK and Apple's documentation expose writable tap descriptions.
On macOS 26, `CATapDescription.bundleIDs` and `isProcessRestoreEnabled` add native
bundle-based inclusion/exclusion and restart restoration. Both are unavailable on
the supported macOS 15 minimum. Use availability checks and preserve explicit
process-object membership for that older system. [Apple CATapDescription](https://developer.apple.com/documentation/coreaudio/catapdescription)

Register for process-object-list changes and retain a polling fallback. Recompute
all dedicated memberships and the catch-all exclusion set together. A changed
membership must suspend routing through an independent render gate while the
control worker updates the tap descriptions; ordinary bus control edits must not
override that temporary suspension. Restore the prior user settings only after
all updates succeed and the graph generation remains current. Failure stops the
helper and requires a manual start. The gate should keep draining capture FIFOs
so a control update does not replay stale audio afterward.

Native bundle-based exclusions can cover known app/helper identities before a
new process begins playback. On macOS 15, notification-based retargeting has an
observation interval; real tests must measure transitions and cannot assume an
atomic cross-tap change. Test application exit/relaunch, new browser tabs/audio
service processes, a selected app becoming idle, and a system remainder beside
several dedicated apps. Compare independently recorded waveforms for duplication,
leakage into the remainder, expected restoration, and silence after stop.

## Device, audio-service, and power events

Listen for device inventory, device-alive, nominal-rate, and audio-service-restart
notifications in addition to periodic checks. Invalidate the running generation
and stop on loss, incompatible format/rate changes, or an audio-service reset.
Refresh inventory after reconnect/wake; do not resume playback automatically.
Observe sleep/wake in the supervisor as well as the helper so a stalled native
worker cannot leave the GUI reporting an active route indefinitely.

Add a running-helper heartbeat deadline for a blocked helper main loop, and a
per-output frame-progress watchdog for a stalled device or plugin render block.
The progress threshold must account for the supported maximum buffer duration.
The two checks detect different faults: a responsive main loop does not prove
that an audio callback is returning. Fault tests can validate containment, while
real hardware removal, sleep/wake, and driver-reset tests remain separate evidence.

No local sleep, privacy approval, driver installation, audio-service restart, or
default-device mutation is needed to implement the pure resolver and fault tests.
Actual capture and hardware/power qualification require their corresponding
authorized environment and recorded provenance.
