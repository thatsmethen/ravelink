#!/usr/bin/env python3
"""Verify independently captured loopback phases; never align, resample or gain-fit."""
import argparse
import array
import json
import math
from pathlib import Path
import struct
import sys


MAX_CAPTURE_BYTES = 256 * 1024 * 1024


def verify(path):
    with Path(path).open('rb') as file:
        payload = file.read(MAX_CAPTURE_BYTES + 1)
    if len(payload) > MAX_CAPTURE_BYTES:
        raise ValueError(f'Capture exceeds the {MAX_CAPTURE_BYTES}-byte analysis limit')
    if len(payload) < 12 or payload[:4] != b'RIFF' or payload[8:12] != b'WAVE':
        raise ValueError('Expected a RIFF/WAVE capture')
    if struct.unpack_from('<I', payload, 4)[0] + 8 != len(payload):
        raise ValueError('RIFF length does not match file')
    chunks = {}; offset = 12
    while offset + 8 <= len(payload):
        name, size = struct.unpack_from('<4sI', payload, offset); offset += 8
        if size > len(payload) - offset or name in chunks: raise ValueError('Malformed or duplicate WAV chunk')
        chunks[name] = payload[offset:offset+size]; offset += size + size % 2
    if offset != len(payload) or len(chunks.get(b'fmt ', b'')) < 16: raise ValueError('Incomplete WAV')
    encoding, channels, rate, byte_rate, align, bits = struct.unpack_from('<HHIIHH', chunks[b'fmt '])
    if (encoding, channels, bits, align, byte_rate) != (3, 2, 32, 8, rate*8): raise ValueError('Expected stereo Float32 PCM')
    data = chunks.get(b'data', b'')
    if not data or len(data) % 8: raise ValueError('Incomplete stereo samples')
    samples = array.array('f'); samples.frombytes(data)
    if sys.byteorder != 'little': samples.byteswap()
    if any(not math.isfinite(v) for v in samples): raise ValueError('Non-finite audio')
    frames = len(samples)//2
    if rate < 8000 or frames < rate*4: raise ValueError('Capture too short or invalid sample rate')
    window = round(rate * .05)
    unity = .12589254; attenuated = unity * 10**(-12/20)
    counts = dict(unity=0, minus12dB=0, silenceAfterSignal=0)
    seen_signal = False
    peaks = []; phases = []
    for start in range(0, frames-window+1, window):
        block = samples[start*2:(start+window)*2]
        peak = max(abs(x) for x in block); peaks.append(peak)
        if abs(peak-unity) < .003:
            phase = 'unity'; counts['unity'] += 1; seen_signal = True
        elif abs(peak-attenuated) < .001:
            phase = 'minus12dB'; counts['minus12dB'] += 1
        elif peak < 1e-5:
            phase = 'silence'
            if seen_signal: counts['silenceAfterSignal'] += 1
        else:
            phase = 'transition'
        phases.append(phase)

    def settled_run(label, minimum, after):
        run_start = None
        for index in range(after, len(phases) + 1):
            if index < len(phases) and phases[index] == label:
                if run_start is None: run_start = index
            else:
                if run_start is not None and index-run_start >= minimum:
                    return run_start, index
                run_start = None
        raise ValueError(f'Missing sustained ordered {label} phase ({minimum} windows): {counts}')

    unity_start, unity_end = settled_run('unity', 10, 0)
    attenuated_start, attenuated_end = settled_run('minus12dB', 6, unity_end)
    muted_start, muted_end = settled_run('silence', 6, attenuated_end)
    # Permit at most two 50 ms transition windows at each gain change. A phase
    # cannot be assembled from scattered windows or silence/dropouts mid-signal.
    if any(phase == 'minus12dB' for phase in phases[:unity_start]):
        raise ValueError('Attenuated phase occurred before unity')
    for first, last, expected in [(unity_start, attenuated_start, 'unity'),
                                  (attenuated_start, muted_start, 'minus12dB')]:
        segment = phases[first:last]
        if any(phase not in (expected, 'transition') for phase in segment) or segment.count('transition') > 2:
            raise ValueError(f'Discontinuous or out-of-order {expected} phase')
    if any(phase != 'silence' for phase in phases[muted_start:]):
        raise ValueError('Signal returned after the settled muted phase')
    if max(peaks) > unity + .003: raise ValueError(f'Unexpected signal gain or foreign audio: {max(peaks)}')
    channel_error = max(abs(samples[i]-samples[i+1]) for i in range(0,len(samples),2))
    if channel_error > 1e-5: raise ValueError('Stereo calibration channels differ')
    def measure_frequency(first, last):
        # Drop the first window to avoid the gain-change transient. No phase
        # alignment, resampling, fitting, or audio repair is performed.
        left = samples[(first+1)*window*2:last*window*2:2]
        crossings = [i for i in range(1,len(left)) if left[i-1] <= 0 < left[i]]
        if len(crossings) < 4: raise ValueError('No stable tone crossings')
        frequency = (len(crossings)-1)*rate/(crossings[-1]-crossings[0])
        if abs(frequency-440) > 1: raise ValueError(f'Unexpected tone frequency: {frequency}')
        return frequency
    frequency = measure_frequency(unity_start, unity_end)
    attenuated_frequency = measure_frequency(attenuated_start, attenuated_end)
    return dict(sampleRate=rate, frames=frames, seconds=frames/rate, peak=max(peaks), frequencyHz=frequency,
                stereoDifference=channel_error, phaseWindows=counts, windowSeconds=.05,
                phaseFrequenciesHz=dict(unity=frequency, minus12dB=attenuated_frequency),
                orderedPhaseStartsSeconds=dict(unity=unity_start*.05, minus12dB=attenuated_start*.05, muted=muted_start*.05),
                evidence='signal analysis only; caller supplies capture provenance; no alignment, resampling or gain fitting')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('wav'); args = parser.parse_args()
    try: print(json.dumps(verify(args.wav), indent=2))
    except (ValueError, OSError, struct.error) as error:
        print(f'Loopback verification failed: {error}', file=sys.stderr); raise SystemExit(1)
