"""Trim two ASR-boundary overhangs in generated cache; never touches recordings."""
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,'/task')
from edit import probe,run,write_json

root=Path('/edit')
base=json.loads((root/'result.json').read_text())
assert base['full_decode_ok']
manifest=json.loads((root/'manifest.json').read_text())
final=root/'小红泡_最温柔的教练_反差精剪.mp4'
assert not final.exists(),'Final cut already exists; will not overwrite'
durations={'spoiler':3.6,'fifteen':9.1}
items=[]
for i,shot in enumerate(manifest['shots']):
    p=root/f'{i:02}-{shot["id"]}.mkv'
    if shot['id'] in durations:
        target=root/f'{i:02}-{shot["id"]}-tight.mkv'
        if not target.exists():
            run(['ffmpeg','-hide_banner','-v','error','-nostdin','-threads','1','-i',str(p),'-t',str(durations[shot['id']]),'-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','1','-bf','0','-g','60','-c:a','pcm_s16le','-ar','48000','-ac','2','-y',str(target)])
        p=target
    items.append(p)
concat=root/'concat-final.txt'
concat.write_text(''.join(f"file '{p}'\n" for p in items),encoding='utf-8')
temp=root/'tight.partial.mp4'
write_json(root/'progress.json',{'status':'finalizing','detail':'Trim speech-boundary overhangs; full-decode validation next','updated_at':time.time()})
run(['ffmpeg','-hide_banner','-v','error','-nostdin','-f','concat','-safe','0','-i',str(concat),'-map','0:v:0','-map','0:a:0','-c:v','copy','-af','alimiter=limit=0.891:level=false:latency=true','-c:a','aac','-b:a','192k','-movflags','+faststart','-y',str(temp)])
result=probe(temp)
run(['ffmpeg','-v','error','-threads','1','-i',str(temp),'-map','0:v:0','-map','0:a:0','-f','null','-'])
for source in manifest['sources'].values():
    s=Path(source['path']).stat()
    assert (s.st_size,s.st_mtime_ns)==(source['size'],source['mtime_ns'])
temp.replace(final)
result.update({'file':str(final),'full_decode_ok':True,'source_stats_unchanged':True,'refined_durations':durations,'no_upload':True,
               'subtitle_source':'Existing ASR, selective obvious corrections; no audio listening or human speech verification claimed'})
write_json(root/'result-final.json',result)
write_json(root/'progress.json',{'status':'completed','file':str(final),'updated_at':time.time()})
offset=0
for i,(shot,p) in enumerate(zip(manifest['shots'],items)):
    duration=float(probe(p)['format']['duration'])
    at=offset+min(duration/2,2.5)
    run(['ffmpeg','-v','error','-threads','1','-ss',str(at),'-i',str(final),'-frames:v','1','-vf','scale=960:540','-y',str(root/f'final-review-{i:02}.jpg')])
    offset+=duration
print(json.dumps({'file':str(final),'duration':result['format']['duration'],'size':result['format']['size'],'decode':'ok'},ensure_ascii=False),flush=True)
