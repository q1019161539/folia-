import ctypes, gc, json, os, subprocess, tempfile, threading
from pathlib import Path

# Set before importing Hugging Face consumers: Qwen also loads its processor
# separately and does not forward model kwargs to that second load.
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'

from fastapi import FastAPI, File, Form, UploadFile
from faster_whisper import WhisperModel

app=FastAPI(title='Folia Local Speech Worker')
lock=threading.Lock(); whisper_model=None; aligner_model=None
MODEL=os.getenv('WHISPER_MODEL','large-v3-turbo'); DEVICE=os.getenv('WHISPER_DEVICE','cpu'); COMPUTE=os.getenv('WHISPER_COMPUTE_TYPE','int8')
ALIGNER_MODEL=os.getenv('ALIGNER_MODEL','Qwen/Qwen3-ForcedAligner-0.6B')

def unload_aligner():
    global aligner_model
    if aligner_model is not None: aligner_model=None; gc.collect()

def unload_whisper():
    global whisper_model
    if whisper_model is not None: whisper_model=None; gc.collect()

def trim_memory():
    gc.collect()
    try: ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception: pass

def get_whisper():
    global whisper_model
    if whisper_model is None:
        unload_aligner(); whisper_model=WhisperModel(MODEL,device=DEVICE,compute_type=COMPUTE,download_root='/models/whisper')
    return whisper_model

def local_aligner_snapshot():
    candidate=Path(ALIGNER_MODEL).expanduser()
    if candidate.is_dir():
        snapshot=candidate.resolve()
    else:
        from huggingface_hub import snapshot_download
        try:
            snapshot=Path(snapshot_download(repo_id=ALIGNER_MODEL,local_files_only=True)).resolve()
        except Exception as exc:
            raise RuntimeError(f'Qwen 离线模型缓存不可用：{ALIGNER_MODEL}；请预先安装完整模型缓存') from exc
    required=('config.json','model.safetensors','preprocessor_config.json','tokenizer_config.json','vocab.json','merges.txt')
    missing=[name for name in required if not (snapshot/name).is_file() or (snapshot/name).stat().st_size<=0]
    if missing:
        raise RuntimeError('Qwen 离线模型缓存不完整：'+', '.join(missing))
    return str(snapshot)

def get_aligner():
    global aligner_model
    if aligner_model is None:
        unload_whisper()
        snapshot=local_aligner_snapshot()
        import torch
        from qwen_asr import Qwen3ForcedAligner
        torch.set_num_threads(max(1,min(10,os.cpu_count() or 1)))
        aligner_model=Qwen3ForcedAligner.from_pretrained(snapshot,device_map='cpu',dtype=torch.float32,local_files_only=True)
    return aligner_model

@app.get('/healthz')
def health():
    return {'ok':True,'model':MODEL,'loaded':whisper_model is not None,'aligner':ALIGNER_MODEL,'aligner_loaded':aligner_model is not None,'aligner_offline':True,'device':DEVICE,'compute_type':COMPUTE}

@app.post('/unload')
def unload():
    with lock:
        unloaded={'whisper':whisper_model is not None,'aligner':aligner_model is not None}
        unload_whisper(); unload_aligner(); trim_memory()
    return {'ok':True,'unloaded':unloaded,'loaded':False,'aligner_loaded':False}

@app.post('/recognize')
def recognize(file:UploadFile=File(...),language:str=Form('zh'),vad_filter:bool=Form(True),word_timestamps:bool=Form(True)):
    suffix=Path(file.filename or 'input.mp4').suffix
    with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as f:
        while chunk:=file.file.read(1024*1024): f.write(chunk)
        name=f.name
    try:
        with lock:
            segments,info=get_whisper().transcribe(
                name,language=language,beam_size=5,word_timestamps=word_timestamps,vad_filter=vad_filter,
                condition_on_previous_text=False,chunk_length=15,
                hallucination_silence_threshold=2.0,
                vad_parameters={'min_silence_duration_ms':500,'speech_pad_ms':200},
            )
            out=[]; texts=[]
            for s in segments:
                words=[{'text':w.word,'start_ms':round(w.start*1000),'end_ms':round(w.end*1000),'probability':round(w.probability,3)} for w in (s.words or [])]
                confidence=sum(x['probability'] for x in words)/len(words) if words else .7
                out.append({'start':s.start,'end':s.end,'text':s.text,'confidence':confidence,'words':words}); texts.append(s.text.strip())
        return {'text':' '.join(texts),'language':info.language,'duration':info.duration,'segments':out}
    finally: os.unlink(name)

def repair_items(items,start_ms,end_ms):
    """Repair zero-duration spans occasionally returned by qwen-asr 0.0.6."""
    clean=[]
    for item in items:
        text=str(getattr(item,'text','') or '')
        if not text: continue
        start=round(float(getattr(item,'start_time',0) or 0)*1000)+start_ms
        end=round(float(getattr(item,'end_time',0) or 0)*1000)+start_ms
        clean.append({'text':text,'start_ms':start,'end_ms':end})
    if not clean: return []
    ceiling=max(start_ms+1,end_ms)
    positive=sorted(max(1,x['end_ms']-x['start_ms']) for x in clean if x['end_ms']>x['start_ms'] and x['end_ms']-x['start_ms']<=3000)
    typical=positive[len(positive)//2] if positive else 160
    for i,item in enumerate(clean):
        item['start_ms']=max(start_ms,min(ceiling-1,item['start_ms']))
        next_start=clean[i+1]['start_ms'] if i+1<len(clean) else min(ceiling,item['start_ms']+typical)
        if item['end_ms']<=item['start_ms']: item['end_ms']=max(item['start_ms']+30,next_start)
        item['end_ms']=max(item['start_ms']+1,min(ceiling,item['end_ms']))
    return clean

def media_duration_ms(path:Path):
    proc=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],capture_output=True,text=True)
    if proc.returncode: return 0
    try: return max(0,round(float(proc.stdout.strip())*1000))
    except Exception: return 0

@app.post('/force-align')
def force_align(file:UploadFile=File(...),lines_json:str=Form(...),language:str=Form('Chinese'),padding_ms:int=Form(900)):
    lines=json.loads(lines_json); suffix=Path(file.filename or 'input.mp4').suffix
    with tempfile.TemporaryDirectory(prefix='folia-align-') as tempdir:
        source=Path(tempdir)/('source'+suffix)
        with source.open('wb') as f:
            while chunk:=file.file.read(1024*1024): f.write(chunk)
        source_duration=media_duration_ms(source)
        results=[]
        with lock:
            model=get_aligner()
            for index,line in enumerate(lines):
                coarse_start=max(0,int(line.get('start_ms',0))); coarse_end=max(coarse_start+200,int(line.get('end_ms',coarse_start+2500)))
                clip_start=max(0,coarse_start-max(0,padding_ms)); clip_end=min(source_duration,coarse_end+max(0,padding_ms)); wav=Path(tempdir)/f'{index:04d}.wav'
                if source_duration<=0 or clip_end-clip_start<100:
                    results.append({'index':int(line.get('index',index)),'error':'alignment window is outside valid media duration'}); continue
                proc=subprocess.run(['ffmpeg','-loglevel','error','-y','-ss',f'{clip_start/1000:.3f}','-to',f'{clip_end/1000:.3f}','-i',str(source),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],capture_output=True,text=True)
                if proc.returncode or not wav.is_file() or wav.stat().st_size<6400 or media_duration_ms(wav)<100:
                    results.append({'index':int(line.get('index',index)),'error':'audio extraction failed'}); continue
                try:
                    aligned=model.align(audio=str(wav),text=str(line.get('text','')),language=language)[0]
                    results.append({'index':int(line.get('index',index)),'items':repair_items(aligned.items,clip_start,clip_end),'window_start_ms':clip_start,'window_end_ms':clip_end})
                except Exception as exc: results.append({'index':int(line.get('index',index)),'error':str(exc)[:300]})
        return {'model':ALIGNER_MODEL,'lines':results}
