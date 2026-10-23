# RaveLink macOS HAL

The independently authored Rust AudioServerPlugIn is in `crates/ravelink-hal`.
It publishes one stereo virtual cable named **RaveLink**. Playback written to its
output stream can be captured from its input stream. The fixed native format is
48,000 Hz, packed interleaved Float32, two channels. Its device UID is
`au.textual.ravelink.cable.1`; its bundle ID is `au.textual.ravelink.hal`.

This is an implementation and local validation candidate. Passing tests or
building a bundle does not establish operation inside macOS's audio host.
Installation, host loading, app-to-app capture, sleep/wake, rate conversion,
aggregate-device behavior and sustained production use remain unverified.
In particular, the synthetic host supplies its own timestamp relationship; actual
HAL callback ordering and input-latency calibration require an installed-host test.

## Build and validate

From the repository root on macOS:

```sh
cargo test -p ravelink-hal
sh drivers/macos/tests/run-native-host.sh
sh drivers/macos/build-bundle.sh
```

The bundle script produces `dist/macos/RaveLink.driver` for the current machine's
architecture. Set `RAVELINK_HAL_TARGET` to `aarch64-apple-darwin` or
`x86_64-apple-darwin` after installing that Rust target to build another
architecture. `RAVELINK_HAL_OUTPUT` chooses the bundle location. The default
signature is local ad-hoc signing; `RAVELINK_SIGN_IDENTITY` selects an authorized
release signing identity. These commands do not install anything or restart
audio services. A universal bundle and Developer ID/notarized release installer
are separate release work.

## Behavior and limits

- IDs: plugin 1, device 100, capture stream 101, playback stream 102.
- Sample ring: 16,384 stereo frames, timestamp-addressed; independent capture
  readers. A missing/overwritten/contested frame yields silence. Full Float32 bit
  patterns are preserved without clamping or lossy encoding.
- Capture delay: 512 frames, reported as device input latency. IO calls accept
  up to 8,192 frames; larger calls fail before accessing a buffer.
- Each IO callback performs bounded work with preallocated storage and atomic
  operations. It makes no heap allocations, CF calls, notifications, filesystem
  calls or mutex acquisitions. Each frame publication makes at most one CAS;
  writers that encounter a contested slot drop that frame without waiting.
- Client registration and start/stop use a mutex only on control paths, support
  64 clients, reject unbalanced lifecycle calls, and notify the host when running
  state changes. Neither client bundle strings nor caller-owned pointers are kept.
- The clock uses Mach absolute time and integer-rational conversion to 48 kHz.
  Its 16,384-frame timestamp period exceeds Apple's documented minimum. A single
  timeline lasts for the plug-in lifetime; restarting IO does not rewind it.
- Device/stream format properties are read-only. Reasserting the exact existing
  ASBD/rate is a harmless no-op. Different formats/rates are rejected. No dynamic
  configuration request is made; configuration callbacks reject unsolicited work.
- `device::DEVICES` is the extensibility point for independently buffered cables.
  Up to eight registry entries fit the current bounded property response arrays.
  Dynamic creation, persistence, renaming and application control are not yet
  implemented.

Rust tests exercise ring wrap/overwrite, competing producers and readers, clock
monotonicity, device isolation, malformed properties/formats, lifecycle and
stereo loopback through the vtable, and allocation counting around IO callbacks.
The C host independently compiles the SDK ABI, opens the local dylib and calls
the exported factory and complete IO lifecycle. It checks 1-, 127-, 512-, 4,096-
and 8,192-frame blocks, read-before-write silence, wraparound and repeated IO
restart clearing. Neither test is a system HAL installation test, CFPlugIn
discovery test or real-host latency measurement.

See `PROVENANCE.md` for source origins.
