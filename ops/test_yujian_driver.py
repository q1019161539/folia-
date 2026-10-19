"""Exercise the one-shot driver without Docker, network, rendering or upload."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

if sys.platform=='win32':
    sys.modules['fcntl']=types.SimpleNamespace(LOCK_EX=2,LOCK_NB=4,flock=lambda *a:None)
spec=importlib.util.spec_from_file_location('driver',Path(__file__).with_name('run-yujian-repair-once.py'))
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


class DriverChecks(unittest.TestCase):
    def run_case(self,states):
        calls=[];events=[];iterator=iter(states)
        def action(name,stdin=None):
            calls.append(name)
            if name=='snapshot':return copy.deepcopy(next(iterator))
            if name=='submit':return {'accepted':True,'task_id':'test-task','publish_id':driver.PUB}
            return {}
        with tempfile.TemporaryDirectory(prefix='folia-yujian-driver-test-') as directory:
            with patch.object(driver,'ROOT',Path(directory)),patch.object(driver,'event',lambda **x:events.append(x)),\
                 patch.object(driver,'action',action),patch.object(driver,'verify_paths',lambda s:calls.append('verify_paths')),\
                 patch.object(driver.time,'sleep',lambda seconds:None):
                driver.main()
        return calls,events

    @staticmethod
    def state(status='completed',publish=None,native=None):
        return {'status':status,'native':native or {},'publish':publish or {},'record':{}}

    def test_one_submission_then_only_poll(self):
        ready={'id':driver.PUB,'status':'ready','submit_attempts':0}
        accepted={'id':driver.PUB,'status':'uploading','bililive_task_id':'test-task','submit_attempts':1}
        completed={**accepted,'status':'completed','aid':'1234','bvid':'BVexample'}
        calls,events=self.run_case([self.state(publish=ready),self.state(publish=accepted),
            self.state(publish=completed),self.state(publish=completed)])
        self.assertEqual(calls.count('submit'),1)
        self.assertLess(calls.index('verify_paths'),calls.index('submit'))
        self.assertLess(calls.index('deleted'),calls.index('submit'))
        self.assertEqual(events[-1]['stage'],'completed')

    def test_uncertain_submit_is_not_repeated(self):
        calls,events=self.run_case([self.state(publish={'id':driver.PUB,'status':'submitting','submit_attempts':1})])
        self.assertNotIn('submit',calls)
        self.assertEqual(events[-1]['stage'],'stopped_needs_inspection')

    def test_terminal_render_stops_without_upload_or_retry(self):
        calls,events=self.run_case([self.state('rendering',native={'status':'failed','id':'rid','error':'browser failed'})])
        self.assertNotIn('submit',calls);self.assertNotIn('render',calls)
        self.assertEqual(events[-1]['stage'],'stopped_render_failure')

    def test_known_completed_renderer_recovered_without_new_post(self):
        calls,events=self.run_case([self.state('rendering',native={'status':'completed','id':'rid'}),
            self.state(publish={'id':driver.PUB,'status':'failed','submit_attempts':0})])
        self.assertIn('recover_render',calls);self.assertNotIn('render',calls);self.assertNotIn('submit',calls)


if __name__=='__main__':unittest.main()
