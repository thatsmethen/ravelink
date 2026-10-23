#!/usr/bin/env python3
"""Verify independent installed-HAL AU PCM; no gain fit, alignment, or repair."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location('ravelink_matrix_verifier', Path(__file__).with_name('verify-matrix.py'))
wave = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wave)
PHASES = [
    ('active-plus6dB', 10 ** (6.0206 / 20)),
    ('live-minus6dB', 10 ** (-6.0206 / 20)),
    ('host-bypass', 1),
    ('restored-plus12dB', 10 ** (12 / 20)),
    ('final-mute', 0),
]


def analyze(path):
    rate, samples = wave.load(path)
    measured = wave.windows(rate, samples)
    labels = []
    for window in measured:
        found = [name for name, gain in PHASES if wave.matches(window, (gain, gain))]
        labels.append(found[0] if len(found) == 1 else 'transition')
    position = 0
    while position < len(labels) and labels[position] == 'final-mute':
        position += 1
    result = []
    for phase, gain in PHASES:
        transition = 0
        restart_silence = 0
        while position < len(labels) and labels[position] != phase:
            label = labels[position]
            if label == 'transition':
                transition += 1
            elif phase == 'restored-plus12dB' and label == 'final-mute':
                restart_silence += 1
            else:
                raise ValueError(f'Unexpected {label} while awaiting {phase}')
            if transition > 4 or restart_silence > 60:
                raise ValueError(f'Excessive transition/dropout before {phase}')
            position += 1
        start = position
        while position < len(labels) and labels[position] == phase:
            position += 1
        if position - start < 25:
            raise ValueError(f'Missing sustained {phase}: {position-start} settled 50ms windows')
        checked = measured[start:position]
        result.append(dict(name=phase, expectedPeak=wave.TONE * gain, startSeconds=start * .05,
                           settledSeconds=(position-start)*.05, precedingTransitionWindows=transition,
                           precedingRestartSilenceSeconds=restart_silence*.05,
                           maximumPeak=max(c['channels'][0][0] for c in checked),
                           minimumRMS=min(c['channels'][0][1] for c in checked)))
    if position != len(labels):
        raise ValueError('Audio returned after the final muted phase')
    if max(abs(sample) for sample in samples) > wave.TONE * PHASES[3][1] * 1.03:
        raise ValueError('Unexpected overshoot or foreign audio')
    return dict(sampleRate=rate, frames=len(samples)//2, phases=result,
                evidence='Independent recorded PCM; fixed expected gain/RMS/440Hz/stereo correlation, ordered continuous phases, no alignment/resampling/gain fitting. Latency is not measured by this amplitude sequence.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav')
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.wav), indent=2))
    except (OSError, ValueError) as error:
        print(f'AU loopback verification failed: {error}', file=sys.stderr)
        raise SystemExit(1)
