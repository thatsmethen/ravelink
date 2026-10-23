# Audio Unit catalog and isolated probe

`RaveLinkPluginHost` implements registry discovery and selected-effect inspection. It does not yet process mixer audio, persist effect chains, display vendor editors, or establish third-party compatibility.

The app-side `PluginCatalog` asynchronously launches a disposable helper. Catalog enumeration uses `AudioComponentFindNext`, `AudioComponentCopyName`, `AudioComponentGetDescription`, and `AudioComponentGetVersion`; it never instantiates an effect. Only Audio Unit effect (`aufx`) and music-effect (`aumf`) components are included. A selected probe must name a concrete type/subtype/manufacturer tuple and, when known, the catalog version.

The probe requests out-of-process instantiation through `AVAudioUnit`. This option does not isolate AUv2 from the helper; AUv2 code runs inside the disposable helper. This boundary contains ordinary process crashes and stalls. It is not a security sandbox, and does not promise cleanup of arbitrary subprocesses created by a plug-in.

The helper configures main input and output bus 0 to mono or stereo noninterleaved Float32 at the requested sample rate, checks that the format remains set, and attempts offline render-resource allocation with a 512-frame maximum. It reports allocation independently of configuration acceptance, plus the actual bus formats/layout tags, channel capabilities, latency/tail values, parameter ranges, initial values, and available legacy declared defaults. Auxiliary buses are reported but not negotiated. Initial values and declared defaults remain distinct; unsupported defaults are `null`.

No audio is rendered or hardware started by this inspection path. Successful allocation does not establish correct audio output, callback safety, latency compensation, automation, preset support, or real-time performance.

## Protocol and bounds

Each invocation reads one JSON object from stdin, then writes one versioned JSON response to stdout and exits. The request uses `protocolVersion: 1` and `operation: "list"` or `"probe"`. A probe additionally supplies `component`, `sampleRate`, `channels`, and optionally `expectedVersion`. Plug-in stdout logging is redirected to stderr before loading any unit so it cannot corrupt the JSON response.

The parent accepts at most 4 MiB stdout and 256 KiB stderr, validates the schema, component identity, protocol version, and matching operation, and discards arbitrary stderr text. Errors remain typed. Catalog and parameter counts are capped at 4096; bus counts are capped at 64 per direction. Requests are bounded and written before launch to avoid a parent SIGPIPE when a child exits immediately.

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
