#!/usr/bin/env python3
"""Analyze two independently recorded outputs of InstalledMatrixTests.

No resampling, waveform alignment or gain fitting. Every settled 50 ms window
must have the expected peak, RMS and tone frequency in both channels. Adjacent
phases with the same expected signal are combined before inspecting the capture.
"""
import argparse
import array
import json
import math
from pathlib import Path
import struct
import sys

TONE = 10 ** (-18 / 20)
QUARTER = 10 ** (-12 / 20)
HALF = 10 ** (-6.0206 / 20)
PHASES = [
    ('baseline', (1, 1), (HALF, HALF)),
    ('route-level-A', (QUARTER, QUARTER), (HALF, HALF)),
    ('route-pan-A-left', (QUARTER, 0), (HALF, HALF)),
    ('route-mute-A', (0, 0), (HALF, HALF)),
    ('master-mute-B', (0, 0), (0, 0)),
    ('restored-baseline', (1, 1), (HALF, HALF)),
    ('source-mute', (0, 0), (0, 0)),
    ('secondary-solo', (0, 0), (QUARTER, QUARTER)),
    ('summed-sources', (1, 1), (HALF + QUARTER, HALF + QUARTER)),
    ('source-gain', (HALF, HALF), (HALF * HALF + QUARTER, HALF * HALF + QUARTER)),
    ('master-level-B', (HALF, HALF), ((HALF * HALF + QUARTER) * QUARTER,) * 2),
    ('final-mute', (0, 0), (0, 0)),
]


def load(path):
    limit = 64 * 1024 * 1024
    with Path(path).open('rb') as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise ValueError('Capture exceeds 64 MiB analysis limit')
    if len(payload) < 12 or payload[:4] != b'RIFF' or payload[8:12] != b'WAVE':
        raise ValueError('Expected RIFF/WAVE')
    if struct.unpack_from('<I', payload, 4)[0] + 8 != len(payload):
        raise ValueError('Incorrect RIFF length')
    chunks = {}; offset = 12
    while offset + 8 <= len(payload):
        name, size = struct.unpack_from('<4sI', payload, offset); offset += 8
        if size > len(payload) - offset or name in chunks:
            raise ValueError('Malformed WAV chunk')
        chunks[name] = payload[offset:offset + size]; offset += size + size % 2
    if offset != len(payload) or len(chunks.get(b'fmt ', b'')) < 16:
        raise ValueError('Incomplete WAV')
    encoding, channels, rate, byte_rate, align, bits = struct.unpack_from('<HHIIHH', chunks[b'fmt '])
    if not 8000 <= rate <= 192000 or (encoding, channels, byte_rate, align, bits) != (3, 2, rate * 8, 8, 32):
        raise ValueError('Expected stereo Float32 PCM at a supported rate')
    data = chunks.get(b'data', b'')
    if not data or len(data) % 8:
        raise ValueError('Incomplete stereo samples')
    samples = array.array('f'); samples.frombytes(data)
    if sys.byteorder != 'little': samples.byteswap()
    if any(not math.isfinite(sample) for sample in samples):
        raise ValueError('Non-finite audio')
    if len(samples) < rate * 2 * 16:
        raise ValueError('Capture shorter than the control sequence')
    return rate, samples


def windows(rate, samples):
    frames = round(rate * .05)
    result = []
    for offset in range(0, len(samples), frames * 2):
        channels = []
        stereo = []
        for channel in (0, 1):
            values = samples[offset + channel:offset + frames * 2:2]
            stereo.append(values)
            peak = max(abs(v) for v in values)
            rms = math.sqrt(sum(v * v for v in values) / len(values))
            crossings = [i for i in range(1, len(values)) if values[i - 1] <= 0 < values[i]]
            frequency = (len(crossings) - 1) * rate / (crossings[-1] - crossings[0]) if len(crossings) >= 4 else None
            channels.append((peak, rms, frequency))
        energy = [sum(v * v for v in values) for values in stereo]
        correlation = (sum(a * b for a, b in zip(*stereo)) / math.sqrt(energy[0] * energy[1])) if all(energy) else None
        result.append(dict(channels=channels, correlation=correlation, frames=len(stereo[0])))
    return result


def matches(window, expected):
    for (peak, rms, frequency), coefficient in zip(window['channels'], expected):
        target = TONE * coefficient
        if coefficient == 0:
            if peak >= 1e-5: return False
        elif (abs(peak - target) > max(.0003, target * .02)
              or abs(rms - target / math.sqrt(2)) > max(.0002, target * .02)
              or frequency is None or abs(frequency - 440) > 1):
            return False
    if all(expected) and (window['correlation'] is None or window['correlation'] < .999):
        return False
    return True


def analyze(path, output):
    rate, samples = load(path)
    measured = windows(rate, samples)
    groups = []
    for name, a, b in PHASES:
        expected = a if output == 'A' else b
        if groups and groups[-1]['expected'] == expected:
            groups[-1]['names'].append(name)
        else:
            groups.append(dict(names=[name], expected=expected))
    cursor = 0
    while cursor < len(measured) and matches(measured[cursor], (0, 0)):
        cursor += 1
    results = []
    for group in groups:
        transition = 0
        while cursor < len(measured) and not matches(measured[cursor], group['expected']):
            cursor += 1; transition += 1
            if transition > 3:
                raise ValueError(f'{output}: unexpected signal or gap before {group["names"]}')
        first = cursor
        while cursor < len(measured) and matches(measured[cursor], group['expected']):
            cursor += 1
        duration = sum(w['frames'] for w in measured[first:cursor]) / rate
        if duration + 1e-9 < .8 * len(group['names']):
            raise ValueError(f'{output}: insufficient sustained signal for {group["names"]}: {duration:.2f}s')
        peaks = [[w['channels'][c][0] for w in measured[first:cursor]] for c in (0, 1)]
        results.append(dict(phases=group['names'], startSeconds=first * .05,
                            durationSeconds=duration,
                            expectedPeak=[TONE * v for v in group['expected']],
                            minPeak=[min(v) for v in peaks], maxPeak=[max(v) for v in peaks]))
    if cursor != len(measured):
        raise ValueError(f'{output}: audio returned after final mute')
    return dict(output=output, sampleRate=rate, frames=len(samples)//2, phases=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_a'); parser.add_argument('output_b'); args = parser.parse_args()
    try:
        print(json.dumps(dict(outputs=[analyze(args.output_a, 'A'), analyze(args.output_b, 'B')],
                              evidence='Independent signal analysis; caller supplies recorder provenance; no alignment, resampling or gain fitting'), indent=2))
    except (ValueError, OSError, struct.error) as error:
        print(f'Matrix verification failed: {error}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
