"""One-off, resumable CPU-only compilation. Never alters source media or publishing DB."""
from __future__ import annotations
import argparse
import collections
import contextlib
import difflib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import time
import urllib.request

WORK=Path(os.environ.get('COMPILATION_DIR','/output/小红泡-管珩心/歌曲长篇合集/2026-10-18'))
FPS=30
VERSION='compilation-v1'
CURRENT={}

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    partial=path.with_suffix(path.suffix+'.partial')
    partial.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');partial.replace(path)

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def probe(path):
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,duration,start_time,sample_rate,channels','-of','json',str(path)],capture_output=True,text=True,timeout=45,check=True)
    data=json.loads(result.stdout);video=next(s for s in data['streams'] if s['codec_type']=='video')
    audio=next(s for s in data['streams'] if s['codec_type']=='audio')
    seconds=float(video.get('duration') or data['format']['duration'])
    return {'duration':round(seconds*FPS)/FPS,'format_duration':float(data['format']['duration']),
            'width':video['width'],'height':video['height'],'video_codec':video['codec_name'],
            'fps':video['r_frame_rate'],'audio_codec':audio['codec_name'],'sample_rate':audio['sample_rate'],
            'channels':audio['channels'],'video_start':float(video.get('start_time') or 0),'audio_start':float(audio.get('start_time') or 0)}

def source_ok(row):
    stat=Path(row['path']).stat()
    if stat.st_size!=row['size'] or stat.st_mtime_ns!=row['mtime_ns']:raise RuntimeError('源成片变化，停止：'+row['title'])

def inventory():
    from opencc import OpenCC
    from title_generation import song_display_title
    cc=OpenCC('t2s');db=sqlite3.connect('file:/data/studio.db?mode=ro',uri=True,timeout=30);db.row_factory=sqlite3.Row
    published={r[0] for r in db.execute("SELECT source_job_id FROM publish_jobs WHERE streamer LIKE ? AND status='completed'",('%小红泡%',))}
    rows=db.execute("SELECT * FROM jobs WHERE status='completed' AND source LIKE ? ORDER BY created_at",('小红泡-管珩心/%',)).fetchall()
    groups=collections.defaultdict(list);excluded=[]
    for raw in rows:
        row=dict(raw);out=json.loads(row['output'] or '{}');alignment=json.loads(row['alignment'] or '{}')
        if out.get('sample') is not False or not out.get('path'):continue
        path=Path(out['path'])
        try:
            unverified=not bool(row['identified_title'])
            # Legacy labels are visibly unverified display text, never a replacement identity.
            title=song_display_title(row['identified_title']) if not unverified else '旧版待核对：'+path.parent.name
            if not unverified and re.search(r'(?:^|[-—_])前奏$',title):raise ValueError('明确标记为前奏片段，非完整演唱')
            if not path.is_file() and path.is_relative_to(Path('/output')):
                legacy=Path('/output-legacy')/path.relative_to('/output')
                if legacy.is_file():path=legacy
            if not path.is_file() or path.suffix.lower()!='.mp4':raise ValueError('成片不存在或非MP4')
            if not any(path.is_relative_to(Path(root)) for root in ('/output','/output-legacy')):raise ValueError('不在共享输出目录')
            stat=path.stat();key='unidentified:'+row['id'] if unverified else re.sub(r'\s+','',cc.convert(title).casefold())
            tier=out.get('confidence_tier') or (alignment.get('timeline_match') or {}).get('confidence_tier') or 'unknown'
            bounds=[line for line in alignment.get('lines',[]) if line.get('enabled') is not False and line.get('text') and line.get('start_ms') is not None and line.get('end_ms') is not None]
            offset=float(out.get('trim_start_ms') or 0)
            # Only explicit render-trim metadata proves alignment-to-output projection.
            first=min((float(x['start_ms']) for x in bounds),default=0)-offset
            last=max((float(x['end_ms']) for x in bounds),default=0)-offset
            explicit=bool(out.get('post_render_stream_copy_trim') and bounds)
            text=re.sub(r'[^\w\u4e00-\u9fff]','',cc.convert(''.join(x.get('text','') for x in bounds)).casefold())
            groups[key].append({'job_id':row['id'],'title':title,'identified_title':row['identified_title'],
                'identified_artist':row['identified_artist'],'identity_source':row['identity_source'],'song_key':key,
                'path':str(path),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'tier':tier,
                'title_unverified':unverified,
                'published':row['id'] in published,'smooth':out.get('output_mode')=='smooth' or '_smooth' in path.name,
                'created_at':row['created_at'],'source':row['source'],'lyric_first':first/1000 if explicit else None,
                'lyric_last':last/1000 if explicit else None,'lyric_fingerprint':hashlib.sha256(text.encode()).hexdigest() if len(text)>=80 else None})
        except (ValueError,OSError) as exc:excluded.append({'job_id':row['id'],'path':str(path),'reason':str(exc)})
    selected=[];duplicates=[];conflicts=[]
    for key,items in groups.items():
        artists={cc.convert(x['identified_artist']).strip().casefold() for x in items if x['identified_artist']}
        lyric_sets={x['lyric_fingerprint'] for x in items}
        if len(artists)>1 and (len(lyric_sets)>1 or None in lyric_sets):
            conflicts.append({'title':items[0]['title'],'candidates':[{k:x[k] for k in ('job_id','identified_artist','tier','source')} for x in items]})
        # Prefer reliable lyric output, then already approved/published versions and remasters.
        items.sort(key=lambda x:({'high':3,'deepseek':1,'local':1}.get(x['tier'],0),x['published'],x['smooth'],x['created_at']),reverse=True)
        selected.append(items[0]);duplicates.extend({'kept':items[0]['job_id'],'excluded':x['job_id'],'title':x['title'],'reason':'same normalized authoritative display title'} for x in items[1:])
    # Identical substantial rendered lyrics can reveal exact aliases, without renaming identity.
    by_lyrics={};unique=[]
    for item in sorted(selected,key=lambda x:(x['published'],x['tier']=='high',x['created_at']),reverse=True):
        fingerprint=item['lyric_fingerprint']
        if fingerprint and fingerprint in by_lyrics:
            duplicates.append({'kept':by_lyrics[fingerprint]['job_id'],'excluded':item['job_id'],'title':item['title'],'reason':'identical rendered lyric sequence (>=80 characters)'})
        else:
            if fingerprint:by_lyrics[fingerprint]=item
            unique.append(item)
    unique.sort(key=lambda x:(x['source'],x['title']))
    for index,item in enumerate(unique):
        item.update(probe(item['path']));item['index']=index+1
        save(WORK/'inventory-progress.json',{'probed':index+1,'total':len(unique)})
    manifest={'version':VERSION,'created_at':time.time(),'source_projects':len(rows),'selected':unique,'duplicates':duplicates,'excluded':excluded,'artist_conflicts':conflicts,
              'total_seconds':sum(x['duration'] for x in unique)}
    target=WORK/'manifest.json'
    if target.exists():
        archive=WORK/'manifest-before-legacy-recovery.json'
        if archive.exists() or (WORK/'parts').exists() or (WORK/'preview.json').exists():raise RuntimeError('已开工或清单已有归档，拒绝覆盖')
        target.replace(archive)
    save(target,manifest)
    print(json.dumps({'source_projects':len(rows),'songs':len(unique),'duplicate_versions':len(duplicates),'excluded':excluded,
        'duration_hours':round(manifest['total_seconds']/3600,3),'artist_conflicts':conflicts,'titles':[x['title'] for x in unique]},ensure_ascii=False),flush=True)

def health_busy():
    endpoint=os.environ.get('COMPILATION_HEALTH_URL','http://studio-api:8000/api/automation/health')
    try:
        with urllib.request.urlopen(endpoint,timeout=5) as response:return json.load(response)['heavy_task_slot']['busy']
    except Exception:return True  # Fail closed rather than compete with an unobservable production task.

def reviewed_alias():
    # Manually compared the full openings/endings: the legacy mislabeled rendition
    # contains the same Chinese lyrics as the trusted high-confidence 讨厌 version.
    old_id='13c30fcb7b5049f7b32afdaa0e0587b1';keep_id='95ec5299d8264ff2bb26bdf8db3bb3c1'
    manifest=read(WORK/'manifest.json');rows=manifest['selected']
    old=next(x for x in rows if x['job_id']==old_id);keep=next(x for x in rows if x['job_id']==keep_id)
    assert old['title_unverified'] and keep['title']=='讨厌' and keep['tier']=='high'
    backup=WORK/'manifest-before-reviewed-alias.json'
    if backup.exists() or (WORK/'parts').exists():raise RuntimeError('已处理或已开工，不能重复修改清单')
    manifest['selected']=[x for x in rows if x['job_id']!=old_id]
    manifest['duplicates'].append({'kept':keep_id,'excluded':old_id,'title':old['title'],
        'reason':'explicit manual lyric review: same 讨厌 chorus/opening/ending, similarity 0.9349; authoritative identity untouched'})
    for i,row in enumerate(manifest['selected'],1):row['index']=i
    manifest['total_seconds']=sum(x['duration'] for x in manifest['selected'])
    (WORK/'manifest.json').replace(backup);save(WORK/'manifest.json',manifest)
    print(json.dumps({'songs':len(manifest['selected']),'hours':manifest['total_seconds']/3600,'duplicates':len(manifest['duplicates'])}),flush=True)

def review_aliases():
    from opencc import OpenCC
    cc=OpenCC('t2s');manifest=read(WORK/'manifest.json');rows=manifest['selected']
    backup=WORK/'manifest-before-alias-review.json'
    if backup.exists():raise RuntimeError('别名清单已核对，拒绝重复改写')
    c=sqlite3.connect('file:/data/studio.db?mode=ro',uri=True,timeout=30)
    def text(row):
        raw=c.execute('SELECT alignment FROM jobs WHERE id=?',(row['job_id'],)).fetchone()[0]
        lines=json.loads(raw or '{}').get('lines',[])
        return re.sub(r'[^\w\u4e00-\u9fff]','',cc.convert(''.join(x.get('text','') for x in lines if x.get('enabled') is not False)).casefold())
    removed=set();review=[]
    known={x['song_key']:x for x in rows if not x.get('title_unverified')}
    for old in rows:
        if not old.get('title_unverified'):continue
        label=old['title'].split('：',1)[-1]
        key=re.sub(r'\s+','',cc.convert(label).casefold());other=known.get(key)
        if not other:continue
        a,b=text(old),text(other);ratio=difflib.SequenceMatcher(None,a,b,autojunk=False).ratio()
        entry={'legacy_job':old['job_id'],'known_job':other['job_id'],'legacy_label':label,'ratio':round(ratio,4)}
        entry['duplicate']=len(a)>=80 and len(b)>=80 and ratio>=.9
        review.append(entry)
        if entry['duplicate']:
            removed.add(old['job_id']);manifest['duplicates'].append({'kept':other['job_id'],'excluded':old['job_id'],'title':label,'reason':'legacy folder label matches known title and aligned lyrics >=90% identical; identity unchanged'})
    manifest['selected']=[x for x in rows if x['job_id'] not in removed]
    for i,row in enumerate(manifest['selected'],1):row['index']=i
    manifest['total_seconds']=sum(x['duration'] for x in manifest['selected'])
    manifest['legacy_alias_review']=review
    manifest['review_conflicts']=[x for x in review if not x['duplicate']]
    (WORK/'manifest.json').replace(backup);save(WORK/'manifest.json',manifest)
    print(json.dumps({'songs':len(manifest['selected']),'hours':round(manifest['total_seconds']/3600,3),'review':review},ensure_ascii=False),flush=True)

def run(command,stage,guard=True):
    log=WORK/'ffmpeg.log'
    if guard:
        while health_busy():
            save(WORK/'progress.json',{'state':'waiting_for_production','stage':stage,'updated_at':time.time(),**CURRENT});time.sleep(15)
    with log.open('a',encoding='utf-8') as handle:
        process=subprocess.Popen(command,cwd=WORK,stdout=handle,stderr=handle,start_new_session=True)
        paused=False
        try:
            while process.poll() is None:
                busy=guard and health_busy()
                if busy!=paused:
                    with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGSTOP if busy else signal.SIGCONT)
                    paused=busy
                save(WORK/'progress.json',{'state':'paused_for_production' if paused else 'rendering','stage':stage,'updated_at':time.time(),**CURRENT})
                time.sleep(5)
            if process.returncode:raise RuntimeError(f'FFmpeg失败（{process.returncode}）：{stage}\n'+log.read_text(encoding='utf-8',errors='replace')[-3000:])
        except BaseException:
            with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGCONT);os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGKILL)
                process.wait()
            raise

def ffmpeg():return ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-filter_complex_threads','1','-filter_threads','1']
def encoder():return ['-c:v','libx264','-preset','veryfast','-crf','19','-threads','1','-bf','0','-pix_fmt','yuv420p','-r','30','-g','60','-keyint_min','60','-sc_threshold','0','-c:a','pcm_s16le','-ar','48000','-ac','2','-f','matroska']
def inputs(row,start,length):
    source_ok(row)
    return ['-threads','1','-ss',f'{start:.6f}','-t',f'{length:.6f}','-i',row['path']]
def filters(index,length,width,gain=0):
    height=width*9//16
    return (f'[{index}:v]fps=30,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.1,trim=duration={length:.6f},settb=1/30,setpts=N,fps=30[v{index}];'
            f'[{index}:a]aresample=48000,asetpts=PTS-STARTPTS,volume={gain:.4f}dB,apad=whole_dur={length:.6f},atrim=duration={length:.6f}[a{index}]')

def cached(target,duration):
    if not target.is_file():return False
    try:return abs(probe(target)['format_duration']-duration)<.1
    except Exception:return False

def body(row,start,length,target,width,gain=0,guard=True,fade_in=False,fade_out=False):
    if cached(target,length):return
    partial=target.with_suffix('.partial.mkv')
    graph=filters(0,length,width,gain)
    vmap='[v0]';amap='[a0]'
    if fade_in or fade_out:
        vf=[];af=[]
        if fade_in:vf.append('fade=t=in:st=0:d=0.15');af.append('afade=t=in:st=0:d=0.01')
        if fade_out:vf.append(f'fade=t=out:st={max(0,length-.15):.6f}:d=0.15');af.append(f'afade=t=out:st={max(0,length-.01):.6f}:d=0.01')
        graph+=';[v0]'+','.join(vf)+'[vf];[a0]'+','.join(af)+'[af]';vmap='[vf]';amap='[af]'
    run(ffmpeg()+inputs(row,start,length)+['-filter_complex',graph,'-map',vmap,'-map',amap]+encoder()+[str(partial)],row['title'],guard)
    if not cached(partial,length):raise RuntimeError('片段时长校验失败：'+row['title'])
    partial.replace(target)

def transition(left,right,length,target,width,gains=(0,0),guard=True):
    if cached(target,length):return
    partial=target.with_suffix('.partial.mkv')
    graph=filters(0,length,width,gains[0])+';'+filters(1,length,width,gains[1])
    graph+=f';[v0][v1]xfade=transition=fade:duration={length:.6f}:offset=0[v];[a0][a1]acrossfade=d={length:.6f}:c1=tri:c2=tri[a]'
    run(ffmpeg()+inputs(left,left['duration']-length,length)+inputs(right,0,length)+['-filter_complex',graph,'-map','[v]','-map','[a]']+encoder()+[str(partial)],left['title']+' → '+right['title'],guard)
    if not cached(partial,length):raise RuntimeError('转场时长校验失败')
    partial.replace(target)

def overlap(left,right):
    if left['lyric_last'] is None or right['lyric_first'] is None:return 0
    available=min(.8,left['duration']-left['lyric_last']-.35,right['lyric_first']-.35)
    return math.floor(max(0,available)*FPS)/FPS if available>=.2 else 0

def join(segments,target,chapters=None,guard=True):
    concat=target.with_suffix('.concat.txt')
    concat.write_text('ffconcat version 1.0\n'+''.join(f"file '{path.relative_to(WORK).as_posix()}'\nduration {duration:.9f}\n" for path,duration in segments),encoding='utf-8')
    extra=[]
    if chapters:
        metadata=target.with_suffix('.ffmetadata')
        def escape(text):return re.sub(r'([\\=;#])',r'\\\1',text.replace('\n',' '))
        metadata.write_text(';FFMETADATA1\n'+''.join(f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(start*1000)}\nEND={round(end*1000)}\ntitle={escape(title)}\n' for start,end,title in chapters),encoding='utf-8')
        extra=['-f','ffmetadata','-i',str(metadata),'-map_metadata','1','-map_chapters','1']
    partial=target.with_suffix('.partial.mp4')
    duration=sum(seconds for _,seconds in segments)
    run(ffmpeg()+['-f','concat','-safe','0','-i',str(concat)]+extra+['-map','0:v:0','-map','0:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-threads','1','-af','aresample=async=1:first_pts=0','-t',f'{duration:.6f}','-movflags','+faststart',str(partial)],'封装单集',guard)
    info=probe(partial)
    if abs(info['format_duration']-duration)>.2 or abs(info['video_start']-info['audio_start'])>.06:raise RuntimeError('最终时长或音视频起点校验失败')
    partial.replace(target);return info

def loudness(row):
    cache=WORK/'levels'/f"{row['job_id']}.json";cache.parent.mkdir(exist_ok=True)
    fingerprint=digest({k:row[k] for k in ('path','size','mtime_ns')})
    if cache.exists():
        saved=read(cache)
        if saved.get('fingerprint')==fingerprint:return saved['gain_db']
    report=WORK/'levels'/f"{row['job_id']}.txt"
    # Audio-only analysis; never use per-snippet loudness as a proxy for the entire song.
    command=ffmpeg()+['-threads','1','-i',row['path'],'-vn','-af','loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-']
    # loudnorm's diagnostic JSON is informational, requiring info log level.
    command[command.index('error')]='info'
    before=(WORK/'ffmpeg.log').stat().st_size if (WORK/'ffmpeg.log').exists() else 0
    run(command,'响度分析：'+row['title'])
    with (WORK/'ffmpeg.log').open('rb') as handle:handle.seek(before);text=handle.read().decode('utf-8',errors='replace')
    match=re.search(r'\{\s*"input_i".*?\}',text,re.S)
    if not match:raise RuntimeError('响度分析结果缺失')
    data=json.loads(match.group());integrated=float(data['input_i']);peak=float(data['input_tp'])
    if not math.isfinite(integrated) or not math.isfinite(peak):raise RuntimeError('音频响度无效')
    gain=max(-24,min(12,-18-integrated,-1.5-peak))
    save(cache,{'fingerprint':fingerprint,'gain_db':gain,'input_i':integrated,'input_tp':peak})
    return gain

def preview(manifest):
    chosen=[next(row for row in manifest['selected'] if row['title']==title) for title in ('回到过去','退后','爱琴海')]
    for row in chosen:source_ok(row)
    cache=WORK/'preview-parts';cache.mkdir(exist_ok=True)
    outputs=[]
    gains={row['job_id']:loudness(row) for row in chosen}
    for number,(left,right) in enumerate(zip(chosen,chosen[1:]),1):
        length=overlap(left,right)
        if not length:raise RuntimeError('试片转场没有可靠的非演唱余量')
        a=cache/f'{number}-tail.mkv';b=cache/f'{number}-transition.mkv';d=cache/f'{number}-head.mkv'
        body(left,left['duration']-12,12-length,a,960,gains[left['job_id']])
        transition(left,right,length,b,960,(gains[left['job_id']],gains[right['job_id']]))
        body(right,length,12-length,d,960,gains[right['job_id']])
        target=WORK/f'衔接试片{number:02d}.mp4'
        join([(a,12-length),(b,length),(d,12-length)],target)
        outputs.append({'path':str(target),'from':left['title'],'to':right['title'],'overlap_seconds':length})
    save(WORK/'preview.json',outputs);save(WORK/'progress.json',{'state':'preview_completed','outputs':outputs})
    print(json.dumps(outputs,ensure_ascii=False),flush=True)

def render(manifest):
    if manifest.get('artist_conflicts'):raise RuntimeError('同名歌曲存在不同歌手/不同歌词，需要先核对artist_conflicts清单')
    if manifest.get('review_conflicts'):raise RuntimeError('旧版同名歌歌词证据不足，需要先人工核对review_conflicts')
    fingerprint=digest({'version':VERSION,'rows':manifest['selected'],'transition':.8,'target_lufs':-18})
    cache=WORK/'parts'/fingerprint[:16];cache.mkdir(parents=True,exist_ok=True)
    rows=manifest['selected'];seams=[overlap(a,b) for a,b in zip(rows,rows[1:])]
    planned=0;draft=[]
    for index,row in enumerate(rows):
        draft.append({'start_seconds':planned,'title':row['title'],'job_id':row['job_id'],'title_unverified':row.get('title_unverified',False)})
        planned+=row['duration']-(seams[index] if index<len(seams) else 0)
    save(WORK/'planned-playlist.json',{'entries':draft,'expected_seconds':planned,'order':'recording date and source filename; no speed/pitch changes'})
    segments=[];starts=[];elapsed=0
    for index,row in enumerate(rows):
        CURRENT.update(track=index+1,total_tracks=len(rows),title=row['title'])
        source_ok(row);gain=loudness(row)
        left=seams[index-1] if index else 0;right=seams[index] if index<len(seams) else 0
        starts.append(max(0,elapsed-left))
        path=cache/f'{index:03d}-body.mkv';length=row['duration']-left-right
        body(row,left,length,path,1920,gain,fade_in=index>0 and not left,fade_out=index<len(rows)-1 and not right)
        segments.append((path,length));elapsed+=length
        if right:
            other=rows[index+1];next_gain=loudness(other);edge=cache/f'{index:03d}-transition.mkv'
            transition(row,other,right,edge,1920,(gain,next_gain));segments.append((edge,right));elapsed+=right
        save(WORK/'completed-tracks.json',{'done':index+1,'total':len(rows),'elapsed_seconds':elapsed,'fingerprint':fingerprint})
    chapters=[(start,starts[i+1] if i+1<len(starts) else elapsed,rows[i]['title']) for i,start in enumerate(starts)]
    target=WORK/'小红泡_歌曲长篇合集_去重.mp4'
    if target.exists():raise RuntimeError('最终合集已存在，拒绝覆盖')
    info=join(segments,target,chapters)
    def stamp(seconds):
        value=round(seconds);return f'{value//3600:02d}:{value%3600//60:02d}:{value%60:02d}'
    (WORK/'歌单时间轴.txt').write_text('\n'.join(f'{stamp(start)} {title}' for start,_,title in chapters)+'\n',encoding='utf-8')
    result={'state':'completed','output':str(target),'songs':len(rows),'fingerprint':fingerprint,'probe':info,
            'no_overlap_boundaries':[{'from':a['title'],'to':b['title']} for a,b,t in zip(rows,rows[1:],seams) if not t]}
    save(WORK/'result.json',result);save(WORK/'progress.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inventory','review','reviewed-alias','preview','render']);args=parser.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    with (WORK/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            if args.action=='inventory':inventory()
            elif args.action=='review':review_aliases()
            elif args.action=='reviewed-alias':reviewed_alias()
            elif args.action=='preview':preview(read(WORK/'manifest.json'))
            else:render(read(WORK/'manifest.json'))
        except Exception as exc:
            save(WORK/'progress.json',{'state':'failed','error':str(exc),'at':time.time()});raise

if __name__=='__main__':main()
