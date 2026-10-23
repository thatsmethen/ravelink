# Native audio engine and evidence

The current engine uses CoreAudio device IOProcs for actual device capture and
rendering, and macOS process taps with private aggregate devices for application
and system capture. It does not change system default devices, device volume, or
nominal sample rates. Application/system capture requires macOS audio-recording
consent. Physical input capture requires microphone consent.

The GUI uses `EngineClient`, which supervises a separate `RaveLinkEngine` process.
The GUI performs no HAL calls and writes no blocking pipes. A bounded JSON-lines
protocol carries complete session snapshots and coalesced 20 Hz telemetry. Each
line is limited to 4 MiB, requests and replies have checked IDs and generations,
and invalid or oversized messages stop the helper. Continuous control edits send
the latest snapshot on a 25 ms target interval rather than waiting for the
user to release a slider. Session topology changes rebuild the native graph;
ordinary gain, mute, pan, and effect parameter changes retain it.

Device discovery, routing, and stop have separate hard deadlines of 10, 12, and
2 seconds. After a timeout or crash, the supervisor closes the control pipe,
sends SIGTERM, escalates to SIGKILL after 250 ms when necessary, and reaps the
child off the UI thread. A replacement helper starts only after its predecessor
has exited and been reaped. Failed audio never resumes automatically. An edit
during a pending start cancels that helper and prepares the latest session in a
fresh process. Closing the parent pipe also makes the real helper exit, including
when a driver call is blocked on its control worker.

A running helper must keep reporting current-generation state within three
seconds. Each output also has an independent frame-progress watchdog (five
seconds or four maximum buffer durations, whichever is larger). Sleep stops the
helper; wake refreshes devices without resuming audio. These checks cover separate
failure modes: a live process/control loop does not prove a device callback is
returning.

Inside the helper, `AudioCoordinator` keeps state on its main actor. Device discovery, graph
preparation, hardware start/stop, and device-health reads run on a dedicated serial
worker. `starting` describes preparation; `running` becomes true only after all
IOProcs start and the current request is accepted. A ten-second watchdog rejects
an unresponsive start. Each start has a cancellation token, checked around setup
and before each IO start. Candidate output buses remain muted until accepted, so
a late driver return cannot broadcast an obsolete mix. Candidate process taps
initially preserve original playback. Only an accepted generation enables
`mutedWhenTapped`, suppressing original app playback while RaveLink routes it.
Stopping capture restores that playback.

Application identity includes actual enclosing app bundles, grouping nested
browser helpers without guessing from bundle-ID prefixes. Dedicated inputs and
the system remainder share one process snapshot. Process-list events retarget all
affected taps behind an independent output gate, unregister capture callbacks,
discard queued capture, and reopen only after the current generation succeeds.
macOS 26 adds bundle restoration; macOS 15 uses explicit process-object updates.
Device listeners and a polling fallback revalidate alive state, rates, channel
ranges, and Float32 byte layout; a stalled health check has a three-second limit.
Actual tap transitions and hardware/power changes still require runtime
qualification; see [application lifecycle](application-capture-lifecycle-plan.md).

A blocked CoreAudio call cannot be cancelled within the helper; the supervisor
terminates the process instead. This recovers the application's control boundary,
not a broken system driver. If callback unregistration fails, callback storage and
retained Audio Unit owners are intentionally quarantined until process exit rather
than freed while HAL could still reference them. Direct `AudioCoordinator` tests
do not have this outer process boundary; hardware tests must use external limits.

## Real-time graph

The C layer allocates buffers before IO begins. Its callbacks contain no Swift
object access, allocation, file IO, mutexes, or dispatch. Controls and telemetry
use lock-free C11 atomics. Input capture uses one single-producer/single-consumer
stereo FIFO for each output device clock. Duplex capture callbacks explicitly
contribute silence to their output buffers.

Each source is converted to the destination rate, then sources belonging to one
visible input are summed. Gain, one-pole high-pass, gate, and compressor operate
once on that summed waveform. Source meters report that processed group signal.
Configured Audio Unit effects then process the group before its sends. Each
output clock has its own prepared rack instance. The Objective-C bridge uses
cached render/pull blocks and preallocated planar buffers in 512-frame slices.
Live parameter assignments use validated Audio Unit controls on the engine control
thread; bypass crossfades the dry/wet signal over approximately 5 ms while the effect continues processing.
Changing effect identity, order, version, or saved state rebuilds the graph.
A render error or invalid returned waveform latches the output silent and stops
audio with the effect and input identified. Third-party code may still block,
allocate, or crash; isolation limits its impact on the GUI rather than making
arbitrary plugins real-time safe.

The rack aligns each effect's bypass path to its reported latency and aligns
shorter input racks to the longest rack on that output clock. Telemetry reports
`effectAlignmentLatencySeconds`, bounded to two seconds. This is effect alignment
only; it excludes physical device, driver, and FIFO latency. A live effect change
that changes latency stops audio and requires a new graph rather than silently
misaligning the channels.
Each send has independent gain, stereo balance, and mute; each bus has independent
gain and mute. Source mute/solo and send/bus controls use short smoothing ramps.
Multiple mix destinations preserve the parent bus controls and are rendered on
their own device clocks. Output samples are finite and clamped to ±1; bus meters
remain before this ceiling so overload is visible. This ceiling is not a
look-ahead or true-peak limiter.

The resampler uses a precomputed Blackman-windowed sinc kernel: 512 phases and
64 × ceil(max(1, input/output rate)) taps. Its cutoff is 90% of the lower Nyquist
frequency. An elastic FIFO applies a small bounded clock correction. Rate ratios
outside 1:24 through 24:1 are rejected. The conservative cutoff trades upper-band
extension for stopband rejection; full-band response, clock drift, latency, and
long-session behaviour still need a release qualification protocol. This is not
a claim of transparent or bit-perfect conversion.

Devices must expose packed native-endian Float32 virtual streams at their nominal
rate. Input offsets support mono duplication and stereo pairs; outputs require
an available stereo pair. Buffer requests above 16,384 frames fail closed.
Virtual feedback validation catches cycles through overlapping channel pairs,
including cycles spanning several virtual devices. Different pairs on the same
multichannel device remain usable. Physical duplex devices are not assumed to
loop back internally.

There is no arbitrary product channel count cap. Model expansion and real-time
allocation each have conservative preflight budgets, bounded by the lesser of
one sixteenth of physical RAM and 512 MiB. Actual usable graph size also depends
on device limits, CPU, sample rates, scheduling, and plugin behaviour. The memory
estimate is a resource guard, not a measurement or a real-time CPU guarantee.
It also reserves conservative AU bridge overhead and actual host delay-buffer
storage across output clocks. Vendor-private plugin allocations and process RSS
are outside this estimate.

## Sound Check isolation

Sound Check uses a separate engine session with one selected input group and one
explicit listening destination. Every API/protocol entry validates that shape;
the studio is not resumed automatically. The system remainder keeps the original
studio's dedicated-application exclusions, including across live control edits.
It records at most 30 seconds of the dry, summed input into preallocated memory.
Recording, idle, and ready states produce silence, including a second gate after
Audio Unit processing to suppress effect tails. Playback replaces the live input
with that dry clip before the complete effect chain; loop boundaries have a short
fade. Clip PCM never enters the JSON protocol or a file.

Gain, mute, pan, parameter, and bypass edits retain the clip. Changing an input,
destination, effect identity/order/state, or another graph topology discards it
and stops Sound Check with an explicit message. Closing the session or terminating
the helper also discards it. Mode and recorded frame count are published together
in one atomic state so the UI cannot observe a torn transition. The helper's
snapshot must keep reporting the expected clip while the check is running.

## Verification and limits

Run `scripts/test.sh` for deterministic tests. Audio tests cover the filter/gate/
compressor, source grouping before nonlinear effects, route independence,
source/send/bus smoothing and mute, channel offsets, mono capture, invalid input,
FIFO overflow/underrun, sample-rate conversion stopband controls, memory overflow,
and virtual feedback cycles. Hardware tests are opt-in.

`EngineClientTests` exercise unexpected exit, a live peer closing its input pipe
(forcing the EPIPE write path without SIGPIPE terminating the caller), oversized output, ignored SIGTERM,
discovery and stop deadlines, stale telemetry, reaping before replacement, and
continuous control input. The opt-in supervised silent-output test verifies real
native rendering through IPC and checks that the helper PID disappears after
shutdown. See `research/evidence/engine-process-tests.txt` for the recorded run.
Sound Check routing tests prove dry grouped recording before effects, processing
the same clip with changed gain, and post-effect tail silence. The opt-in physical
test records generated tone and exercises commands/live edits while keeping its
listening bus muted throughout playback; it is a silent callback/IPC test, not
independent evidence of the listening waveform.

On the development host, independent native registration, one second of silent
physical output, stop, and unregister all succeeded. The independent C probe
observed 94 callbacks / 48,128 frames at 48 kHz. A separate native coordinator test
rendered 50,688 silent frames with zero bus peak. See
`research/evidence/coreaudio-silent-output.txt` and
`research/evidence/native-silent-output-test.txt`.

The bundled RaveLink HAL driver also passed an installed-device test in a disposable
GitHub macOS runner at commit `597be4d` (run `39961789278`). Its independent C
receiver recorded 576,000 stereo frames at 48 kHz: fitted frequency 439.99959 Hz,
peak 0.12589075, the expected unity / -12 dB / mute phases, and matching stereo
channels. The coordinator reported zero dropped and underrun frames. Artifacts
and run provenance are in `research/evidence/installed-hal-39961789278/`. This
establishes that specific installed-driver lifecycle and waveform path; it does
not establish long-session, multi-device, or third-party plugin performance.

The installed BlackHole 2ch v0.5.0 (build 595) did not return from
`AudioDeviceCreateIOProcID`. An independent minimal C probe reproduced this
registration hang for BlackHole while the built-in speakers registered normally.
The engine's opt-in BlackHole test failed with its ten-second watchdog; no
successful local virtual-loopback result is claimed. See
`research/evidence/blackhole-registration-isolation.txt` and
`research/evidence/blackhole-loopback-failure.txt`. Neither coreaudiod nor system
audio routing was changed to obtain this evidence.

Use the following explicit hardware probes:

```sh
scripts/audio-device-probe.py --list
scripts/audio-device-probe.py --uid BuiltInSpeakerDevice --silent-seconds 1
RAVELINK_TEST_SILENT_OUTPUT=1 scripts/test.sh --filter testSilentPhysicalOutputLifecycle
RAVELINK_TEST_SILENT_OUTPUT=1 scripts/test.sh --filter realSilentOutputThroughSupervisedProcess
RAVELINK_TEST_LOOPBACK=1 RAVELINK_LOOPBACK_DEVICE_UID=BlackHole2ch_UID \
  scripts/test.sh --filter testBlackHoleLoopbackAndLiveBusControls
```

The loopback test observes a -18 dBFS reference tone through the selected real
virtual device, verifies -12 dB bus gain and mute, and repeats start/stop. It checks
that default devices remain unchanged. These return meters come from the same
coordinator and are not an independent receiver.

For an independent receiver, `scripts/audio-device-probe.c` links only CoreAudio
and CoreFoundation and has its own IOProc. It preallocates stereo capture memory,
outputs silence, and writes an IEEE Float32 stereo WAV after stopping. Its Python
runner imposes a hard process timeout. Example:

```sh
scripts/audio-device-probe.py --timeout 20 --uid YOUR_VIRTUAL_UID \
  --capture-seconds 12 --wav /tmp/ravelink-independent.wav \
  --ready-file /tmp/ravelink-recorder.ready
```

Start that recorder concurrently with the loopback test and provide
`RAVELINK_CAPTURE_READY_FILE=/tmp/ravelink-recorder.ready` to the test. Analyze the
saved waveform separately for level transitions, frequency, dropouts, and mute.
A recorded waveform is independent evidence only when that run actually succeeds.
Process-tap consent, app restarts, hardware hotplug, multi-device clock drift,
long-duration load, all supported OS versions, and third-party effect rendering
are not established by the synthetic tests or the silent physical-output run.
