#!/usr/bin/env python3
"""Read-only, descriptive PCM diagnosis; does not replace acceptance analyzers.
Run: python3 audio-zero-packet-probe.py /path/to/installed-driver-artifact
Requires numpy and scipy; writes one JSON report to stdout.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from scipy.io import wavfile


def inspect(path):
    rate, data = wavfile.read(path)
    pair = data[:, :2]
    signal = np.max(np.abs(pair), axis=1) > 1e-7
    indices = np.flatnonzero(signal)
    assert len(indices), f'No signal: {path}'
    first, last = int(indices[0]), int(indices[-1]) + 1
    zeros = np.all(pair[first:last] == 0, axis=1)
    edges = np.diff(np.r_[False, zeros, False].astype(int))
    starts = np.flatnonzero(edges == 1) + first
    ends = np.flatnonzero(edges == -1) + first
    lengths = ends - starts
    selected = lengths >= 8
    starts, lengths = starts[selected], lengths[selected]
    return dict(
        file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        sampleRate=int(rate), frames=int(len(data)), channels=int(data.shape[1]),
        firstSignalFrame=first, lastSignalFrameExclusive=last,
        firstSignalSeconds=first/rate, lastSignalSecondsExclusive=last/rate,
        maximumAbsoluteSample=float(abs(data).max()),
        interiorExactZeroRunsAtLeast8Frames=int(len(starts)),
        interiorExactZeroFramesInThoseRuns=int(lengths.sum()),
        longestRunFrames=int(max(lengths, default=0)),
        commonRunLengths=collections.Counter(map(int, lengths)).most_common(12),
        commonStartFrameModulo512=collections.Counter(map(int, starts % 512)).most_common(12),
        firstThirtyRuns=[dict(startFrame=int(s), startSeconds=int(s)/rate, frames=int(n))
                         for s, n in zip(starts[:30], lengths[:30])],
    )


def main():
    directory = Path(sys.argv[1])
    results = [inspect(directory / name) for name in
               ['soak-a.wav', 'soak-b.wav', 'sound-check-output.wav']]
    print(json.dumps(dict(
        sourceCommit='f733a8c26124b1ace95b85624222f091516e93eb', ciRun=40022691623,
        evidence='Descriptive offline analysis of untouched installed-run PCM; no resampling, alignment, gain fit, or threshold changes.',
        method='First stereo pair only. Active bounds use absolute value >1e-7; within those bounds report exact stereo zeros lasting at least8 frames, excluding isolated natural zero crossings. No pass/fail criterion is introduced.',
        observed=results,
        interpretation=[
            'Sound Check playback has recurring whole512-frame silent packets. Its selected source was a tone recorded to the dry clip, so its playback path does not read a capture FIFO/SRC.',
            'Soak recurrent449-frame gaps are consistent with512-frame silent input packets shortened by63 samples of64-tap sinc support; this identifies a candidate mechanism, not a driver trace.',
            'Continuous HAL timestamp reports and uninterrupted engine frame counters do not imply continuous nonzero audio.',
            'Driver read/write/generation tracing or a controlled reproduction is required before attributing the holes to a particular validity predicate or changing source.'
        ],
        limitations=[
            'This only describes the retained first stereo pairs and does not replace the strict eight-bus or Sound Check acceptance analyses.',
            'No loopback WAV was retained because its existing failure trap terminated the receiver after Swift assertions failed.',
            'No hardware IO, privacy grant, driver installation, default-device change, or audio-service restart is performed by this probe.'
        ]), indent=2))

if __name__ == '__main__': main()
