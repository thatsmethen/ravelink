# First installed native capture diagnostic observation — FAIL

[GitHub run 40046411757](https://github.com/thatsmethen/ravelink/actions/runs/40046411757),
attempt 1, exact source **db639ffefcb49020b9c0cea08d5ca03b8bfa2cf0**, completed with
both observation jobs failing. Both cleanup jobs independently verified both
original Rust cable UIDs absent. No retry, altered threshold or repaired PCM is
substituted for this result. No development-machine device was opened or changed.

The runner was macOS 15.7.9 build 24G830, ARM64 VMAPPLE, SDK 15.5, Rust 1.91.1.
Both independent C jobs enabled supplemental diagnostics. Original logs, API
metadata, archives, reports, PCM and manifests are retained unchanged.

## Actual runtime result

The runtime started, captured Cable 1, rendered into Cable 2 and acknowledged the
initial -6 dB phase. It then stopped during that first phase with **Xrun (code 5)**,
exiting 1 after 3.573 seconds. The required remaining phases and normal stop event
are missing, so the fixed protocol fails. The source writer and independent
recorder exited 0 within their original deadlines and retained their complete
60-second and 32-second observations. Both independent callback clocks remained
continuous. This is not a successful runtime gain/mute/restore qualification.

The terminal native capture record retains packet 276 as Published, no first
packet-validation fault, no contention, and explicit OwnerCompleted. Native stop,
destroy and listener removal all returned status 0; shutdown was observed. This
does not identify the Xrun origin: code 5 can originate from the native input's
callback reentry guard, its processor-overload listener, or the CPAL output's
processor-overload listener. Those paths do not record distinct first-fault
origins/ticks. Capture FIFO underflow/overflow are separate codes 11/12.

The last-good/first-bad telemetry bracket is 70.010 ms. Around that failure:

| Observer | Entry relative to its native timestamp | Work inside recorded callback |
| --- | ---: | ---: |
| Native input packet 276 | +22.916 ms | 23.708 µs |
| Independent Cable 2 reader, 0.571 ms later | +21.070 ms | 2.208 µs |
| Independent source writer, 2.006 ms later | −4.411 ms (future output lead) | 22.375 µs |

Nearby ordinary input entries are about +10.7 ms; ordinary source output entries
have about 10.6 ms future lead. The coincident late entries across processes
support a scheduling-disturbance hypothesis. They do not establish its cause,
prove an output-render overrun, or rule out native input reentry. No output
callback duration journal exists. A missing overload notification in another
process is not proof that the runtime received none.

Final counters were 141,312 captured and 137,728 rendered, with the last published
buffer occupancy 778 and correction −1,294.9 ppm. Occupancy is from the previous
successful prepare, not necessarily the fault instant; frame subtraction cannot
reconstruct queue occupancy because priming, ASRC phase and history differ.

## Separate basic HAL result

The source writer skipped **764 sample frames** after callback 2357. That callback
entered 5.064 ms after its future output timestamp but performed only 7.750 µs
of recorded work. A processor-overload notification arrived 99.083 µs after entry.
The next callback's sample/host clocks advanced together at 48 kHz. The failure
occurred 4.67–4.89 seconds after both reader processes had stopped.

Both readers' full clocks and fixed tone interiors passed, they matched exactly
across 757,196 common frames, and restart capture was silent. Those narrower
passes do not satisfy the whole protocol because the writer's full clock failed.
Apple documents [processor overload](https://developer.apple.com/documentation/coreaudio/kaudiodeviceprocessoroverload)
as notification of an IO cycle passing its deadline; it does not by itself state
which processing, scheduling or host condition caused that deadline miss.

## Custody and reproducibility

| Original asset | Bytes | SHA-256 |
| --- | ---: | --- |
| original-runtime.zip | 1,318,980 | `305f7fb58d47ed58a0463f34a5d260e649c56545255663df12400ec11a18b6a3` |
| original-hal.zip | 10,535,374 | `5561b48ae602bd1a2da04982882660edff15760cdcaaa054a520e89b0590486d` |

The archive digests match GitHub artifact metadata. All 56 runtime and 65 HAL
manifest files match their original byte counts and SHA-256; each archive also
contains its manifest. Original artifact IDs are 12541960470 and 12541612201.
`publication.json` records the public release assets and re-download verification.

Published at the [failed-run evidence prerelease](https://github.com/thatsmethen/ravelink/releases/tag/evidence-native-runtime-40046411757),
whose tag resolves to the exact source above. Anonymous re-downloads of
[original-runtime.zip](https://github.com/thatsmethen/ravelink/releases/download/evidence-native-runtime-40046411757/original-runtime.zip)
and [original-hal.zip](https://github.com/thatsmethen/ravelink/releases/download/evidence-native-runtime-40046411757/original-hal.zip)
matched the original complete archive bytes and every member. The first metadata
retrieval timed out; `publication-fetch-attempt-1.json` retains that retrieval
failure. A subsequent read-only public API retrieval and asset verification
succeeded. No experiment was rerun.

Download both archives into one folder, then run:

```sh
python3 verify.py --archives /path/to/downloads
python3 diagnose_timing.py --archives /path/to/downloads
```

`derived-timing.json` is reproducible supplemental chronology. It does not rerun,
replace or repair the frozen acceptance reports. The precise first-fault source,
output callback timing, physical-device behavior, Windows behavior and production
reliability remain unqualified. Diagnostic instrumentation may itself perturb
scheduling; this observation cannot qualify uninstrumented timing performance.
