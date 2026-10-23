# RaveLink local driver patch

`Drivers/BlackHole/` remains the pristine GPL-3.0-only upstream pin.
`manifest.json` fixes the SHA-256 of that input, every local patch and the
complete patched C source. `scripts/virtual-devices.py` rejects mismatches,
applies the unified patch with zero fuzz and distributes the pristine source,
patch, manifest, generated source, configuration and build instructions inside
each driver bundle. Changing this patch requires updating both digests and
rerunning the actual built-bundle controls.

The patch addresses a demonstrated stale replay: an old nonzero ring slot could
be read for a new timeline interval whose write was skipped. Frame metadata now
identifies its absolute sample, timeline generation and publication sequence.
Readers return silence for missing, expired, overwritten or changing frames;
they never erase the shared ring. Independent clients can read different ranges
without destroying each other's valid data.

One fully mixed HAL `WriteMix` stream is the producer. A compile-time assertion
requires the hidden mirror to have no output stream. Atomic sample bits and sequence publication support concurrent
readers, not multiple independent writers. A release fence after odd publication
and an acquire fence before the reader's second sequence check pair through any
new atomic sample/metadata store observed by that reader. Final even publication
is a release store. A reader seeing an incomplete/changed sequence discards that
frame. Native 32/64-bit lock-free atomics are required at compile time. Callback
code contains no allocation, mutex, spin wait or explicit retry loop.

The first active client allocates/initializes samples and validity, with checked
allocation failure. The last stop releases both. A backward writer timestamp or
reset of the writer's HAL cycle counter invalidates earlier generations. Reader
counters are deliberately not authoritative: clients may lag or lead without
resetting another client's data. Generation or sequence exhaustion fails closed.
The current device clock in `GetZeroTimeStamp` only advances its sample counter;
its sole reset is the first-client `StartIO` allocation, which also resets frame
validity. A reader's cycle-counter resynchronization alone does not rewind this
device clock and is not treated as authoritative. If that clock-reset ownership
changes in a later driver patch, validity must be reset by the same authority.
Finite nonnegative fractional timestamps preserve upstream truncation to an
integer frame on both paths; nonfinite, negative and out-of-range values fail
before conversion.

Controls use the real built bundle interface in a private process, not an
installed HAL driver. They cover the original missed-write case and positive
adjacent writes, partial holes, variable blocks crossing the ring boundary,
expired/overwritten reads, nonzero interleaved reader counters, writer reset,
multiple-client stop/start, malformed bounds and concurrent reader integrity.
Original failure evidence is retained under `research/evidence/hal-missed-write-*`.
Subsequent installed-driver acceptance must keep its strict PCM/timestamp gates.
Silencing a missing frame does not repair an undelivered macOS callback or prove
that the application meets a real-time operating envelope.
