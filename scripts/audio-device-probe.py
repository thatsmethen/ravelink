#!/usr/bin/env python3
"""Compile and run the independent CoreAudio probe with bounded child cleanup."""
import argparse
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile


class Interrupted(Exception):
    def __init__(self, signum):
        self.signum = signum


def interrupt(signum, _frame):
    raise Interrupted(signum)


def terminate_group(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            return process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return process.communicate(timeout=2)


def run_managed(arguments, timeout):
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        stdout, stderr = terminate_group(process)
        return 124, stdout, stderr + f'probe-timeout seconds={timeout:g}\n'
    except Interrupted:
        # Ignore a second cancellation while bounded termination/reaping runs.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        terminate_group(process)
        raise
    finally:
        if process.poll() is None:
            terminate_group(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--timeout', type=float, default=15)
    options, arguments = parser.parse_known_args()
    if not 1 <= options.timeout <= 120:
        parser.error('--timeout must be between 1 and 120 seconds')
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        with tempfile.TemporaryDirectory(prefix='ravelink-audio-probe-') as directory:
            executable = str(Path(directory) / 'probe')
            code, stdout, stderr = run_managed(
                ['xcrun', 'clang', '-std=c11', '-O2', str(Path(__file__).with_suffix('.c')),
                 '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-o', executable], 30)
            if code == 0:
                code, stdout, stderr = run_managed([executable, *arguments], options.timeout)
            print(stdout, end='')
            print(stderr, file=sys.stderr, end='')
            return code
    except Interrupted as error:
        print(f'probe-interrupted signal={error.signum}; child process group terminated and reaped', file=sys.stderr)
        return 128 + error.signum


if __name__ == '__main__':
    raise SystemExit(main())
