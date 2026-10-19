import unittest
from unittest.mock import patch

modules = ['test_song_analysis', 'test_automation', 'test_automation_runtime',
           'test_publish_v2', 'test_publish_control', 'test_publishing',
           'test_title_generation', 'test_cover_frames', 'test_performance_gate',
           'test_recording_time', 'test_render_revisions']


def no_network(*args, **kwargs):
    raise AssertionError('Offline tests must not access the network')


with patch('socket.create_connection', no_network), patch('publish_v2.log_exception'):
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(modules))
raise SystemExit(not result.wasSuccessful())
