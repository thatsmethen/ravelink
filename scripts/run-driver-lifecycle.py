#!/usr/bin/env python3
"""Installer/receipt/HAL lifecycle acceptance, exclusively on disposable GitHub runners.

Never use on a workstation. Tests only ci-lifecycle-a/b; does not start audio IO.
Original command logs and state snapshots survive failed assertions.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'driver-lifecycle'
HAL = Path('/Library/Audio/Plug-Ins/HAL')
IDS = ('ci-lifecycle-a', 'ci-lifecycle-b')
DRIVER = ROOT / 'scripts' / 'virtual-devices.py'


def authorized(environment):
    return (environment.get('RAVELINK_TEST_DRIVER_LIFECYCLE') == '1'
            and environment.get('GITHUB_ACTIONS') == 'true'
            and environment.get('RUNNER_ENVIRONMENT') == 'github-hosted')


def tree_hash(path):
    """Content identity includes every relative name and byte, independent of owner/time."""
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f'Expected real bundle directory: {path}')
    digest = hashlib.sha256()
    for child in sorted(path.rglob('*')):
        if child.is_symlink(): raise ValueError(f'Unexpected symlink: {child}')
        if child.is_file():
            digest.update(str(child.relative_to(path)).encode() + b'\0')
            digest.update(hashlib.sha256(child.read_bytes()).digest())
    return digest.hexdigest()


class Acceptance:
    def __init__(self):
        self.events = []
        self.counter = 0
        self.owns_devices = False
        self.report_state = {}

    def save(self, **extra):
        self.report_state.update(extra)
        (OUT / 'report.json').write_text(json.dumps({'scope': 'Disposable runner only; Installer payload/receipt and HAL format lifecycle. No audio IO or universal upgrade atomicity claim.',
                                                   'revision': os.environ.get('GITHUB_SHA'), 'events': self.events, **self.report_state}, indent=2) + '\n')

    @staticmethod
    def terminate(process):
        if process.poll() is not None: return
        # sudo children may belong to root; cleanup targets only the new group.
        subprocess.run(['sudo', '-n', '/bin/kill', '-TERM', '--', f'-{process.pid}'], check=False, timeout=5)
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            subprocess.run(['sudo', '-n', '/bin/kill', '-KILL', '--', f'-{process.pid}'], check=False, timeout=5)
            process.wait(timeout=5)

    def command(self, label, args, success=True, timeout=120, expected_refusal=None, allowed_failures=None):
        self.counter += 1
        log = OUT / f'{self.counter:02d}-{label}.log'
        with log.open('wb') as stream:
            process = subprocess.Popen([str(x) for x in args], stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try: code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.terminate(process)
                code = 124
            except BaseException as error:
                self.terminate(process)
                self.events.append({'command': label, 'arguments': [str(x) for x in args], 'exitCode': process.returncode,
                                    'log': log.name, 'interrupted': str(error)})
                self.save(completed=False)
                raise
        output = log.read_text(errors='replace')
        self.events.append({'command': label, 'arguments': [str(x) for x in args], 'exitCode': code, 'log': log.name})
        self.save(completed=False)
        allowed = allowed_failures and code in allowed_failures and allowed_failures[code] in output
        if code == 124 or (not allowed and ((success and code != 0) or (not success and code == 0))):
            raise AssertionError(f'{label}: unexpected exit {code}; see {log}')
        if expected_refusal and expected_refusal not in output:
            raise AssertionError(f'{label}: expected policy refusal was not observed; see {log}')
        return output

    def receipt(self, slug):
        receipt_id = 'au.textual.ravelink.audio.package.' + slug
        available = subprocess.run(['/usr/sbin/pkgutil', '--pkgs-plist'], check=True, capture_output=True, timeout=10)
        ids = plistlib.loads(available.stdout)
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
            raise ValueError('Invalid receipt database enumeration')
        if receipt_id not in ids: return None
        result = subprocess.run(['/usr/sbin/pkgutil', '--pkg-info-plist', receipt_id],
                                check=True, capture_output=True, timeout=10)
        return {'data': plistlib.loads(result.stdout), 'sha256': hashlib.sha256(result.stdout).hexdigest()}

    def snapshot(self, label):
        state = {}
        for slug in IDS:
            bundle = HAL / f'RaveLink-{slug}.driver'
            state[slug] = {'payloadSHA256': tree_hash(bundle) if bundle.exists() else None, 'receipt': self.receipt(slug)}
        self.events.append({'snapshot': label, 'state': state});self.save(completed=False)
        return state

    def build(self, name, slug, channels, version, number):
        folder = OUT / name
        self.command('build-' + name, [sys.executable, DRIVER, 'build', '--device', slug + ':' + name,
                                     '--channels', channels, '--version', version, '--build-number', number, '--output', folder])
        return folder / f'RaveLink-{slug}.driver'

    def package(self, name, bundles):
        path = OUT / (name + '.pkg')
        self.command('package-' + name, [sys.executable, DRIVER, 'package', *bundles, '--output', path])
        return path

    def install(self, name, package, success=True, expected_refusal=None):
        # Installer -dumplog omits installd's preinstall stdout/stderr on macOS15.
        # Retain only this invocation's appended system log, never an old match.
        position = json.loads(self.command(name + '-log-position', ['sudo', '-n', sys.executable, '-c',
            'import os,json; s=os.stat("/var/log/install.log"); print(json.dumps([s.st_ino,s.st_size]))']))
        try:
            output = self.command(name, ['sudo', '-n', '/usr/sbin/installer', '-dumplog', '-verboseR', '-pkg', package, '-target', '/'], success=success)
        finally:
            system_log = self.command(name + '-system-log', ['sudo', '-n', sys.executable, '-c',
                'import os,sys,time; time.sleep(0.2); f=open("/var/log/install.log","rb"); s=os.fstat(f.fileno()); '
                'assert s.st_ino==int(sys.argv[1]) and s.st_size>=int(sys.argv[2]), "Installer log rotated; evidence unavailable"; '
                'f.seek(int(sys.argv[2])); data=f.read(8*1024*1024+1); assert len(data)<=8*1024*1024, "Installer log exceeds instrument limit"; '
                'sys.stdout.buffer.write(data)', *map(str, position)])
        if expected_refusal and expected_refusal not in output + system_log:
            raise AssertionError(f'{name}: expected policy refusal was not observed in this invocation')
        return output

    def assert_payload(self, slug, expected, build):
        bundle = HAL / f'RaveLink-{slug}.driver'
        assert tree_hash(bundle) == tree_hash(expected), f'{slug}: installed bytes differ from package source'
        receipt = self.receipt(slug)
        assert receipt and receipt['data']['pkg-version'] == str(build), f'{slug}: wrong receipt'
        self.command('validate-' + slug, [sys.executable, DRIVER, 'validate', bundle])

    def reload(self):
        self.command('reload-disposable-audio-service', ['sudo', '-n', '/usr/bin/killall', 'coreaudiod'],
                     allowed_failures={1: 'No matching processes were found'})
        time.sleep(3)

    def state(self, slug, channels=None, name=None, rate=None, set_rate=False):
        args = [OUT / 'driver-state-probe', 'RaveLink.' + slug + '_UID']
        if set_rate: args += [str(rate)]
        result = json.loads(self.command('inspect-' + slug, args, timeout=15))
        if channels is None:
            assert result == {'present': False}, f'{slug}: removed device still visible'
        else:
            assert result['present'] and result['inputChannels'] == channels and result['outputChannels'] == channels, result
            assert result['name'] == 'RaveLink ' + name, result
            if rate: assert result['sampleRate'] == rate, result
        self.events.append({'HAL': result});self.save(completed=False)
        return result

    def run(self):
        # Refuse any pre-existing payload/receipt; this test never adopts devices.
        for slug in IDS:
            path = HAL / f'RaveLink-{slug}.driver'
            if path.exists() or path.is_symlink() or self.receipt(slug):
                raise ValueError('Lifecycle fixtures already exist; refusing to modify them')
        self.owns_devices = True
        self.save(completed=False)
        (OUT / 'owned-fixtures.json').write_text(json.dumps({'ids': IDS, 'runID': os.environ.get('GITHUB_RUN_ID')}) + '\n')
        a, b = IDS
        self.command('compile-observer', ['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', ROOT / 'scripts' / 'driver-state-probe.c',
                                          '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-o', OUT / 'driver-state-probe'])
        a17 = self.build('A17', a, 2, '0.2.0', 17); b17 = self.build('B17', b, 2, '0.2.0', 17)
        a18 = self.build('A18', a, 4, '0.3.0', 18)
        a19 = self.build('A19', a, 4, '0.3.0', 19); b16 = self.build('B16', b, 2, '0.2.0', 16)
        # Receipt/build number is the documented ordering policy, independent of marketing version.
        a19lower = self.build('A19LowerMarketing', a, 4, '0.1.0', 19)
        initial = self.package('initial17', [a17, b17]); upgrade = self.package('upgrade18', [a18])
        mixed = self.package('mixed-upgrade-downgrade', [a19, b16]); lower_marketing = self.package('build19-lower-marketing', [a19lower])
        b_only = self.package('b-only17', [b17])
        self.install('install17', initial)
        self.assert_payload(a, a17, 17); self.assert_payload(b, b17, 17);self.snapshot('installed17')
        self.reload();self.state(a, 2, 'A17');self.state(b, 2, 'B17')
        self.install('upgrade17-to18', upgrade)
        self.assert_payload(a, a18, 18);self.assert_payload(b, b17, 17);self.snapshot('upgraded18')
        self.reload();self.state(a, 4, 'A18');self.state(b, 2, 'B17')
        self.state(a, 4, 'A18', 44100, True);self.state(a, 4, 'A18', 48000, True)
        # Same-build repair must restore changed bytes, not merely return success.
        damaged = HAL / f'RaveLink-{a}.driver' / 'Contents' / 'Resources' / 'RaveLink.icns'
        self.command('damage-owned-fixture', ['sudo', '-n', sys.executable, '-c',
                     'from pathlib import Path; import sys; p=Path(sys.argv[1]); p.write_bytes(p.read_bytes()+b"repair-fixture")', damaged])
        assert tree_hash(HAL / f'RaveLink-{a}.driver') != tree_hash(a18)
        self.install('same-build18-repair', upgrade);self.assert_payload(a, a18, 18)
        before = self.snapshot('before-policy-rejections')
        self.install('reject-downgrade18-to17', initial, success=False,
                     expected_refusal='Refusing driver downgrade: ci-lifecycle-a installed build 18, package build 17.')
        assert self.snapshot('after-downgrade-rejection') == before, 'Rejected downgrade modified payload or receipt'
        self.install('reject-mixed-upgrade-downgrade', mixed, success=False,
                     expected_refusal='Refusing driver downgrade: ci-lifecycle-b installed build 17, package build 16.')
        assert self.snapshot('after-mixed-rejection') == before, 'Mixed policy rejection modified payload or receipt'
        self.command('reject-duplicate-uninstall', ['sudo', '-n', sys.executable, DRIVER, 'uninstall', a, a], success=False,
                     expected_refusal='Duplicate uninstall device IDs; no devices removed')
        assert self.snapshot('after-duplicate-uninstall') == before, 'Duplicate removal modified payload or receipt'
        self.install('higher-build-lower-marketing', lower_marketing)
        self.assert_payload(a, a19lower, 19);self.assert_payload(b, b17, 17)
        b_before = self.snapshot('before-selected-removal')[b]
        self.command('remove-a-only', ['sudo', '-n', sys.executable, DRIVER, 'uninstall', a])
        after = self.snapshot('after-selected-removal')
        assert after[a] == {'payloadSHA256': None, 'receipt': None} and after[b] == b_before
        self.reload();self.state(a);self.state(b, 2, 'B17')
        # Deliberately create a stale receipt for this owned CI fixture only.
        self.command('remove-owned-b-payload', ['sudo', '-n', '/bin/rm', '-rf', HAL / f'RaveLink-{b}.driver'])
        assert self.receipt(b) and not (HAL / f'RaveLink-{b}.driver').exists()
        self.install('repair-stale-receipt', b_only);self.assert_payload(b, b17, 17)
        self.command('remove-final-b', ['sudo', '-n', sys.executable, DRIVER, 'uninstall', b])
        self.reload();self.state(a);self.state(b)
        for value in self.snapshot('completed-removal').values(): assert value == {'payloadSHA256': None, 'receipt': None}

    def cleanup(self):
        if not self.owns_devices: return
        # Known fixed IDs, recorded absent before test. Explicit cleanup also
        # handles the deliberately corrupted bundle used by repair acceptance.
        for slug in IDS:
            self.command('cleanup-' + slug, ['sudo', '-n', '/bin/rm', '-rf', HAL / f'RaveLink-{slug}.driver'])
            if self.receipt(slug):
                self.command('forget-' + slug, ['sudo', '-n', '/usr/sbin/pkgutil', '--forget', 'au.textual.ravelink.audio.package.' + slug])
        self.reload()
        if (OUT / 'driver-state-probe').exists():
            for slug in IDS: self.state(slug)
        for value in self.snapshot('cleanup-verified').values():
            assert value == {'payloadSHA256': None, 'receipt': None}


def main():
    if not authorized(os.environ):
        print('Refusing: requires explicit lifecycle opt-in on a GitHub-hosted disposable runner.', file=sys.stderr);return 2
    if sys.argv[1:] == ['--cleanup']:
        marker = OUT / 'owned-fixtures.json'
        if not marker.exists(): return 0
        ownership = json.loads(marker.read_text())
        if ownership != {'ids': list(IDS), 'runID': os.environ.get('GITHUB_RUN_ID')}:
            raise ValueError('Cleanup ownership does not match this runner invocation')
        old = json.loads((OUT / 'report.json').read_text())
        acceptance = Acceptance();acceptance.owns_devices = True;acceptance.events = old['events']
        acceptance.report_state = {key: value for key, value in old.items() if key not in ('scope', 'revision', 'events')}
        acceptance.counter = sum('command' in event for event in acceptance.events)
        try: acceptance.cleanup()
        except Exception as failure:
            acceptance.save(completed=False, cleanupCompleted=False, cleanupError=str(failure))
            print(f'Cleanup failed: {failure}', file=sys.stderr);return 1
        acceptance.save(completed=old.get('completed', False), error=old.get('error'), cleanupCompleted=True)
        return 0
    if sys.argv[1:]:
        print('Unknown arguments', file=sys.stderr);return 2
    if OUT.exists():
        print('Refusing existing lifecycle output directory; preserve previous evidence.', file=sys.stderr);return 2
    OUT.mkdir(parents=True)
    def interrupted(signum, _frame): raise RuntimeError(f'Interrupted by signal {signum}')
    signal.signal(signal.SIGINT, interrupted);signal.signal(signal.SIGTERM, interrupted)
    acceptance = Acceptance();error = None
    try: acceptance.run()
    except Exception as failure: error = str(failure)
    finally:
        try: acceptance.cleanup()
        except Exception as failure: error = f'{error or ""}; cleanup: {failure}'
        acceptance.save(completed=error is None, error=error)
    if error: print(error, file=sys.stderr);return 1
    print('Disposable Installer/receipt/HAL lifecycle acceptance passed.');return 0


if __name__ == '__main__': raise SystemExit(main())
