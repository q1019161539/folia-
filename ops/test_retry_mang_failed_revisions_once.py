import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('retry_workflow',Path(__file__).with_name('retry-mang-failed-revisions-once.py'))
workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)


class RetryPolicyTests(unittest.TestCase):
    def test_completed_reuses_renderer_result(self):
        self.assertEqual(workflow.classify({'decision':'pass'},'completed'),'recover_completed')

    def test_only_confirmed_terminal_or_missing_can_rerender(self):
        for state in ('failed','cancelled','missing'):
            self.assertEqual(workflow.classify({'decision':'pass'},state),'queue_rerender_once')
        for state in ('unknown',None,'unavailable'):
            with self.assertRaises(RuntimeError):workflow.classify({'decision':'pass'},state)

    def test_active_renderer_only_resumed_not_recreated(self):
        for state in ('running','queued'):
            self.assertEqual(workflow.classify({'decision':'pass'},state),'resume_existing')

    def test_audio_exclusion_precedes_renderer_status(self):
        for state in ('completed','failed','missing','unknown'):
            self.assertEqual(workflow.classify({'decision':'skip'},state),'excluded_audio')

    def test_only_explicit_six_and_no_direct_renderer_or_upload_post(self):
        self.assertEqual(len(workflow.TARGETS),6);self.assertEqual(len(set(workflow.TARGETS)),6)
        source=Path(__file__).with_name('retry-mang-failed-revisions-once.py').read_text(encoding='utf-8')
        self.assertNotIn("folia_renderer_request('POST'",source)
        self.assertNotIn('/api/bili/upload',source)
        self.assertIn("c.execute('BEGIN IMMEDIATE')",source)
        self.assertIn('render_revision_retry_once:',source)


if __name__=='__main__':unittest.main()
