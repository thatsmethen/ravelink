# Native input capture

The shipping Rust runtime accepts `Hardware.device_id` and `Virtual.endpoint_id`
values returned by `AudioRuntime::enumerate_input_devices()`. These are CPAL's
host-qualified CoreAudio device UIDs or WASAPI endpoint IDs. A display name,
default-device alias, or absent ID is never substituted. Restart after a
failure requires an explicit new start; no reconnect or route-following loop
runs in the background. Creating the runtime does not enumerate or open devices.

Input selection is independent of output selection. One native input stream is
opened per distinct input ID; duplicate logical source channels share its PCM.
Mono input is duplicated to left and right. Stereo and wider PCM devices use
channels 1 and 2 only. Input and output formats must expose the exact nominal
session rate. Physical PCM layouts are bounded to 256 device channels and
16,384 frames per callback; the number of logical inputs is memory-derived.
Application/process capture still requires a separate platform implementation.

## Clock transport

Every device has an independently allocated 65,536-frame stereo SPSC queue.
Frames are packed into `AtomicU64` slots; the write cursor publishes a complete
packet with release ordering and the read cursor releases old filter history.
Neither callback allocates, locks, spins, waits, does I/O, or changes a graph.
There is one writer and one reader per queue. The output callback is the master
clock. Captured PCM passes through an original 128-tap Blackman-windowed sinc
resampler, using a shared precomputed 1,025-phase table and interpolating adjacent
phase rows. No third-party resampling implementation was copied or linked.

Both devices request the same nominal sample rate. A low-pass-filtered FIFO
occupancy error drives a bounded PI correction of at most +/-2,000 ppm. This is
asynchronous clock compensation, not general sample-rate conversion. Startup
waits for at least 1,024 frames, or two observed device packet spans plus filter
history if larger. Initial excess prefill is discarded when choosing the first
filter center. At 48 kHz and 256-frame packets, the queue target is 21.3 ms;
actual total latency also includes device buffers and scheduling. After startup,
no individual frames are inserted, removed, repeated, or overwritten to repair a
clock mismatch. Underflow, overflow, or failure to prime within two seconds of
output callbacks stops the whole engine and exposes an explicit fault.

Every capture and output callback checks the start cancellation token, generation
and latched fault. Stopping revokes those gates without waiting for an OS call.
Fresh starts allocate fresh queues, so an old stream cannot feed a new session.
Already captured OS buffers and already submitted output cannot be recalled.
A stuck OS call still requires the planned process supervisor for hard recovery.

## Evidence and limits

Offline tests exercise distinct stereo PCM across multiple ring wraps, mono and
wider-channel selection, non-finite sample sanitization, startup/underflow/
overflow, duplicate logical source mapping, cancellation, fresh-start isolation,
and zero application allocations/deallocations in capture plus mix callbacks.
A 60-second simulation at each of -1,000 and +1,000 ppm checks occupancy,
convergence and signal continuity. The filter response is tested at 44.1/48 kHz
from 20 Hz through 20 kHz within 0.1 dB and across the correction's folded Nyquist
band below -65 dB. These are algorithm tests, not installed-driver, device,
latency, microphone permission, Windows execution, or long-duration qualification.

The implementation was checked against the pinned `cpal 0.18.2` primary source:
`src/traits.rs` (`DeviceTrait::build_input_stream_raw`, device discovery),
`src/host/coreaudio/macos/device.rs` (device UID and explicit input stream),
`src/host/wasapi/device.rs` (endpoint ID/configuration), and
`src/host/wasapi/stream.rs` (capture callback and discontinuity reporting).
Native host tests must still qualify real callback cadence, permissions,
disconnection, the ASRC servo with real clocks, and operating-system buffer flags.

### Original Windows WASAPI capture adapter

Windows capture now uses first-party `wasapi_capture.rs` and portable
`wasapi_packet.rs`. CPAL still supplies explicit endpoint discovery/configuration
and output. The native capture worker resolves the exact backend ID through
`IMMDeviceEnumerator::GetDevice`, validates active capture direction and the
requested shared PCM format, installs an event before starting, and registers
with MMCSS Pro Audio. COM interfaces, packet leases and the event stay on that
one worker. Normal waits are bounded to 20 ms; command acknowledgement remains
bounded by the runtime deadline, and teardown never joins a hung driver call.

`AUDCLNT_BUFFERFLAGS_SILENT` packets create zero stereo frames without borrowing
the OS payload, even if its pointer is null or its contents are nonzero. Every
nonempty acquired packet is released exactly once, including invalid packets and
early returns. Frame-position gaps and later discontinuity flags stop capture.
The initial discontinuity flag at position zero is permitted. Timestamp-error
flags and non-increasing packet QPC values cause a separate capture-timing fault.
Fresh starts do not reuse old native streams or transport queues.

The former pinned-CPAL capture path ignored the SILENT flag. This adapter removes
that path from Windows builds. Portable tests exercise silence, malformed data,
position/QPC checks, PCM valid bits, packet release errors, and no application
allocation while converting packets into the ring. Windows-only tests also check
SDK flag values, WAVEFORMATEXTENSIBLE layout values and device-error mapping.
Cross-target compilation is not native Windows execution or qualification.

Primary API contracts used for this original implementation:

- [Buffer flags](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/ne-audioclient-_audclnt_bufferflags)
- [GetBuffer packet and release lifetime](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudiocaptureclient-getbuffer)
- [Initialize format and event contract](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient-initialize)
- [SetEventHandle ordering](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient-seteventhandle)
