"""Song-scoped AI covers and BililiveTool submission; no Bilibili uploader here."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import threading
import time
import traceback
import unicodedata
import uuid
from sqlite_runtime import is_busy_error, short_write
import httpx
from opencc import OpenCC
from PIL import Image
from cover_frames import select_reference_frame, validate_region
from cover_fallback import (CoverError, GeminiCoverClient, use_gemini_for_cover,
    fallback_configured, provided_reference, HALF_BODY_INSTRUCTION)
from recorder_identity import recording_start_time
from title_generation import generate_publish_title, song_display_title
from performance_gate import gate_settings, decide_volume, VERSION as GATE_VERSION
from publishing import (BililiveToolClient, PublishPrepareError, PublishRetryableError,
    build_title, build_description, build_tags, build_payload, map_to_bililive_path,
    merge_preset_config, preset_description_template, json_text, retry_delay_seconds)

LOCK = threading.Lock()
COVER_MAX_ATTEMPTS = 10


class PublishPaused(Exception):
    """A user pause is neither a preparation failure nor a new paid attempt."""


T2S = OpenCC('t2s')
DEFAULT_REGIONS = {'芒芒_Mou':[.32,.08,.74,.78], '小红泡-管珩心':[.37,.18,.69,.74]}
PROMPT = '''根据参考图生成16:9歌曲封面。保持参考人物的脸型、五官比例、瞳色、发型和标志性配饰，不重新设计面部，必须看得出是同一个人物。表情、视线、动作和姿态可以根据歌曲“{song}”的风格与氛围自然变化，让人物生动有感染力。人物在右，左侧完整写出歌名“{song}”，歌名文字准确清晰，书名号可加可不加，由AI根据排版自由决定。字体、文字效果与背景根据歌曲氛围自由发挥，与人物画风协调。参考图仅用于保持人物身份，不沿用直播背景。根据歌曲独立设计场景、主色调和光线，避免统一套用同一种背景风格。去除直播界面、弹幕和字幕，不加主播名、额外文字或装饰横线。'''


def safe_error(value):
    text=str(value)
    for name in ('COVER_API_KEY','COVER_FALLBACK_API_KEY','BILILIVETOOL_PASSKEY','TITLE_API_KEY'):
        secret=os.getenv(name,'')
        if secret: text=text.replace(secret,'[redacted]')
    text=re.sub(r'sk-[A-Za-z0-9_-]+','[redacted]',text)
    return re.sub(r'(https?://[^\s?]+)\?[^\s]+',r'\1?[redacted]',text)


def log_exception():
    # Keep the full stack and exception chain, but redact credentials and signed URLs.
    print(safe_error(traceback.format_exc()),flush=True)


def normalized_title(title):
    value = unicodedata.normalize('NFKC', str(title or '')).strip()
    # Only explicit terminal performance annotations; never erase arbitrary brackets.
    value = re.sub(r'\s*(?:\((?:live|现场版|翻唱|cover(?:\s*[:：][^()]*)?)\)|\[(?:live|cover)\])\s*$', '', value, flags=re.I)
    return re.sub(r'\s+', '', T2S.convert(value)).casefold()


def broadcaster_key(profile):
    identity = profile.get('recorder_identity') or {}
    if identity.get('platform') and identity.get('room_id'):
        return f"{identity['platform']}:{identity['room_id']}"
    return 'profile:' + profile['id']


def completed_at(project):
    # A durable render watermark, not a mutable project updated_at timestamp.
    return float((project.get('output') or {}).get('finalized_at') or 0)


def eligible(project):
    output = project.get('output') or {}
    match = (project.get('alignment') or {}).get('timeline_match') or {}
    gate = (project.get('alignment') or {}).get('performance_gate') or {}
    if gate.get('decision') == 'skip': return False
    if gate and gate_settings()['enabled']:
        # A saved old-policy pass cannot bypass tighter rules at prepare/submit.
        try:
            if decide_volume(float(gate['mean_db']), float(gate['peak_db']), gate_settings())['decision'] != 'pass':
                return False
        except (KeyError, TypeError, ValueError, RuntimeError): return False
    return ((not project.get('render_revision_parent_id') or project.get('render_revision_publish') == 1)
            and project.get('status') == 'completed' and output.get('sample') is False
            and str(output.get('path') or '').lower().endswith('.mp4')
            and output.get('confidence_tier') == 'high' and match.get('confidence_tier') == 'high'
            and not match.get('song_identity_suspicious')
            and ((project.get('alignment') or {}).get('performance_gate') or {}).get('decision') != 'skip'
            and bool(str(project.get('identified_title') or '').strip()))


def init_schema(c):
    def columns(table, additions):
        names = {r[1] for r in c.execute(f'PRAGMA table_info({table})')}
        for name, definition in additions.items():
            if name not in names: c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    columns('automation_profiles', {'cover_region_json':"TEXT NOT NULL DEFAULT ''"})
    columns('publish_jobs', {'pipeline_version':'INTEGER NOT NULL DEFAULT 1',
        'song_project_id':'TEXT', 'failure_stage':'TEXT', 'submit_attempts':'INTEGER NOT NULL DEFAULT 0',
        'submit_started_at':'REAL', 'submit_before_json':'TEXT', 'upload_progress':'REAL DEFAULT 0',
        'next_review_at':'REAL','title_generation_json':'TEXT','priority_at':'REAL NOT NULL DEFAULT 0',
        'collection_status':'TEXT','collection_error':'TEXT','collection_attempts':'INTEGER NOT NULL DEFAULT 0',
        'next_collection_at':'REAL'})
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS publish_song_unique ON publish_jobs(song_project_id) WHERE song_project_id IS NOT NULL')
    c.execute('''CREATE TABLE IF NOT EXISTS song_projects(
        id TEXT PRIMARY KEY, broadcaster_key TEXT NOT NULL, song_key TEXT NOT NULL,
        streamer TEXT NOT NULL, identified_title TEXT NOT NULL, identified_artist TEXT,
        identity_source TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        cover_status TEXT NOT NULL DEFAULT 'pending', cover_attempts INTEGER NOT NULL DEFAULT 0,
        cover_error TEXT, cover_prompt TEXT, cover_model TEXT, reference_json TEXT,
        original_cover_path TEXT, cover_path TEXT, cover_sha256 TEXT, cover_dimensions_json TEXT,
        cover_attempt_started REAL, publish_job_id TEXT, conflict INTEGER NOT NULL DEFAULT 0,
        UNIQUE(broadcaster_key,song_key))''')
    c.execute('''CREATE TABLE IF NOT EXISTS song_performances(
        source_job_id TEXT PRIMARY KEY, song_project_id TEXT, automation_run_id TEXT,
        identified_title TEXT, identified_artist TEXT, identity_source TEXT,
        video_path TEXT, disposition TEXT NOT NULL, reason TEXT, created_at REAL NOT NULL)''')
    c.execute("INSERT OR IGNORE INTO app_meta(key,value) VALUES('publish_v2_rollout','{\"mode\":\"acceptance\",\"allowlist\":[],\"cutover\":0}')")


def image_bytes(raw):
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height > 40_000_000: raise ValueError('too many pixels')
            image.load()
            if min(image.size) < 512 or abs(image.width/image.height-16/9) > .08:
                raise ValueError('invalid dimensions/aspect ratio')
            return image.copy().convert('RGB'), image.format
    except Exception as exc:
        raise CoverError('生图返回的图片不可读或不符合横版尺寸要求', True) from exc


class GPTCoverClient:
    def __init__(self, transport=None):
        self.key = os.getenv('COVER_API_KEY','').strip()
        self.base = os.getenv('COVER_API_BASE_URL','https://www.codex789.com/v1').rstrip('/')
        self.model = os.getenv('COVER_API_MODEL','gpt-image-2')
        self.proxy = os.getenv('COVER_API_PROXY','').strip() or None
        self.transport = transport

    def generate(self, reference, prompt):
        if not self.key: raise CoverError('COVER_API_KEY 未配置')
        try:
            with httpx.Client(timeout=600, transport=self.transport, proxy=self.proxy, follow_redirects=False) as client:
                with Path(reference).open('rb') as handle:
                    response = client.post(self.base+'/images/edits',
                        headers={'Authorization':'Bearer '+self.key},
                        data={'model':self.model,'prompt':prompt,'n':'1','size':'2048x1152','quality':'high','output_format':'png'},
                        files={'image':(Path(reference).name,handle,'image/png')})
                if response.status_code != 200:
                    # Never log upstream bodies: these may contain tokens or signed URLs.
                    retryable = response.status_code >= 500
                    raise CoverError(f'GPT 生图 HTTP {response.status_code}，请检查服务或账号额度',retryable)
                try:
                    items = response.json()['data']
                    if len(items) != 1: raise ValueError('expected one image')
                    item = items[0]
                    if item.get('b64_json'): return base64.b64decode(item['b64_json'],validate=True)
                    url = item.get('url','')
                    if not url.startswith('https://'): raise ValueError('invalid image URL')
                    download = client.get(url)  # no Authorization on artifact downloads
                    download.raise_for_status()
                    if len(download.content) > 50_000_000: raise ValueError('image too large')
                    return download.content
                except (KeyError,ValueError,TypeError,httpx.HTTPError) as exc:
                    raise CoverError('GPT 返回无效图片结果',True) from exc
        except httpx.RequestError as exc:
            raise CoverError('GPT 生图连接失败或超时',True) from exc


class PublishingV2:
    def __init__(self, db, settings, get_project, get_run, get_profile, cover_client_factory=GPTCoverClient,
                 bili_client_factory=None):
        self.db,self.settings,self.get_project,self.get_run,self.get_profile=db,settings,get_project,get_run,get_profile
        self.cover_factory=cover_client_factory
        self.bili_factory=bili_client_factory or (lambda: BililiveToolClient(settings.bililive_base_url,settings.bililive_passkey))
        self.database_failures_recovered=False

    def rollout(self):
        with self.db() as c:
            return json.loads(c.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0])

    def allowed(self, job_id, completed_at=0):
        state=self.rollout()
        if state['mode']=='paused': return False
        if job_id in state.get('allowlist',[]): return True
        if state['mode']=='active' and state.get('authorized_render_batches'):
            project=self.get_project(job_id)
            batch=project.get('render_revision_batch_id')
            grants=[g for g in state['authorized_render_batches'] if isinstance(g,dict) and g.get('batch_id')==batch]
            if grants:
                run=self.get_run_for_revision(project)
                gate=(project.get('alignment') or {}).get('performance_gate') or {}
                fingerprint=gate.get('input') or {}
                clip=Path(str(fingerprint.get('path') or '')).resolve()
                if not clip.is_file(): return False
                stat=clip.stat()
                return (any(g.get('profile_id')==run.get('profile_id') for g in grants)
                        and bool(project.get('render_revision_parent_id')) and eligible(project)
                        and (project.get('output') or {}).get('output_mode')=='smooth'
                        and gate.get('version')==GATE_VERSION
                        and gate.get('decision')=='pass' and gate.get('settings')==gate_settings()
                        and fingerprint=={'path':str(clip),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns})
        return (state['mode']=='active' and completed_at>state['cutover']
                and not any(start<=completed_at<=end for start,end in state.get('paused_periods',[])))

    def get_run_for_revision(self, project):
        with self.db() as c:
            row=c.execute('SELECT automation_run_id FROM publish_jobs WHERE source_job_id=?',(project['id'],)).fetchone()
        return self.get_run(row['automation_run_id']) if row else {}

    def set_automatic_enabled(self, enabled):
        # Serialize double clicks/concurrent operators and retain state across restarts.
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            state=json.loads(c.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0])
            now=time.time()
            if enabled:
                if state['mode']=='active': return state
                previous=state.get('resume_mode') if state['mode']=='paused' else state['mode']
                if previous!='active':
                    ids=state.get('allowlist') or []
                    if len(ids)!=2: raise PublishPrepareError('尚未完成两首验收')
                    for source in ids:
                        job=c.execute('SELECT * FROM publish_jobs WHERE source_job_id=?',(source,)).fetchone()
                        if not job or job['pipeline_version']!=2 or job['status']!='completed' or not job['aid']:
                            raise PublishPrepareError('两首验收均取得AID后才能开放新成片')
                    state['cutover']=now
                elif state.get('paused_at') is not None:
                    state.setdefault('paused_periods',[]).append([state['paused_at'],now])
                state.update(mode='active',enabled_at=now)
                state.pop('paused_at',None); state.pop('resume_mode',None)
            else:
                if state['mode']=='paused': return state
                state.update(resume_mode=state['mode'],mode='paused',paused_at=now)
            c.execute("UPDATE app_meta SET value=? WHERE key='publish_v2_rollout'",(json_text(state),))
            return state

    def row(self, table, id):
        if table not in ('song_projects','publish_jobs'): raise ValueError('invalid table')
        with self.db() as c: row=c.execute(f'SELECT * FROM {table} WHERE id=?',(id,)).fetchone()
        if row is None: raise PublishPrepareError('歌曲项目或投稿记录不存在')
        return dict(row)

    def update(self, table, id, **values):
        if table not in ('song_projects','publish_jobs'): raise ValueError('invalid table')
        values['updated_at']=time.time()
        def write(c):
            c.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in values)} WHERE id=?",(*values.values(),id))
            row=c.execute(f'SELECT * FROM {table} WHERE id=?',(id,)).fetchone()
            if row is None: raise PublishPrepareError('歌曲项目或投稿记录不存在')
            return dict(row)
        return short_write(self.db,write)

    def checkpoint(self, job, kind, values=None):
        """Durable external responses, not credentials; never a new upload request."""
        allowed={
            'title':{'title','title_generation_json'},
            'accepted':{'bililive_task_id','status','publish_error','failure_stage','next_retry_at'},
            'published':{'aid','status','publish_result','published_at','upload_progress','publish_error','next_review_at'},
        }
        if kind not in allowed: raise ValueError('invalid checkpoint kind')
        root=self.settings.output_root/'publish'/'songs'/job['song_project_id']/'checkpoints'
        path=root/f'{job["id"]}-{kind}.json'
        keys=('id','source_job_id','song_project_id','identified_title','identified_artist',
              'identity_source','streamer','video_path','video_size','video_mtime','bililive_uid','bililive_preset_id')
        if kind=='title':
            # Authorized re-renders reuse wording for the same authoritative song.
            keys=('id','song_project_id','identified_title','identified_artist','identity_source','streamer')
        fingerprint={key:job.get(key) for key in keys}
        if kind!='title':
            fingerprint['payload_sha256']=hashlib.sha256((job.get('bililive_payload_json') or '').encode()).hexdigest()
        if values is not None:
            if set(values)-allowed[kind]: raise ValueError('invalid checkpoint fields')
            root.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.partial')
            with temporary.open('w',encoding='utf-8') as handle:
                handle.write(json_text({'input':fingerprint,'values':values}))
                handle.flush(); os.fsync(handle.fileno())
            temporary.replace(path)
            return values
        if not path.is_file(): return None
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('input')!=fingerprint or set(data.get('values',{}))-allowed[kind]:
            raise PublishPrepareError('投稿恢复记录与输入不一致，请人工核对；不再次提交')
        return data['values']

    def recover_responses(self, job):
        for kind,key in (('accepted','bililive_task_id'),('published','aid')):
            saved=self.checkpoint(job,kind)
            if not saved: continue
            if job.get(key) and str(job[key])!=str(saved.get(key)):
                raise PublishPrepareError('投稿恢复任务ID/AID冲突，请人工核对')
            if not job.get(key): job=self.update('publish_jobs',job['id'],**saved)
        return job

    def recover_database_failures(self):
        # Only never-submitted V2 failures. IDs/attempts/assets survive.
        def recover(c):
            c.execute("UPDATE publish_jobs SET status=CASE WHEN failure_stage='submit' THEN 'ready' ELSE 'pending' END,next_retry_at=?,updated_at=? "
                      "WHERE pipeline_version=2 AND status='failed' AND "
                      "lower(publish_error) IN ('database is locked','database table is locked','database schema is locked') "
                      "AND submit_attempts=0 AND bililive_task_id IS NULL AND aid IS NULL AND bvid IS NULL "
                      "AND (failure_stage IN ('metadata','title','cover','prepare') OR "
                      "(failure_stage='submit' AND bililive_payload_json IS NOT NULL AND bililive_payload_json<>'{}'))",
                      (time.time()+10,time.time()))
        short_write(self.db,recover)

    def attach(self, project, run, profile, legacy=False, enqueue=False):
        title=str(project.get('identified_title') or '').strip()
        artist=str(project.get('identified_artist') or '').strip()
        if not title: return None
        output=project.get('output') or {}; now=time.time(); source=project['id']
        priority_at=(recording_start_time(run.get('source'),profile.get('recorder_identity')).timestamp()
                     if enqueue and project.get('render_revision_parent_id') else 0)
        key=normalized_title(title)
        # Do not open a second connection / inspect source files under a write lock.
        scope_allowed=legacy or enqueue or self.allowed(source,completed_at(project))
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO song_projects(id,broadcaster_key,song_key,streamer,identified_title,identified_artist,identity_source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (uuid.uuid4().hex,broadcaster_key(profile),key,profile.get('publish_streamer') or profile['name'],title,artist,project.get('identity_source'),now,now))
            song=dict(c.execute('SELECT * FROM song_projects WHERE broadcaster_key=? AND song_key=?',(broadcaster_key(profile),key)).fetchone())
            known={normalized_title(r[0]) for r in c.execute('SELECT identified_artist FROM song_performances WHERE song_project_id=? AND identified_artist IS NOT NULL',(song['id'],)) if str(r[0]).strip()}
            if song['identified_artist']: known.add(normalized_title(song['identified_artist']))
            conflict=bool(artist and known and any(value!=normalized_title(artist) for value in known))
            if conflict: c.execute('UPDATE song_projects SET conflict=1,updated_at=? WHERE id=?',(now,song['id']))
            existing=c.execute('SELECT * FROM publish_jobs WHERE source_job_id=?',(source,)).fetchone()
            replace_revision=False
            if enqueue and project.get('render_revision_parent_id') and song['publish_job_id'] and not conflict:
                master=c.execute('SELECT * FROM publish_jobs WHERE id=?',(song['publish_job_id'],)).fetchone()
                if master and master['source_job_id']!=source and not (master['bililive_task_id'] or master['aid'] or master['bvid'] or master['status'] in ('submitting','uploading','completed','preparing')):
                    existing=master; replace_revision=True
            reason=''; disposition='candidate'
            if conflict: disposition,reason='blocked','同名歌曲歌手信息冲突，请人工核对'
            elif song['publish_job_id'] and (not existing or existing['id']!=song['publish_job_id']):
                disposition,reason='duplicate','同一主播重复歌曲，未生成封面或投稿'
            elif not legacy and not eligible(project): disposition,reason='ineligible','仅完整高置信且身份无可疑标记的成片可投稿'
            elif not legacy and not profile.get('bililive_preset_id'): disposition,reason='ineligible','未绑定主播投稿模板'
            c.execute('INSERT OR IGNORE INTO song_performances(source_job_id,song_project_id,automation_run_id,identified_title,identified_artist,identity_source,video_path,disposition,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (source,song['id'],run.get('id'),title,artist,project.get('identity_source'),output.get('path'),disposition,reason,now))
            if disposition in ('candidate',) and scope_allowed:
                video=Path(str(output.get('path') or '')).resolve()
                # Already-posted songs remain a deduplication guard even if the file was removed.
                if not legacy:
                    if not video.is_file(): raise PublishPrepareError('成片文件不存在')
                    map_to_bililive_path(video,self.settings)
                stat=video.stat() if video.is_file() else None
                if not existing:
                    pid=uuid.uuid4().hex
                    c.execute('INSERT INTO publish_jobs(id,source_job_id,automation_run_id,created_at,updated_at,status,publish_attempts,video_path,video_size,video_mtime,streamer,identified_title,identified_artist,identity_source,bililive_preset_id,bililive_uid,pipeline_version,song_project_id,priority_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (pid,source,run.get('id'),now,now,'pending',0,str(video),stat.st_size,stat.st_mtime,song['streamer'],title,artist,project.get('identity_source'),profile.get('bililive_preset_id'),self.settings.bililive_uid,2,song['id'],priority_at))
                else:
                    pid=existing['id']
                    if replace_revision:
                        c.execute("UPDATE publish_jobs SET source_job_id=?,automation_run_id=?,video_path=?,video_size=?,video_mtime=?,pipeline_version=2,song_project_id=?,status='pending',bililive_payload_json=NULL,validation_result_json=NULL,publish_error='',failure_stage=NULL,next_retry_at=NULL,updated_at=?,priority_at=? WHERE id=?",
                                  (source,run.get('id'),str(video),stat.st_size,stat.st_mtime,song['id'],now,priority_at,pid))
                    elif legacy:
                        c.execute('UPDATE publish_jobs SET song_project_id=? WHERE id=?',(song['id'],pid))
                    elif existing['pipeline_version']==1 and not existing['bililive_task_id'] and not existing['aid'] and existing['status'] in ('failed','ready','pending'):
                        c.execute("UPDATE publish_jobs SET pipeline_version=2,song_project_id=?,status='pending',bililive_payload_json=NULL,cover_path=NULL,publish_error='',failure_stage=NULL WHERE id=?",(song['id'],pid))
                c.execute('UPDATE song_projects SET publish_job_id=?,updated_at=? WHERE id=?',(pid,now,song['id']))
            return song['id']

    def seed_completed(self):
        with self.db() as c: rows=c.execute("SELECT * FROM publish_jobs WHERE (status='completed' OR aid IS NOT NULL OR bvid IS NOT NULL) AND song_project_id IS NULL").fetchall()
        for raw in rows:
            job=dict(raw)
            try:
                project=self.get_project(job['source_job_id']); run=self.get_run(job['automation_run_id']); profile=self.get_profile(run['profile_id'])
                project={**project,'identified_title':job['identified_title'],'identified_artist':job['identified_artist'],'identity_source':job['identity_source']}
                self.attach(project,run,profile,legacy=True)
            except Exception: log_exception()

    def cover(self, job):
        song=self.row('song_projects',job['song_project_id'])
        root=self.settings.output_root/'publish'/'songs'/song['id']; root.mkdir(parents=True,exist_ok=True)
        if song['cover_path']:
            cover=Path(song['cover_path'])
            if cover.is_file() and hashlib.sha256(cover.read_bytes()).hexdigest()==song['cover_sha256']:
                return cover
            raise CoverError('已保存封面缺失或损坏，需人工恢复，不自动重新扣费')
        # Recover a received original before spending another attempt, even after a crash.
        originals=sorted(root.glob('original-*.bin'),reverse=True)
        raw=None
        for original in originals:
            try: image_bytes(original.read_bytes()); raw=original.read_bytes(); break
            except CoverError: continue
        if raw is None:
            if song['cover_attempts']>=COVER_MAX_ATTEMPTS:
                raise CoverError(f'已达到每个歌曲项目 {COVER_MAX_ATTEMPTS} 次生图请求上限')
            fallback=use_gemini_for_cover(song['cover_attempts'])
            client=GeminiCoverClient() if fallback else self.cover_factory()
            if hasattr(client,'key') and not client.key: raise CoverError('生图密钥未配置')
            run=self.get_run(job['automation_run_id']); profile=self.get_profile(run['profile_id'])
            configured=profile.get('cover_region_json')
            region=json.loads(configured) if configured else DEFAULT_REGIONS.get(profile.get('publish_streamer') or profile['name'])
            frame=provided_reference(broadcaster_key(profile),root/'references',selection_key=song['song_key'])
            if frame is None:
                frame=select_reference_frame(job['video_path'],root/'references',streamer=song['streamer'],
                    regions={song['streamer']:region} if region else {})
            if frame['status']!='selected': raise CoverError('未找到合格参考帧，需要人工选帧')
            if self.rollout()['mode']=='paused': raise PublishPaused()
            prompt=PROMPT.format(song=song_display_title(job['identified_title']))+'\n'+HALF_BODY_INSTRUCTION
            number=song['cover_attempts']+1
            self.update('song_projects',song['id'],cover_status='generating',cover_attempts=number,
                cover_attempt_started=time.time(),cover_prompt=prompt,cover_model=getattr(client,'model','gpt-image-2'),reference_json=json_text(frame))
            attempt={'number':number,'provider':'gemini' if fallback else 'gpt','model':getattr(client,'model','gpt-image-2'),
                'status':'request_started','started_at':time.time(),'reference':frame,'prompt':prompt,
                'request_config':getattr(client,'request_config',None)}
            receipt=root/f'attempt-{number}.json'
            def save_attempt():
                partial=receipt.with_suffix('.partial'); partial.write_text(json_text(attempt),encoding='utf-8'); partial.replace(receipt)
            save_attempt()  # Persist provider/reference before the single paid POST; never store credentials.
            try:
                raw=client.generate(frame['frame_path'],prompt)
                original=root/f'original-{number}.bin'
                temporary=root/f'original-{number}.partial'; temporary.write_bytes(raw); temporary.replace(original)
                attempt.update(status='received',finished_at=time.time(),sha256=hashlib.sha256(raw).hexdigest())
                save_attempt()
            except Exception as exc:
                attempt.update(status='failed',finished_at=time.time(),error=safe_error(exc)[:1000])
                save_attempt()
                raise
        image,fmt=image_bytes(raw)
        original_dimensions=list(image.size)
        extension={'PNG':'png','JPEG':'jpg','WEBP':'webp'}.get(fmt,'bin')
        original_path=root/f'original.{extension}'
        if not original_path.exists(): original_path.write_bytes(raw)
        # Integer 16:9 crop only; never upscale, redraw, add text or erase a watermark.
        unit=min(image.width//16,image.height//9); w,h=unit*16,unit*9
        left=(image.width-w)//2; top=(image.height-h)//2
        image=image.crop((left,top,left+w,top+h))
        cover=root/'cover.jpg'; temporary=root/'cover.partial'
        image.save(temporary,format='JPEG',quality=95); temporary.replace(cover)
        self.update('song_projects',song['id'],cover_status='ready',cover_error='',original_cover_path=str(original_path),
            cover_path=str(cover),cover_sha256=hashlib.sha256(cover.read_bytes()).hexdigest(),cover_dimensions_json=json_text({'original':original_dimensions,'upload':[w,h]}))
        return cover

    def prepare(self, job):
        pid=job['id']; stage='metadata'; client=None
        try:
            if self.rollout()['mode']=='paused': return
            project=self.get_project(job['source_job_id'])
            if not eligible(project): raise PublishPrepareError('成片已不符合高置信/当前响度投稿条件')
            song=self.row('song_projects',job['song_project_id'])
            if song['conflict']: raise PublishPrepareError('歌曲身份有冲突，请人工核对')
            self.update('publish_jobs',pid,status='preparing',publish_attempts=job['publish_attempts']+1)
            video=Path(job['video_path']); stat=video.stat()
            if stat.st_size!=job['video_size'] or stat.st_mtime!=job['video_mtime']: raise PublishPrepareError('成片已变化，需人工核对')
            payload=json.loads(job.get('bililive_payload_json') or '{}')
            if not payload:
                display_title=song_display_title(job['identified_title'])
                run=self.get_run(job['automation_run_id']); profile=self.get_profile(run['profile_id'])
                recorded_at=recording_start_time(run.get('source'),profile.get('recorder_identity'))
                title_previous=json.loads(job.get('title_generation_json') or '{}')
                saved_title=self.checkpoint(job,'title')
                saved_record=json.loads((saved_title or {}).get('title_generation_json') or '{}')
                if (saved_title and int(saved_record.get('attempts',0))>=int(title_previous.get('attempts',0))
                        and (not job.get('title') or job.get('title_generation_json')!=saved_title['title_generation_json'])):
                    job=self.update('publish_jobs',pid,**saved_title)
                    title_previous=json.loads(job.get('title_generation_json') or '{}')
                if title_previous and job.get('title') and not (title_previous.get('retry_pending') or title_previous.get('in_flight')):
                    title=job['title']
                else:
                    stage='title'
                    def persist_title_attempt(record):
                        if self.rollout()['mode']=='paused': raise PublishPaused()
                        self.update('publish_jobs',pid,title_generation_json=json_text(record))
                    title,title_record=generate_publish_title(job['streamer'],job['identified_title'],job['identified_artist'],
                        lyrics=project.get('lyrics') or '',previous_record=title_previous,persist_record=persist_title_attempt)
                    # Freeze before cover generation; retries/restarts do not pay for a new title.
                    title_values={'title':title,'title_generation_json':json_text(title_record)}
                    self.checkpoint(job,'title',title_values)
                    self.update('publish_jobs',pid,**title_values)
                    if title_record.get('retry_pending'):
                        raise PublishRetryableError('AI标题临时失败，已保存次数并等待重试；耗尽后使用固定标题')
                tags=build_tags(job['streamer'],display_title,job['identified_artist'])
                if self.rollout()['mode']=='paused': raise PublishPaused()
                stage='cover'; cover=self.cover(job)
                stage='prepare'; client=self.bili_factory()
                preset=client.get_video_preset(job['bililive_preset_id'])
                description=client.format_description(preset_description_template(preset,build_description(job['streamer'],display_title,job['identified_artist'])),
                    {'title':display_title,'username':job['streamer'],
                     'time':recorded_at.isoformat(),
                     'roomId':str((profile.get('recorder_identity') or {}).get('room_id') or ''), 'filename':Path(run.get('source') or video.name).name})
                config=merge_preset_config(preset,title,description,tags,map_to_bililive_path(cover,self.settings))
                payload=build_payload(job['bililive_uid'],map_to_bililive_path(video,self.settings),display_title,config)
                collection={}
                if config.get('seasonId'):
                    client.collection_capabilities()
                    payload['options']['foliaCollectionTracking']=True
                    collection={'collection_status':'pending','collection_error':'','collection_attempts':0}
                self.update('publish_jobs',pid,title=title,description=description,tags_json=json_text(tags),cover_path=str(cover),bililive_payload_json=json_text(payload),**collection)
            else:
                self.cover(job)  # verify existing artifact without generating it again
                client=self.bili_factory()
            validation=client.validate_upload_config(payload['config'])
            self.update('publish_jobs',pid,status='ready',publish_error='',failure_stage=None,next_retry_at=None,validation_result_json=json_text(validation))
        except PublishPaused:
            self.update('publish_jobs',pid,status='pending',next_retry_at=None)
        except Exception as exc:
            log_exception()
            retry=is_busy_error(exc) or isinstance(exc,PublishRetryableError) or (isinstance(exc,CoverError) and exc.retryable and self.row('song_projects',job['song_project_id'])['cover_attempts']<COVER_MAX_ATTEMPTS)
            message=safe_error(exc)[:1000]
            if isinstance(exc,CoverError): self.update('song_projects',job['song_project_id'],cover_status='failed',cover_error=message)
            self.update('publish_jobs',pid,status='pending' if retry else 'failed',publish_error=message,failure_stage=stage,
                next_retry_at=time.time()+retry_delay_seconds(job['publish_attempts']+1) if retry else None)
        finally:
            if client: client.close()

    def submit(self, job):
        client=None
        try:
            job=self.recover_responses(job)
            if self.rollout()['mode']=='paused': return
            if job.get('bililive_task_id') or job.get('aid') or job.get('bvid'): return
            song=self.row('song_projects',job['song_project_id'])
            if song['conflict'] or not eligible(self.get_project(job['source_job_id'])):
                raise PublishPrepareError('投稿资格/当前响度已失效或歌曲身份冲突')
            stat=Path(job['video_path']).stat()
            if stat.st_size!=job['video_size'] or stat.st_mtime!=job['video_mtime']:
                raise PublishPrepareError('成片已变化，停止提交')
            if not song.get('cover_path'): raise PublishPrepareError('成功封面记录缺失，停止提交')
            self.cover(job)  # Existing successful cover must be intact before submitting.
            payload=json.loads(job['bililive_payload_json']); client=self.bili_factory()
            if payload.get('options',{}).get('foliaCollectionTracking') is True:
                client.collection_capabilities()  # A ready snapshot must not submit through a reverted/unsupported uploader.
            tasks=client.list_upload_tasks()
            if job['status']=='submitting':
                before=set(json.loads(job.get('submit_before_json') or '[]'))
                matches=[t for t in tasks if t['taskId'] not in before and t.get('type')=='bili'
                         and (t.get('name')=='创建稿件：'+job['title'] or re.fullmatch(re.escape('创建稿件：'+job['title'])+r'（等待投稿间隔，还需 \d+ 分钟）',t.get('name') or ''))
                         and abs((t.get('startTime') or 0)/1000-(job.get('submit_started_at') or 0))<120]
                if len(matches)==1:
                    self.update('publish_jobs',job['id'],bililive_task_id=matches[0]['taskId'],status='uploading',publish_error=''); return
                if len(matches)>1: raise PublishPrepareError('多个可能的上传任务，需要人工核对')
                if job['submit_attempts']>=2: raise PublishPrepareError('提交恢复已重试一次，请人工核对BililiveTool')
            if self.rollout()['mode']=='paused': return
            self.update('publish_jobs',job['id'],status='submitting',submit_attempts=job['submit_attempts']+1,
                submit_started_at=time.time(),submit_before_json=json_text([t['taskId'] for t in tasks]),next_retry_at=time.time()+60)
            task_id=client.create_upload(payload)
            accepted={'bililive_task_id':task_id,'status':'uploading','publish_error':'','failure_stage':None,'next_retry_at':None}
            try: self.checkpoint(job,'accepted',accepted)
            except OSError:
                log_exception()  # Still persist the known ID; never turn a file error into another POST.
            self.update('publish_jobs',job['id'],**accepted)
        except PublishRetryableError as exc:
            log_exception()
            self.update('publish_jobs',job['id'],publish_error=safe_error(exc),failure_stage='submit',next_retry_at=time.time()+60)
        except Exception as exc:
            log_exception()
            if is_busy_error(exc):
                self.update('publish_jobs',job['id'],publish_error=safe_error(exc)[:1000],failure_stage='database',next_retry_at=time.time()+60)
            else: self.update('publish_jobs',job['id'],status='failed',publish_error=safe_error(exc)[:1000],failure_stage='submit')
        finally:
            if client: client.close()

    def poll_collection(self, job):
        # Only new opted-in upload snapshots. User-fixed historical archives are untouched.
        if not job.get('aid') or not job.get('collection_status') or job['collection_status'] in ('joined','failed'):
            return
        if (job.get('next_collection_at') or 0)>time.time(): return
        client=None
        try:
            payload=json.loads(job.get('bililive_payload_json') or '{}')
            # A non-NULL status is opt-in: normally set with the new payload marker,
            # or explicitly by a scoped maintenance test on an already uploaded job.
            # Historical rows remain NULL; never rewrite their frozen payload.
            if not payload.get('config',{}).get('seasonId'):
                raise PublishPrepareError('合集跟踪缺少原投稿快照的目标合集')
            client=self.bili_factory();result=client.collection_job(job['aid'],job['bililive_uid'])
            if result is None:
                missing=time.time()-(job.get('published_at') or time.time())>600
                self.update('publish_jobs',job['id'],collection_status='failed' if missing else 'pending',
                    collection_error='合集交接记录缺失，请人工核对' if missing else '等待合集交接记录',next_collection_at=time.time()+60)
                return
            if str(result.get('seasonId'))!=str(payload['config'].get('seasonId')) or result.get('taskId')!=job.get('bililive_task_id'):
                raise PublishPrepareError('合集记录与投稿快照不一致，请人工核对')
            self.update('publish_jobs',job['id'],collection_status=result['status'],collection_error=result.get('error') or '',
                collection_attempts=int(result.get('attempts') or 0),next_collection_at=time.time()+60)
        except Exception as exc:
            log_exception()
            self.update('publish_jobs',job['id'],collection_error=safe_error(exc)[:800],
                collection_status='failed' if isinstance(exc,PublishPrepareError) and not isinstance(exc,PublishRetryableError) else job['collection_status'],next_collection_at=time.time()+60)
        finally:
            if client:client.close()

    def poll(self, job):
        client=None
        try:
            job=self.recover_responses(job)
            client=self.bili_factory()
            aid=job.get('aid')
            if not aid:
                task=client.get_upload_task(job['bililive_task_id'])
                if task is None: raise PublishPrepareError('已知上传任务已丢失，请人工核对；不会再次提交')
                if task.get('status') in ('error','canceled'): raise PublishPrepareError(task.get('error') or 'BililiveTool上传失败或取消')
                if task.get('status')!='completed':
                    self.update('publish_jobs',job['id'],upload_progress=task.get('progress') or 0,next_retry_at=time.time()+15); return
                aid=str(task.get('output') or '')
                if not aid.isdigit() or int(aid)<=0: raise PublishPrepareError('BililiveTool完成但未取得有效AID，请人工核对')
                published={'aid':aid,'status':'completed','publish_result':'success','published_at':time.time(),
                           'upload_progress':100,'publish_error':'','next_review_at':time.time()}
                try: self.checkpoint(job,'published',published)
                except OSError:
                    log_exception()  # The AID must still be saved even if the extra receipt fails.
                self.update('publish_jobs',job['id'],**published)
                job=self.row('publish_jobs',job['id'])
            self.poll_collection(job)
            detail=client.archive_detail(aid,job['bililive_uid'])
            archive=detail['archive']
            self.update('publish_jobs',job['id'],bvid=archive.get('bvid'),review_state=archive.get('state'),
                review_state_desc=archive.get('state_desc'),next_review_at=time.time()+3600,publish_error='',next_retry_at=None)
        except PublishRetryableError as exc:
            log_exception()
            self.update('publish_jobs',job['id'],publish_error=safe_error(exc),next_retry_at=time.time()+60,next_review_at=time.time()+60)
        except Exception as exc:
            log_exception()
            if is_busy_error(exc):
                self.update('publish_jobs',job['id'],publish_error=safe_error(exc)[:1000],next_retry_at=time.time()+60,next_review_at=time.time()+60)
            elif job.get('aid') or self.row('publish_jobs',job['id']).get('aid'):
                self.update('publish_jobs',job['id'],publish_error='审核查询失败：'+safe_error(exc)[:800],next_review_at=time.time()+3600)
            else: self.update('publish_jobs',job['id'],status='failed',failure_stage='upload',publish_error=safe_error(exc)[:1000])
        finally:
            if client: client.close()

    def tick(self):
        if not LOCK.acquire(blocking=False): return
        try:
            now=time.time()
            if not self.database_failures_recovered:
                self.recover_database_failures()
                self.database_failures_recovered=True
            with self.db() as c:
                rows=c.execute("SELECT * FROM publish_jobs WHERE pipeline_version=2 AND status IN ('pending','preparing','ready','submitting','uploading','completed') ORDER BY CASE WHEN status IN ('submitting','uploading','completed') THEN 0 ELSE 1 END,priority_at DESC,created_at").fetchall()
            for raw in rows:
                job=dict(raw)
                # Keep tracking accepted tasks/reviews even while automation is paused.
                if job['status'] in ('uploading','completed'):
                    self.poll_collection(job)
                    if job.get('next_retry_at') and job['next_retry_at']>now: continue
                    if job['status']=='uploading' or (job.get('next_review_at') or 0)<=now: self.poll(job)
                    continue
                try:
                    render_time=completed_at(self.get_project(job['source_job_id']))
                except Exception as exc:
                    log_exception()
                    self.update('publish_jobs',job['id'],publish_error='源项目查询失败：'+safe_error(exc)[:800],next_retry_at=now+60)
                    continue
                if not self.allowed(job['source_job_id'],render_time): continue
                if job.get('next_retry_at') and job['next_retry_at']>now: continue
                if job['status']=='completed':
                    if (job.get('next_review_at') or 0)<=now: self.poll(job)
                elif job['status']=='uploading': self.poll(job)
                elif job['status'] in ('ready','submitting'):
                    if self.settings.auto_publish_enabled: self.submit(job)
                else:
                    self.prepare(job); break  # single paid request in flight
        finally: LOCK.release()
