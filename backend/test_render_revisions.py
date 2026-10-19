import ast
import contextlib
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, StrictBool

from automation import render_output_mode
from render_revisions import RenderRevisions, init_schema


class RevisionTests(unittest.TestCase):
    def test_priority_newest_first_without_preempting_running(self):
        self.add_job('second',title='另一个歌')
        batch=self.service.create('mang',['original','second'])
        rows=self.service.items(batch['batch_id'])['items']
        old,new=rows[0]['job_id'],rows[1]['job_id']
        with self.db() as c:
            c.execute('UPDATE render_revisions SET priority_at=100 WHERE job_id=?',(old,))
            c.execute('UPDATE render_revisions SET priority_at=200 WHERE job_id=?',(new,))
        self.assertEqual(self.service.next_item()['job_id'],new)
        self.service.set_status(old,'running')
        self.assertEqual(self.service.next_item()['job_id'],old)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.database=self.root/'db'
        self.profile={'id':'mang','name':'芒芒_Mou','style':{'effect':'folia-native','folia':{'mode':'tilt','keep_alpha_mov':True}},'recorder_identity':{'platform':'bilibili','room_id':'1'}}
        self.source=self.root/'歌.mp4'; self.source.write_bytes(b'source-unchanged')
        self.video=self.root/'old.mp4'; self.video.write_bytes(b'old-video-unchanged')
        with self.db() as c:
            c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,created_at REAL,updated_at REAL,status TEXT,source TEXT,title TEXT,artist TEXT,identified_title TEXT,identified_artist TEXT,identity_source TEXT,alignment TEXT,style TEXT,output TEXT,error TEXT,future_column TEXT)')
            c.execute('CREATE TABLE automation_runs(id TEXT PRIMARY KEY,profile_id TEXT,songs TEXT)')
            c.execute('CREATE TABLE song_projects(id TEXT,broadcaster_key TEXT)')
            c.execute('CREATE TABLE publish_jobs(id TEXT,source_job_id TEXT,automation_run_id TEXT,song_project_id TEXT,identified_title TEXT,streamer TEXT,bililive_task_id TEXT,aid TEXT,bvid TEXT,status TEXT)')
            init_schema(c)
        self.add_job('original')
        self.service=RenderRevisions(self.db,self.get_job,lambda _:self.profile,Path,self.root)

    def tearDown(self): self.temp.cleanup()

    @contextlib.contextmanager
    def db(self):
        c=sqlite3.connect(self.database,timeout=10); c.row_factory=sqlite3.Row
        try: yield c; c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()

    def add_job(self,jid,title='真实歌名'):
        with self.db() as c:
            c.execute('INSERT INTO jobs(id,created_at,updated_at,status,source,title,artist,identified_title,identified_artist,identity_source,alignment,style,output,future_column) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (jid,1,1,'completed',self.source.name,'错误显示标题','错误候选歌手',title,'真实歌手','acrcloud',json.dumps({'lines':[{'text':'歌词'}],'timeline_match':{'confidence_tier':'high'}}),json.dumps(self.profile['style']),json.dumps({'path':str(self.video),'sample':False,'confidence_tier':'high'}),'future-value'))
            c.execute('INSERT INTO automation_runs(id,profile_id,songs) VALUES(?,?,?)',(jid+'-run','mang',json.dumps([{'project_id':jid}])))

    def get_job(self,jid):
        with self.db() as c: j=dict(c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
        for key in ('alignment','style','output'): j[key]=json.loads(j[key] or '{}')
        return j

    def update_job(self,jid,**values):
        with self.db() as c:
            c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',tuple(json.dumps(v) if isinstance(v,dict) else v for v in values.values())+(jid,))

    def complete(self,jid):
        path=self.root/(jid+'.mp4'); path.write_bytes(b'new-smooth')
        self.update_job(jid,status='completed',output={'path':str(path),'output_mode':'smooth','sample':False})

    def test_only_explicit_profile_mode_and_no_alpha(self):
        self.assertEqual(render_output_mode({}),'fast')
        self.assertEqual(render_output_mode({'render_output_mode':'smooth'}),'smooth')
        for mode in ('alpha','unknown'):
            with self.assertRaises(ValueError): render_output_mode({'render_output_mode':mode})

    def test_new_revision_preserves_identity_timeline_original_and_future_columns(self):
        before=self.get_job('original'); result=self.service.create('mang',['original'],True)
        item=self.service.next_item(); j=self.get_job(item['job_id'])
        self.assertEqual(self.get_job('original'),before)
        for key in ('identified_title','identified_artist','identity_source','alignment','future_column'): self.assertEqual(j[key],before[key])
        self.assertEqual(j['render_revision_parent_id'],'original'); self.assertEqual(j['render_revision_publish'],1)
        self.assertFalse(j['style']['folia']['keep_alpha_mov']); self.assertFalse(result['keep_mov'])
        self.assertEqual(item['publish_status'],'pending')
        self.assertEqual(self.video.read_bytes(),b'old-video-unchanged'); self.assertEqual(self.source.read_bytes(),b'source-unchanged')

    def test_legacy_effect_uses_bound_native_style_without_changing_lyrics(self):
        self.update_job('original',style={'effect':'classic'})
        self.service.create('mang',['original']); j=self.get_job(self.service.next_item()['job_id'])
        self.assertEqual(j['style']['effect'],'folia-native'); self.assertEqual(j['style']['folia']['mode'],'tilt')
        self.assertEqual(j['alignment'],self.get_job('original')['alignment'])

    def test_sample_missing_identity_and_missing_file_are_rejected_atomically(self):
        cases=[{'identified_title':''},{'status':'failed'},{'output':{'sample':True,'path':str(self.video)}},{'source':'../outside.mp4'},{'alignment':{'lines':[]}}]
        before=self.get_job('original')
        for values in cases:
            self.update_job('original',**values)
            with self.assertRaises(ValueError): self.service.create('mang',['original'])
            self.update_job('original',**{k:before[k] for k in values})
        self.video.unlink()
        with self.assertRaises(ValueError): self.service.create('mang',['original'])
        with self.db() as c: self.assertEqual(c.execute('SELECT count(*) FROM render_revisions').fetchone()[0],0)

    def test_dedup_and_posted_song_guard(self):
        self.add_job('duplicate',title='真實歌名 (Live)')
        with self.assertRaises(ValueError): self.service.create('mang',['original','duplicate'])
        with self.db() as c: c.execute("INSERT INTO publish_jobs(id,automation_run_id,identified_title,status,bililive_task_id) VALUES('accepted','original-run','真实歌名','uploading','task')")
        with self.assertRaises(ValueError): self.service.create('mang',['original'])

    def test_concurrent_same_source_only_one_revision(self):
        results=[]; errors=[]
        def call():
            try: results.append(self.service.create('mang',['original']))
            except ValueError as exc: errors.append(str(exc))
        threads=[threading.Thread(target=call) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(results),1); self.assertEqual(len(errors),2)

    def test_restart_pending_and_completed_reuse(self):
        self.service.create('mang',['original']); item=self.service.next_item()
        fresh=RenderRevisions(self.db,self.get_job,lambda _:self.profile,Path,self.root)
        fresh.execute(item,self.complete,Mock(side_effect=AssertionError('no renderer ID')))
        render=Mock(side_effect=AssertionError('must not rerender')); fresh.execute(item,render,Mock())
        self.assertEqual(fresh.items()['counts'],{'completed':1}); render.assert_not_called()
        self.assertEqual(self.video.read_bytes(),b'old-video-unchanged')

    def test_known_renderer_id_resumes_without_second_create(self):
        self.service.create('mang',['original']); item=self.service.next_item()
        self.update_job(item['job_id'],status='rendering',output={'render_id':'durable-id','output_mode':'smooth'})
        render=Mock(); resume=Mock(side_effect=self.complete)
        self.service.execute(item,render,resume); render.assert_not_called(); resume.assert_called_once_with(item['job_id'])

    def test_failure_never_changes_original(self):
        before=self.get_job('original'); self.service.create('mang',['original']); item=self.service.next_item()
        with self.assertRaises(RuntimeError): self.service.execute(item,Mock(side_effect=RuntimeError('render error')),Mock())
        self.assertEqual(before,self.get_job('original')); self.assertEqual(self.video.read_bytes(),b'old-video-unchanged')

    def test_publish_failure_separate_and_success_idempotent(self):
        self.service.create('mang',['original'],True); item=self.service.next_item(); self.service.execute(item,self.complete,Mock())
        with self.assertRaises(RuntimeError): self.service.publish_next(Mock(side_effect=RuntimeError('publish error')))
        row=self.service.items()['items'][0]
        self.assertEqual(row['status'],'completed'); self.assertEqual(row['publish_status'],'failed'); self.assertEqual(row['project_status'],'completed')
        with self.db() as c: c.execute("UPDATE render_revisions SET publish_status='pending'")
        enqueue=Mock(return_value={'id':'publish-task'}); self.service.publish_next(enqueue); self.service.publish_next(enqueue)
        enqueue.assert_called_once(); self.assertEqual(self.service.items()['items'][0]['publish_status'],'enqueued')

    def test_render_only_never_calls_publish(self):
        self.service.create('mang',['original']); self.service.execute(self.service.next_item(),self.complete,Mock())
        handoff=Mock(); self.service.publish_next(handoff); handoff.assert_not_called()

    def test_schema_idempotent_and_named_inserts(self):
        with self.db() as c: init_schema(c); init_schema(c)
        source=Path(__file__).with_name('render_revisions.py').read_text(encoding='utf-8')
        self.assertNotIn('INSERT INTO jobs VALUES(',source)
        app=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        self.assertIn("render_task(project['id'],False,0,render_output_mode(current_profile))",app)
        self.assertIn("if j.get('render_revision_parent_id'): outdir=outdir/('逐帧重制_'+jid)",app)
        docker=Path(__file__).with_name('Dockerfile').read_text(encoding='utf-8')
        self.assertIn('render_revisions.py',docker)


class RevisionRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.database=Path(self.temp.name)/'db'
        with self.db() as c:
            c.execute("CREATE TABLE automation_profiles(id TEXT PRIMARY KEY,render_output_mode TEXT DEFAULT 'fast',updated_at REAL,style TEXT)")
            c.executemany('INSERT INTO automation_profiles(id,style) VALUES(?,?)', [('mang','{"effect":"folia-native"}'),('other','{"effect":"folia-native"}'),('legacy','{"effect":"classic"}')])
        self.service=Mock(); self.service.create.return_value={'count':1}
        names={'ProfileRenderIn','RenderRevisionsIn','update_profile_render_output','create_render_revisions'}
        tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        nodes=[node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names]
        self.ns={'app':FastAPI(),'BaseModel':BaseModel,'StrictBool':StrictBool,'HTTPException':HTTPException,
                 'db':self.db,'get_automation_profile':self.profile,'render_output_mode':render_output_mode,
                 'time':time,'render_revision_service':lambda:self.service}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'revision-routes','exec'),self.ns)
        self.client=TestClient(self.ns['app'])

    def tearDown(self): self.temp.cleanup()

    @contextlib.contextmanager
    def db(self):
        c=sqlite3.connect(self.database); c.row_factory=sqlite3.Row
        try: yield c; c.commit()
        finally: c.close()

    def profile(self,id):
        with self.db() as c: row=c.execute('SELECT * FROM automation_profiles WHERE id=?',(id,)).fetchone()
        if not row: raise HTTPException(404,'missing profile')
        item=dict(row); item['style']=json.loads(item['style']); return item

    def test_save_only_selected_broadcaster_and_preserve_style(self):
        before=self.profile('mang')['style']
        response=self.client.put('/api/automation/profiles/mang/render-output',json={'output_mode':'smooth'})
        self.assertEqual(response.status_code,200); self.assertEqual(self.profile('mang')['render_output_mode'],'smooth')
        self.assertEqual(self.profile('mang')['style'],before); self.assertEqual(self.profile('other')['render_output_mode'],'fast')

    def test_alpha_invalid_and_non_native_are_rejected(self):
        for mode in ('alpha','bad',''):
            self.assertEqual(self.client.put('/api/automation/profiles/mang/render-output',json={'output_mode':mode}).status_code,400)
        self.assertEqual(self.client.put('/api/automation/profiles/legacy/render-output',json={'output_mode':'smooth'}).status_code,400)
        self.assertEqual(self.client.put('/api/automation/profiles/missing/render-output',json={'output_mode':'smooth'}).status_code,404)

    def test_revisions_enqueued_by_explicit_request_and_strict_boolean(self):
        response=self.client.post('/api/automation/profiles/mang/render-revisions',json={'project_ids':['old'],'enqueue_publish':True})
        self.assertEqual(response.status_code,200);self.service.create.assert_called_once_with('mang',['old'],True)
        self.assertEqual(self.client.post('/api/automation/profiles/mang/render-revisions',json={'project_ids':['old'],'enqueue_publish':'false'}).status_code,422)

    def test_duplicate_error_is_400_and_no_second_batch(self):
        self.service.create.side_effect=ValueError('duplicate')
        self.assertEqual(self.client.post('/api/automation/profiles/mang/render-revisions',json={'project_ids':['old']}).status_code,400)
