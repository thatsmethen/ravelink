# Shared capture coherence

The release baseline on the disposable macOS runner completed its native frame
throughput counters with zero dropped/underrun frames, but independent recordings
failed absolute component-amplitude checks for all eight mix destinations. Each
of twelve visible input groups had its own capture of the same two device pairs.
Separate FIFO start positions and resampling cursors can make repeated copies of
one waveform cancel when mixed. That is the failure mechanism addressed here;
it is not a claim that every timestamp or device fault in the baseline shares
that cause. Frozen baseline evidence remains under
`research/evidence/installed-hal-39998798881/`.

The engine now canonicalizes each expanded capture selector using the model's
source semantics. Repeated device UID/channel-offset, exact application bundle,
or system-remainder selections share one capture IOProc. Different pairs and
application selectors remain distinct, including a saved helper-specific selection
beside its parent application. Tone generators are independent.

Each unique capture still has one FIFO for each output clock. The renderer reads
and resamples that FIFO once and fans the identical raw block into each member's
input group before built-in effects and Audio Units. Aliases are direct links to
an earlier configured root; chains, cycles, reparenting, configured alias storage,
and invalid indices are rejected. Links are configured before callbacks begin.
No callback allocation, locking, or graph mutation is introduced: each
root has a preconfigured singly linked list, and every logical source contributes
once to its chosen group's raw sum.

Group effects and sends remain independent. Muting the logical input that first
owns a capture does not stop that capture or silence another group using it.
Per-output clocks and the existing sinc/elastic-clock algorithm are unchanged.
Partially overlapping pairs (such as channels 1–2 and 2–3) still have distinct
capture paths and are outside this exact-selector coherence guarantee.

`AudioDiagnostics.captureSourceCount` reports unique native capture IOProcs.
`capturedFrames` sums those IOProcs' frame counters. A fixture with twelve groups
and two shared input pairs therefore still has 24 logical source references,
96 parent routes, and 192 expanded routes, but two physical capture sources. The
installed soak records both counts and explicitly requires the physical count to
be two. Its sample amplitudes, absolute amplitude/frequency checks, duration,
render-throughput envelope, and zero-drop/underrun/timestamp gates are unchanged.

## Deterministic evidence

`research/evidence/capture-alias-focused-tests.txt` records 31 focused tests. The
new comparison feeds unequal stereo, two-frequency 96 kHz input through a 48 kHz
render clock. Samples entering the two independent group chains are bit-identical
(maximum difference zero). An inverted second group cancels the first to a
maximum residual of `7.450435e-09`, below one Float32 rounding step for this
signal. A second test verifies independent gain, nonlinear post-sum compression,
pan, parent-only routing, and logical-owner mute. Ring underruns remain zero.

The first new test expected an exactly zero **mixed** output and failed because
floating-point multiply-add accumulation leaves rounding residue; that run is
preserved in `capture-alias-exact-cancellation-initial.txt`. The revised oracle
checks exact equality before inversion and separately bounds the mixed arithmetic
residual. No installed-driver acceptance tolerance was changed.

These buffer tests do not establish the installed HAL waveform result. The next
installed-device run must retain its independent recordings and pass the existing
absolute component and timestamp checks before this failure is considered fixed.

## Older SDK compatibility

The preceding lifecycle checkpoint failed to compile on a runner SDK lacking the
macOS 26 `CATapDescription.bundleIDs` and `isProcessRestoreEnabled` declarations.
An OS availability check alone does not make absent SDK symbols compile. The
optional restoration path now uses the documented public Objective-C setters
through KVC, guarded by both macOS 26 availability and setter capability checks.
Older systems continue using explicit process IDs. A descriptor-only test reads
back the properties when available; it creates no audio tap and requests no
capture permission. Actual capture restoration remains separately unqualified.
