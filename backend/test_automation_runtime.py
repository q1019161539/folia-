import unittest
from automation_runtime import ScanDiagnostics


class ScanDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.state = ScanDiagnostics(lambda: self.now)

    def test_unstarted_is_not_healthy(self):
        self.assertEqual(self.state.snapshot(True)['status'], 'not_started')

    def test_success_records_counts_and_duration(self):
        self.state.start(); self.now += 2
        self.state.finish({'profiles': 2, 'queued': 1})
        result = self.state.snapshot(True)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['last_counts']['queued'], 1)
        self.assertEqual(result['last_duration_seconds'], 2)
        result['last_counts']['queued'] = 99
        self.assertEqual(self.state.snapshot(True)['last_counts']['queued'], 1)

    def test_failure_is_safe_and_recovery_keeps_history(self):
        self.state.start(); self.state.finish({}, RuntimeError('secret-token'))
        self.assertEqual(self.state.snapshot(True)['status'], 'error')
        self.assertNotIn('secret-token', str(self.state.snapshot(True)))
        self.now += 30; self.state.start(); self.state.finish({})
        result = self.state.snapshot(True)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['error_count'], 1)
        self.assertEqual(result['last_error_type'], 'RuntimeError')

    def test_stale_and_stopped_are_distinct(self):
        self.state.start(); self.now += 121
        self.assertEqual(self.state.snapshot(True)['status'], 'stale')
        self.assertEqual(self.state.snapshot(False)['status'], 'stopped')


if __name__ == '__main__':
    unittest.main()
