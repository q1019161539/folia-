"""Isolated editorial cut. Sources/DB are read-only; no production job or upload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/edit')
IDS = {'A':'bb7f52c750104d038615d56ad6316027', 'B':'cfeb008f758a4759ad3366547f03f9dc', 'C':'4fc7dff4534a49b48b19eb495393b174'}
# Source-relative seconds, full chronological progression except marked bookends.
SHOTS = [
 ('hook','A',1923.78,1926.80,'温柔教练？', 'gold'),
 ('spoiler','C',2067.55,2071.45,'先看一眼结局', 'red'),
 ('setup','A',1921.30,1926.80,'开玩前：自信满满', 'gold'),
 ('promise','A',1970.36,1987.05,'人设：最温柔的女教练', 'gold'),
 ('ready','B',2166.95,2173.14,'开玩前 · 再次确认人设', 'gold'),
 ('gentle','B',2534.9,2545.25,'第一阶段：耐心教学', 'mint'),
 ('praise','B',2920.18,2924.8,'第二阶段：夸夸教育', 'mint'),
 ('calm','C',324.65,328.75,'第三阶段：让我冷静一下', 'orange'),
 ('mindset','C',447.15,457.35,'开始调整心态……', 'orange'),
 ('fifteen','C',1942.85,1952.05,'交流额度：15 字', 'orange'),
 ('five','C',1999.08,2011.05,'交流额度：5 字', 'red'),
 ('angry','C',2067.45,2079.6,'温柔额度：已用完', 'red'),
 ('bye','C',3509.95,3525.0,'最终方案：下班，降火', 'red'),
 ('callback','A',1984.55,1987.0,'回顾一下开场宣言', 'gold'),
]
# Correct only clear transcription errors in selected lines; preserve raw transcript.
FIX = {
 ('A',768):'我将会成为 B 站史上',
 ('A',769):'教妹妹开车最温柔的女教练',
 ('C',166):None,
 ('C',967):None,
 ('C',1716):None,
 ('C',1717):'降降火，我要降火',
}

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError('Command failed: '+str(cmd[0])+'\n'+p.stderr[-4000:])
    return p.stdout

def probe(p):
    return json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(p)]))

def write_json(p, value):
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(p)

def prepare():
    ROOT.mkdir(exist_ok=True)
    if (ROOT/'manifest.json').exists():
        m=json.loads((ROOT/'manifest.json').read_text())
        shots=[dict(zip(('id','source','start','end','label','theme'),x)) for x in SHOTS]
        if m['shots']!=shots:
            assert not list(ROOT.glob('*.mkv')),'Cannot change timeline after rendering starts'
            m['shots']=shots;write_json(ROOT/'manifest.json',m)
        return m
    records=json.loads((ROOT/'source-records.json').read_text(encoding='utf-8'))
    sources={}
    for key,rid in IDS.items():
        r=records[key]
        p=Path('/sources')/r['source']
        assert p.is_file(),str(p)
        s=p.stat()
        sources[key]={'path':str(p),'size':s.st_size,'mtime_ns':s.st_mtime_ns,'probe':probe(p),'transcript':r['transcript']}
    manifest={'sources':sources,'shots':[dict(zip(('id','source','start','end','label','theme'),x)) for x in SHOTS],
              'created_at':time.time(),'method':'ASR-guided editorial cut; transcript has no speaker diarization; human listening still required',
              'no_upload':True,'no_new_ai_requests':True}
    write_json(ROOT/'manifest.json',manifest)
    return manifest

def inspect(m):
    times={'A':[1924.5,1983.0],'B':[2538,2922],'C':[325.8,1946,2000,2071,3515]}
    for key,items in times.items():
        for t in items:
            out=ROOT/f'frame-{key}-{t}.jpg'
            if not out.exists():run(['ffmpeg','-v','error','-threads','1','-ss',str(t),'-i',m['sources'][key]['path'],'-frames:v','1','-vf','scale=960:-2','-q:v','3',str(out)])
    selected=[]
    for shot in m['shots']:
        selected.append({'shot':shot, 'segments':[s for s in m['sources'][shot['source']]['transcript'] if s['end']>shot['start'] and s['start']<shot['end']]})
    write_json(ROOT/'selected-transcript.json',selected)
    print(json.dumps({'frames':len(list(ROOT.glob('frame-*.jpg'))),'seconds':sum(s['end']-s['start'] for s in m['shots'])},ensure_ascii=False),flush=True)

def ass_time(t):
    v=round(max(0,t)*100)
    return f'{v//360000}:{v//6000%60:02}:{v//100%60:02}.{v%100:02}'

def clean(s):
    return str(s).replace('\\','').replace('{','').replace('}','').replace('\n',' ')

def captions(m,shot,index):
    duration=shot['end']-shot['start']
    colors={'gold':'&H0085DFFF','mint':'&H00C5F2A4','orange':'&H0079B9FF','red':'&H009999FF'}
    col=colors[shot['theme']]
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Speech,Noto Sans CJK SC,59,&H00FFFFFF,&H00FFFFFF,&H00171018,&H99000000,-1,0,0,0,100,100,1,0,1,4,1,2,110,110,76,1
Style: Sister,Noto Sans CJK SC,59,&H00FFDFAC,&H00FFFFFF,&H00171018,&H99000000,-1,0,0,0,100,100,1,0,1,4,1,2,110,110,76,1
Style: Label,Noto Sans CJK SC,42,&H00FFFFFF,&H00FFFFFF,&H00201725,&H99000000,-1,0,0,0,100,100,1,0,1,3,1,7,65,65,147,1
Style: Badge,Noto Sans CJK SC,34,&H00E6E6E6,&H00FFFFFF,&H00171018,&H99000000,-1,0,0,0,100,100,0,0,1,2,0,9,55,55,53,1
Style: Impact,Noto Sans CJK SC,91,&H00FFFFFF,&H00FFFFFF,&H00171018,&H99000000,-1,0,0,0,100,100,2,0,1,5,2,5,100,100,70,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[]
    def ev(a,b,style,txt,layer=1):
        if b>a:events.append(f'Dialogue: {layer},{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{txt}')
    ev(0,duration,'Label',r'{\fad(100,100)\c'+col+'}'+clean(shot['label']))
    ev(0,duration,'Badge',r'{\alpha&H28&}小红泡 · 教妹妹开车')
    for s in m['sources'][shot['source']]['transcript']:
        a=max(0,s['start']-shot['start']);b=min(duration,s['end']-shot['start'])
        if b<=a or b-a<.16:continue
        text=FIX.get((shot['source'],s.get('segment_id')),s['text'])
        if text is None:continue
        # Avoid guessing unclear ASR or inventing a speaker identity.
        overrides={
          '我搓气的不行':'', '我现在看到他脸':'我现在看到她脸',
          '你每句话只能说15个字以内':'你每句话只能说十五个字以内',
          '你每句话只能说五个字以内':'你每句话只能说五个字以内',
          '我需要去吃点那个酱火药':'', '我需要去吃點那個醬火藥':'',
          '喝点植花茶 酱酱火 我要酱火':'喝点菊花茶，降降火，我要降火',
          '喝點植花茶 醬醬火 我要醬火':'喝点菊花茶，降降火，我要降火',
          '就這樣吧 明天再播吧':'就这样吧，明天再播吧',
          '明天中午11點播 朋友們':'明天中午十一点播，朋友们',
          '我下班了 我受不了這個妹妹了':'我下班了，我受不了这个妹妹了',
          '玩玩教妹妹开车':'玩玩《教妹妹开车》',
        }
        text=overrides.get(text,text)
        if not text:continue
        style='Speech'
        if shot['source']=='C' and s.get('segment_id') in (933,968,969):
            style='Sister';text='妹妹：'+text
        fx=r'{\fad(50,70)}'
        if any(w in text for w in ('我脾气很好','不可能有比我温柔','我好生气','十五个字','五个字')):
            fx=r'{\fad(50,70)\c'+col+r'\fscx108\fscy108\t(0,140,\fscx100\fscy100)}'
        ev(a,b,style,fx+clean(text))
    if shot['id']=='spoiler':
        ev(.2,min(duration,2.6),'Impact',r'{\pos(960,420)\c&H009999FF&\fad(80,120)}说好的不生气呢？')
    if shot['id']=='setup':
        ev(0,min(duration,1.4),'Impact',r'{\pos(960,400)\fad(80,180)\c&H0085DFFF&}时间倒回开玩前')
    if shot['id']=='five':
        ev(.1,2.3,'Impact',r'{\pos(960,400)\fad(100,150)\c&H009999FF&}15 字 → 5 字')
    if shot['id']=='callback':
        ev(.1,duration,'Impact',r'{\pos(960,400)\fad(100,250)\c&H0085DFFF&}温柔教练 · 今日结业')
    p=ROOT/f'{index:02}-{shot["id"]}.ass'
    p.write_text(header+'\n'.join(events)+'\n',encoding='utf-8')
    return p

def smoke(m):
    for ident in ('setup','gentle','five','angry','callback'):
        i,shot=next((i,s) for i,s in enumerate(m['shots']) if s['id']==ident)
        ass=captions(m,shot,i)
        # Shift selected footage into the ASS test interval without changing the real cut.
        seek=shot['start']+(.5 if ident!='five' else 1.5)
        vf=f"scale=1920:1080,drawbox=x=0:y=942:w=iw:h=138:color=black@0.72:t=fill,drawbox=x=35:y=125:w=1020:h=98:color=black@0.55:t=fill,setpts=PTS-STARTPTS+1/TB,ass={ass},scale=960:540"
        run(['ffmpeg','-v','error','-threads','1','-ss',str(seek),'-i',m['sources'][shot['source']]['path'],'-vf',vf,'-frames:v','1','-filter_threads','1','-y',str(ROOT/f'qa-{ident}.jpg')])
    print('ASS and font smoke checks passed',flush=True)

def render(m):
    assert not (ROOT/'小红泡_最温柔的教练_反差精剪_v1.mp4').exists(),'Final exists; will not overwrite'
    outputs=[]
    for i,shot in enumerate(m['shots']):
        source=m['sources'][shot['source']];p=Path(source['path']);st=p.stat()
        assert (st.st_size,st.st_mtime_ns)==(source['size'],source['mtime_ns'])
        duration=shot['end']-shot['start'];ass=captions(m,shot,i)
        out=ROOT/f'{i:02}-{shot["id"]}.mkv'
        write_json(ROOT/'progress.json',{'status':'rendering','shot':i+1,'total':len(m['shots']),'label':shot['label'],'updated_at':time.time()})
        if not out.exists():
            # Read only selected source window. Slight punch-in never removes the game context.
            vf='scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30'
            if shot['id'] in ('spoiler','angry'):
                vf+=",eq=saturation=0.86:contrast=1.04,crop=1880:1058:x='20+4*sin(n*1.8)':y='11+2*sin(n*2.3)',scale=1920:1080"
            if shot['id']=='callback':vf+=',eq=saturation=0.55'
            # Dedicated lower caption rail keeps original game text separate.
            vf+=",drawbox=x=0:y=942:w=iw:h=138:color=black@0.72:t=fill,drawbox=x=35:y=125:w=1020:h=98:color=black@0.55:t=fill"
            vf+=f",ass={ass},fade=t=in:st=0:d=0.045,fade=t=out:st={max(0,duration-.055):.3f}:d=0.055"
            temp=out.with_suffix('.partial.mkv')
            cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-threads','1','-ss',str(shot['start']),'-i',str(p),'-t',str(duration),'-map','0:v:0','-map','0:a:0','-vf',vf,'-af',f'aresample=48000,asetpts=PTS-STARTPTS,afade=t=in:d=0.009,afade=t=out:st={duration-.012:.3f}:d=0.012','-filter_threads','1','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','1','-bf','0','-g','60','-c:a','pcm_s16le','-ar','48000','-ac','2','-y',str(temp)]
            run(cmd);temp.replace(out)
        outputs.append(out)
    concat=ROOT/'concat.txt';concat.write_text(''.join(f"file '{p}'\n" for p in outputs),encoding='utf-8')
    temp=ROOT/'final.partial.mp4';final=ROOT/'小红泡_最温柔的教练_反差精剪_v1.mp4'
    run(['ffmpeg','-hide_banner','-v','error','-nostdin','-f','concat','-safe','0','-i',str(concat),'-map','0:v:0','-map','0:a:0','-c:v','copy','-af','alimiter=limit=0.891:level=false:latency=true','-c:a','aac','-b:a','192k','-movflags','+faststart','-y',str(temp)])
    result=probe(temp)
    run(['ffmpeg','-v','error','-threads','1','-i',str(temp),'-map','0:v:0','-map','0:a:0','-f','null','-'])
    for source in m['sources'].values():
        st=Path(source['path']).stat();assert (st.st_size,st.st_mtime_ns)==(source['size'],source['mtime_ns'])
    temp.replace(final)
    result.update({'file':str(final),'source_stats_unchanged':True,'full_decode_ok':True,'sha256':hashlib.sha256(final.read_bytes()).hexdigest(),'no_upload':True})
    write_json(ROOT/'result.json',result)
    write_json(ROOT/'progress.json',{'status':'completed','file':str(final),'updated_at':time.time()})
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','smoke','render']);args=parser.parse_args()
    m=prepare()
    if args.action=='inspect':inspect(m)
    elif args.action=='smoke':smoke(m)
    else:render(m)
