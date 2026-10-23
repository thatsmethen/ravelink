#!/usr/bin/env python3
"""Run the independent eight-channel HAL soak instrument with bounded cleanup."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys
import tempfile

SPEC = importlib.util.spec_from_file_location('managed_probe', Path(__file__).with_name('audio-device-probe.py'))
managed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(managed)


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--timeout', type=float, default=110)
    options, arguments = parser.parse_known_args()
    if not 1 <= options.timeout <= 120:
        parser.error('--timeout must be between 1 and 120 seconds')
    signal.signal(signal.SIGTERM, managed.interrupt)
    signal.signal(signal.SIGINT, managed.interrupt)
    try:
        with tempfile.TemporaryDirectory(prefix='ravelink-soak-probe-') as directory:
            executable = str(Path(directory) / 'probe')
            code, stdout, stderr = managed.run_managed(
                ['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra',
                 str(Path(__file__).with_suffix('.c')), '-framework', 'CoreAudio',
                 '-framework', 'CoreFoundation', '-o', executable], 30)
            if code == 0:
                code, stdout, stderr = managed.run_managed([executable, *arguments], options.timeout)
            print(stdout, end=''); print(stderr, file=sys.stderr, end='')
            return code
    except managed.Interrupted as error:
        print(f'soak-probe-interrupted signal={error.signum}; child process group terminated and reaped', file=sys.stderr)
        return 128 + error.signum


if __name__ == '__main__':
    raise SystemExit(main())
