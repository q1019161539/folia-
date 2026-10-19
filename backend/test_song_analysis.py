import ast
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import httpx
from song_analysis import SongAnalysisClient, SongAnalysisError

SEGMENTS = [{'segment_id': 0, 'start_ms': 5000, 'end_ms': 8000, 'text': '歌词一'},
            {'segment_id': 1, 'start_ms': 100000, 'end_ms': 110000, 'text': '歌词二'}]
SONG = {'title': '测试歌', 'start_segment_id': 0, 'end_segment_id': 1, 'confidence': .95,
        'start_ms': 99999, 'end_ms': 999999, 'reason': '完整演唱'}
ENV = {'TITLE_API_KEY': 'private-primary', 'TITLE_API_BASE_URL': 'https://primary.test/v1',
       'TITLE_API_MODEL': 'another-title-model', 'DEEPSEEK_API_KEY': 'private-fallback',
       'DEEPSEEK_BASE_URL': 'https://fallback.test', 'DEEPSEEK_MODEL': 'deepseek-v4-flash'}


def response(value):
    return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(value)}}]})


class SongAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []

    def client(self, handler):
        def receive(request):
            self.calls.append(request)
            return handler(request)
        return SongAnalysisClient(httpx.MockTransport(receive))

    def test_primary_same_title_service_but_explicit_song_model(self):
        accepted, skipped, record = self.client(lambda r: response({'songs': [SONG]})).detect(SEGMENTS, .8)
        req = self.calls[0]; body = json.loads(req.content)
        self.assertEqual(str(req.url), 'https://primary.test/v1/chat/completions')
        self.assertEqual(req.headers['Authorization'], 'Bearer private-primary')
        self.assertEqual(body['model'], 'gpt-6.1-sol')
        self.assertFalse(body['stream']); self.assertNotIn('response_format', body)
        self.assertEqual((accepted[0]['start_ms'], accepted[0]['end_ms']), (5000, 110000))
        self.assertEqual(skipped, []); self.assertFalse(record['fallback_used'])
        self.assertEqual(record['requested_model'], 'gpt-6.1-sol'); self.assertEqual(len(self.calls), 1)

    def test_valid_empty_is_success_not_fallback(self):
        a, s, record = self.client(lambda r: response({'songs': []})).detect(SEGMENTS, .8)
        self.assertEqual((a, s), ([], [])); self.assertEqual(record['status'], 'completed')
        self.assertEqual(len(self.calls), 1)

    def test_low_confidence_and_invalid_ids_remain_local_skips(self):
        for song in ({**SONG, 'confidence': .2}, {**SONG, 'end_segment_id': 999}):
            with self.subTest(song=song):
                self.calls.clear()
                a, s, _ = self.client(lambda r: response({'songs': [song]})).detect(SEGMENTS, .8)
                self.assertEqual(a, []); self.assertEqual(len(s), 1); self.assertEqual(len(self.calls), 1)

    def test_http_failures_fall_back_once_using_deepseek_structure(self):
        for status in (400, 401, 429, 500, 502):
            with self.subTest(status=status):
                self.calls.clear()
                a, _, record = self.client(lambda r: httpx.Response(status, text='private-primary')
                    if r.url.host == 'primary.test' else response({'songs': [SONG]})).detect(SEGMENTS, .8)
                self.assertEqual(len(a), 1); self.assertTrue(record['fallback_used'])
                self.assertEqual(record['requested_model'], 'deepseek-v4-flash')
                self.assertEqual(len(self.calls), 2)
                self.assertEqual(record['attempts'][0]['error'], 'http_' + str(status))
                req = self.calls[1]; body = json.loads(req.content)
                self.assertEqual(req.headers['Authorization'], 'Bearer private-fallback')
                self.assertEqual(body['response_format'], {'type': 'json_object'})
                self.assertNotIn('private-', json.dumps(record))

    def test_timeout_and_connection_fall_back_without_hidden_retry(self):
        for error in (httpx.ReadTimeout, httpx.ConnectError):
            with self.subTest(error=error):
                self.calls.clear()
                def handler(req):
                    if req.url.host == 'primary.test': raise error('private-primary', request=req)
                    return response({'songs': []})
                _, _, record = self.client(handler).detect(SEGMENTS, .8)
                self.assertTrue(record['fallback_used']); self.assertEqual(len(self.calls), 2)
                self.assertNotIn('private-', json.dumps(record))

    def test_malformed_schema_is_not_misreported_as_no_songs(self):
        for value in ({}, {'songs': None}, {'songs': 'x'}, {'songs': [None]},
                      {'songs': [{**SONG, 'confidence': 'nan'}]},
                      {'songs': [{**SONG, 'start_segment_id': .5}]}):
            with self.subTest(value=value):
                self.calls.clear()
                _, _, record = self.client(lambda r: response(value) if r.url.host == 'primary.test'
                                          else response({'songs': []})).detect(SEGMENTS, .8)
                self.assertTrue(record['fallback_used']); self.assertEqual(record['attempts'][0]['error'], 'invalid_response')

    def test_invalid_json_response_falls_back(self):
        _, _, record = self.client(lambda r: httpx.Response(200, text='not json') if r.url.host == 'primary.test'
                                  else response({'songs': []})).detect(SEGMENTS, .8)
        self.assertTrue(record['fallback_used'])

    def test_primary_works_without_fallback_and_without_ai_title_switch(self):
        os.environ.pop('DEEPSEEK_API_KEY'); os.environ['AI_TITLE_ENABLED'] = '0'
        client = self.client(lambda r: response({'songs': []}))
        self.assertTrue(client.public_config()['song_analysis_configured'])
        self.assertFalse(client.public_config()['fallback_configured'])
        client.detect(SEGMENTS, .8); self.assertEqual(len(self.calls), 1)

    def test_missing_primary_uses_configured_fallback(self):
        os.environ.pop('TITLE_API_KEY')
        _, _, record = self.client(lambda r: response({'songs': []})).detect(SEGMENTS, .8)
        self.assertTrue(record['fallback_used']); self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].url.host, 'fallback.test')

    def test_both_failed_are_redacted_and_durable(self):
        snapshots = []
        with self.assertRaises(SongAnalysisError) as error:
            self.client(lambda r: httpx.Response(500, text='private-primary private-fallback')).detect(
                SEGMENTS, .8, lambda r: snapshots.append(copy.deepcopy(r)))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(snapshots[-1]['status'], 'failed')
        self.assertNotIn('private-', str(error.exception) + json.dumps(snapshots))
        self.assertEqual(snapshots[0]['attempts'][0]['status'], 'in_flight')

    def test_no_keys_no_network_and_disabled_readiness(self):
        os.environ.clear()
        client = self.client(lambda r: self.fail('No HTTP without keys'))
        self.assertFalse(client.public_config()['song_analysis_configured'])
        with self.assertRaises(SongAnalysisError): client.detect(SEGMENTS, .8)

    def test_persistence_error_stops_before_network(self):
        def fail(record): raise RuntimeError('database locked')
        with self.assertRaisesRegex(RuntimeError, 'database locked'):
            self.client(lambda r: self.fail('No request before persistence')).detect(SEGMENTS, .8, fail)

    def test_input_identity_and_segments_are_unchanged(self):
        segments = [{**s, 'identified_title': '真实标题', 'identified_artist': '真实歌手'} for s in SEGMENTS]
        before = copy.deepcopy(segments)
        self.client(lambda r: response({'songs': [SONG]})).detect(segments, .8)
        self.assertEqual(segments, before)

    def test_timeout_config_and_no_secret_in_public_config(self):
        config = SongAnalysisClient().public_config()
        self.assertEqual(config['timeout_seconds'], 600)
        self.assertNotIn('private-', json.dumps(config))


class IntegrationTests(unittest.TestCase):
    source = Path(__file__).with_name('app.py').read_text(encoding='utf-8')

    def test_run_uses_new_client_and_atomically_saves_result(self):
        tree = ast.parse(self.source)
        run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'process_automation_run')
        source = ast.get_source_segment(self.source, run)
        self.assertIn('SongAnalysisClient().detect(', source)
        self.assertIn("analysis.get('status')!='completed'", source)
        self.assertIn('songs=songs,timings=timings', source)
        self.assertNotIn('detect_songs_deepseek', source)

    def test_manual_and_enable_gates_accept_primary_without_deepseek(self):
        tree = ast.parse(self.source)
        for name in ('enable_automation_profile', 'run_existing_recording'):
            source = ast.get_source_segment(self.source, next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name))
            self.assertIn("public_config()['song_analysis_configured']", source)
            self.assertNotIn('if not DEEPSEEK_KEY', source)

    def test_actual_model_is_published_from_durable_record(self):
        self.assertIn("analysis.get('requested_model') or 'legacy-deepseek (未记录请求模型)'", self.source)

    def test_new_module_is_explicitly_copied(self):
        self.assertIn('song_analysis.py', Path(__file__).with_name('Dockerfile').read_text())

    def run_context(self, record=None):
        run = {'id': 'run', 'profile_id': 'profile', 'source': 'recording.mp4', 'songs': [],
               'timings': {'song_analysis': record} if record else {}}
        client = Mock()
        def update(run_id, **fields):
            if 'songs' in fields:
                self.assertIn('timings', fields, 'Final songs and model record must be atomic')
            run.update(copy.deepcopy(fields))
            return copy.deepcopy(run)
        def mark(run_id, **fields):
            run['timings'].update(copy.deepcopy(fields))
            return copy.deepcopy(run['timings'])
        tree = ast.parse(self.source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'process_automation_run')
        ns = {'get_automation_run': lambda *args: copy.deepcopy(run),
              'get_automation_profile': lambda *args: {'min_confidence': .8},
              'update_automation_run': update, 'mark_run_timing': mark,
              'run_timings': lambda r: copy.deepcopy(r['timings']),
              'ensure_automation_transcript': lambda r: SEGMENTS,
              'SongAnalysisClient': lambda: client, 'publish_automation_song_analysis': Mock(),
              'notify_automation_stage': Mock(), 'stage_elapsed': lambda *args: 0,
              'automation_cancelled': lambda *args: False,
              'time': Mock(time=lambda: 123)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'app.py', 'exec'), ns)
        return run, client, ns

    def test_empty_success_is_atomic_and_not_reanalyzed_after_restart(self):
        record = {'status': 'completed', 'requested_model': 'gpt-6.1-sol', 'fallback_used': False}
        run, client, ns = self.run_context()
        client.detect.return_value = ([], [], record)
        ns['process_automation_run']('run')
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(run['timings']['song_analysis'], record)
        self.assertEqual(client.detect.call_count, 1)
        ns['process_automation_run']('run')
        self.assertEqual(client.detect.call_count, 1)
        self.assertEqual(ns['publish_automation_song_analysis'].call_count, 2)

    def test_failed_analysis_record_survives_retryable_run_error(self):
        run, client, ns = self.run_context()
        record = {'status': 'failed', 'attempts': [{'error': 'timeout'}]}
        def fail(segments, threshold, persist):
            persist(record)
            raise SongAnalysisError('sanitized failure')
        client.detect.side_effect = fail
        ns['process_automation_run']('run')
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['timings']['song_analysis'], record)
        ns['publish_automation_song_analysis'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
