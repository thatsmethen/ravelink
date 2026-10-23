#!/usr/bin/env python3
"""Analyze all eight independently recorded stereo outputs of the device soak.

Fixed-frequency projections measure absolute component levels; no gain fitting,
waveform alignment or resampling is performed. Host timestamps describe HAL
sample presentation, not acoustic round-trip latency.
"""
import argparse
import array
import json
import math
from pathlib import Path
import struct
import sys

FREQUENCIES = (400, 1000)


def load(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(256 * 1024 * 1024 + 1)
    if len(raw) > 256 * 1024 * 1024: raise ValueError('WAV exceeds 256 MiB instrument limit')
    if len(raw) < 12 or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE' or struct.unpack_from('<I', raw, 4)[0] + 8 != len(raw):
        raise ValueError('Invalid RIFF/WAVE length or header')
    offset = 12; chunks = {}
    while offset + 8 <= len(raw):
        name, length = struct.unpack_from('<4sI', raw, offset); offset += 8
        if length > len(raw) - offset or name in chunks: raise ValueError('Malformed or duplicate WAV chunk')
        chunks[name] = raw[offset:offset + length]; offset += length + length % 2
    if offset != len(raw) or len(chunks.get(b'fmt ', b'')) < 16: raise ValueError('Truncated WAV')
    encoding, channels, rate, byte_rate, align, bits = struct.unpack_from('<HHIIHH', chunks[b'fmt '])
    if not 8000 <= rate <= 96000 or (encoding, channels, byte_rate, align, bits) != (3, 8, rate * 32, 32, 32):
        raise ValueError('Expected eight-channel Float32 PCM at 8–96 kHz')
    data = chunks.get(b'data', b'')
    if not data or len(data) % 32: raise ValueError('Incomplete eight-channel PCM frames')
    samples = array.array('f'); samples.frombytes(data)
    if sys.byteorder != 'little': samples.byteswap()
    if any(not math.isfinite(x) for x in samples): raise ValueError('Non-finite PCM')
    return rate, samples


def inspect_pair(rate, samples, pair, bus_index, minimum_seconds=29):
    frames = round(rate * .05)
    basis = [(tuple(math.cos(2 * math.pi * f * n / rate) for n in range(frames)),
              tuple(math.sin(2 * math.pi * f * n / rate) for n in range(frames))) for f in FREQUENCIES]
    target = .01 * 10 ** (-3 * bus_index / 20)
    # The last partial block is inspected too; it may only be settled silence.
    windows = []
    first_sample = None
    for at in range(0, len(samples), frames * 8):
        left = samples[at + pair * 2:at + frames * 8:8]
        right = samples[at + pair * 2 + 1:at + frames * 8:8]
        peak = max(max(abs(x) for x in left), max(abs(x) for x in right))
        if first_sample is None:
            first_sample = next((at // 8 + i for i, (a, b) in enumerate(zip(left, right)) if max(abs(a), abs(b)) > target * .001), None)
        quiet = peak < 1e-6
        coefficients = [(2 * sum(x * c for x, c in zip(left, cosine)) / len(left),
                         2 * sum(x * s for x, s in zip(left, sine)) / len(left)) for cosine, sine in basis]
        amplitudes = [math.hypot(c, s) for c, s in coefficients]
        energy = sum(x * x for x in left) / len(left)
        residual = max(0, energy - sum(a * a for a in amplitudes) / 2)
        stereo_error = max(abs(a - b) for a, b in zip(left, right))
        jump = max((abs(b - a) for a, b in zip(left, left[1:])), default=0)
        good = (len(left) == frames and all(abs(a - target) <= target * .03 for a in amplitudes)
                and abs(math.sqrt(energy) - target) <= target * .03 and residual <= target * target * .01
                and stereo_error <= target * .001 and abs(sum(left) / len(left)) <= target * .002
                and jump <= target * min(4, 1.5 * 2 * math.pi * sum(FREQUENCIES) / rate))
        windows.append(dict(quiet=quiet, good=good, frames=len(left), amplitudes=amplitudes,
                            phase=[math.atan2(-s, c) for c, s in coefficients], residual=residual,
                            stereoError=stereo_error))
    cursor = 0
    while cursor < len(windows) and windows[cursor]['quiet']: cursor += 1
    transition = 0
    while cursor < len(windows) and not windows[cursor]['good']:
        cursor += 1; transition += 1
        if transition > 4: raise ValueError(f'Bus {bus_index}: invalid onset or missing tone')
    first = cursor
    while cursor < len(windows) and windows[cursor]['good']: cursor += 1
    duration = sum(w['frames'] for w in windows[first:cursor]) / rate
    if duration < minimum_seconds: raise ValueError(f'Bus {bus_index}: only {duration:.3f}s of uninterrupted valid input routing')
    settled = windows[first:cursor]
    transition = 0
    while cursor < len(windows) and not windows[cursor]['quiet']:
        cursor += 1; transition += 1
        if transition > 4: raise ValueError(f'Bus {bus_index}: invalid signal before final silence')
    tail = windows[cursor:]
    if not tail or any(not w['quiet'] for w in tail) or sum(w['frames'] for w in tail) / rate < .8:
        raise ValueError(f'Bus {bus_index}: missing final mute or signal returned afterward')
    frequency = []
    for component, nominal in enumerate(FREQUENCIES):
        changes = [math.remainder(b['phase'][component] - a['phase'][component] - 2 * math.pi * nominal * frames / rate, 2 * math.pi)
                   for a, b in zip(settled, settled[1:])]
        deviations = [change / (2 * math.pi * frames / rate) for change in changes]
        if not deviations or max(abs(v) for v in deviations) > 2:
            raise ValueError(f'Bus {bus_index}: tone phase continuity exceeds 2 Hz window-to-window envelope')
        mean = sum(deviations) / len(deviations)
        frequency.append(dict(nominalHz=nominal, averageHz=nominal + mean,
                              measuredAveragePPM=mean / nominal * 1e6, maxWindowDeviationHz=max(abs(v) for v in deviations)))
    return dict(bus=bus_index, stereoPair=pair, firstSignalFrame=first_sample,
                settledStartSeconds=first * .05, settledSeconds=duration, expectedComponentAmplitude=target,
                minComponentAmplitude=[min(w['amplitudes'][c] for w in settled) for c in (0, 1)],
                maxComponentAmplitude=[max(w['amplitudes'][c] for w in settled) for c in (0, 1)],
                maxStereoError=max(w['stereoError'] for w in settled), componentClock=frequency)


def checked_report(path, mode):
    data = json.loads(Path(path).read_text())
    if data.get('mode') != mode or data.get('complete') is not True or data.get('channels') != 8:
        raise ValueError(f'{path}: incomplete or incorrect instrument report')
    if data.get('timestampDiscontinuities') != 0 or data.get('invalidTimestamps') != 0:
        raise ValueError(f'{path}: HAL timestamps were invalid or discontinuous')
    if not 8000 <= data['sampleRate'] <= 96000 or data['firstFrameHostSeconds'] <= 0:
        raise ValueError(f'{path}: invalid rate or host clock')
    return data


def analyze(directory):
    directory = Path(directory)
    feeder = checked_report(directory / 'soak-feeder.json', 'feed')
    engine = json.loads((directory / 'soak-engine.json').read_text())
    for name, expected in [('visibleInputGroups', 12), ('captureSources', 24), ('mixBuses', 8), ('physicalOutputs', 2),
                           ('parentRoutes', 96), ('expandedRoutes', 192), ('droppedFrames', 0), ('underrunFrames', 0), ('oversizedBlocks', 0)]:
        if engine.get(name) != expected: raise ValueError(f'Unexpected measured engine {name}')
    if not 30 <= engine['measuredSeconds'] < 35 or feeder['frames'] / feeder['sampleRate'] < 34:
        raise ValueError('Incomplete sustained run or feeder ended before final mute')
    outputs = []
    for name, first_bus in [('a', 0), ('b', 4)]:
        report = checked_report(directory / f'soak-{name}.json', 'record')
        rate, samples = load(directory / f'soak-{name}.wav')
        if report['sampleRate'] != rate or report['frames'] != len(samples) // 8:
            raise ValueError('Recorder metadata disagrees with PCM')
        pairs = [inspect_pair(rate, samples, pair, first_bus + pair) for pair in range(4)]
        for pair in pairs:
            onset = report['firstFrameHostSeconds'] + pair['firstSignalFrame'] / rate
            interval = onset - feeder['firstSignalHostSeconds']
            if not -.01 <= interval <= 1: raise ValueError('HAL onset timestamps disagree by more than the instrument envelope')
            pair['halOnsetIntervalMilliseconds'] = interval * 1000
        outputs.append(dict(device=name, sampleRate=rate, recorder=report, pairs=pairs))
    return dict(evidence='Measured named-device envelope only; independent raw PCM and HAL timestamps; no resampling, waveform alignment or gain fitting',
                limitation='HAL onset intervals are timestamp-based device presentation intervals, not acoustic round-trip latency. A 30-second run does not establish indefinite stability.',
                engine=engine, feeder=feeder, outputs=outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.directory), indent=2, allow_nan=False)); return 0
    except (ValueError, OSError, KeyError, TypeError, struct.error) as error:
        print(f'Device soak verification failed: {error}', file=sys.stderr); return 1


if __name__ == '__main__': raise SystemExit(main())
