from pathlib import Path
import json
import subprocess
import tempfile
import unittest


class DriverDiagnosticsObserverTests(unittest.TestCase):
    def test_malformed_properties_fail_and_complete_snapshot_is_preserved(self):
        source = Path(__file__).with_name('driver_diagnostics_observer_contract.c')
        with tempfile.TemporaryDirectory() as folder:
            executable = str(Path(folder) / 'contract')
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', str(source),
                            '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-o', executable],
                           check=True, timeout=30)
            result = subprocess.run([executable], capture_output=True, text=True, check=True, timeout=10)
        self.assertIn('controls passed; HAL mocked', result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['diagnosticProtocol'], 1)
        self.assertEqual(len(payload['devices']), 2)
        first = payload['devices'][0]
        self.assertEqual(first['uid'], 'fixture"line\n')
        self.assertEqual(first['readCalls'], 2**64 - 1)
        self.assertEqual(first['writeCalls'], 39)
        self.assertEqual(first['readFrames'], 2048)
        self.assertEqual(first['writeFrames'], 1536)
        self.assertEqual(first['startAllocations'], 2)
        self.assertEqual(len(first['reasons']), first['reasonCount'])
        self.assertTrue({'noPublishedWrite', 'futureWindow', 'expiredWindow', 'unpublishedFrame',
                         'sampleMismatch', 'generationMismatch', 'frameInFlight', 'sequenceChanged',
                         'timelineChanged', 'muted', 'writerCycleReset', 'writerTimeRewind'}.issubset(first['reasons']))
        future = first['reasons']['futureWindow']
        self.assertEqual(future['frameCount'], 512)
        self.assertEqual(future['blockCount'], 1)
        self.assertEqual(len(future['events']), 4)
        self.assertEqual(future['events'][1:], [None] * 3)
        event = future['events'][0]
        self.assertIsNone(event['requestedSampleTime'])
        self.assertFalse(event['requestedSampleTimeFinite'])
        self.assertEqual(event['requestedFrame'], 2560)
        self.assertEqual(event['writeEnd'], 2560)
        self.assertEqual(event['beforeSequence'], 4)
        self.assertEqual(event['afterSequence'], 6)
        self.assertEqual(event['priorCycle'], 28)
        self.assertEqual(len(event), 18)


if __name__ == '__main__': unittest.main()
