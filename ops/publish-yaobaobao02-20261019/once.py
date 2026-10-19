"""Explicitly authorized upload of ONE already-rendered performance. No AI requests."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid
sys.path.insert(0,'/app')
from publishing import (BililiveToolClient, build_tags, build_description, build_payload,
    map_to_bililive_path, merge_preset_config, preset_description_template, json_text)
from publish_v2 import eligible, safe_error
from recorder_identity import recording_start_time

PROJECT='3d18a332b1ed4dd6b0b42e7687242a72'
PROFILE='020f333ed8af475da2fb0d98f8cd81ba'
RUN='cfeb008f758a4759ad3366547f03f9dc'
SONG='70bcc3639eac4a6d81ccf3966160c2fb'
OLD='8e0fd2d0b6c84c7ebeda1b3df3fa39c2'
PID=uuid.uuid5(uuid.NAMESPACE_URL,'folia:explicit:xhp:yaobaobao02:20261019:'+PROJECT).hex
ROOT=Path('/data/publish-template-backups/yaobaobao02-20261019')

def save(name,value):
    temp=ROOT/(name+'.partial')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(ROOT/name)

def app_module():
    import app
    with sqlite3.connect('file:/data/studio.db?mode=ro',uri=True) as c:
        assert {'pipeline_version','collection_status','song_project_id'} <= {r[1] for r in c.execute('pragma table_info(publish_jobs)')}
    app._schema_ready.set()  # Existing deployed schema only; no startup/worker/DDL.
    return app

def client(app):
    s=app.PUBLISH_SETTINGS
    return BililiveToolClient(s.bililive_base_url,s.bililive_passkey)

def row(app,table,id):
    with app.db() as c:r=c.execute('SELECT * FROM '+table+' WHERE id=?',(id,)).fetchone()
    return dict(r) if r else None

def inputs(app):
    p=app.getjob(PROJECT);assert eligible(p),'Not a complete high-confidence performance'
    assert p['identified_title']=='要抱抱' and not p['identified_artist']
    video=Path(p['output']['path']);assert video.name=='要抱抱_02_folia_overlay.mp4'
    assert video.is_file() and video.stat().st_size==202871135
    profile=app.get_automation_profile(PROFILE);run=app.get_automation_run(RUN,False)
    assert run['profile_id']==PROFILE and profile['bililive_preset_id']=='ign19v4u95a'
    song=row(app,'song_projects',SONG);old=row(app,'publish_jobs',OLD)
    assert song['broadcaster_key']=='bilibili:2516117' and song['song_key']=='要抱抱' and not song['conflict']
    assert old['status']=='completed' and old['aid']=='117454722304821'
    cover=Path(song['cover_path']);assert cover.is_file()
    assert hashlib.sha256(cover.read_bytes()).hexdigest()==song['cover_sha256']
    from PIL import Image
    with Image.open(cover) as image:image.verify()
    shared=json.loads((ROOT/'shared-paths.json').read_text())
    for f in (video,cover):
        q=shared[map_to_bililive_path(f,app.PUBLISH_SETTINGS)];s=f.stat()
        assert q['size']==s.st_size and q['mtime_ns']==s.st_mtime_ns,'Shared path stat mismatch'
    return p,profile,run,song,old,video,cover

def backup(app):
    if (ROOT/'studio-before.sqlite').exists():return
    src=sqlite3.connect('file:/data/studio.db?mode=ro',uri=True,timeout=30)
    dest=sqlite3.connect(ROOT/'studio-before.sqlite');src.backup(dest)
    assert dest.execute('pragma integrity_check').fetchone()[0]=='ok'
    dest.close();src.close()
    save('before.json',{'old_publish':row(app,'publish_jobs',OLD),'song':row(app,'song_projects',SONG),
                        'authorization':'User explicitly requests today 要抱抱_02, not the duet or first performance'})

def prepare(app):
    existing=row(app,'publish_jobs',PID)
    if existing:return {k:existing.get(k) for k in ('id','status','bililive_task_id','aid','bvid')}
    with app.db() as c:
        assert c.execute('SELECT id FROM publish_jobs WHERE source_job_id=?',(PROJECT,)).fetchone() is None
    p,profile,run,song,old,video,cover=inputs(app)
    b=client(app)
    try:
        # Creator-side duplicate evidence, not a public search or guessed error code.
        checked=0
        for page in range(1,9):
            response=b._request('GET','/bili/archives',params={'uid':old['bililive_uid'],'pn':page,'ps':30})
            assert response.status_code==200,'Cannot verify creator archives'
            items=response.json().get('arc_audits') or [];checked+=len(items)
            for item in items:
                a=item.get('Archive',{})
                assert not ('抱抱' in a.get('title','') and '2026.10.19' in a.get('desc','')),'Today already has a same-song archive; inspect before upload'
            if len(items)<30:break
        assert not [t for t in b.list_upload_tasks() if '抱抱' in t.get('name','') and t.get('status') not in ('error','canceled')],'Existing same-song task needs verification'
        preset=b.get_video_preset(profile['bililive_preset_id'])
        assert preset['config'].get('seasonId')==9133790,'Wrong collection'
        recorded=recording_start_time(run['source'],profile.get('recorder_identity'))
        assert recorded.date().isoformat()=='2026-10-19'
        streamer=old['streamer'];title=old['title']
        assert '《要抱抱》' in title and streamer in title
        tags=build_tags(streamer,p['identified_title'],p['identified_artist'])
        description=b.format_description(preset_description_template(preset,build_description(streamer,p['identified_title'],p['identified_artist'])),
          {'title':p['identified_title'],'username':streamer,'time':recorded.isoformat(),'roomId':'2516117','filename':Path(run['source']).name})
        assert '2026.10.19' in description and '2026.10.17' not in description
        config=merge_preset_config(preset,title,description,tags,map_to_bililive_path(cover,app.PUBLISH_SETTINGS))
        payload=build_payload(old['bililive_uid'],map_to_bililive_path(video,app.PUBLISH_SETTINGS),p['identified_title'],config)
        b.collection_capabilities();payload['options']['foliaCollectionTracking']=True
        backup(app)
        now=time.time();st=video.stat()
        values={'id':PID,'source_job_id':PROJECT,'automation_run_id':RUN,'created_at':now,'updated_at':now,
          'status':'preparing','publish_attempts':1,'video_path':str(video),'video_size':st.st_size,'video_mtime':st.st_mtime,
          'streamer':streamer,'identified_title':p['identified_title'],'identified_artist':p['identified_artist'],'identity_source':p['identity_source'],
          'bililive_preset_id':profile['bililive_preset_id'],'bililive_uid':old['bililive_uid'],'cover_path':str(cover),'title':title,
          'description':description,'tags_json':json_text(tags),'bililive_payload_json':json_text(payload),'pipeline_version':1,
          'title_generation_json':json_text({'status':'reused','attempts':0,'source_publish_id':OLD,'reason':'same song; explicit new performance upload'}),
          'collection_status':'pending','collection_attempts':0,'submit_attempts':0}
        with app.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO publish_jobs('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()));c.commit()
        # Snapshot is durable BEFORE parameter validation.
        save('payload.json',payload)
        validation=b.validate_upload_config(payload['config'])
        app.update_publish_job(PID,status='ready',validation_result_json=json_text(validation),publish_error='')
        save('prepared.json',{'publish_id':PID,'source_job_id':PROJECT,'video':str(video),'input_size':st.st_size,'input_mtime_ns':st.st_mtime_ns,
          'cover_sha256':song['cover_sha256'],'title':title,'description':description,'tags':tags,'preset':profile['bililive_preset_id'],
          'collection':9133790,'validation':validation,'checked_archives':checked,'new_ai_requests':0})
        return {'id':PID,'status':'ready','title':title,'video':str(video),'validation':validation}
    finally:b.close()

def adopt(app,taskid):
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        assert c.execute('SELECT publish_job_id FROM song_projects WHERE id=?',(SONG,)).fetchone()[0] in (OLD,PID)
        c.execute('UPDATE publish_jobs SET song_project_id=NULL WHERE id=? AND song_project_id=?',(OLD,SONG))
        c.execute("UPDATE publish_jobs SET bililive_task_id=?,status='uploading',pipeline_version=2,song_project_id=?,publish_error='',failure_stage=NULL,next_retry_at=NULL,updated_at=? WHERE id=?",(taskid,SONG,time.time(),PID))
        c.execute('UPDATE song_projects SET publish_job_id=?,updated_at=? WHERE id=?',(PID,time.time(),SONG))
        c.execute("UPDATE song_performances SET disposition='selected',reason=? WHERE source_job_id=? AND song_project_id=?",('用户明确指定2026-10-19第二遍上传；旧稿历史保留，复用封面和标题',PROJECT,SONG))
        c.commit()

def submit(app):
    job=app.get_publish_job(PID)
    if job.get('bililive_task_id') or job.get('aid') or job.get('bvid'):
        return {'already_accepted':True,'task_id':job.get('bililive_task_id'),'aid':job.get('aid'),'bvid':job.get('bvid')}
    receipt=ROOT/'accepted.json'
    if receipt.exists():
        taskid=json.loads(receipt.read_text())['task_id'];adopt(app,taskid)
        app.publisher_v2().checkpoint(app.get_publish_job(PID),'accepted',{'bililive_task_id':taskid,'status':'uploading','publish_error':'','failure_stage':None,'next_retry_at':None})
        return {'recovered_receipt':True,'task_id':taskid}
    assert job['status']=='ready' and job['submit_attempts']==0,'Submission may have started; NEVER issue a second POST automatically'
    p,profile,run,song,old,video,cover=inputs(app)
    assert (video.stat().st_size,video.stat().st_mtime)==(job['video_size'],job['video_mtime'])
    payload=job['bililive_payload'];assert payload['videos'][0]['path']==map_to_bililive_path(video,app.PUBLISH_SETTINGS)
    assert payload['options']['removeOriginAfterUploadCheck'] is False
    b=client(app)
    try:
        b.collection_capabilities();before=b.list_upload_tasks()
        assert not [t for t in before if '抱抱' in t.get('name','') and t.get('status') not in ('error','canceled')]
        with app.db() as c:
            c.execute('BEGIN IMMEDIATE')
            changed=c.execute("UPDATE publish_jobs SET status='submitting',submit_attempts=1,submit_started_at=?,submit_before_json=?,updated_at=? WHERE id=? AND status='ready' AND submit_attempts=0 AND bililive_task_id IS NULL AND aid IS NULL",(time.time(),json_text([t['taskId'] for t in before]),time.time(),PID)).rowcount
            assert changed==1;c.commit()
        taskid=b.create_upload(payload)
        save('accepted.json',{'publish_id':PID,'source_job_id':PROJECT,'task_id':taskid,'accepted_at':time.time(),'payload_sha256':hashlib.sha256(json_text(payload).encode()).hexdigest()})
        adopt(app,taskid)
        # The scoped receipt precedes DB adoption; the normal checkpoint needs the adopted song link.
        app.publisher_v2().checkpoint(app.get_publish_job(PID),'accepted',{'bililive_task_id':taskid,'status':'uploading','publish_error':'','failure_stage':None,'next_retry_at':None})
        return {'accepted':True,'publish_id':PID,'task_id':taskid}
    finally:b.close()

def status(app):
    j=app.get_publish_job(PID)
    if j.get('aid'):
        with app.db() as c:
            c.execute("UPDATE song_performances SET disposition='published',reason=? WHERE source_job_id=? AND song_project_id=?",('用户明确指定2026-10-19第二遍；已取得AID，旧稿历史保留',PROJECT,SONG));c.commit()
    result={k:j.get(k) for k in ('id','status','title','bililive_task_id','aid','bvid','upload_progress','review_state','review_state_desc','collection_status','collection_error','publish_error','submit_attempts')}
    save('result.json',result);return result

def poll(app):
    job=app.get_publish_job(PID)
    assert job.get('bililive_task_id'),'No known task; inspect receipt, never resubmit'
    app.publisher_v2().poll(job)
    job=app.get_publish_job(PID)
    if job.get('aid') and not job.get('bvid'):
        b=client(app)
        try:
            response=b._request('GET','/bili/archives',params={'uid':job['bililive_uid'],'pn':1,'ps':30})
            assert response.status_code==200
            for item in response.json().get('arc_audits') or []:
                a=item.get('Archive',{})
                if str(a.get('aid'))==str(job['aid']):
                    assert a.get('mid')==job['bililive_uid'] and a.get('title')==job['title']
                    values={'bvid':a['bvid']}
                    if a.get('state') is not None:values['review_state']=a['state']
                    if a.get('state_desc'):values['review_state_desc']=a['state_desc']
                    app.update_publish_job(PID,**values)
        finally:b.close()
    return status(app)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','submit','status','poll'));args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (ROOT/'once.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            app=app_module();result=globals()[args.action](app)
            print(json.dumps(result,ensure_ascii=False),flush=True)
        except Exception as exc:
            print(json.dumps({'error':safe_error(exc),'action':args.action,'publish_id':PID},ensure_ascii=False),flush=True)
            raise SystemExit(1)
