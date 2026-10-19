import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import compilation as c

class CompilationTests(unittest.TestCase):
    def test_production_guard_pauses_and_resumes_only_own_process_group(self):
        class Process:
            pid=12345;returncode=None
            def __init__(self):self.calls=0
            def poll(self):
                self.calls+=1
                if self.calls>=3:self.returncode=0
                return self.returncode
        with tempfile.TemporaryDirectory() as directory,patch.object(c,'WORK',Path(directory)),patch.object(c,'health_busy',side_effect=[False,True,False]),patch.object(c.subprocess,'Popen',return_value=Process()),patch.object(c.os,'killpg') as kill,patch.object(c.time,'sleep'):
            c.run(['owned-test-process'],'test')
            self.assertEqual([args.args for args in kill.call_args_list],[(12345,c.signal.SIGSTOP),(12345,c.signal.SIGCONT)])
    def test_overlap_uses_only_non_lyric_margins(self):
        left={'duration':200,'lyric_last':195};right={'lyric_first':5}
        self.assertEqual(c.overlap(left,right),.8)
        self.assertEqual(c.overlap(dict(left,lyric_last=199.9),right),0)
        self.assertEqual(c.overlap(left,{'lyric_first':None}),0)
        self.assertLessEqual(c.overlap(dict(left,lyric_last=199.2),right),.45)

    def test_source_stat_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.mp4';path.write_bytes(b'original')
            row={'path':str(path),'title':'test','size':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns}
            c.source_ok(row);path.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):c.source_ok(row)

    def test_real_ffmpeg_three_songs_two_transitions_pcm_join_and_chapters(self):
        real_sleep=time.sleep
        with tempfile.TemporaryDirectory() as directory,patch.object(c,'WORK',Path(directory)),patch.object(c,'health_busy',return_value=False),patch.object(c.time,'sleep',side_effect=lambda seconds:real_sleep(.02)):
            root=Path(directory);rows=[]
            for index,color in enumerate(('red','green','blue')):
                path=root/f'source-{index}.mp4'
                subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',f'color=c={color}:s=160x90:r=30:d=3',
                    '-f','lavfi','-i',f'sine=frequency={300+index*100}:sample_rate=48000:duration=3',
                    '-c:v','libx264','-preset','ultrafast','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-ac','2','-y',str(path)],check=True)
                stat=path.stat();rows.append({'path':str(path),'title':color,'duration':3.,'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'lyric_first':1.3,'lyric_last':1.7})
            segments=[]
            for index,row in enumerate(rows):
                left=.8 if index else 0;right=.8 if index<2 else 0
                target=root/f'body-{index}.mkv';duration=3-left-right
                c.body(row,left,duration,target,160);segments.append((target,duration))
                if right:
                    target=root/f'transition-{index}.mkv';c.transition(row,rows[index+1],.8,target,160);segments.append((target,.8))
            c.body(rows[0],0,1,root/'safe-fade.mkv',160,fade_in=True,fade_out=True)
            output=root/'result.mp4';info=c.join(segments,output,[(0,2.2,'一'),(2.2,4.4,'二'),(4.4,7.4,'三')])
            self.assertAlmostEqual(info['format_duration'],7.4,delta=.08)
            self.assertLess(abs(info['video_start']-info['audio_start']),.04)
            result=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_chapters','-of','json',str(output)],text=True))
            self.assertEqual(len(result['chapters']),3)
            self.assertTrue(all(path.is_file() for path,_ in segments))

if __name__=='__main__':unittest.main()
