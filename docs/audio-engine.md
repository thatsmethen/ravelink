# Native audio engine and evidence

The current engine uses CoreAudio device IOProcs for actual device capture and
rendering, and macOS process taps with private aggregate devices for application
and system capture. It does not change system default devices, device volume, or
nominal sample rates. Application/system capture requires macOS audio-recording
consent. Physical input capture requires microphone consent.

`AudioCoordinator` keeps UI state on the main actor. Device discovery, graph
preparation, hardware start/stop, and device-health reads run on a dedicated serial
worker. `starting` describes preparation; `running` becomes true only after all
IOProcs start and the current request is accepted. A ten-second watchdog rejects
an unresponsive start. Each start has a cancellation token, checked around setup
and before each IO start. Candidate output buses remain muted until accepted, so
a late driver return cannot broadcast an obsolete mix. Candidate process taps
initially preserve original playback. Only an accepted generation enables
`mutedWhenTapped`, suppressing original app playback while RaveLink routes it.
Stopping capture restores that playback.

A blocked CoreAudio call cannot be cancelled in this process. The watchdog keeps
the UI responsive and requires a new process after a timeout; it does not recover
the driver. If callback unregistration fails, callback storage is intentionally
quarantined until exit rather than freed while HAL could still reference it.
Full process isolation and recovery remain separate work.

## Real-time graph

The C layer allocates buffers before IO begins. Its callbacks contain no Swift
object access, allocation, file IO, mutexes, or dispatch. Controls and telemetry
use lock-free C11 atomics. Input capture uses one single-producer/single-consumer
stereo FIFO for each output device clock. Duplex capture callbacks explicitly
contribute silence to their output buffers.

Each source is converted to the destination rate, then sources belonging to one
visible input are summed. Gain, one-pole high-pass, gate, and compressor operate
once on that summed waveform. Source meters report that processed group signal.
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

## Verification and limits

Run `scripts/test.sh` for deterministic tests. Audio tests cover the filter/gate/
compressor, source grouping before nonlinear effects, route independence,
source/send/bus smoothing and mute, channel offsets, mono capture, invalid input,
FIFO overflow/underrun, sample-rate conversion stopband controls, memory overflow,
and virtual feedback cycles. Hardware tests are opt-in.

On the development host, independent native registration, one second of silent
physical output, stop, and unregister all succeeded. The independent C probe
observed 94 callbacks / 48,128 frames at 48 kHz. A separate native coordinator test
rendered 50,688 silent frames with zero bus peak. See
`research/evidence/coreaudio-silent-output.txt` and
`research/evidence/native-silent-output-test.txt`.

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
