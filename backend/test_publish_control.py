"""Exercise actual route functions against an isolated FastAPI app, never production."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel,StrictBool
from publishing import PublishPrepareError
from publish_v2 import COVER_MAX_ATTEMPTS
from cover_fallback import primary_cover_configured
from title_generation import TITLE_MAX_ATTEMPTS, TITLE_TIMEOUT_SECONDS


class ControlApiTests(unittest.TestCase):
    def setUp(self):
        environment=patch.dict('os.environ',{'COVER_PRIMARY_PROVIDER':'gpt','COVER_API_KEY':'',
                                           'COVER_FALLBACK_ENABLED':'0','COVER_FALLBACK_API_KEY':''})
        environment.start();self.addCleanup(environment.stop)
        names={'PublishControlIn','publish_v2_activate','publish_control','set_publish_control','retry_publish_job'}
        tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        nodes=[node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names]
        self.service=Mock();self.service.rollout.return_value={'mode':'acceptance','allowlist':['a','b'],'cutover':0}
        self.job={'id':'job','pipeline_version':2,'status':'failed','failure_stage':'cover','song_project_id':'song',
                  'submit_attempts':0,'bililive_task_id':None,'aid':None,'bvid':None,'publish_result':None}
        self.song={'cover_path':None,'cover_attempts':2};self.service.row.return_value=self.song
        self.settings=SimpleNamespace(enabled=True,auto_publish_enabled=True)
        import os
        self.ns={'app':FastAPI(),'BaseModel':BaseModel,'StrictBool':StrictBool,'HTTPException':HTTPException,
                 'publisher_v2':lambda:self.service,'PUBLISH_SETTINGS':self.settings,'os':os,
                 'PublishPrepareError':PublishPrepareError,'publish_wakeup':Mock(),'COVER_MAX_ATTEMPTS':COVER_MAX_ATTEMPTS,
                 'get_publish_job':lambda id:self.job,'update_publish_job':Mock(return_value=self.job),
                 'TITLE_MAX_ATTEMPTS':TITLE_MAX_ATTEMPTS,'TITLE_TIMEOUT_SECONDS':TITLE_TIMEOUT_SECONDS,
                 'primary_cover_configured':primary_cover_configured}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'app-control-routes','exec'),self.ns)
        self.client=TestClient(self.ns['app'])

    def test_read_only_status_and_no_secret(self):
        with patch.dict('os.environ',{'COVER_API_KEY':'private-key'}): response=self.client.get('/api/publish-v2/control')
        self.assertEqual(response.status_code,200);self.assertFalse(response.json()['enabled'])
        self.assertNotIn('private-key',response.text);self.service.set_automatic_enabled.assert_not_called()
        self.assertEqual(response.json()['cover_max_attempts'],10)
        self.assertEqual(response.json()['title_max_attempts'],3)
        self.assertEqual(response.json()['title_timeout_seconds'],120)

    def test_enable_and_pause_wire_format(self):
        with patch.dict('os.environ',{'COVER_API_KEY':'private-key'}):
            self.assertEqual(self.client.post('/api/publish-v2/control',json={'enabled':True}).status_code,200)
        self.service.set_automatic_enabled.assert_called_with(True)
        self.assertEqual(self.client.post('/api/publish-v2/control',json={'enabled':False}).status_code,200)
        self.service.set_automatic_enabled.assert_called_with(False)

    def test_environment_gate_and_pause_always_available(self):
        self.settings.auto_publish_enabled=False
        with patch.dict('os.environ',{'COVER_API_KEY':'private-key'}):
            self.assertEqual(self.client.post('/api/publish-v2/control',json={'enabled':True}).status_code,409)
            self.assertEqual(self.client.post('/api/publish-v2/activate').status_code,409)
        self.service.set_automatic_enabled.assert_not_called()
        self.assertEqual(self.client.post('/api/publish-v2/control',json={'enabled':False}).status_code,200)

    def test_missing_key_and_incomplete_acceptance_rejected(self):
        with patch.dict('os.environ',{'COVER_API_KEY':''}):
            self.assertEqual(self.client.post('/api/publish-v2/control',json={'enabled':True}).status_code,409)
        self.service.set_automatic_enabled.side_effect=PublishPrepareError('尚未完成两首验收')
        with patch.dict('os.environ',{'COVER_API_KEY':'private-key'}):
            self.assertEqual(self.client.post('/api/publish-v2/control',json={'enabled':True}).status_code,409)

    def test_boolean_is_strict(self):
        for value in ('false','true',1,None):
            self.assertEqual(self.client.post('/api/publish-v2/control',json={'enabled':value}).status_code,422)

    def test_gemini_primary_can_enable_without_gpt_and_never_exposes_key(self):
        with patch.dict('os.environ',{'COVER_PRIMARY_PROVIDER':'gemini','COVER_FALLBACK_ENABLED':'1',
                                    'COVER_FALLBACK_API_KEY':'test-gemini-private-value'}):
            response=self.client.post('/api/publish-v2/control',json={'enabled':True})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['cover_configured'])
        self.assertEqual(response.json()['cover_primary_provider'],'gemini')
        self.assertNotIn('test-gemini-private-value',response.text)
        self.service.set_automatic_enabled.assert_called_once_with(True)

    def test_gemini_primary_does_not_fall_back_to_gpt_key(self):
        with patch.dict('os.environ',{'COVER_PRIMARY_PROVIDER':'gemini','COVER_API_KEY':'test-gpt-private-value'}):
            response=self.client.post('/api/publish-v2/control',json={'enabled':True})
        self.assertEqual(response.status_code,409)
        self.service.set_automatic_enabled.assert_not_called()

    def test_retry_old_two_failures_without_resetting_cover_attempts(self):
        self.assertEqual(self.client.post('/api/publish-jobs/job/retry').status_code,200)
        self.ns['update_publish_job'].assert_called_once_with('job',status='pending',publish_error='',next_retry_at=None)
        self.assertEqual(self.song['cover_attempts'],2)

    def test_retry_rejects_ten_attempts_but_allows_saved_cover(self):
        self.song['cover_attempts']=10
        self.assertEqual(self.client.post('/api/publish-jobs/job/retry').status_code,409)
        self.ns['update_publish_job'].assert_not_called()
        self.song['cover_path']='/output/saved.jpg'
        self.assertEqual(self.client.post('/api/publish-jobs/job/retry').status_code,200)

    def test_retry_never_resets_accepted_or_submit_failed_tasks(self):
        for field,value in [('bililive_task_id','known-task'),('aid','123'),('bvid','BVtest'),('submit_attempts',1),('publish_result','success')]:
            original=self.job[field];self.job[field]=value
            self.assertEqual(self.client.post('/api/publish-jobs/job/retry').status_code,409)
            self.job[field]=original
        self.ns['update_publish_job'].assert_not_called()
        self.service.set_automatic_enabled.assert_not_called()
