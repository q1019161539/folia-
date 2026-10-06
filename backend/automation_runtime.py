"""Read-only, process-local scan diagnostics; never changes task decisions."""
import threading
import time


class ScanDiagnostics:
    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._state = {
            'last_started_at': None, 'last_success_at': None,
            'last_error_at': None, 'last_error_type': '',
            'scanning': False, 'scan_count': 0, 'error_count': 0,
            'last_counts': {}, 'last_duration_seconds': None,
        }
        self._current_error = False

    def start(self):
        with self._lock:
            self._state.update(last_started_at=self._clock(), scanning=True)
            self._state['scan_count'] += 1

    def finish(self, counts, error=None):
        with self._lock:
            now = self._clock()
            self._state['scanning'] = False
            self._state['last_counts'] = dict(counts)
            self._state['last_duration_seconds'] = round(max(0, now - self._state['last_started_at']), 3)
            self._current_error = error is not None
            if error is not None:
                # Full traceback remains in logs. Exception text may contain credentials.
                self._state.update(last_error_at=now, last_error_type=type(error).__name__)
                self._state['error_count'] += 1
            else:
                self._state['last_success_at'] = now

    def snapshot(self, thread_alive, stale_seconds=120):
        with self._lock:
            result = {**self._state, 'last_counts': dict(self._state['last_counts'])}
            now = self._clock()
            reference = result['last_started_at']
            stale = reference is not None and now - reference > stale_seconds
            result.update(thread_alive=bool(thread_alive), stale=stale,
                          age_seconds=round(max(0, now-reference), 3) if reference is not None else None)
            result['status'] = ('stopped' if not thread_alive else
                                'not_started' if reference is None else
                                'stale' if stale else 'error' if self._current_error else
                                'scanning' if result['scanning'] else 'ok')
            return result
