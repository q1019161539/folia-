import ast
import copy
import json
import os
from pathlib import Path
import subprocess
import shutil
import math
import struct
import wave
import tempfile
import unittest
from unittest.mock import Mock,patch

from performance_gate import screen_clip,parse_volume,decide_volume,gate_settings,VERSION
from publish_v2 import eligible
from fastapi import HTTPException


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.clip=self.root/'song.mp4';self.clip.write_bytes(b'original clip')
        self.settings={'enabled':True,'mean_db':-38.,'peak_db':-25.}
    def tearDown(self):self.tmp.cleanup()

    def response(self,mean='-45.0',peak='-30.9',code=0):
        return subprocess.CompletedProcess([],code,'',f'mean_volume: {mean} dB\nmax_volume: {peak} dB')

    def test_observed_background_rejected_and_singing_passes(self):
        self.assertEqual(decide_volume(-45,-30.9,self.settings)['decision'],'skip')
        for mean,peak in [(-18.6,-.4),(-18.2,-.2),(-18.7,-.4),(-25.9,-4.2),(-30,-12)]:
            self.assertEqual(decide_volume(mean,peak,self.settings)['decision'],'pass')

    def test_either_quiet_average_or_peak_rejected(self):
        self.assertEqual(decide_volume(-42,-15,self.settings)['decision'],'skip')
        self.assertEqual(decide_volume(-24,-27,self.settings)['decision'],'skip')

    def test_stricter_default_boundaries_and_observed_samples(self):
        with patch.dict(os.environ,{},clear=True):
            settings=gate_settings()
        self.assertEqual(settings,{'enabled':True,'mean_db':-30.,'peak_db':-15.,'logic':'any'})
        for mean,peak in [(-45,-30.9),(-36.2,-20.5),(-37,-9.1),(-31,-.1),(-30,-1),(-20,-15),(-30,-15),(-31.9,-25),(-40,-17.9)]:
            self.assertEqual(decide_volume(mean,peak,settings)['decision'],'skip')
        for mean,peak in [(-18.6,-.4),(-18.2,-.2),(-18.7,-.4),(-25.9,-4.2),(-29.9,-14.9)]:
            self.assertEqual(decide_volume(mean,peak,settings)['decision'],'pass')

    def test_old_default_cached_pass_rechecked_under_stricter_default(self):
        with patch('performance_gate.subprocess.run',return_value=self.response('-31','-2')) as run:
            old=screen_clip(self.clip,settings=self.settings)
            self.assertEqual(old['decision'],'pass')
            with patch.dict(os.environ,{},clear=True):
                new=screen_clip(self.clip,previous=old)
            self.assertEqual(new['decision'],'skip');self.assertEqual(run.call_count,2)

    def test_parse_silence_finite_and_invalid_result_fails(self):
        self.assertEqual(parse_volume('mean_volume: -inf dB\nmax_volume: -inf dB'),{'mean_volume':-120.,'max_volume':-120.})
        for text in ('','mean_volume: -30 dB'):
            with self.assertRaises(RuntimeError):parse_volume(text)
        for mean,peak in [(float('nan'),-20),(-40,float('inf')),(1,-20)]:
            with self.assertRaises(RuntimeError):decide_volume(mean,peak,self.settings)

    def test_decode_readonly_no_reencode_and_cache_reused(self):
        with patch('performance_gate.subprocess.run',return_value=self.response()) as run:
            result=screen_clip(self.clip,settings=self.settings)
            self.assertEqual(result['decision'],'skip')
            self.assertEqual(screen_clip(self.clip,result,self.settings),result);run.assert_called_once()
            args=run.call_args.args[0];self.assertIn('volumedetect',args);self.assertIn('0:a:0',args)
        self.assertEqual(self.clip.read_bytes(),b'original clip')
        self.assertEqual(json.loads(json.dumps(result))['mean_db'],-45)

    def test_changed_file_threshold_or_version_invalidates_cache(self):
        with patch('performance_gate.subprocess.run',return_value=self.response()) as run:
            result=screen_clip(self.clip,settings=self.settings)
            self.clip.write_bytes(b'updated original clip')
            result=screen_clip(self.clip,result,self.settings)
            result=screen_clip(self.clip,result,{**self.settings,'mean_db':-39})
            result['version']='old';screen_clip(self.clip,result,self.settings)
            self.assertEqual(run.call_count,4)

    def test_measurement_failures_stop_processing(self):
        for outcome in (self.response(code=1),self.response(mean='bad'),subprocess.TimeoutExpired('ffmpeg',90),OSError('unavailable')):
            with patch('performance_gate.subprocess.run',side_effect=outcome if isinstance(outcome,Exception) else None,return_value=outcome):
                with self.assertRaises(RuntimeError):screen_clip(self.clip,settings=self.settings)
        with self.assertRaises(RuntimeError):screen_clip(self.root/'missing',settings=self.settings)

    def test_enabled_settings_and_bad_config(self):
        with patch.dict(os.environ,{'PERFORMANCE_GATE_ENABLED':'0'}):
            self.assertFalse(gate_settings()['enabled'])
            with patch('performance_gate.subprocess.run') as run:
                self.assertEqual(screen_clip(self.clip)['decision'],'disabled');run.assert_not_called()
        for value in ('nan','-1','wrong'):
            with patch.dict(os.environ,{'PERFORMANCE_GATE_MEAN_DB':value}):
                with self.assertRaises(ValueError):gate_settings()

    def test_publishing_cannot_accept_explicitly_rejected_audio(self):
        project={'status':'completed','identified_title':'原身份歌名','output':{'sample':False,'path':'song.mp4','confidence_tier':'high'},
                 'alignment':{'timeline_match':{'confidence_tier':'high'},'performance_gate':{'decision':'skip'}}}
        self.assertFalse(eligible(project))
        project['alignment']['performance_gate'].update(decision='pass',mean_db=-18,peak_db=-1)
        self.assertTrue(eligible(project))
        project['alignment']['performance_gate'].update(mean_db=-37,peak_db=-9.1)
        self.assertFalse(eligible(project))
        project['alignment']['performance_gate'].update(mean_db=-20,peak_db=-18)
        self.assertFalse(eligible(project))
        project['alignment']['performance_gate'].pop('mean_db')
        self.assertFalse(eligible(project))

    def test_same_threshold_old_and_cache_version_invalidated(self):
        with patch('performance_gate.subprocess.run',return_value=self.response('-37','-9.1')) as run:
            settings={'enabled':True,'mean_db':-32.,'peak_db':-18.}
            gate=screen_clip(self.clip,settings=settings)
            gate.update(version='quiet-clip-v1',decision='pass')
            self.assertEqual(screen_clip(self.clip,gate,settings)['decision'],'skip')
            self.assertEqual(run.call_count,2)

    def test_new_module_in_docker(self):
        self.assertIn('performance_gate.py',Path(__file__).with_name('Dockerfile').read_text(encoding='utf-8'))

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg unavailable on this test host')
    def test_real_decode_quiet_and_normal_audio(self):
        for amplitude,expected in [(20,'skip'),(7000,'pass')]:
            path=self.root/f'{amplitude}.wav'
            with wave.open(str(path),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
                f.writeframes(b''.join(struct.pack('<h',int(amplitude*math.sin(i*2*math.pi*440/16000))) for i in range(32000)))
            before=path.read_bytes();result=screen_clip(path,settings=self.settings)
            self.assertEqual(result['decision'],expected);self.assertEqual(path.read_bytes(),before)


class AutomationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.clip=self.root/'song.mp4';self.clip.write_bytes(b'original media')
        self.song={'title':'ASR显示名','status':'clipped','clip_path':str(self.clip)}
        self.project={'id':'immutable-project','status':'completed','identified_title':'权威歌名','identified_artist':'真实歌手',
                      'alignment':{'timeline_match':{'status':'completed','confidence_tier':'high'},'aligner_progress':{'status':'completed'}},
                      'output':{'path':str(self.clip),'sample':False}}
        tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='process_automation_song')
        self.ns={'Any':object,'Path':Path,'MEDIA_WRITE':self.root,'automation_cancelled':Mock(return_value=False),
                 'update_automation_run':Mock(),'screen_clip':Mock(return_value={'version':VERSION,'decision':'skip','reason':'疑似低响度背景音乐','reason_code':'suspected_quiet_background'}),
                 'create_imported_song_job':Mock(return_value=self.project),'auto_standard_timeline_task':Mock(),
                 'force_align_task':Mock(),'render_task':Mock(),'ensure_publish_job':Mock(),
                 'getjob':Mock(return_value=self.project)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'automation-screening','exec'),self.ns)
    def tearDown(self):self.tmp.cleanup()

    def call(self):self.ns['process_automation_song']({'id':'run'}, {}, [], [self.song], 0)

    def assert_no_downstream(self):
        for name in ('create_imported_song_job','auto_standard_timeline_task','force_align_task','render_task','ensure_publish_job'):
            self.ns[name].assert_not_called()
        self.assertEqual(self.clip.read_bytes(),b'original media')

    def test_rejected_clip_exits_before_project_identity_qwen_lyrics_render_publish(self):
        self.call();self.assertEqual(self.song['status'],'skipped')
        self.assertEqual(self.song['skip_reason'],'suspected_quiet_background');self.assert_no_downstream()
        self.assertEqual(self.song['performance_gate']['decision'],'skip')
        self.assertIn('song_screening',[x.kwargs.get('stage') for x in self.ns['update_automation_run'].call_args_list])

    def test_decoder_error_and_escaping_path_never_continue(self):
        self.ns['screen_clip'].side_effect=RuntimeError('decode failed');self.call()
        self.assertEqual(self.song['status'],'failed');self.assert_no_downstream()
        self.song.update(status='clipped',clip_path=str(self.root.parent/'outside.mp4'))
        self.ns['screen_clip'].reset_mock();self.call();self.ns['screen_clip'].assert_not_called();self.assert_no_downstream()

    def test_pass_preserves_identity_media_and_normal_handoff(self):
        before=copy.deepcopy(self.project);self.ns['screen_clip'].return_value={'decision':'pass'}
        self.call();self.assertEqual(self.song['status'],'completed');self.assertEqual(self.project,before)
        self.ns['ensure_publish_job'].assert_called_once();self.assertEqual(self.clip.read_bytes(),b'original media')

    def test_already_skipped_completed_not_reanalyzed(self):
        for status in ('skipped','completed'):
            self.song['status']=status;self.call()
        self.ns['screen_clip'].assert_not_called();self.assert_no_downstream()

    def test_cancelled_historical_publish_cannot_be_retried(self):
        tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='retry_publish_job');node.decorator_list=[]
        update=Mock();ns={'HTTPException':HTTPException,'get_publish_job':Mock(return_value={'pipeline_version':2,'status':'failed','failure_stage':'policy'}),'update_publish_job':update}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'publish-policy-retry','exec'),ns)
        with self.assertRaises(HTTPException) as raised:ns['retry_publish_job']('cancelled')
        self.assertEqual(raised.exception.status_code,409);update.assert_not_called()
