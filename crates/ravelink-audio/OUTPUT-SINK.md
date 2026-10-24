# Whole-callback rendering boundary

`RenderState::write_to` renders one complete callback into a borrowed `StereoSink`.
The sink validates its complete frame extent, clears every channel to the format's
equilibrium, and accepts sequential stereo chunks. Capture preparation and control
bank application still happen once per callback; splitting native planes or PCM
chunks cannot advance the mixer or capture clock twice.

The existing CPAL wrapper uses `InterleavedSink`. Its conversion preserves the
previous clamp, `FromSample`, first-channel-pair mapping and extra-channel silence.
Invalid buffers, failed encoding, render failure and cancellation clear the whole
callback. A nonempty, fully rendered callback publishes the graph's accepted
control target and returns its frame count and version. Priming, empty, rejected
and cancelled callbacks do not acknowledge new targets. This is graph completion,
not device submission, settled ramp completion or physical playback.

Native owners must check authorization again at their actual handoff and retain
their own submission result. [CoreAudio PCM packets](NATIVE-OUTPUT-PCM.md) remain
default-silent until explicit completion handoff. [WASAPI render leases](WASAPI-RENDER-PACKET.md)
release the full acquired buffer once and use `SILENT` unless complete PCM is
explicitly authorized. Both adapters are portable prerequisites at this checkpoint;
the running application still uses CPAL output.

Four rendering controls cover a continuous analytical sine through different
callback/chunk sizes, failure after a partial write, cancellation inside copying,
and first-callback/rejected-extent allocation behavior. Twelve CoreAudio encoding
controls and fourteen WASAPI encoding/lease controls cover their separate native
byte and lifetime contracts. Independent source review and focused reruns found no
blocking issues. The macOS workspace passes all 164 tests, strict Clippy and
formatting checks; Windows MSVC cross-target strict audio Clippy passes. Dependency
notices are unchanged and verified. These results do not establish native output
startup, callback timing, teardown or installed Windows operation.
