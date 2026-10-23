# Application capture and device lifecycle

The lifecycle implementation below has deterministic fault, identity, format,
and buffer tests. A real silent built-in-device route also survives its periodic
health checks through the supervised helper. Those results do **not** establish
application-tap transition fidelity: capture consent, real browser subprocess
churn, app relaunch, device removal, sleep/wake, and audio-service restart still
need separate authorized runtime acceptance. No privacy approval, host sleep,
service restart, driver installation, or default-device mutation was performed
for this work.

## Process identity and shared selection

The inventory retains CoreAudio's process object, PID, reported bundle ID, and
owning application identity. The resolver uses a bounded `proc_pidpath` lookup,
resolved filesystem ancestry, and actual `APPL` bundle metadata. An outer app
precedes an embedded helper `.app`, so Chromium helpers appear under their owner.
It falls back to `NSRunningApplication` metadata and the reported ID when bundle
ancestry is unavailable. It never infers ownership from an identifier prefix;
unresolved shared/XPC services remain unattributed. Saved exact helper IDs retain
their previous narrower meaning.

The picker, dedicated capture, and system remainder use the same resolver. Tap
inclusion and catch-all exclusion are computed from one inventory snapshot,
including the engine's own process and RaveLink's application identity. Empty
memberships remain watched, including apps excluded only for an isolated Sound
Check, so an excluded app starting later triggers reconfiguration too.

Pure tests cover nested helpers, missing reported IDs, legacy helper IDs,
unrelated prefixes, empty/exited/restarted memberships, duplicate inventory
entries, own-process exclusion, and inclusion as a subset of remainder exclusions.
They establish identity/selection logic, not captured playback behaviour.

## Tap membership transaction

The graph listens for CoreAudio process-list changes and polls as a fallback.
A notification closes an independent atomic output gate before the control worker
checks membership. A polling-detected change closes it before any mutation. User
fader/mute edits cannot override this gate; callbacks continue processing and
consuming input. Unrelated process changes do not gate graphs without taps.

If memberships changed, original application playback remains suppressed while
all tap IOProcs stop/unregister. Dedicated tap descriptions are applied before
catch-all descriptions, using the same new inventory. Consumer-owned FIFO reset
requests discard queued pre-change capture and reset resampler history. Only then
do capture IOProcs restart. The current actor generation can reopen output after
every step succeeds, with a 5 ms ramp. A changed generation, failed property write,
or failed native callback operation leaves output closed and stops the graph;
there is no automatic retry of a failed engine. Effect/clip state survives a
successful membership refresh; a Sound Check recording may include silence during
that short interruption.

macOS 26 additionally supplies explicit bundle IDs and enables CoreAudio process
restoration. Both properties are availability-guarded. macOS 15 uses explicit
process-object retargeting. Starting a new dedicated input still requires the app
to be open and registered with CoreAudio; an existing tap can be retargeted to an
empty membership while waiting for its app to return. These native semantics
must be exercised on both supported OS generations before qualification.
[Apple CATapDescription](https://developer.apple.com/documentation/coreaudio/catapdescription)

Neither a process-list notification nor multiple writable tap descriptions is an
atomic cross-application boundary. Newly encountered helper bundle IDs and macOS
15 retargeting have an observation interval. These tests do not establish zero
leakage or zero duplication during actual app transitions. Acceptance must record
independent waveforms during new browser tabs/audio services, app exit/relaunch,
and a system remainder alongside dedicated inputs. It must measure unexpected
remainder content, restoration, continuity, and silence after stop.

## Device, service, power, and liveness

Each active graph listens for device inventory, alive state, nominal rate, stream
configuration, stream virtual format, and audio-service restart events. Health
checks revalidate device identity, alive state, rate, requested channel ranges,
and dense native Float32 layout, including byte/packet strides. A same-rate change
to integer or incompatible PCM therefore stops the route. Listener callbacks
carry no audio-buffer pointers. Notifications close the output gate before
worker validation; a polling fallback remains. Hardware format transitions still
need real device qualification because notification delivery itself is not a
sample-atomic boundary.

Only one health check is queued per graph; another event requests one follow-up.
A three-second health/retarget deadline closes the graph and marks its worker
unusable. The GUI supervisor then terminates/reaps that helper. Audio-service
restart invalidates the graph; it does not attempt to reuse stale HAL object IDs.

The GUI supervisor independently requires fresh running telemetry within three
seconds; old generations cannot refresh it. The engine monitors each output's
frame counter separately, allowing the larger of five seconds or four maximum
buffer durations. Thus a responsive control loop cannot hide a stalled render
callback, and a progressing device cannot hide another stalled output.

Both supervisor and helper observe workspace sleep/wake. Sleep invalidates the
session; the supervisor closes and terminates the helper without waiting for HAL.
Wake performs device discovery only. It never resumes a saved route or Sound
Check clip. Injected power-event tests verify this policy and child reaping; they
do not claim a physical sleep/resume test.

## Evidence

`research/evidence/audio-lifecycle-focused-tests.txt` records the deterministic
supervisor, transaction-ordering, resolver, format, and render-gate tests.
The earlier `audio-lifecycle-focused-tests-startup-failure.txt` is retained: its
stale-state fixture did not reach readiness within its old three-second setup
wait, so no stale-state assertion ran. The isolated diagnostic passed. Setup now
allows six seconds against a five-second fixture start deadline and distinguishes
an engine error from readiness; discovery/stop deadline assertions are unchanged.
`audio-lifecycle-supervisor-final-tests.txt` records the final supervisor checks.
`research/evidence/audio-lifecycle-silent-native-tests.txt` records a real
`BuiltInSpeakerDevice` output with 200,704 rendered frames and zero peak, through
two periodic health checks, plus a 4,096-frame temporary Sound Check retained
through live gain edits and stopped/discarded on topology change. Hardware output
was explicitly silent throughout. This is device/control evidence, not an
independently recorded audible or application-capture acceptance case.
