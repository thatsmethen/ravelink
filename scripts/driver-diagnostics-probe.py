#!/usr/bin/env python3
"""Compile/read the driver diagnostic property without opening audio IO."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys
import tempfile

source = Path(__file__).with_name('audio-device-probe.py')
spec = importlib.util.spec_from_file_location('managed_audio_probe', source)
managed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(managed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', action='append', required=True)
    parser.add_argument('--timeout', type=float, default=15)
    options = parser.parse_args()
    if not 1 <= options.timeout <= 120:
        parser.error('--timeout must be between 1 and 120 seconds')
    if len(options.uid) > 64:
        parser.error('at most 64 device UIDs may be read')
    signal.signal(signal.SIGTERM, managed.interrupt)
    signal.signal(signal.SIGINT, managed.interrupt)
    try:
        with tempfile.TemporaryDirectory(prefix='ravelink-driver-diagnostics-') as directory:
            executable = str(Path(directory) / 'probe')
            code, stdout, stderr = managed.run_managed(
                ['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra',
                 str(Path(__file__).with_suffix('.c')), '-framework', 'CoreAudio',
                 '-framework', 'CoreFoundation', '-o', executable], 30)
            if code == 0:
                arguments = [value for uid in options.uid for value in ['--uid', uid]]
                code, stdout, stderr = managed.run_managed([executable, *arguments], options.timeout)
            print(stdout, end=''); print(stderr, file=sys.stderr, end='')
            return code
    except managed.Interrupted as error:
        print(f'diagnostic-probe-interrupted signal={error.signum}; child group terminated and reaped', file=sys.stderr)
        return 128 + error.signum


if __name__ == '__main__':
    raise SystemExit(main())
