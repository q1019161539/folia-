"""One explicitly authorized lyric correction/repost; never deletes an archive.

Runs inside the existing API container. It uses existing lyric, renderer and
BililiveTool clients, not a new uploader. The original completed outcome,
identity, task IDs and payload stay immutable. Once validated, only its main-
task association moves to the replacement, with old history preserved. The
separate replacement is maintenance-owned (version 1),
so the automatic worker cannot race this explicit operation.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

SOURCE = 'ed4ca17f79b54ebcbabd80cf3ff88929'
OLD_PUBLISH = '32341710c8de41f19212c9f43b73bb20'
OLD_BVID = 'BV1bzHS6LEwe'
SONG = '1a103df274ac462c9b8a17524aa6d25b'
KEY = 'maintenance:yujian-lyrics-repost:20261008'
NEW_JOB = uuid.uuid5(uuid.NAMESPACE_URL, KEY + ':job').hex
NEW_PUBLISH = uuid.uuid5(uuid.NAMESPACE_URL, KEY + ':publish').hex
ROOT = Path('/data/lyric-repairs/20261008-yujian')


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def emit(value):
    print(dump(value), flush=True)


def module():
    sys.path.insert(0, '/app')
    import app
    # This is an operation against an already initialized live deployment, not
    # another API startup. Never rerun schema DDL beside active production work.
    with sqlite3.connect('file:/data/studio.db?mode=ro',uri=True) as c:
        fields={r[1] for r in c.execute('PRAGMA table_info(publish_jobs)')}
        assert {'pipeline_version','bililive_task_id','title_generation_json'} <= fields
    app._schema_ready.set()
    return app


def get_record(app):
    with app.db() as c:
        row = c.execute('SELECT value FROM app_meta WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {}


def save_record(app, **values):
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT value FROM app_meta WHERE key=?', (KEY,)).fetchone()
        record = json.loads(row[0]) if row else {}
        record.update(values, updated_at=time.time())
        c.execute('INSERT INTO app_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                  (KEY, dump(record)))
    return record


def assert_quality(result):
    assert result['timing_confidence'] == 'high'
    assert result['word_bootstrap_status'] == 'accepted'
    assert result['shift_source'] == 'word' and not result['cross_model_conflict']
    assert result['word_anchor_span_ms'] >= 145000
    assert result['word_anchor_lines'] >= 6 and result['word_anchor_count'] >= 40
    assert result['word_residual_p90_ms'] < 400
    assert abs(result['word_vs_line_shift_diff_ms']) < 100


async def candidate(app):
    from word_timeline import score_provider_timeline
    found, platforms, revision = await app.search_lddc_candidates('遇见 孙燕姿')
    chosen = next(c for c in found if c['candidate_id'] == 'qq:8145')
    assert chosen['title'] == '遇见' and chosen['artist'] == '孙燕姿'
    data = await app.fetch_lddc_candidate(chosen['candidate_ref'])
    assert data['timing_type'] == 'verbatim'
    rows = app.normalized_lddc_rows(data)
    old = app.getjob(SOURCE)
    result = score_provider_timeline(rows, old['alignment']['asr_segments'], title_score=1)
    assert_quality(result)
    return old, chosen, rows, result, revision, platforms


def align(app):
    from standard_timeline import build_shifted_timeline, lyric_render_window
    from word_timeline import apply_shifted_provider_words
    record = get_record(app)
    if record.get('job_id'):
        emit({'already_created': record['job_id'], 'record': record}); return
    old, chosen, rows, result, revision, platforms = asyncio.run(candidate(app))
    source = (app.MEDIA / old['source']).resolve()
    assert source.is_relative_to(app.MEDIA.resolve()) and source.is_file()
    stat = source.stat(); duration = round(app.media_duration(source) * 1000)
    lines = build_shifted_timeline(rows, result['shift_ms'], duration,
                                   anchors=result['evidence_anchors'])
    counts = apply_shifted_provider_words(lines, rows, result['shift_ms'])
    assert len(lines) == 25 and counts['lddc_standard'] > 200
    assert 4000 < lines[0]['start_ms'] < 5500
    assert lines[-1]['end_ms'] > 170000
    assert sum('我遇见谁' in line['text'] for line in lines) == 2
    assert all(line['words'] and line['fixed_timeline'] for line in lines)
    window = lyric_render_window([{'start': x['start_ms'], 'end': x['end_ms']} for x in lines], duration)
    assert window[0] == 0 and window[1] - window[0] > 175000
    # Copy original recognition and identity exactly; only lyric matching changes.
    al = copy.deepcopy(old['alignment']); al['lines'] = lines; al['offset_ms'] = 0
    report = {k: v for k, v in result.items() if k != 'word_anchors'}
    report.update(status='completed', mode='standard-piecewise', candidate_id=chosen['candidate_id'],
        platform=chosen['platform'], song_id=chosen['song_id'], title=chosen['title'],
        artist=chosen['artist'], album=chosen['album'], lddc_ref=revision,
        timing_type='verbatim', confidence_tier='high', low_confidence=False,
        identified_title=old['identified_title'], identified_artist=old['identified_artist'],
        identity_source=old['identity_source'], song_identity_suspicious=False,
        matched_title=chosen['title'], matched_artist=chosen['artist'],
        word_timing_counts=counts, finished_at=time.time(),
        correction={'reason':'explicit user lyric-axis repair', 'source_job_id':SOURCE,
                    'old_publish_id':OLD_PUBLISH, 'old_bvid':OLD_BVID,
                    'search_only_title':'遇见', 'identity_unchanged':True})
    al['timeline_match'] = report
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    snapshot = {}
    with app.db() as c:
        for table, id in [('jobs',SOURCE), ('publish_jobs',OLD_PUBLISH), ('song_projects',SONG)]:
            snapshot[table] = dict(c.execute('SELECT * FROM '+table+' WHERE id=?', (id,)).fetchone())
    assert snapshot['publish_jobs']['bvid'] == OLD_BVID
    assert snapshot['publish_jobs']['status'] == 'completed'
    with sqlite3.connect('file:/data/studio.db?mode=ro', uri=True) as dbsource:
        with sqlite3.connect(str(ROOT / 'studio-before.db')) as backup:
            dbsource.backup(backup)
    (ROOT / 'before.json').write_text(dump(snapshot), encoding='utf-8')
    (ROOT / 'candidate-rows.json').write_text(dump(rows), encoding='utf-8')
    (ROOT / 'corrected-alignment.json').write_text(dump(al), encoding='utf-8')
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        assert not c.execute('SELECT 1 FROM app_meta WHERE key=?', (KEY,)).fetchone()
        now = time.time()
        values = (NEW_JOB,now,now,'aligned',old['source'],old['engine'],old['title'],old['artist'],
                  '\n'.join(x['text'] for x in lines),dump(al),dump(old['style']),'','{}',
                  old['identified_title'],old['identified_artist'],old['identity_source'])
        c.execute(app.JOB_INSERT, values)
        # The unique output directory prevents overwriting either earlier MP4.
        c.execute('UPDATE jobs SET render_revision_parent_id=?,render_revision_publish=0 WHERE id=?',
                  (SOURCE,NEW_JOB))
        record = {'job_id':NEW_JOB,'publish_id':NEW_PUBLISH,'old_publish_id':OLD_PUBLISH,
            'old_bvid':OLD_BVID,'song_project_id':SONG,'state':'aligned','created_at':now,
            'authorization':'user will delete old archive; correct lyrics and upload once',
            'input':{'path':str(source),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns},
            'candidate_id':chosen['candidate_id'],'shift_ms':result['shift_ms'],'trim_window_ms':window,
            'backup':str(ROOT),'platforms':platforms}
        c.execute('INSERT INTO app_meta(key,value) VALUES(?,?)', (KEY,dump(record)))
    assert (source.stat().st_size,source.stat().st_mtime_ns) == (stat.st_size,stat.st_mtime_ns)
    emit({'record':record,'word_audit':{k:report[k] for k in ('word_anchor_span_ms','word_anchor_count',
        'word_residual_p90_ms','word_vs_line_shift_diff_ms','timing_confidence')},
        'line_times':[{'text':x['text'],'start_ms':x['start_ms'],'end_ms':x['end_ms']} for x in lines]})


def render(app):
    import httpx
    record = get_record(app); assert record['job_id'] == NEW_JOB
    j = app.getjob(NEW_JOB)
    if j['status'] in ('rendering','queued','completed'):
        emit({'existing_job_status':j['status'],'output':j['output']}); return
    assert j['status'] == 'aligned', j.get('error')
    response = httpx.post('http://127.0.0.1:8000/api/jobs/'+NEW_JOB+'/render',
                         json={'sample':False,'output_mode':'smooth','start_ms':0}, timeout=20)
    if response.status_code == 409:
        emit({'waiting_for_existing_render':True}); return
    assert response.status_code == 200, response.status_code
    save_record(app,state='render_requested',render_requested_at=time.time())
    emit({'render_requested':NEW_JOB})


def wait_render(app):
    """Wait behind production rendering; never cancel or restart another job."""
    import httpx
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline:
        j = app.getjob(NEW_JOB)
        if j['status'] in ('rendering','queued','completed'):
            emit({'existing_job_status':j['status'],'job_id':NEW_JOB}); return
        assert j['status'] == 'aligned', j.get('error')
        health = httpx.get('http://127.0.0.1:8000/healthz',timeout=10).json()
        if not health['render_busy']:
            render(app)
            if app.getjob(NEW_JOB)['status'] != 'aligned': return
        # Claim only the brief free slot between normal jobs; do not preempt.
        time.sleep(1)
    raise RuntimeError('Waited an hour; kept aligned project, no duplicate render or upload')


def retry_render(app):
    record=get_record(app);j=app.getjob(NEW_JOB);old=j.get('output') or {}
    assert record.get('render_retries',0)==0, 'Limited to one confirmed terminal render retry'
    rid=old.get('render_id');assert rid
    state=app.folia_renderer_request('GET','/api/renders/'+rid)
    assert state['status']=='failed' and state.get('error')=='Chromium DevTools 启动失败'
    # Persist the terminal ID/result before clearing ONLY this new repair job.
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        current=json.loads(c.execute('SELECT output FROM jobs WHERE id=?',(NEW_JOB,)).fetchone()[0])
        assert current.get('render_id')==rid
        record=json.loads(c.execute('SELECT value FROM app_meta WHERE key=?',(KEY,)).fetchone()[0])
        assert record.get('render_retries',0)==0
        record.update(render_retries=1,failed_render=state,state='aligned',updated_at=time.time())
        c.execute('UPDATE app_meta SET value=? WHERE key=?',(dump(record),KEY))
        c.execute("UPDATE jobs SET status='aligned',output='{}',error='',updated_at=? WHERE id=?",
                  (time.time(),NEW_JOB))
    emit({'one_terminal_retry_requested':True,'old_failed_render_id':rid,'job_id':NEW_JOB})


def prepare(app):
    import subprocess
    from publishing import map_to_bililive_path
    record = get_record(app); j = app.getjob(NEW_JOB)
    assert j['status'] == 'completed' and j['output']['sample'] is False
    assert j['output']['output_mode'] == 'smooth'
    video = Path(j['output']['path']); assert NEW_JOB in video.parent.name
    assert video.is_file() and video.stat().st_size > 1000000
    detail = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'format=duration:stream=codec_type,width,height,r_frame_rate','-of','json',str(video)],text=True))
    assert {'video','audio'} <= {s['codec_type'] for s in detail['streams']}
    assert 175 < float(detail['format']['duration']) < 181
    assert_quality(j['alignment']['timeline_match'])
    with app.db() as c:
        old = dict(c.execute('SELECT * FROM publish_jobs WHERE id=?', (OLD_PUBLISH,)).fetchone())
        song = dict(c.execute('SELECT * FROM song_projects WHERE id=?', (SONG,)).fetchone())
        existing = c.execute('SELECT * FROM publish_jobs WHERE id=?', (NEW_PUBLISH,)).fetchone()
    if existing:
        emit({'already_prepared':NEW_PUBLISH,'status':existing['status']}); return
    cover = Path(song['cover_path'])
    assert cover.is_file() and hashlib.sha256(cover.read_bytes()).hexdigest() == song['cover_sha256']
    payload = json.loads(old['bililive_payload_json']); assert len(payload['videos']) == 1
    payload['videos'][0]['path'] = map_to_bililive_path(video,app.PUBLISH_SETTINGS)
    assert payload['options']['removeOriginAfterUploadCheck'] is False
    assert payload['config']['cover'] == map_to_bililive_path(cover,app.PUBLISH_SETTINGS)
    assert payload['config']['title'] == old['title']
    assert 'Authorization' not in dump(payload) and 'passkey' not in dump(payload)
    now = time.time(); stat = video.stat()
    # A new named-column row, not a reset of a completed task or its IDs.
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('''INSERT INTO publish_jobs(id,source_job_id,automation_run_id,created_at,updated_at,
            status,publish_attempts,video_path,video_size,video_mtime,streamer,identified_title,
            identified_artist,identity_source,bililive_preset_id,bililive_uid,cover_path,title,
            description,tags_json,bililive_payload_json,pipeline_version,title_generation_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (NEW_PUBLISH,NEW_JOB,old['automation_run_id'],now,now,'preparing',0,str(video),stat.st_size,
             stat.st_mtime,old['streamer'],old['identified_title'],old['identified_artist'],
             old['identity_source'],old['bililive_preset_id'],old['bililive_uid'],str(cover),old['title'],
             old['description'],old['tags_json'],dump(payload),1,old['title_generation_json']))
    client = app.publisher_v2().bili_factory()
    try: validation = client.validate_upload_config(payload['config'])
    finally: client.close()
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        assert c.execute('SELECT publish_job_id FROM song_projects WHERE id=?',(SONG,)).fetchone()[0] == OLD_PUBLISH
        c.execute('UPDATE publish_jobs SET song_project_id=NULL WHERE id=? AND song_project_id=?',
                  (OLD_PUBLISH,SONG))
        c.execute("UPDATE publish_jobs SET status='ready',song_project_id=?,validation_result_json=?,updated_at=? WHERE id=?",
                  (SONG,dump(validation),time.time(),NEW_PUBLISH))
        c.execute('UPDATE song_projects SET publish_job_id=?,updated_at=? WHERE id=?',
                  (NEW_PUBLISH,time.time(),SONG))
    save_record(app,state='ready',video_probe=detail,cover_sha256=song['cover_sha256'],
                old_cover_attempts=song['cover_attempts'])
    emit({'publish_id':NEW_PUBLISH,'status':'ready','payload':payload,'validation':validation,
          'probe':detail,'new_ai_requests':0})


def submit(app):
    from publishing import map_to_bililive_path
    record = get_record(app); assert record.get('shared_paths_verified') is True
    job = app.get_publish_job(NEW_PUBLISH)
    if any(job.get(k) for k in ('bililive_task_id','aid','bvid')):
        emit({'already_accepted':True,'task_id':job.get('bililive_task_id'),'bvid':job.get('bvid')}); return
    assert job['status'] == 'ready' and job['submit_attempts'] == 0
    j = app.getjob(NEW_JOB); assert_quality(j['alignment']['timeline_match'])
    source = Path(record['input']['path']); stat = source.stat()
    assert record['input'] == {'path':str(source),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
    video = Path(job['video_path']); stat = video.stat()
    assert (stat.st_size,stat.st_mtime) == (job['video_size'],job['video_mtime'])
    payload = job['bililive_payload']
    assert payload['videos'][0]['path'] == map_to_bililive_path(video,app.PUBLISH_SETTINGS)
    assert payload['options']['removeOriginAfterUploadCheck'] is False
    assert job['source_job_id'] == NEW_JOB and job['pipeline_version'] == 1
    client = app.publisher_v2().bili_factory()
    try:
        before = client.list_upload_tasks()
        # Commit the attempt BEFORE the request. Never automatically retry a lost response.
        with app.db() as c:
            c.execute('BEGIN IMMEDIATE')
            changed = c.execute("UPDATE publish_jobs SET status='submitting',submit_attempts=1,"
                'submit_started_at=?,submit_before_json=?,updated_at=? '
                "WHERE id=? AND status='ready' AND submit_attempts=0 AND bililive_task_id IS NULL AND aid IS NULL",
                (time.time(),dump([t['taskId'] for t in before]),time.time(),NEW_PUBLISH)).rowcount
            assert changed == 1
        task_id = client.create_upload(payload)
        app.update_publish_job(NEW_PUBLISH,bililive_task_id=task_id,status='uploading',publish_error='')
        save_record(app,state='uploading',task_id=task_id,submit_count=1)
        emit({'accepted':True,'task_id':task_id,'publish_id':NEW_PUBLISH})
    finally: client.close()


def poll(app):
    job = app.get_publish_job(NEW_PUBLISH)
    assert job.get('bililive_task_id'), 'No known task; inspect before any second request'
    # Existing poll handles AID vs review separately without issuing upload.
    app.publisher_v2().poll(job)
    job = app.get_publish_job(NEW_PUBLISH)
    if job.get('aid'):
        with app.db() as c:
            c.execute('BEGIN IMMEDIATE')
            song = c.execute('SELECT publish_job_id FROM song_projects WHERE id=?', (SONG,)).fetchone()
            assert song[0] in (OLD_PUBLISH,NEW_PUBLISH)
            c.execute('UPDATE song_projects SET publish_job_id=?,updated_at=? WHERE id=?',
                      (NEW_PUBLISH,time.time(),SONG))
            c.execute('''INSERT OR IGNORE INTO song_performances(source_job_id,song_project_id,
                automation_run_id,identified_title,identified_artist,identity_source,video_path,
                disposition,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (NEW_JOB,SONG,job['automation_run_id'],job['identified_title'],job['identified_artist'],
                 job['identity_source'],job['video_path'],'published',
                 '用户明确授权：《遇见》歌词轴修正版，旧稿由用户删除；复用封面和标题',time.time()))
        save_record(app,state='completed',aid=job['aid'],bvid=job.get('bvid'),
                    review_state=job.get('review_state'),review_state_desc=job.get('review_state_desc'))
    emit({k:job.get(k) for k in ('id','status','bililive_task_id','aid','bvid','upload_progress',
                                'review_state','review_state_desc','publish_error')})


def status(app):
    import httpx
    record = get_record(app)
    j = app.getjob(NEW_JOB) if record else {}
    emit({'record':record,'job_status':j.get('status'),'output':j.get('output'),'error':j.get('error'),
          'health':httpx.get('http://127.0.0.1:8000/healthz',timeout=10).json(),
          'heavy_task_slot':httpx.get('http://127.0.0.1:8000/api/automation/health',timeout=10).json().get('heavy_task_slot')})


def snapshot(app):
    record=get_record(app);j=app.getjob(NEW_JOB);o=j.get('output') or {};native={}
    if o.get('render_id'):
        native=app.folia_renderer_request('GET','/api/renders/'+o['render_id'])
    with app.db() as c:
        row=c.execute('SELECT * FROM publish_jobs WHERE id=?',(NEW_PUBLISH,)).fetchone()
    p=dict(row) if row else {}
    emit({'record':record,'status':j['status'],'output':o,'native':native,
          'publish':{k:p.get(k) for k in ('id','status','video_path','video_size','cover_path',
             'bililive_task_id','aid','bvid','submit_attempts','review_state_desc','publish_error')}})


def recover_render(app):
    j=app.getjob(NEW_JOB);o=j['output'];rid=o['render_id']
    state=app.folia_renderer_request('GET','/api/renders/'+rid)
    assert state['status']=='completed' and state['result']['path']==o['path']
    assert NEW_JOB in Path(o['path']).parent.name
    assert o['trim_start_ms']==0 and o['trim_end_ms']==179244
    # Only consume this known completed renderer; no POST or cross-job recovery.
    app.resume_render_revision(NEW_JOB)
    emit({'recovered_completed_render_id':rid,'job_id':NEW_JOB})


def verify_shared(app):
    from publishing import map_to_bililive_path
    receipt=json.load(sys.stdin);job=app.get_publish_job(NEW_PUBLISH)
    assert receipt['video']['path']==map_to_bililive_path(Path(job['video_path']),app.PUBLISH_SETTINGS)
    assert receipt['video']['size']==job['video_size'] and receipt['video']['file'] is True
    assert receipt['cover']['path']==map_to_bililive_path(Path(job['cover_path']),app.PUBLISH_SETTINGS)
    record=get_record(app)
    assert receipt['cover']['sha256']==record['cover_sha256'] and receipt['cover']['file'] is True
    save_record(app,shared_paths_verified=True,shared_receipt=receipt)
    emit({'shared_paths_verified':True})


def deleted(app):
    old=app.get_publish_job(OLD_PUBLISH);client=app.publisher_v2().bili_factory()
    try:
        a=client.archive_detail(old['aid'],old['bililive_uid'])['archive']
        assert a['state']==-100 and a['bvid']==OLD_BVID, 'Old archive deletion not confirmed; do not submit'
        save_record(app,old_archive_deleted_confirmed_at=time.time())
        emit({'old_archive_deleted':True})
    finally:client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action',choices=['align','render','wait_render','retry_render','prepare','submit','poll','status','snapshot','recover_render','verify_shared','deleted'])
    action = parser.parse_args().action
    globals()[action](module())
