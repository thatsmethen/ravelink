#!/usr/bin/env python3
"""Inspect independent Sound Check PCM without alignment, resampling or gain fitting."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

SPEC = importlib.util.spec_from_file_location('matrix_pcm', Path(__file__).with_name('verify-matrix.py'))
pcm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pcm)
TONE = 10 ** (-18 / 20)
ATTENUATION = 10 ** (-12 / 20)


def inspect(path, clip_seconds):
    rate, samples = pcm.load(path)
    frames = len(samples) // 2
    if not .6 <= clip_seconds <= 2:
        raise ValueError('Unexpected dry clip duration')
    if max(abs(a - b) for a, b in zip(samples[::2], samples[1::2])) > 1e-5:
        raise ValueError('Stereo clip channels differ')
    if max(abs(v) for v in samples) > TONE * 1.025:
        raise ValueError('Unexpected gain or foreign signal')
    size = round(rate * .05)
    measured = []
    for start in range(0, frames, size):
        values = samples[start * 2:min(start + size, frames) * 2:2]
        peak = max(abs(v) for v in values)
        rms = math.sqrt(sum(v * v for v in values) / len(values))
        label = 'silence' if peak < 1e-5 else 'transition'
        for name, gain in [('unity', 1), ('minus12dB', ATTENUATION)]:
            target = TONE * gain
            # The product fades the last/first5ms of every loop to avoid a hard
            # seam. This fixed RMS envelope accommodates that brief attenuation.
            if len(values) == size and abs(peak - target) <= target * .025 and .58 * target <= rms <= .725 * target:
                label = name
        measured.append(dict(label=label, frames=len(values), peak=peak, rms=rms))
    cursor = 0
    while cursor < len(measured) and measured[cursor]['label'] == 'silence':
        cursor += 1
    if cursor * .05 < 1.5:
        raise ValueError('Missing silent recording and ready interval')
    phases = []
    for label, gain in [('unity', 1), ('minus12dB', ATTENUATION), ('silence', 0)]:
        transition = 0
        while cursor < len(measured) and measured[cursor]['label'] != label:
            if measured[cursor]['label'] != 'transition':
                raise ValueError(f'Unexpected {measured[cursor]["label"]} before {label}')
            transition += 1; cursor += 1
            if transition > 3:
                raise ValueError(f'Missing ordered {label} phase')
        first = cursor
        while cursor < len(measured) and measured[cursor]['label'] == label:
            cursor += 1
        duration = sum(w['frames'] for w in measured[first:cursor]) / rate
        minimum = max(2.7, clip_seconds * 2) if gain else .8
        if duration < minimum or (gain and duration > 4.0):
            raise ValueError(f'Unexpected {label} duration: {duration:.3f}s')
        result = dict(phase=label, startSeconds=first * .05, seconds=duration)
        if gain:
            values = samples[first * size * 2:min(cursor * size, frames) * 2:2]
            crossings = [i - 1 - values[i - 1] / (values[i] - values[i - 1])
                         for i in range(1, len(values)) if values[i - 1] <= 0 < values[i]]
            periods = [b - a for a, b in zip(crossings, crossings[1:])]
            if not periods:
                raise ValueError('Missing tone crossings')
            frequency = rate / statistics.median(periods)
            outliers = sum(abs(rate / p - 440) > 3 for p in periods) / len(periods)
            if abs(frequency - 440) > 1 or outliers > .02:
                raise ValueError('Unexpected playback tone or excessive phase discontinuities')
            target = TONE * gain
            maximum_jump = max(abs(b - a) for a, b in zip(values, values[1:]))
            # A sine derivative plus the documented5ms edge envelope, with a
            # fixed numerical margin. No measured gain or phase is fitted.
            jump_limit = target * (2 * math.pi * 440 / rate + 1 / (rate * .005)) * 1.25
            if maximum_jump > jump_limit:
                raise ValueError('Playback has a hard loop discontinuity')
            result.update(frequencyHz=frequency, crossingOutlierFraction=outliers,
                          maximumAdjacentSampleJump=maximum_jump, jumpLimit=jump_limit,
                          minimumPeak=min(w['peak'] for w in measured[first:cursor]),
                          maximumPeak=max(w['peak'] for w in measured[first:cursor]))
        phases.append(result)
    if cursor != len(measured):
        raise ValueError('Signal returned after stop or clear')
    return dict(sampleRate=rate, seconds=frames / rate, phases=phases)


def analyze(directory):
    directory = Path(directory)
    engine = json.loads((directory / 'sound-check-engine.json').read_text())
    if engine.get('completed') is not True or engine.get('helperReaped') is not True:
        raise ValueError('Sound Check engine sequence did not complete and reap its helper')
    if engine.get('initialGainDB') != -12 or engine.get('finalMode') != 'empty' or engine.get('finalFrames') != 0:
        raise ValueError('Incorrect dry-recording or final-state contract')
    if engine.get('visibleInputGroups') != 1 or engine.get('mixBuses') != 1:
        raise ValueError('Sound Check was not an isolated one-destination audition')
    output = inspect(directory / 'sound-check-output.wav', engine['recordedFrames'] / engine['sampleRate'])
    rate, guard = pcm.load(directory / 'sound-check-guard.wav')
    peak = max(abs(v) for v in guard)
    if peak >= 1e-5:
        raise ValueError('Sound Check leaked into the separate guard output')
    return dict(evidence='Independent installed-HAL Sound Check PCM; absolute expected levels; no waveform alignment, resampling or gain fitting',
                limitation='The guard observes one named stereo pair, not every possible system endpoint. Generated tone input does not establish microphone permissions or hardware recording compatibility.',
                engine=engine, output=output, guard=dict(sampleRate=rate, seconds=len(guard) / 2 / rate, peak=peak))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.directory), indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'Sound Check verification failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
