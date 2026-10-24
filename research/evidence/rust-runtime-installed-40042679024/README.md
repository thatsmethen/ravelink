# First installed capture/mixer observation: FAIL

Run [40042679024](https://github.com/thatsmethen/ravelink/actions/runs/40042679024),
attempt 1, tested immutable source `4fad7fca69415bc86aae17caa5cab2641576a26e` on
macOS 15.7.9 (24G830), arm64 VMAPPLE, Apple SDK 15.5, Rust 1.91.1. The runtime
job failed the unchanged complete protocol. The separate basic installed-HAL
job passed. This is not a production or full runtime qualification.

## Original evidence custody

`original-run.json`, `original-jobs.json`, `original-artifacts.json` and
`original-run.log` retain GitHub's original metadata and logs. The downloaded
archives are unchanged:

| Archive | Bytes | SHA-256 | Exact members |
| --- | ---: | --- | ---: |
| `original-runtime.zip` | 6,597,920 | `cafd890813f3b676f22631526273427994add1a69a22629be1e6f866c956fc11` | 52 |
| `original-hal.zip` | 10,302,395 | `e4f2b23eead23d3e1846efab083f1c3305aa317bfbe9353b07e0157aaa0b7b52` | 58 |

Both ZIP hashes match the GitHub artifact metadata. Every extracted byte length
and SHA-256 matches its runner manifest: 51 runtime files and 57 HAL files, plus
each manifest itself. There are no omitted or extra members. Verification is
recorded in `custody-verification.json`. The unchanged archives are published as [public release assets](https://github.com/thatsmethen/ravelink/releases/tag/evidence-rust-runtime-40042679024). A second download verified both hashes and every manifest member; exact asset URLs and sizes are in `publication.json`. Download those assets into any directory and run `python3 verify.py --archives /path/to/downloads`. Large PCM archives are retained as release assets rather than duplicated in Git history.
Original PCM/reports were not repaired, normalized, realigned or overwritten.

## What passed and what failed

All three runtime-protocol processes exited successfully without a reported
fault. The actual Hardware capture and mixer delivered the independently
generated 440/997 Hz stereo source through Cable 1 into Cable 2 at the expected
-6/-12 dB gains. All four fixed PCM phases passed. Maximum relative amplitude
error was approximately 0.0023%; no eight-frame silent hole occurred in either
unmuted interval, including the live gain handoff. Mute steady PCM and the full
post-stop tail were exactly zero. Detected gain/mute/restore responses were
approximately 30/35/25 ms from request, and stop response approximately 25 ms.
These are the fixed 20 ms envelope-window observations, not calibrated transport
latency. Acknowledgements were 17.8–25.4 ms. Rendered-frame throughput was
47,983.47 frames/s, within the fixed 1% limit.

The complete protocol nevertheless failed native callback continuity:

- Source writer skipped 768 frames before `start()` returned and before the
  runtime phase sequence; it later skipped 1,168 frames after runtime stop.
- The independent Cable 2 recorder skipped 1,412 frames in the same post-stop
  interval. Its post-stop PCM remained silent, which cannot restore those missing
  native callback frames or turn the complete observation into a pass.
- The sample-to-host timestamp relationship remained 48 kHz. No host reversal
  was reported. All expected frames were eventually retained, but their native
  timeline contains gaps, so contiguous capture was not established.

Relative to the runtime's started event, stop was requested at 23.177935 s and
returned at 23.303161 s. The recorder's new timestamp after its gap is at
23.702859 s; the writer's is at 23.723525 s. Their preceding callbacks were
observed after PCM work at 23.702611 and 23.701145 s respectively. This supports
a coincident late observation/resynchronization hypothesis, but does not identify
whether dispatch, preemption, CoreAudio reconfiguration or another cause was
responsible. The existing observed time is sampled after PCM work, not on callback
entry. `diagnose_timing.py` reproducibly derives `derived-timing.json` from the
unchanged CSVs and phase events.

The separate basic HAL job passed its source/readers/clock checks, exact aligned
two-reader comparison across 758,160 frames, fresh-start silence and both-device
cleanup. Both jobs' final cleanup independently found both UIDs absent. That
bounded pass does not supersede this runtime failure or the earlier intermittent
failure in run 40041055533.

## Frozen-source teardown review and diagnostic plan

At `4fad7fc`, `Running::drop` revokes callback publication, then drops its CPAL
output stream followed by capture streams. `AudioRuntime::stop()` replies only
after dropping that owner. CPAL 0.18.2 holds each AUHAL in `StreamInner`; its
disconnect monitor holds a weak reference. `coreaudio-rs` 0.14.2 drops an audio
unit by stopping it, uninitializing it, freeing callbacks and disposing the
instance, ignoring native errors during `Drop`. Apple documents uninitialization
as resource deallocation and instance disposal as destruction:
[AudioUnitUninitialize](https://developer.apple.com/documentation/audiotoolbox/audiounituninitialize(_:)),
[AudioComponentInstanceDispose](https://developer.apple.com/documentation/audiotoolbox/audiocomponentinstancedispose(_:)).
This does not prove when every asynchronous CoreAudio/listener operation finishes.

No reviewed teardown path deliberately changes a default device, nominal rate
or hardware buffer size. Startup can attempt physical-format/sample-rate
configuration through CPAL; the fixed driver accepts only the existing format,
and runtime stream configs use the default buffer size. The driver start/stop
code tracks client IDs independently per cable, clears a ring only on a stopped
to running transition, and notifies running-state changes only at zero/nonzero
boundaries. Stop does not reset the anchor or clock. Synthetic tests exercise
an additional client's start/stop without disturbing another active client;
the installed observation does not contain actual client-count events, so host
lifecycle behavior is not proven. Apple's
[StopIO contract](https://developer.apple.com/documentation/coreaudio/audioserverplugindriverinterface/stopio)
identifies the requesting registered client; no new single-client assumption is
introduced here.

Next diagnostic work should preserve this failure and keep its criteria unchanged:

1. Add callback-entry Mach ticks alongside the existing post-PCM ticks in the
   independent C observer, plus the OS-provided current timestamp. Continue using
   preallocated storage and bounded writes. This separates late entry from long
   callback execution/preemption without changing waveform assertions.
2. Record bounded per-client property notifications for processor overload,
   running state, rate and buffer-size changes, and runtime request/return/drop
   milestones. No default-device changes or recovery retries. Listener callbacks
   must only publish fixed atomic records; serialization stays off callback.
3. If those events implicate HAL lifecycle, use a distinct diagnostic build with
   bounded per-device Add/Start/Stop/Remove records, before/after running counts
   and clock-anchor values exposed by a read-only diagnostic property. Do not
   silently add diagnostics to the original acceptance binary. Driver event
   instrumentation can perturb scheduling and is not performance qualification.
4. A bounded runner-only scheduling trace may then distinguish host/VM stalls
   from CoreAudio operations if available. Keep that separate from acceptance;
   do not keep rerunning the same protocol until a pass replaces the failure.

The native CoreAudio capture adapter being developed after this checkpoint is
separate work. This observation neither proves CPAL caused the gaps nor proves
that changing the capture backend fixes them.
