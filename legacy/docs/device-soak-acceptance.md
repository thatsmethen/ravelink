# Installed device input acceptance

This is an opt-in measurement on a disposable macOS host with the three named
RaveLink CI devices installed at eight channels each. It does not install drivers,
change system defaults, or change sample rates. It must not be run as part of
ordinary local tests. The independent probe refuses non-virtual devices.

The existing loopback test proves a generated signal reaches the installed HAL.
This additional case feeds actual device input into the mixer: an independent C
process writes 400 Hz to `ci-loopback` channels 1–2 and 1 kHz to channels 3–4,
each at amplitude 0.01. Twelve visible input groups each capture both pairs.
Their 24 logical source references share two physical capture contexts, one per
distinct input pair. Each output resamples each unique capture once and fans the
same raw block into all referencing groups before their independent effects.
They feed eight buses through 96 visible routes (192 lowered routes). Each bus
uses a distinct stereo pair: four on `ci-mix-a`, four on
`ci-mix-b`. Route gain is 1/12; bus levels are 0, −3, −6, −9, −12, −15, −18 and
−21 dB. There are no generated tone sources in the mixer graph.

Two independent C recorder processes capture all eight channels of each output.
The engine warms for three seconds while the feeder contributes silence, signals
the feeder to begin, runs for at least 30 seconds, then mutes every bus. The
feeder continues for 35 seconds, so recorded final silence must come from mixer
mute, not from a stopped source. Recorders collect 60 seconds each.

After the test targets have been compiled, CI runs:

```sh
RAVELINK_TEST_DEVICE_SOAK=1 scripts/run-device-soak.sh
```

The script supervises all three probe processes, checks readiness, runs the
opt-in Swift test, waits for raw recordings, and analyzes them. An engine test
failure still lets each bounded recorder finish, so the failed audio observation
is retained. `soak-exit-status.json` records every component's exit status, and any
failure keeps the overall run failed. Its EXIT trap terminates and reaps every
still-owned probe on interruption or early setup failure. Each Python supervisor
also bounds its C child and escalates termination after two seconds. No local
HAL run is implied by compiling this instrument or passing its synthetic controls.

Archive `build/soak-*.wav`, `build/soak-*.json`, and `build/soak-*.log`. The JSON
records graph counts, actual sample rates, configured and observed block sizes,
capture/render counters, measured interval, CPU time divided by wall time,
process peak RSS, host identity and per-half-second counters. CPU/RSS are observed
values for the direct native coordinator in the test process, not isolated GUI
worker overhead or guaranteed capacity. Startup counters are reported separately;
there must be no new dropped, underrun, or oversized-block counts after warmup.
The report separates 24 logical sources from the observed physical capture count,
which must remain exactly two; expected captured-frame throughput uses that
runtime physical count. The earlier frozen baselines had 24 physical captures.

The verifier checks all eight stereo pairs independently: at least 29 uninterrupted
seconds with both expected absolute tone amplitudes within 3%, stereo equality,
DC and residual limits, phase continuity within a 2 Hz adjacent-window envelope,
and sustained final silence. It inspects partial tail blocks. It does not align
waveforms, resample, or fit gains. Tone phase tracks describe the measured relative
clock behavior over this interval. Incorrect repeated-source timing can cause
phase cancellation; this is a test failure, not a reason to fit the gain.

The probes retain CoreAudio input/output sample timestamps and reject missing or
discontinuous timestamps. The verifier reports the interval between the feeder's
first signal timestamp and the first received signal timestamp. These are HAL
sample-presentation intervals, not physical/acoustic round-trip latency. A
30-second run at the recorded rates does not establish indefinite clock stability,
all hardware compatibility, or an unlimited performance envelope.

`Drivers/tests/test_device_soak_verifier.py` supplies synthetic valid and invalid
controls for the instrument. Those tests prove analyzer behavior only; actual
installed-driver evidence requires raw WAVs, probe reports, engine report, passing
analysis and CI provenance from the same run.

The first expanded run, GitHub Actions `39967965423` at revision `b34a841`, failed
this acceptance on macOS 15.7.9, three logical processors, with the debug test
build. During 32.337 seconds at 48 kHz it captured 37,306,368 frames and rendered
2,553,344 frames, about 82.25% of the expected render count. The engine counted
11,546,018 dropped frames, zero underrun frames and zero oversized blocks; process
CPU use was 1.396 core equivalents and peak RSS was 60,489,728 bytes. The original
shell aborted its independent probes when Swift assertions failed, so this run
has no raw soak waveform and cannot diagnose phase coherence. That observation
gap prompted the failure-preserving orchestration above. Original engine metrics,
logs, provenance and the separate passing loopback/matrix captures are frozen in
`research/evidence/installed-hal-39967965423/`. This run establishes a failed
configuration, not a successful scale envelope.

The first release baseline, run `39998798881` at `b787263`, retained the same
24-capture graph and passed its engine counter assertions over 32.321674 seconds:
37,355,520 captured frames, 3,108,352 rendered frames, and zero new drops,
underruns or oversized blocks. Measured CPU was 0.44458 core equivalents and peak
RSS 61,259,776 bytes on the same macOS 15.7.9/three-processor class of runner.
However, the overall acceptance **failed**. Recorder A observed one timestamp
discontinuity. Separate post-run inspection of the preserved PCM also rejected
all eight buses for incorrect component levels; bus 0 at 10 s contained amplitudes
0.00729535 and 0.00148798 instead of 0.01 for each tone, with substantial variation
over time. This is a signal-integrity failure even though throughput counters
improved. The timestamp failure and original failed analysis remain unchanged;
post-run diagnosis does not replace that result. Full provenance and diagnostics
are in `research/evidence/installed-hal-39998798881/`. Later probes additionally
retain the first discontinuity's sample/host timestamps in stderr to distinguish
onset and sustained failures; the zero-discontinuity criterion remains unchanged.
