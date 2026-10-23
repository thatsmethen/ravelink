# Audio Unit catalog and isolated probe

`RaveLinkPluginHost` implements registry discovery, selected-effect inspection, and bounded offline rendering with state snapshots. The native engine also supports persistent channel racks through a separate preallocated bridge, described below. Vendor editors and broad third-party qualification remain outstanding.

The app-side `PluginCatalog` asynchronously launches a disposable helper. Catalog enumeration uses `AudioComponentFindNext`, `AudioComponentCopyName`, `AudioComponentGetDescription`, and `AudioComponentGetVersion`; it never instantiates an effect. Only Audio Unit effect (`aufx`) and music-effect (`aumf`) components are included. A selected probe must name a concrete type/subtype/manufacturer tuple and, when known, the catalog version.

The probe requests out-of-process instantiation through `AVAudioUnit`. This option does not isolate AUv2 from the helper; AUv2 code runs inside the disposable helper. This boundary contains ordinary process crashes and stalls. It is not a security sandbox, and does not promise cleanup of arbitrary subprocesses created by a plug-in.

The helper configures main input and output bus 0 to mono or stereo noninterleaved Float32 at the requested sample rate, checks that the format remains set, and attempts offline render-resource allocation with a 512-frame maximum. It reports allocation independently of configuration acceptance, plus the actual bus formats/layout tags, channel capabilities, latency/tail values, parameter ranges, initial values, and available legacy declared defaults. Auxiliary buses are reported but not negotiated. Initial values and declared defaults remain distinct; unsupported defaults are `null`.

The list/probe inspection path renders no audio and starts no hardware. Successful allocation does not establish correct audio output, callback safety, latency compensation, automation, preset support, or real-time performance.

## Protocol and bounds

Each invocation reads one JSON object from stdin, then writes one versioned JSON response to stdout and exits. The request uses `protocolVersion: 1` and `operation: "list"`, `"probe"`, or `"render"`. A probe additionally supplies `component`, `sampleRate`, `channels`, and optionally `expectedVersion`. Plug-in stdout logging is redirected to stderr before loading any unit so it cannot corrupt the JSON response.

The parent accepts at most 4 MiB stdout and 256 KiB stderr, validates the schema, component identity, protocol version, and matching operation, and discards arbitrary stderr text. Errors remain typed. Catalog and parameter counts are capped at 4096; bus counts are capped at 64 per direction. Requests are limited to 2 MiB and written to a private, immediately unlinked temporary file before launch. This handles audio/state payloads without pipe deadlocks or a parent SIGPIPE when a child exits immediately.

The caller timeout defaults to 10 seconds and may range from 50 ms to 60 seconds. The helper separately bounds asynchronous instantiation to 15 seconds. Cancellation, output floods, and deadline expiry stop the helper with TERM followed by KILL after 200 ms if needed. Pipe polling and termination waits run off the UI thread. No global process-wide SIGPIPE handler is changed.

The helper is resolved from the app's `Contents/Helpers`, the loaded SwiftPM test bundle's sibling directory, or beside the command-line executable. Discovery does not search PATH or arbitrary working directories.

## Reproduction and evidence

Build and run the default synthetic protocol/process tests:

```sh
swift build --product RaveLinkPluginHost
scripts/test.sh --filter PluginCatalogTests
```

The selected Apple limiter probe is opt-in; it instantiates only Apple's AUPeakLimiter:

```sh
RAVELINK_PLUGIN_PROBE_APPLE=1 scripts/test.sh --filter PluginCatalogTests
```

Actual host evidence is recorded separately in `research/evidence/audio-unit-probe.json`. Catalog enumeration found 33 effect components. The selected Apple AUPeakLimiter (`aufx:lmtr:appl`, subtype hex `6c6d7472`, version `67072`) accepted stereo 48 kHz, allocated offline resources, and exposed three parameters. Its reported latency was approximately 2 ms. This is one stock Apple unit on one host; it is not a third-party, sound-quality, live-render, or full AU-host qualification.

Synthetic child fixtures cover invalid protocol/payloads, duplicate/non-effect identities, typed failures, cancellation, process death, excessive output, and a TERM-ignoring child that is verified absent after the timeout. These fixtures establish containment behavior, not plug-in compatibility.

## Sources

- Apple [AudioComponentFindNext](https://developer.apple.com/documentation/audiotoolbox/audiocomponentfindnext(_:_:)) documents component lookup by description.
- Apple [AVAudioUnit instantiation](https://developer.apple.com/documentation/avfaudio/avaudiounit/instantiate(with:options:completionhandler:)) documents asynchronous instantiation and options.
- Apple [AUAudioUnit](https://developer.apple.com/documentation/audiotoolbox/auaudiounit) documents the bus, parameter, resource-allocation, and timing interfaces used here.
- The host SDK's `AudioComponent.h` describes AUv3 out-of-process requests and AUv2 in-process behavior; `AUAudioUnit.h` defines the format/resource interfaces. These headers were inspected alongside the online reference.

## Bounded offline rendering

`PluginCatalog.render` accepts one descriptor, interleaved Float32 samples, mono/stereo channel count, 8–192 kHz sample rate, unique parameter address/value assignments, an optional state envelope, host bypass, and block size. The request is limited to 16,384 frames, 256 parameter edits, finite input samples with magnitude at most 16, and blocks of 1–512 frames. The helper enables the main buses, configures native planar Float32, applies fullState before parameter edits, and caches the host `renderBlock` before resource allocation. It supplies preallocated input/output buffers and reads every render status; nonfinite/excessive output is rejected. Responses preserve the requested frame count and interleaving. No device is started.

State uses `AUAudioUnit.fullState` serialized as a binary property list, bounded to 256 KiB and bound to component identity and version. Only the helper parses the property list. The parent stores bytes, validates envelope size/identity/version, and does not unarchive arbitrary plug-in objects. A successful render returns a fresh state snapshot. This allows session storage to preserve the vendor's state in addition to parameter edits, and channel racks persist this state alongside explicit parameter overrides in `MixerChannel.audioUnitEffects`. Older sessions decode with an empty rack.

Host bypass returns exact input samples and still reports the instantiated unit/state. It does not depend on a vendor implementing bypass correctly. Every request creates a fresh instance and resets transient DSP; this API is unsuitable for uninterrupted streaming. It does not flush effect tails, compensate latency, schedule automation, or negotiate sidechain buses.

Run the opt-in actual render verification:

```sh
RAVELINK_PLUGIN_RENDER_APPLE=1 RAVELINK_PLUGIN_PROBE_APPLE=1 scripts/test.sh --filter 'PluginCatalogTests|PluginRenderTests'
```

The Apple limiter test creates distinct 317 Hz and 719 Hz stereo tones, applies +20 dB pre-gain while remaining below the limiter threshold, and compares the result against independently calculated 10x samples after the reported delay. An odd 257-frame block exercises the final partial block. It then restores the saved state in a fresh process, verifies the same samples/parameter, verifies exact host bypass, and rejects an out-of-range parameter. This proves one stock unit's offline DSP and state round trip on the measured host; it does not qualify live render performance or third-party effects.

Apple documents that hosts use [`renderBlock`](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/renderblock), while `internalRenderBlock` is for implementations. The [pull-input block contract](https://developer.apple.com/documentation/audiotoolbox/aurenderpullinputblock) permits the supplied input pointers to remain valid through a render cycle. [`fullState`](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstate) is the persistable property/parameter snapshot used here.

## Persistent engine racks

`LiveAudioUnitGraph` prepares one rack per grouped input per physical output clock. Group members are summed and the built-in channel effects run first; the AU rack then processes the group once before meters and sends. Each output owns separate unit instances configured at that output's rate. Creation, state restoration, parameter metadata inspection, and resource allocation occur on the engine control queue. The GUI does not host these instances.

The Objective-C bridge caches render/pull/schedule blocks and allocates stereo planar ping-pong buffers before processing. It subdivides arbitrary device blocks into at most 512 frames, retains a continuous sample timeline, and never enters Swift from the C audio callback. The bridge's own callback code performs no allocation, locking, logging, Objective-C property lookup, or block copy/release. This is a source-level property of our bridge; a third-party render block can still allocate, stall, or crash. It runs inside the supervised `RaveLinkEngine` process.

UI parameter changes use validated `AUParameter.value` writes on the engine control queue; the callback performs no property lookup. This also updates vendor parameter observers/fullState. During qualification, `master_me` did not persist changes sent solely through the scheduling block despite advertising ramp support. Cached scheduling blocks remain available for a future automation path, but are not used for UI edits. Removed overrides return to values captured after state restoration. Host bypass uses an atomic target and a 5 ms dry/wet transition; the unit continues rendering while bypassed so its DSP timeline stays continuous. Slot order, identity/version, and fullState changes require graph reconstruction. Parameter and bypass changes do not.

A render status failure, malformed bus layout, or nonfinite/excessive output latches immediate silence across that output graph. Other output graphs stop when the engine observes the failure. Error telemetry identifies the channel/effect and requires explicit recovery; the rack does not silently bypass a failed unit or resume by itself. A unit crash or stall is contained by the engine supervisor rather than a recovery attempt on the audio callback.

State is snapshotted on the control queue and keyed by channel and slot identity. Failed preparation releases the partial graph exactly once. Timed-out instantiation abandons its pending result so a late completion cannot retain a unit in the live graph. Full-state preset restoration and parameter overrides are supported; vendor preset browsers, editor windows, and sample-accurate automation are not yet provided.

The native callback tests use real Apple limiter instances through the installed C processing hook, with grouped tone sources. They verify expected gain/delay, parameter changes and bypass on the same graph, and saved state. Synthetic render-block failures verify that earlier successful source output is also silenced and that the fault remains latched. These are callback invocations against generated PCM; they do not establish hardware-device performance or long-duration scheduling behavior.

The opt-in installed `master_me` test verifies finite output, parameter application, state restoration, live callback execution, a live parameter update restored from its state snapshot, and host bypass. Its dynamic processor output is not compared against an independent DSP oracle. The result applies only to the recorded installed build.

```sh
RAVELINK_PLUGIN_RENDER_APPLE=1 scripts/test.sh --filter LiveAudioUnitTests
RAVELINK_PLUGIN_RENDER_MASTER_ME=1 scripts/test.sh --filter ThirdPartyAudioUnitTests
```

## Reported processing latency alignment

Each live slot reports `AUAudioUnit.latency` after resource allocation. The host converts seconds to the nearest sample at that output's rate. The dry branch of host bypass is delayed by the same number of samples, and shorter or empty leader racks receive the remaining delay needed to match the longest rack on that output clock. Group children do not allocate redundant delays. Bypass keeps the configured alignment delay while its 5 ms dry/wet transition runs.

Delay rings are allocated before callbacks begin. Total reported processing latency is limited to two seconds per rack, and all dry/alignment rings together have a 128 MiB budget per output graph. Exceeding either limit rejects startup with an actionable error. These are resource bounds, independent of the number of channels stored in a session. Changing a parameter that changes reported latency latches output silence and requires explicit restart, which rebuilds delays from the new settings. Latency is also checked during engine telemetry polling, so an asynchronous vendor change can remain undetected until the next poll. The host cannot compensate latency that a plug-in does not report correctly.

`LiveAudioUnitGraph.alignmentLatencySeconds` reports the aligned effect-processing delay. This excludes capture FIFO, sample-rate conversion, hardware, network, and transport delay; it does not measure round-trip latency or synchronize separate physical output clocks. Per-slot nearest-sample rounding may introduce up to half a sample of difference from a fractional reported delay.

Apple's [`latency` contract](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/latency) distinguishes processing latency from intentional delay/reverb and recommends fixed latency while rendering. The host SDK `AUAudioUnit.h` (latency property documentation) was also inspected because the web page's Markdown rendition was unavailable to the browser tool.

The local native-hook checks now include two real Apple limiters in series plus an empty channel: both routes align at 192 samples at 48 kHz. A single limiter remains aligned at 96 samples through gain and bypass changes. Changing Apple attack time from 2 ms to 10 ms demonstrably changes reported latency, latches silence, and succeeds after explicit graph reconstruction. Synthetic checks cover irregular block boundaries, cumulative bypass delay, empty-rack alignment, inactive group children, resource rejection, and use of an unfinished graph. Evidence is recorded in `research/evidence/audio-unit-latency.json`. No hardware device was started by these checks.

## Independent installed-HAL acceptance

The opt-in CI path `scripts/run-au-loopback.sh` starts an independent recorder on the installed virtual device, then exercises the supervised engine through `EngineClient`: Apple limiter +6.0206 dB, a live change to -6.0206 dB, host bypass, a saved/restored +12 dB state, and final master mute. The engine must keep its process identity through the sequence. `verify-au-loopback.py` checks ordered, sustained 440 Hz stereo output against predetermined gains, with bounded transition and restart windows. It does not fit gains to observed samples or claim physical latency measurement.

Raw PCM, test/recorder logs, control metadata, analysis, and individual exit statuses are preserved even if an engine assertion fails. Synthetic verifier tests establish acceptance/rejection behavior only. A successful installed-HAL result must be recorded separately with its CI run and artifact provenance; adding this test to CI does not establish a pass.
