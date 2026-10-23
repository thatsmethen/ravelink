# Routing preparation capacity

RaveLink limits resource consumption, rather than imposing a fixed number of channels or mix buses. A small grouped session can still describe a very large internal matrix: 2,000 sources in one visible input and 2,000 destinations on one visible mix expand to four million sends.

`MixerSession.routingCapacityEstimate()` counts expanded inputs, outputs, and routes without constructing the expanded matrix. Arithmetic is checked for overflow. `expandedRouting(memoryBudgetBytes:)` checks this estimate **before** validation sets, maps, generated child IDs, or expanded route arrays are allocated.

The shared default preparation allowance is `min(physicalMemory / 16, 512 MiB)`. Callers can supply an explicit budget to `expandedRouting` for a different deployment policy. There is no fixed channel-count cap: the number of grouped members, destinations, and their cross-product determines whether preparation fits the allowance.

The Swift lowering estimate includes:

- 16 KiB of fixed container and validation allowance.
- Per expanded input: twice `MemoryLayout<MixerChannel>.stride`, plus 256 bytes for maps and temporary records.
- Per expanded output: twice `MemoryLayout<MixBus>.stride`, plus 256 bytes for maps and temporary records.
- Per expanded route: twice `MemoryLayout<MixSend>.stride`, plus 256 bytes for validation sets and generated identifier strings.

These are explicit conservative policy allowances. They are not measured RSS, allocator guarantees, currently free RAM, or a prediction of realtime performance. Retained input-model data, audio buffers, Core Audio allocations, and runtime/allocator bookkeeping are outside this estimate. The audio engine separately checks its rate- and output-dependent C contexts, stereo FIFO capacity, group scratch buffers, and resampling kernels using the same default resource policy before allocating those objects. The two checks cover different preparation stages; passing either check does not prove low latency or freedom from underruns.

An exceeded allowance reports expanded input/output/route counts and estimated versus permitted bytes. Reduce grouped sources, additional outputs, or mixes before starting audio. Arithmetic overflow also fails before matrix allocation.

`ExpandedRoutingTests` verifies exact budget boundaries, arithmetic overflow, equal visible counts with different expansion costs, and rejection of a compact four-million-route request without building that matrix. These are deterministic resource-policy tests, not audio runtime benchmarks.
