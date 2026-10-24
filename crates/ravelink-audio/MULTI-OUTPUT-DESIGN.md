# Simultaneous output design — proposed, not implemented

The current runtime opens one explicitly selected output. This document records
the proposed next implementation. It does not qualify multi-device playback or
change the frozen single-output installed-runtime protocol.

## Public plan and validation

Add `OutputPlan { clock_output: OutputId, routes: Vec<OutputRoute> }`, where each
route contains one explicit native output identity and one session bus ID. Add
`start_outputs` and its cancellable counterpart. Existing start methods remain
one-route wrappers. Existing `RunningConfiguration` output fields describe the
primary output; additive output configuration/telemetry lists describe every
route. A caller explicitly chooses the render clock.

Validate the complete plan before opening any stream: nonempty routes, exactly
one clock output present, existing buses, supported host-qualified identities,
no duplicate physical output identity, supported bounded layouts, and exact
nominal session sample rate. Multiple physical devices may receive the same bus.
The first implementation sends stereo to channels 1–2 of each device and zeros
additional channels. Multiple bus pairs on a single multichannel endpoint are a
separate feature. There is no default-device fallback or automatic clock election.

## One render owner, independent destination clocks

Only the primary output callback owns the `CompiledMixer`, live control reader,
test-tone/DSP state and capture consumers. Native input IDs remain deduplicated
across logical channels. Each input stream and capture FIFO is opened and drained
once. Secondary callbacks never render the graph or consume input rings.

The core already processes all buses on each render. Add a bounded read-only view
of each bus's last successful post-DSP block. Render once with no output copy
descriptors, then fan out those borrowed planes through a precompiled bus-to-route
map. This avoids rendering a source, effect, ramp or meter once per destination.
The primary output receives its selected bus directly. Every secondary output
gets an independent bounded SPSC queue and ASRC reader driven by its own device
callback. Reuse the original 128-tap bandlimited kernel and bounded ±2000 ppm
clock correction after separately validating the output-fanout adaptation.

Start with equal nominal device/session rates. Independent devices still drift;
the secondary queue's occupancy governs its ASRC correction. A queue cannot wait
on another callback, take a mutex, grow, or silently discard/duplicate samples.
FIFO, scratch planes, fixed version tags and kernel coefficients are allocated
before activation. Keep the existing 16384-frame callback and 256-physical-channel
bounds; logical input/bus/route counts are governed by checked memory budgets.

## Publication and controls

Preflight the complete primary callback's capacity in every secondary queue
before consuming capture PCM or advancing graph state. Produce all chunks into
reserved, unpublished space, then commit only after the entire primary callback
has rendered successfully. A consumer can only free more capacity during this
operation. Any fault invalidates the shared epoch; no secondary may authorize
PCM solely because its queue contains data.

Publish a global control acknowledgment only after the entire primary block has
been processed and committed to every enabled secondary queue. This is a graph
render/publication acknowledgment, not proof that hardware or an acoustic output
has played it. The existing single-output acknowledgment occurs earlier and must
be corrected as part of this feature with explicit compatibility tests. The 5 ms
control ramps advance once on the primary render clock and may span blocks.

Each secondary reports submitted device frames, consumed primary source position,
priming state, queue occupancy and clock correction. Exact per-device control
acknowledgments need version tags alongside PCM: one u64 per source frame adds
512 KiB to each 65536-frame secondary queue. Its acknowledged version must be the
minimum version across all FIR-support samples contributing to the whole submitted
callback; merely reading a new control tag does not mean old filter history is
gone. Queue epoch is immutable; no old tags or ASRC history survive a restart.

## Atomic activation, cancellation and faults

Build the complete set of streams with a shared activation gate closed. Start
outputs while their callbacks emit silence, then start captures. Validate native
start results and cancellation before opening the gate once for the new epoch.
Partially successful startup cannot emit program audio. Start success means the
native activation transaction was accepted; secondary priming/readiness remains
separately visible, with a bounded startup failure condition.

Every start uses fresh queues, transport positions, ASRC history and epoch. Stop
first revokes the common gate, then asks owner threads to release native resources.
Callbacks check authorization before work and again before committing each OS
buffer, zeroing a buffer whose authorization was revoked while it was being
prepared. Samples already handed to hardware cannot be recalled. A primary or
secondary device/transport failure stops the complete plan. Do not silently
elect a new primary or degrade to partial playback. A permanently blocked OS
call still needs an external process supervisor; thread cancellation is not proof
of native teardown.

The bounded first-fault attribution checkpoint precedes this implementation so
the endpoint, direction and reporting path survive an all-output cancellation.
Native teardown retention and explicit-ID reservation rules continue to apply.

## Budget and user-visible limits

Deduct every secondary ring, version array, callback scratch plane, ASRC state,
route map and diagnostic record from the 64 MiB graph budget before compilation;
count the shared kernel only once. Reject arithmetic overflow before allocation.
No per-callback allocation, formatting, locks, waiting, retry loops or control
channel sends are allowed in first-party render/transport work.

Independent endpoints are not sample-synchronous. Equal buses share the same
post-DSP source sequence, but each secondary introduces queue/FIR latency and
ASRC interpolation. For small 48 kHz callback sizes the current capture transport
target is roughly 21 ms; larger packets need more buffering. This is a design
reference, not a measured output latency guarantee. Expose actual occupancy and
readiness. Do not promise identical output PCM or wall-clock alignment between
devices without a separate synchronized-clock architecture and qualification.

## Implementation and qualification sequence

1. Add pure plan validation and bounded post-DSP bus access; preserve the old API.
2. Implement secondary queue reservation/publication, ASRC and version semantics
   offline. Test two buses, two destinations for one bus, single capture/graph
   advance, long ±1000 ppm clocks, wraparound, cancellation and stale callbacks.
3. Integrate owner lifecycle/activation and all-output fault gates. Test failed
   starts, missing progress, full queues, fault/cancel races, fresh restart state,
   zero application allocations and checked budget rejection.
4. Integrate explicit UI output/clock selection and separate rendered-versus-
   submitted acknowledgments.
5. Freeze a new installed protocol and independently measure actual macOS and
   Windows output timing, routing, silence, controls and failure behavior.

Material risks remain CPAL output's native ownership/global reconfiguration,
per-route CPU cost, follower latency and FIR acknowledgment delay, and OS calls
that exceed owner deadlines. The earlier failed installed observations remain
unchanged evidence and cannot be promoted by synthetic transport tests.
