"""Explicit single-use maintenance workflow; no renderer POST or Bili uploader here."""
import argparse,json,subprocess,sys,time
from pathlib import Path

BATCH='26e223f70d714588b6e40cdca70e9fca'
TARGETS=('ec1413aac1494969a9ccf51e1cf3ae66','a7b45e92e7884ecd933b39c9ce004b46',
         'ed4ca17f79b54ebcbabd80cf3ff88929','75aad5b665c846eab39dc71494b228f6',
         'aaa80a639c4a4e138a5b1aa829e6868e','4a624071ba724542b6b788dac1c50c2f')


def classify(gate,renderer_status):
    if gate['decision']!='pass':return 'excluded_audio'
    if renderer_status=='completed':return 'recover_completed'
    if renderer_status in ('failed','cancelled','missing'):return 'queue_rerender_once'
    if renderer_status in ('running','queued'):return 'resume_existing'
    raise RuntimeError('渲染器状态无法确认，不清除ID、不创建新任务')


def run(execute=False):
    sys.path.insert(0,'/app')
    import app
    from performance_gate import screen_clip
    # Important: release schema transaction before nested getjob/profile calls.
    with app.db():pass
    backup=Path('/data/render-retry-backups/20261008-once')
    snapshots=[];plan=[]
    for jid in TARGETS:
        with app.db() as c:
            revision=dict(c.execute('SELECT * FROM render_revisions WHERE job_id=?',(jid,)).fetchone())
            raw=dict(c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            previous=c.execute('SELECT value FROM app_meta WHERE key=?',('render_revision_retry_once:'+jid,)).fetchone()
        assert revision['batch_id']==BATCH and raw['render_revision_parent_id']
        if previous:
            plan.append({'job_id':jid,'title':raw['identified_title'],'action':'already_requested','record':json.loads(previous[0])});continue
        if revision['status']!='failed':
            plan.append({'job_id':jid,'title':raw['identified_title'],'action':'not_failed'});continue
        project=app.getjob(jid);profile=app.get_automation_profile(revision['profile_id'])
        with app.db() as c:
            posted=app.render_revision_service().posted_keys(c,profile)
        if app.normalized_title(project['identified_title']) in posted:
            plan.append({'job_id':jid,'title':raw['identified_title'],'action':'already_accepted'});continue
        source=(app.MEDIA/project['source']).resolve()
        assert source.is_relative_to(app.MEDIA.resolve()) and source.is_file()
        before=source.stat();gate=screen_clip(source,(project.get('alignment') or {}).get('performance_gate'))
        assert (before.st_size,before.st_mtime_ns)==(source.stat().st_size,source.stat().st_mtime_ns)
        out=project.get('output') or {};rid=out.get('render_id');state={}
        if gate['decision']=='pass':
            if not rid:status='missing'
            else:
                try:state=app.folia_renderer_request('GET','/api/renders/'+rid);status=state['status']
                except RuntimeError as exc:
                    if str(exc)!='渲染任务不存在':raise
                    status='missing'
            action=classify(gate,status)
            if action=='recover_completed':
                path=app.resolve_saved_output((state.get('result') or {}).get('path') or out.get('path') or '')
                assert jid in path.parts[-2] and path.is_file() and path.stat().st_size
                probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type','-of','json',str(path)],capture_output=True,text=True,timeout=20)
                assert probe.returncode==0,probe.stderr
                detail=json.loads(probe.stdout);assert float(detail['format']['duration'])>0
                assert {'video','audio'}<={s['codec_type'] for s in detail['streams']}
        else:action='excluded_audio'
        snapshots.append({'job':raw,'revision':revision,'renderer':state})
        plan.append({'job_id':jid,'title':raw['identified_title'],'action':action,'gate':gate,'old_render_id':rid,'old_error':revision['error'],'output':out})
    if not execute:
        print(json.dumps({'dry_run':True,'plan':plan},ensure_ascii=False),flush=True);return
    backup.mkdir(mode=0o700,parents=True,exist_ok=True)
    stamp=str(time.time_ns());(backup/('before-'+stamp+'.json')).write_text(json.dumps(snapshots,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]
    for item in plan:
        action=item['action'];jid=item['job_id'];key='render_revision_retry_once:'+jid
        if action not in ('recover_completed','queue_rerender_once','resume_existing'):
            results.append({'job_id':jid,'title':item['title'],'action':action});continue
        with app.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM app_meta WHERE key=?',(key,)).fetchone():continue
            current=c.execute('SELECT r.status,j.output FROM render_revisions r JOIN jobs j ON j.id=r.job_id WHERE r.job_id=?',(jid,)).fetchone()
            assert current['status']=='failed' and json.loads(current['output'] or '{}').get('render_id')==item['old_render_id']
            record={'count':1,'requested_at':time.time(),'action':action,'old_render_id':item['old_render_id'],'old_error':item['old_error'],'state':'requested'}
            c.execute('INSERT INTO app_meta(key,value) VALUES(?,?)',(key,json.dumps(record,ensure_ascii=False)))
            if action in ('queue_rerender_once','resume_existing'):
                out=item['output'].copy()
                if action=='queue_rerender_once':out.update(render_id=None,progress=0,phase='重制重试排队（1/1）')
                c.execute("UPDATE jobs SET status='queued',error='',output=?,updated_at=? WHERE id=?",(json.dumps(out,ensure_ascii=False),time.time(),jid))
                c.execute("UPDATE render_revisions SET status='pending',error='',updated_at=? WHERE job_id=?",(time.time(),jid))
        if action=='recover_completed':
            # Only consume a confirmed completed renderer result. No new render/create.
            app.resume_render_revision(jid)
            service=app.render_revision_service();service.set_status(jid,'completed')
            with app.db() as c:
                current=dict(c.execute('SELECT * FROM render_revisions WHERE job_id=?',(jid,)).fetchone())
            if app.getjob(jid).get('render_revision_publish')==1:
                try:
                    published=app.enqueue_render_revision(current)
                    with app.db() as c:
                        c.execute('UPDATE render_revisions SET publish_status=?,publish_error=?,updated_at=? WHERE job_id=?',
                                  ('enqueued' if published else 'ineligible','' if published else '投稿资格未通过',time.time(),jid))
                except Exception as exc:
                    with app.db() as c:c.execute("UPDATE render_revisions SET publish_status='failed',publish_error=?,updated_at=? WHERE job_id=?",(app.safe_error(str(exc)),time.time(),jid))
                    raise
            record['state']='recovered'
            with app.db() as c:c.execute('UPDATE app_meta SET value=? WHERE key=?',(json.dumps(record,ensure_ascii=False),key))
        results.append({'job_id':jid,'title':item['title'],'action':action,'retry_count':1})
    (backup/('result-'+stamp+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'results':results,'backup':str(backup),'native_renderer_not_restarted':True,'source_media_unchanged':True},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');run(parser.parse_args().execute)
