import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
import once

class OnceTests(unittest.TestCase):
    def test_known_task_never_submits_again(self):
        app=MagicMock();app.get_publish_job.return_value={'bililive_task_id':'known','aid':None,'bvid':None}
        with patch.object(once,'client') as factory:
            self.assertTrue(once.submit(app)['already_accepted']);factory.assert_not_called()

    def test_uncertain_submit_never_posts_again(self):
        app=MagicMock();app.get_publish_job.return_value={'status':'submitting','submit_attempts':1}
        with tempfile.TemporaryDirectory() as td,patch.object(once,'ROOT',Path(td)),patch.object(once,'client') as factory:
            with self.assertRaises(AssertionError):once.submit(app)
            factory.assert_not_called()

    def test_receipt_recovery_adopts_without_post(self):
        app=MagicMock();app.get_publish_job.return_value={'status':'submitting','submit_attempts':1}
        with tempfile.TemporaryDirectory() as td,patch.object(once,'ROOT',Path(td)),patch.object(once,'client') as factory,patch.object(once,'adopt') as adopt:
            (Path(td)/'accepted.json').write_text(json.dumps({'task_id':'accepted'}),encoding='utf-8')
            self.assertTrue(once.submit(app)['recovered_receipt'])
            adopt.assert_called_once_with(app,'accepted');factory.assert_not_called()
            app.publisher_v2.return_value.checkpoint.assert_called_once()

    def test_existing_prepared_job_not_recreated(self):
        with patch.object(once,'row',return_value={'id':once.PID,'status':'ready'}),patch.object(once,'inputs') as inputs:
            self.assertEqual(once.prepare(MagicMock())['status'],'ready');inputs.assert_not_called()

if __name__=='__main__':unittest.main()
