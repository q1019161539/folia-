import base64
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import httpx
from PIL import Image
from publish_v2 import (PublishingV2, GPTCoverClient, CoverError, init_schema, normalized_title,
                        eligible, image_bytes, broadcaster_key, PROMPT, COVER_MAX_ATTEMPTS)
from publishing import PublishSettings, PublishRetryableError, BililiveToolClient


class Cover:
    model='gpt-image-2'; key='not-persisted'
    def __init__(self): self.calls=0; self.fail=False
    def generate(self,ref,prompt):
        self.calls+=1
        if self.fail: raise CoverError('timeout',True)
        buffer=io.BytesIO(); Image.new('RGB',(1280,720),'pink').save(buffer,format='PNG')
        return buffer.getvalue()


class Bili:
    def __init__(self): self.calls=0; self.fail=False; self.tasks=[]; self.complete=False; self.desc='主播模板简介'
    def close(self): pass
    def get_video_preset(self,id): return {'config':{'tid':31,'copyright':2,'desc':self.desc,'source':'原直播链接'}}
    def format_description(self,template,options): return template
    def validate_upload_config(self,config):
        if self.fail: raise PublishRetryableError('offline')
        return {'status_code':200,'body':'success'}
    def list_upload_tasks(self): return self.tasks
    def create_upload(self,payload): self.calls+=1; self.payload=payload; return 'task-1'
    def get_upload_task(self,id): return {'status':'completed' if self.complete else 'running','output':'123','progress':50}
    def archive_detail(self,aid,uid): return {'archive':{'bvid':'BVtest','state':-30,'state_desc':'审核中'}}


class V2Tests(unittest.TestCase):
    def tracked_collection(self):
        preset={'config':{'tid':31,'copyright':2,'desc':'模板简介','seasonId':789,'sectionId':321}}
        self.bili.get_video_preset=lambda _:preset
        self.bili.collection_capabilities=lambda:{'version':1,'durable':True}
        _,job=self.attach();self.service.prepare(job)
        return self.service.row('publish_jobs',job['id'])

    def test_collection_opt_in_preserves_template_and_caches_only_new_uploads(self):
        job=self.tracked_collection();payload=json.loads(job['bililive_payload_json'])
        self.assertEqual(job['collection_status'],'pending')
        self.assertTrue(payload['options']['foliaCollectionTracking'])
        self.assertFalse(payload['options']['removeOriginAfterUploadCheck'])
        self.assertEqual(payload['config']['seasonId'],789);self.assertEqual(payload['config']['sectionId'],321)
        self.new_service().prepare(job);self.assertEqual(self.gpt.calls,1)

    def test_collection_result_is_separate_from_upload_and_does_not_repost(self):
        job=self.tracked_collection();self.service.submit(job);self.bili.complete=True
        self.bili.collection_job=lambda aid,uid:{'aid':aid,'uid':uid,'seasonId':789,'taskId':'task-1','status':'retry','attempts':1,'error':'HTTP 412'}
        self.service.poll(self.service.row('publish_jobs',job['id']))
        saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['status'],'completed');self.assertEqual(saved['aid'],'123')
        self.assertEqual(saved['collection_status'],'retry');self.assertEqual(saved['collection_error'],'HTTP 412')
        self.bili.collection_job=lambda aid,uid:{'aid':aid,'uid':uid,'seasonId':789,'taskId':'task-1','status':'joined','attempts':2,'error':''}
        self.service.update('publish_jobs',job['id'],next_collection_at=0,next_review_at=time.time()+3600)
        self.new_service().tick();saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['collection_status'],'joined');self.assertEqual(self.bili.calls,1);self.assertEqual(self.gpt.calls,1)

    def test_collection_lookup_failure_and_conflict_preserve_completed_and_identity(self):
        job=self.tracked_collection();self.service.submit(job)
        self.service.update('publish_jobs',job['id'],aid='123',status='completed',published_at=time.time())
        with patch.object(self.bili,'collection_job',create=True,side_effect=PublishRetryableError('offline')):
            self.service.poll_collection(self.service.row('publish_jobs',job['id']))
        saved=self.service.row('publish_jobs',job['id']);self.assertEqual(saved['status'],'completed');self.assertEqual(saved['collection_status'],'pending')
        self.bili.collection_job=lambda aid,uid:{'seasonId':999,'taskId':'task-1','status':'joined'}
        self.service.update('publish_jobs',job['id'],next_collection_at=0)
        self.new_service().poll_collection(self.service.row('publish_jobs',job['id']))
        saved=self.service.row('publish_jobs',job['id']);self.assertEqual(saved['collection_status'],'failed');self.assertEqual(saved['status'],'completed')
        self.assertEqual(saved['identified_title'],'离人赋');self.assertEqual(saved['identified_artist'],'云汐');self.assertEqual(self.bili.calls,1)

    def test_historical_user_fixed_completed_is_not_enqueued_or_checked(self):
        _,job=self.attach();self.service.prepare(job);self.service.submit(self.service.row('publish_jobs',job['id']))
        self.service.update('publish_jobs',job['id'],status='completed',aid='123',next_review_at=time.time()+3600)
        with patch.object(self.bili,'collection_job',create=True,side_effect=AssertionError('historical archive must not be touched')):
            self.new_service().tick()
        self.assertIsNone(self.service.row('publish_jobs',job['id'])['collection_status']);self.assertEqual(self.bili.calls,1)

    def test_missing_collection_adapter_stops_ready_snapshot_before_upload(self):
        job=self.tracked_collection()
        with patch.object(self.bili,'collection_capabilities',side_effect=PublishRetryableError('adapter unavailable')):
            self.new_service().submit(job)
        saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(self.bili.calls,0);self.assertEqual(saved['status'],'ready');self.assertEqual(saved['submit_attempts'],0)
        self.assertIsNotNone(saved['next_retry_at'])

    def test_explicit_existing_archive_collection_test_keeps_frozen_payload_and_no_reupload(self):
        job=self.tracked_collection();payload=json.loads(job['bililive_payload_json'])
        payload['options'].pop('foliaCollectionTracking')
        frozen=json.dumps(payload)
        job=self.service.update('publish_jobs',job['id'],bililive_payload_json=frozen,collection_status=None)
        self.service.submit(job);self.service.update('publish_jobs',job['id'],status='completed',aid='123',published_at=time.time(),next_review_at=time.time()+3600)
        # Only explicit operator opt-in, not historical scanning or snapshot migration.
        self.service.update('publish_jobs',job['id'],collection_status='pending')
        self.bili.collection_job=lambda aid,uid:{'uid':uid,'aid':aid,'taskId':'task-1','seasonId':789,'status':'joined','attempts':1}
        self.new_service().tick();saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['collection_status'],'joined');self.assertEqual(saved['bililive_payload_json'],frozen)
        self.assertEqual(saved['status'],'completed');self.assertEqual(saved['aid'],'123');self.assertEqual(self.bili.calls,1);self.assertEqual(self.gpt.calls,1)

    def test_title_receipt_recovers_after_database_failure_without_paid_retry(self):
        _,job=self.attach()
        original_update=self.service.update
        title='🌸清风吹来旧心事｜《离人赋》｜【芒芒_Mou】翻唱'
        record={'source':'ai','attempts':1}
        def fail_title(table,id,**values):
            if 'title' in values: raise sqlite3.OperationalError('database is locked')
            return original_update(table,id,**values)
        with patch.object(self.service,'update',side_effect=fail_title), patch('publish_v2.generate_publish_title',return_value=(title,record)) as generator:
            self.service.prepare(job)
        saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['status'],'pending');self.assertIsNotNone(saved['next_retry_at'])
        with patch('publish_v2.generate_publish_title',side_effect=AssertionError('must reuse title receipt')):
            self.new_service().prepare(saved)
        saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['title'],title);self.assertEqual(saved['status'],'ready')
        self.assertEqual(generator.call_count,1);self.assertEqual(self.gpt.calls,1)

    def test_newer_title_receipt_replaces_old_retry_fallback(self):
        _,job=self.attach()
        self.service.update('publish_jobs',job['id'],title='旧fallback',title_generation_json=json.dumps({'attempts':1,'retry_pending':True}))
        title='🌸清风吹来旧心事｜《离人赋》｜【芒芒_Mou】翻唱'
        self.service.checkpoint(job,'title',{'title':title,'title_generation_json':json.dumps({'attempts':2,'source':'ai'})})
        with patch('publish_v2.generate_publish_title',side_effect=AssertionError('must reuse newest response')):
            self.new_service().prepare(self.service.row('publish_jobs',job['id']))
        self.assertEqual(self.service.row('publish_jobs',job['id'])['title'],title)

    def test_cover_database_failure_reuses_raw_image_and_original_video(self):
        song,job=self.attach();original=Path(job['video_path']).read_bytes()
        update=self.service.update
        def fail_ready(table,id,**values):
            if table=='song_projects' and values.get('cover_status')=='ready':
                raise sqlite3.OperationalError('database is locked')
            return update(table,id,**values)
        with patch.object(self.service,'update',side_effect=fail_ready):self.service.prepare(job)
        saved=self.service.row('publish_jobs',job['id']);self.assertEqual(saved['status'],'pending')
        self.new_service().prepare(saved)
        self.assertEqual(self.gpt.calls,1);self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'ready')
        self.assertEqual(Path(job['video_path']).read_bytes(),original)

    def test_accepted_id_receipt_survives_lock_and_restart_without_second_post(self):
        _,job=self.attach();self.service.prepare(job);job=self.service.row('publish_jobs',job['id'])
        update=self.service.update
        def fail_id(table,id,**values):
            if values.get('bililive_task_id'):raise sqlite3.OperationalError('database is locked')
            return update(table,id,**values)
        with patch.object(self.service,'update',side_effect=fail_id):self.service.submit(job)
        saved=self.service.row('publish_jobs',job['id']);self.assertEqual(saved['status'],'submitting')
        self.assertIsNone(saved['bililive_task_id']);self.assertEqual(self.bili.calls,1)
        self.new_service().submit(saved)
        saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['bililive_task_id'],'task-1');self.assertEqual(saved['status'],'uploading')
        self.assertEqual(self.bili.calls,1)
        receipt=self.service.checkpoint(saved,'accepted')
        self.assertEqual(receipt['bililive_task_id'],'task-1')
        text=''.join(p.read_text() for p in (self.root/'publish'/'songs'/job['song_project_id']/'checkpoints').glob('*.json'))
        self.assertNotIn('not-persisted',text);self.assertNotIn('secret',text)

    def test_aid_receipt_survives_lock_when_remote_task_disappears(self):
        _,job=self.attach();self.service.prepare(job);self.service.submit(self.service.row('publish_jobs',job['id']))
        self.bili.complete=True;update=self.service.update
        def fail_aid(table,id,**values):
            if values.get('aid'):raise sqlite3.OperationalError('database is locked')
            return update(table,id,**values)
        with patch.object(self.service,'update',side_effect=fail_aid):self.service.poll(self.service.row('publish_jobs',job['id']))
        with patch.object(self.bili,'get_upload_task',side_effect=AssertionError('must reuse AID receipt')):
            self.new_service().poll(self.service.row('publish_jobs',job['id']))
        saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['aid'],'123');self.assertEqual(saved['bvid'],'BVtest');self.assertEqual(saved['status'],'completed')
        self.assertEqual(self.bili.calls,1)

    def test_receipt_mismatch_and_missing_known_task_never_submit(self):
        _,job=self.attach();self.service.prepare(job);job=self.service.row('publish_jobs',job['id'])
        self.service.checkpoint(job,'accepted',{'bililive_task_id':'task-1','status':'uploading'})
        self.service.update('publish_jobs',job['id'],bililive_payload_json='{}')
        self.new_service().submit(self.service.row('publish_jobs',job['id']))
        self.assertEqual(self.bili.calls,0)
        self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'failed')
        # Existing accepted IDs are not re-created even when the remote query loses them.
        self.service.update('publish_jobs',job['id'],bililive_payload_json=job['bililive_payload_json'],bililive_task_id='task-1',status='uploading')
        with patch.object(self.bili,'get_upload_task',return_value=None):self.new_service().poll(self.service.row('publish_jobs',job['id']))
        self.service.recover_database_failures()
        self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'failed');self.assertEqual(self.bili.calls,0)

    def test_recover_only_never_submitted_v2_lock_failures_keeps_assets(self):
        _,job=self.attach();self.service.prepare(job)
        self.service.update('publish_jobs',job['id'],status='failed',publish_error='database is locked',failure_stage='title')
        before=self.service.row('publish_jobs',job['id']);self.new_service().recover_database_failures()
        saved=self.service.row('publish_jobs',job['id']);self.assertEqual(saved['status'],'pending')
        for key in ('cover_path','title','title_generation_json','bililive_payload_json','publish_attempts'):
            self.assertEqual(saved[key],before[key])
        self.service.update('publish_jobs',job['id'],status='failed',failure_stage='submit')
        self.service.recover_database_failures()
        self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'ready')
        for changes in ({'pipeline_version':1},{'submit_attempts':1},{'bililive_task_id':'known'},{'aid':'123'},{'bvid':'BVx'},{'failure_stage':'upload'},{'publish_error':'invalid params'}):
            self.service.update('publish_jobs',job['id'],status='failed',pipeline_version=2,submit_attempts=0,bililive_task_id=None,aid=None,bvid=None,failure_stage='title',publish_error='database is locked')
            self.service.update('publish_jobs',job['id'],**changes);self.service.recover_database_failures()
            self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'failed')

    def test_authorized_revision_requires_scope_smooth_high_and_current_audio(self):
        from performance_gate import screen_clip,gate_settings,VERSION
        p=self.project();p.update(render_revision_parent_id='original',render_revision_batch_id='explicit-batch',render_revision_publish=1)
        p['output']['output_mode']='smooth'
        clip=self.root/'clip.mp4';clip.write_bytes(b'real input')
        st=clip.stat();fingerprint={'path':str(clip.resolve()),'size':st.st_size,'mtime_ns':st.st_mtime_ns}
        p['alignment']['performance_gate']={'version':VERSION,'decision':'pass','settings':gate_settings(),'input':fingerprint,'mean_db':-18.,'peak_db':-1.}
        _,job=self.attach(p)
        with self.db() as c:
            c.execute("UPDATE app_meta SET value=? WHERE key='publish_v2_rollout'",(json.dumps({'mode':'active','allowlist':[], 'cutover':9999999999,
                      'authorized_render_batches':[{'batch_id':'explicit-batch','profile_id':'profile'}]}),))
        self.assertTrue(self.service.allowed(p['id'],100))
        for field,value in [('output_mode','fast'),('confidence_tier','local')]:
            before=p['output'][field];p['output'][field]=value
            self.assertFalse(self.service.allowed(p['id'],100));p['output'][field]=before
        p['alignment']['performance_gate']['decision']='skip';self.assertFalse(self.service.allowed(p['id'],100))
        p['alignment']['performance_gate']['decision']='pass'
        p['render_revision_publish']=0;self.assertFalse(self.service.allowed(p['id'],100));p['render_revision_publish']=1
        self.run['profile_id']='other';self.assertFalse(self.service.allowed(p['id'],100));self.run['profile_id']='profile'
        clip.write_bytes(b'changed clip');self.assertFalse(self.service.allowed(p['id'],100))
        self.assertFalse(self.service.allowed(self.project('unrelated')['id'],100))

    def test_revision_priority_uses_recording_time_and_tick_newest_first(self):
        old=self.project('older',title='旧歌');old['render_revision_parent_id']='original-old';old['render_revision_publish']=1
        new=self.project('newer',title='新歌');new['render_revision_parent_id']='original-new';new['render_revision_publish']=1
        self.run['source']='芒芒_Mou/2026-09-20/09-00-00_video.mp4'
        sid=self.service.attach(old,self.run,self.profile,enqueue=True)
        oldjob=self.service.row('publish_jobs',self.service.row('song_projects',sid)['publish_job_id'])
        self.run['source']='芒芒_Mou/2026-10-07/09-00-00_video.mp4'
        sid=self.service.attach(new,self.run,self.profile,enqueue=True)
        newjob=self.service.row('publish_jobs',self.service.row('song_projects',sid)['publish_job_id'])
        self.assertGreater(newjob['priority_at'],oldjob['priority_at'])
        self.assertGreater(newjob['created_at'],oldjob['created_at'])
        with patch.object(self.service,'prepare') as prepare:
            self.service.tick()
        self.assertEqual(prepare.call_args.args[0]['id'],newjob['id'])
        self.assertEqual(self.bili.calls,0);self.assertEqual(self.gpt.calls,0)

    def test_prompt_locks_face_but_not_pose(self):
        prompt= PROMPT.format(song='鱼仔')
        self.assertIn('脸型、五官比例、瞳色、发型和标志性配饰',prompt)
        self.assertIn('不重新设计面部',prompt)
        self.assertIn('表情、视线、动作和姿态',prompt)
        self.assertIn('左侧完整写出歌名“鱼仔”',prompt)
        self.assertIn('书名号可加可不加，由AI根据排版自由决定',prompt)
        self.assertNotIn('《',prompt);self.assertNotIn('》',prompt)
        self.assertNotIn('姿势不变',prompt)
        self.assertIn('参考图仅用于保持人物身份，不沿用直播背景',prompt)
        self.assertIn('根据歌曲独立设计场景、主色调和光线',prompt)
        self.assertIn('避免统一套用同一种背景风格',prompt)

    def test_parentheses_removed_from_cover_metadata_not_identity_or_dedup(self):
        raw='公主殿下 (cover: 崔洋)(完整版)';p=self.project(title=raw,artist='崔洋');song,job=self.attach(p)
        with patch.object(self.bili,'format_description',wraps=self.bili.format_description) as formatter:
            self.service.prepare(job)
        saved=self.service.row('publish_jobs',job['id']);cover=self.service.row('song_projects',song['id'])
        payload=json.loads(saved['bililive_payload_json'])
        self.assertIn('《公主殿下》',saved['title']);self.assertNotIn('(cover:',saved['title'])
        self.assertIn('歌名“公主殿下”',cover['cover_prompt']);self.assertNotIn('(完整版)',cover['cover_prompt'])
        self.assertEqual(formatter.call_args.args[1]['title'],'公主殿下')
        self.assertEqual(payload['videos'][0]['title'],'公主殿下')
        self.assertIn('公主殿下',json.loads(saved['tags_json']))
        for identity in (p,job,saved,song):self.assertEqual(identity['identified_title'],raw);self.assertEqual(identity['identified_artist'],'崔洋')
        self.assertEqual(song['song_key'],normalized_title(raw))
        self.new_service().prepare(saved);self.assertEqual(self.gpt.calls,1)

    def test_old_and_policy_pass_cannot_prepare_or_upload(self):
        p=self.project();_,job=self.attach(p)
        p['alignment']['performance_gate']={'version':'quiet-clip-v1','decision':'pass','mean_db':-37.,'peak_db':-9.1}
        self.service.prepare(job)
        self.assertEqual(self.gpt.calls,0);self.assertEqual(self.bili.calls,0)
        self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'failed')

    def test_ready_cover_preserved_when_tighter_policy_blocks_submission(self):
        p=self.project();_,job=self.attach(p);self.service.prepare(job)
        saved=self.service.row('publish_jobs',job['id']);song_before=self.service.row('song_projects',saved['song_project_id'])
        original=Path(saved['video_path']).read_bytes()
        p['alignment']['performance_gate']={'decision':'pass','mean_db':-20.,'peak_db':-18.}
        self.new_service().submit(saved)
        self.assertEqual(self.bili.calls,0);self.assertEqual(self.gpt.calls,1)
        song_after=self.service.row('song_projects',saved['song_project_id'])
        for key in ('cover_attempts','cover_path','cover_sha256'):
            self.assertEqual(song_before[key],song_after[key])
        self.assertEqual(Path(saved['video_path']).read_bytes(),original)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.database=self.root/'db.sqlite'
        self.projects={}; self.profile={'id':'profile','name':'芒芒_Mou','publish_streamer':'芒芒_Mou','bililive_preset_id':'preset',
                                      'recorder_identity':{'platform':'bilibili','room_id':'1'}}
        self.run={'id':'run','profile_id':'profile','mtime':100,'source':'芒芒_Mou/2026-10-07/09-05-13_video.mp4'}
        app=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        ddl='CREATE TABLE IF NOT EXISTS publish_jobs('+app.split("c.execute('''CREATE TABLE IF NOT EXISTS publish_jobs(",1)[1].split(")''')",1)[0]+')'
        with self.db() as c:
            c.execute('PRAGMA journal_mode=WAL'); c.execute(ddl)
            c.execute('CREATE TABLE automation_profiles(id TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE app_meta(key TEXT PRIMARY KEY,value TEXT)')
            init_schema(c)
            c.execute("UPDATE app_meta SET value=? WHERE key='publish_v2_rollout'",(json.dumps({'mode':'active','allowlist':[],'cutover':0}),))
        self.settings=PublishSettings(True,True,'http://bili/api','secret',1,'preset',self.root,self.root/'legacy',Path('/shared'),Path('/legacy'),self.root/'old',self.root/'covers')
        self.gpt=Cover(); self.bili=Bili()
        self.service=self.new_service()
        reference=self.root/'ref.png'; Image.new('RGB',(1280,720)).save(reference)
        self.frames=patch('publish_v2.select_reference_frame',return_value={'status':'selected','time_seconds':10,'frame_path':str(reference)})
        self.frames.start()

    def tearDown(self): self.frames.stop(); self.temp.cleanup()

    @contextlib.contextmanager
    def db(self):
        c=sqlite3.connect(self.database,timeout=10); c.row_factory=sqlite3.Row
        try:
            yield c; c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()

    def new_service(self): return PublishingV2(self.db,self.settings,lambda id:self.projects[id],lambda id:self.run,lambda id:self.profile,lambda:self.gpt,lambda:self.bili)

    def project(self,id='p1',title='离人赋',artist='云汐',tier='high'):
        video=self.root/f'{id}.mp4'; video.write_bytes(b'original-video')
        p={'id':id,'identified_title':title,'identified_artist':artist,'identity_source':'acrcloud','status':'completed','updated_at':100,
           'title':'错误显示标题','manual_title':'错误手动标题','matched_title':'错误歌词标题',
           'output':{'path':str(video),'sample':False,'confidence_tier':tier,'finalized_at':100},'alignment':{'timeline_match':{'confidence_tier':tier}}}
        self.projects[id]=p
        return p

    def attach(self,p=None,profile=None):
        sid=self.service.attach(p or self.project(),self.run,profile or self.profile)
        song=self.service.row('song_projects',sid)
        job=self.service.row('publish_jobs',song['publish_job_id']) if song['publish_job_id'] else None
        return song,job

    def test_fallback_after_six_failures_persists_model_before_request_and_reuses_cache(self):
        song,job=self.attach();self.service.update('song_projects',song['id'],cover_attempts=6)
        gemini=Cover();gemini.model='gemini-3-pro-image-preview'
        original=gemini.generate
        def generate(ref,prompt):
            saved=self.service.row('song_projects',song['id'])
            self.assertEqual(saved['cover_attempts'],7);self.assertEqual(saved['cover_model'],gemini.model)
            receipt=json.loads((self.root/'publish'/'songs'/song['id']/'attempt-7.json').read_text())
            self.assertEqual(receipt['provider'],'gemini');self.assertEqual(receipt['status'],'request_started')
            self.assertNotIn(gemini.key,json.dumps(receipt));self.assertIn('半身近景',prompt)
            return original(ref,prompt)
        gemini.generate=generate
        with patch.dict(os.environ,{'COVER_FALLBACK_ENABLED':'1','COVER_FALLBACK_API_KEY':'test-key'}),patch('publish_v2.GeminiCoverClient',return_value=gemini):
            self.service.prepare(job)
            self.new_service().prepare(self.service.row('publish_jobs',job['id']))
        saved=self.service.row('publish_jobs',job['id'])
        self.assertEqual(saved['status'],'ready');self.assertEqual(gemini.calls,1);self.assertEqual(self.gpt.calls,0)
        self.assertEqual(saved['identified_title'],'离人赋');self.assertEqual(saved['identified_artist'],'云汐')

    def test_gemini_primary_first_attempt_cache_restart_and_budget(self):
        song,job=self.attach();gemini=Cover();gemini.model='gemini-3-pro-image-preview'
        with patch.dict(os.environ,{'COVER_PRIMARY_PROVIDER':'gemini','COVER_FALLBACK_ENABLED':'1','COVER_FALLBACK_API_KEY':'test-key'}),patch('publish_v2.GeminiCoverClient',return_value=gemini):
            self.service.prepare(job)
            self.new_service().prepare(self.service.row('publish_jobs',job['id']))
        saved=self.service.row('song_projects',song['id'])
        self.assertEqual(saved['cover_attempts'],1);self.assertEqual(saved['cover_model'],gemini.model)
        self.assertEqual(gemini.calls,1);self.assertEqual(self.gpt.calls,0)
        self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'ready')
        self.assertEqual(saved['identified_title'],'离人赋')
        receipt=json.loads((self.root/'publish'/'songs'/song['id']/'attempt-1.json').read_text())
        self.assertEqual(receipt['provider'],'gemini')

    def test_gemini_primary_recovery_preserves_attempts_and_ten_request_cap(self):
        song,job=self.attach();self.service.update('song_projects',song['id'],cover_attempts=9)
        gemini=Cover();gemini.model='gemini-3-pro-image-preview';gemini.fail=True
        with patch.dict(os.environ,{'COVER_PRIMARY_PROVIDER':'gemini','COVER_FALLBACK_ENABLED':'1','COVER_FALLBACK_API_KEY':'test-key'}),patch('publish_v2.GeminiCoverClient',return_value=gemini):
            self.service.prepare(job);self.new_service().prepare(self.service.row('publish_jobs',job['id']))
        self.assertEqual(gemini.calls,1);self.assertEqual(self.gpt.calls,0)
        self.assertEqual(self.service.row('song_projects',song['id'])['cover_attempts'],10)
        self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'failed')

    def test_fallback_does_not_reset_total_budget_or_retry_auth_errors(self):
        song,job=self.attach();self.service.update('song_projects',song['id'],cover_attempts=9)
        gemini=Cover();gemini.model='gemini-3-pro-image-preview';gemini.fail=True
        with patch.dict(os.environ,{'COVER_FALLBACK_ENABLED':'1','COVER_FALLBACK_API_KEY':'test-key'}),patch('publish_v2.GeminiCoverClient',return_value=gemini):
            self.service.prepare(job);self.service.prepare(self.service.row('publish_jobs',job['id']))
        self.assertEqual(gemini.calls,1);self.assertEqual(self.service.row('song_projects',song['id'])['cover_attempts'],10)
        self.assertEqual(self.service.row('publish_jobs',job['id'])['status'],'failed')
        self.assertEqual(Path(job['video_path']).read_bytes(),b'original-video')

    def test_supplied_reference_bypasses_video_selection_not_identity(self):
        song,job=self.attach()
        supplied={'status':'selected','type':'provided-transparent-halfbody','frame_path':str(self.root/'ref.png')}
        with patch('publish_v2.provided_reference',return_value=supplied) as provider,patch('publish_v2.select_reference_frame',side_effect=AssertionError('must not select screenshot')):
            self.service.prepare(job)
        self.assertEqual(provider.call_args.args[0],'bilibili:1')
        self.assertEqual(provider.call_args.kwargs['selection_key'],song['song_key'])
        self.assertEqual(json.loads(self.service.row('song_projects',song['id'])['reference_json'])['type'],supplied['type'])
        self.assertEqual(self.service.row('publish_jobs',job['id'])['identified_title'],'离人赋')

    def test_normalization_identity_unchanged(self):
        self.assertEqual(normalized_title(' 離人賦 (Live) '),normalized_title('离人赋'))
        self.assertEqual(normalized_title('离人赋 (cover: X)'),normalized_title('离人赋'))
        self.assertNotEqual(normalized_title('离人赋 (另一首歌)'),normalized_title('离人赋'))
        p=self.project(); song,job=self.attach(p)
        self.assertEqual(job['identified_title'],'离人赋'); self.assertEqual(job['identified_artist'],'云汐')
        self.assertEqual(p['manual_title'],'错误手动标题')

    def test_description_time_uses_recording_not_mtime(self):
        s,j=self.attach()
        with patch.object(self.bili,'format_description',wraps=self.bili.format_description) as formatter:
            self.service.prepare(j)
        self.assertEqual(formatter.call_args.args[1]['time'],'2026-10-07T09:05:13+08:00')

    def test_ai_title_frozen_across_cover_failure_and_restart(self):
        s,j=self.attach(); self.gpt.fail=True
        title='🌸清风吹来旧心事｜《离人赋》｜【芒芒_Mou】翻唱'
        with patch('publish_v2.generate_publish_title',return_value=(title,{'source':'ai','prompt':'approved'})) as generator:
            self.service.prepare(j)
            saved=self.service.row('publish_jobs',j['id'])
            self.assertEqual(saved['title'],title)
            self.gpt.fail=False
            self.new_service().prepare(saved)
            self.assertEqual(generator.call_count,1)
        saved=self.service.row('publish_jobs',j['id'])
        self.assertEqual(json.loads(saved['bililive_payload_json'])['config']['title'],title)
        self.assertEqual(saved['identified_title'],'离人赋');self.assertEqual(saved['identified_artist'],'云汐')

    def test_existing_payload_never_regenerates_ai_title(self):
        s,j=self.attach();self.service.prepare(j)
        saved=self.service.row('publish_jobs',j['id'])
        with patch('publish_v2.generate_publish_title',side_effect=AssertionError('Must reuse payload')):
            self.new_service().prepare(saved)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['title'],saved['title'])

    def test_unknown_recording_time_stops_before_paid_cover(self):
        s,j=self.attach(); self.run['source']='芒芒_Mou/no-date/video.mp4'
        self.service.prepare(j)
        self.assertEqual(self.gpt.calls,0)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'failed')

    def test_high_only(self):
        for tier in ('local','deepseek','low',None):
            p=self.project(str(tier),tier=tier); song,job=self.attach(p)
            self.assertIsNone(job)
        p=self.project('sample'); p['output']['sample']=True; self.assertFalse(eligible(p))
        p=self.project('suspect'); p['alignment']['timeline_match']['song_identity_suspicious']=True; self.assertFalse(eligible(p))
        p=self.project('not-mp4'); p['output']['path']='output.webm';self.assertFalse(eligible(p))
        self.assertEqual(self.gpt.calls,0)

    def test_same_song_no_second_job(self):
        s,j=self.attach(); self.attach(self.project('p2',title='離人賦 (Live)'))
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM publish_jobs').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT disposition FROM song_performances WHERE source_job_id='p2'").fetchone()[0],'duplicate')

    def test_explicit_revision_enqueue_keeps_rollout_and_waits_without_paid_calls(self):
        self.service.set_automatic_enabled(False)
        state=self.service.rollout()
        p=self.project('revision');p.update(render_revision_parent_id='old',render_revision_publish=1)
        sid=self.service.attach(p,self.run,self.profile,enqueue=True)
        job=self.service.row('publish_jobs',self.service.row('song_projects',sid)['publish_job_id'])
        self.assertEqual(job['status'],'pending');self.assertEqual(job['video_path'],p['output']['path'])
        self.assertEqual(self.service.rollout(),state)
        self.service.tick();self.assertEqual(self.gpt.calls,0);self.assertEqual(self.bili.calls,0)
        p['render_revision_publish']=0;self.assertFalse(eligible(p))

    def test_revision_updates_unsubmitted_master_video_and_reuses_cover(self):
        s,j=self.attach();self.service.prepare(j)
        cover=self.service.row('song_projects',s['id'])['cover_path']
        p=self.project('revision');p.update(render_revision_parent_id='p1',render_revision_publish=1)
        self.service.attach(p,self.run,self.profile,enqueue=True)
        new=self.service.row('publish_jobs',j['id'])
        self.assertEqual(new['source_job_id'],'revision');self.assertEqual(new['video_path'],p['output']['path'])
        self.assertIsNone(new['bililive_payload_json']);self.assertEqual(new['status'],'pending')
        self.assertEqual(self.service.row('song_projects',s['id'])['cover_path'],cover)
        self.service.prepare(new);self.assertEqual(self.gpt.calls,1)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'ready')
        with self.db() as c: self.assertEqual(c.execute('SELECT count(*) FROM publish_jobs').fetchone()[0],1)

    def test_revision_never_retargets_accepted_or_completed_master(self):
        for state in ('submitting','uploading','completed'):
            s,j=self.attach(self.project(state,title=state))
            self.service.update('publish_jobs',j['id'],status=state,bililive_task_id='task-'+state)
            p=self.project('revision-'+state,title=state);p.update(render_revision_parent_id=state,render_revision_publish=1)
            self.service.attach(p,self.run,self.profile,enqueue=True)
            self.assertEqual(self.service.row('publish_jobs',j['id'])['source_job_id'],state)

    def test_different_streamer_independent_and_renames_stable(self):
        s,j=self.attach()
        other={**self.profile,'id':'other','recorder_identity':{'platform':'bilibili','room_id':'2'}}
        s2,j2=self.attach(self.project('p2'),other); self.assertNotEqual(s['id'],s2['id'])
        self.assertEqual(broadcaster_key(self.profile),broadcaster_key({**self.profile,'name':'新名字'}))

    def test_artist_conflict_blocks(self):
        s,j=self.attach(); self.attach(self.project('p2',artist='另一歌手'))
        self.assertEqual(self.service.row('song_projects',s['id'])['conflict'],1)
        self.service.tick(); self.assertEqual(self.gpt.calls,0)

    def test_cover_and_payload_reuse_after_restart(self):
        s,j=self.attach(); before=Path(j['video_path']).read_bytes()
        self.bili.fail=True; self.service.tick()
        job=self.service.row('publish_jobs',j['id']); snapshot=job['bililive_payload_json']
        self.assertEqual(job['status'],'pending'); self.assertEqual(self.gpt.calls,1)
        self.assertNotIn('secret',snapshot); self.assertNotIn(self.gpt.key,snapshot)
        self.bili.fail=False; self.bili.desc='changed'
        self.service.update('publish_jobs',j['id'],next_retry_at=0)
        self.service=self.new_service(); self.service.tick()
        self.assertEqual(self.service.row('publish_jobs',j['id'])['bililive_payload_json'],snapshot)
        self.assertEqual(self.gpt.calls,1); self.assertEqual(Path(j['video_path']).read_bytes(),before)
        self.service.tick(); self.assertEqual(self.bili.calls,1)
        self.service=new=self.new_service(); new.tick(); self.assertEqual(self.bili.calls,1)
        self.bili.complete=True; new.update('publish_jobs',j['id'],next_retry_at=0); new.tick()
        done=new.row('publish_jobs',j['id']); self.assertEqual(done['status'],'completed'); self.assertEqual(done['aid'],'123')
        self.assertEqual(done['review_state_desc'],'审核中'); self.assertEqual(done['bvid'],'BVtest')
        new.tick(); self.assertEqual(self.bili.calls,1)

    def test_cover_retry_limit(self):
        s,j=self.attach(); self.gpt.fail=True
        self.assertEqual(COVER_MAX_ATTEMPTS,10)
        for attempt in range(1,COVER_MAX_ATTEMPTS+1):
            self.service.update('publish_jobs',j['id'],next_retry_at=0)
            self.service=self.new_service(); self.service.tick()
            saved=self.service.row('publish_jobs',j['id'])
            self.assertEqual(self.service.row('song_projects',s['id'])['cover_attempts'],attempt)
            self.assertEqual(saved['status'],'pending' if attempt<COVER_MAX_ATTEMPTS else 'failed')
            if attempt<COVER_MAX_ATTEMPTS: self.assertGreater(saved['next_retry_at'],time.time())
        self.service.tick();self.service.tick()
        self.assertEqual(self.gpt.calls,10)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'failed')
        with self.assertRaisesRegex(CoverError,'10 次'):
            self.new_service().cover(self.service.row('publish_jobs',j['id']))
        self.assertEqual(self.gpt.calls,10)

    def test_old_two_failures_resume_without_resetting_count_or_identity(self):
        s,j=self.attach();self.service.update('song_projects',s['id'],cover_attempts=2,cover_status='failed')
        before=Path(j['video_path']).read_bytes()
        self.new_service().prepare(j)
        saved=self.service.row('song_projects',s['id'])
        self.assertEqual(saved['cover_attempts'],3);self.assertEqual(self.gpt.calls,1)
        self.assertEqual(saved['cover_status'],'ready')
        self.assertEqual(saved['identified_title'],'离人赋');self.assertEqual(saved['identified_artist'],'云汐')
        self.assertEqual(Path(j['video_path']).read_bytes(),before)

    def test_tenth_request_can_succeed_and_cached_cover_never_regenerates(self):
        s,j=self.attach();self.service.update('song_projects',s['id'],cover_attempts=9)
        self.service.prepare(j)
        self.assertEqual(self.service.row('song_projects',s['id'])['cover_attempts'],10)
        saved=self.service.row('publish_jobs',j['id']);self.new_service().prepare(saved)
        self.assertEqual(self.gpt.calls,1);self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'ready')

    def test_missing_template_and_legacy_isolated(self):
        p=self.project(); profile={**self.profile,'bililive_preset_id':''}; s,j=self.attach(p,profile); self.assertIsNone(j)
        with self.db() as c:
            c.execute("INSERT INTO publish_jobs(id,source_job_id,created_at,updated_at,status,video_path,streamer) VALUES('old','p1',1,1,'ready','old','name')")
        self.service.tick(); self.assertEqual(self.bili.calls,0); self.assertEqual(self.gpt.calls,0)

    def test_concurrent_attachment(self):
        p=self.project(); errors=[]
        def call():
            try: self.service.attach(p,self.run,self.profile)
            except Exception as exc: errors.append(exc)
        threads=[threading.Thread(target=call) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors,[])
        with self.db() as c: self.assertEqual(c.execute('SELECT count(*) FROM publish_jobs').fetchone()[0],1)

    def test_resume_submission_match_and_bounded_repost(self):
        s,j=self.attach(); self.service.tick(); j=self.service.row('publish_jobs',j['id'])
        self.service.update('publish_jobs',j['id'],status='submitting',submit_attempts=1,submit_started_at=time.time(),submit_before_json='[]')
        j=self.service.row('publish_jobs',j['id'])
        self.bili.tasks=[{'taskId':'recovered','type':'bili','name':'创建稿件：'+j['title'],'startTime':time.time()*1000}]
        self.service.submit(j); self.assertEqual(self.bili.calls,0)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['bililive_task_id'],'recovered')

    def test_snapshot_frozen_on_reattach(self):
        s,j=self.attach(); self.service.tick(); before=self.service.row('publish_jobs',j['id'])['bililive_payload_json']
        self.service.attach(self.projects['p1'],self.run,self.profile)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['bililive_payload_json'],before)

    def test_recover_received_original_without_paid_request(self):
        s,j=self.attach(); folder=self.root/'publish/songs'/s['id']; folder.mkdir(parents=True)
        raw=self.gpt.generate('', ''); (folder/'original-1.bin').write_bytes(raw)
        self.service.update('song_projects',s['id'],cover_attempts=1)
        self.gpt.calls=0; self.service.tick(); self.assertEqual(self.gpt.calls,0)
        self.assertEqual(self.service.row('song_projects',s['id'])['cover_status'],'ready')

    def test_schema_reentrant(self):
        with self.db() as c: init_schema(c); init_schema(c)

    def test_enable_requires_two_completed_acceptance_jobs(self):
        with self.db() as c:
            c.execute("UPDATE app_meta SET value=? WHERE key='publish_v2_rollout'",(json.dumps({'mode':'acceptance','allowlist':[],'cutover':0}),))
        with self.assertRaisesRegex(Exception,'两首验收'): self.service.set_automatic_enabled(True)
        self.assertEqual(self.service.rollout()['mode'],'acceptance')

    def test_first_enable_is_idempotent_and_never_backfills(self):
        for source,title in [('p1','离人赋'),('p2','鱼仔')]:
            s,j=self.attach(self.project(source,title))
            self.service.update('publish_jobs',j['id'],status='completed',aid='123')
        with self.db() as c:
            c.execute("UPDATE app_meta SET value=? WHERE key='publish_v2_rollout'",(json.dumps({'mode':'acceptance','allowlist':['p1','p2'],'cutover':0}),))
        with patch('publish_v2.time.time',return_value=200): state=self.service.set_automatic_enabled(True)
        self.assertEqual(state['cutover'],200)
        with patch('publish_v2.time.time',return_value=300): self.assertEqual(self.service.set_automatic_enabled(True),state)
        self.assertFalse(self.service.allowed('history',199)); self.assertFalse(self.service.allowed('boundary',200))
        self.assertTrue(self.service.allowed('future',201))

    def test_pause_resume_persist_and_exclude_paused_period(self):
        with patch('publish_v2.time.time',return_value=150): paused=self.service.set_automatic_enabled(False)
        self.assertEqual(paused['mode'],'paused');self.assertFalse(self.new_service().allowed('p1',100))
        with patch('publish_v2.time.time',return_value=170): self.assertEqual(self.new_service().set_automatic_enabled(False),paused)
        with patch('publish_v2.time.time',return_value=200): resumed=self.new_service().set_automatic_enabled(True)
        self.assertEqual(resumed['cutover'],0)
        self.assertTrue(self.service.allowed('before-pause',100))
        for value in (150,175,200): self.assertFalse(self.service.allowed('during-pause',value))
        self.assertTrue(self.service.allowed('after-resume',201))

    def test_pause_blocks_pending_ready_and_direct_submission(self):
        s,j=self.attach(); self.service.set_automatic_enabled(False)
        self.service.tick();self.service.prepare(j)
        self.assertEqual(self.gpt.calls,0)
        self.service.update('publish_jobs',j['id'],status='ready')
        self.service.tick();self.service.submit(self.service.row('publish_jobs',j['id']))
        self.assertEqual(self.bili.calls,0)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'ready')
        self.assertIsNone(self.attach(self.project('p2',title='新歌'))[1])

    def test_pause_during_title_preserves_result_without_generating_cover(self):
        s,j=self.attach()
        def generate(*args,**kwargs):
            self.service.set_automatic_enabled(False)
            return 'saved title',{'source':'ai'}
        with patch('publish_v2.generate_publish_title',side_effect=generate): self.service.prepare(j)
        saved=self.service.row('publish_jobs',j['id'])
        self.assertEqual(saved['status'],'pending'); self.assertEqual(saved['title'],'saved title')
        self.assertEqual(self.gpt.calls,0)

    def test_title_retries_are_durable_and_never_generate_cover_until_final_fallback(self):
        from title_generation import generate_publish_title,TitleError
        s,j=self.attach();calls=[]
        outer=self
        class SlowTitle:
            model='gpt-6.1-sol'
            def generate(self,prompt):
                calls.append(prompt)
                saved=outer.service.row('publish_jobs',j['id'])
                record=json.loads(saved['title_generation_json'])
                outer.assertTrue(record['in_flight']);outer.assertEqual(record['attempts'],len(calls))
                raise TitleError('timeout')
        def generate(*args,**kwargs):return generate_publish_title(*args,client_factory=SlowTitle,**kwargs)
        with patch('publish_v2.generate_publish_title',side_effect=generate):
            for attempt in range(1,4):
                self.service=self.new_service()
                self.service.prepare(self.service.row('publish_jobs',j['id']))
                saved=self.service.row('publish_jobs',j['id'])
                self.assertEqual(json.loads(saved['title_generation_json'])['attempts'],attempt)
                self.assertEqual(saved['status'],'pending' if attempt<3 else 'ready')
                self.assertEqual(self.gpt.calls,0 if attempt<3 else 1)
            self.new_service().prepare(self.service.row('publish_jobs',j['id']))
        self.assertEqual(len(calls),3);self.assertEqual(self.gpt.calls,1)
        self.assertEqual(saved['title'],'芒芒_Mou《离人赋》｜直播翻唱')

    def test_pause_during_frame_selection_does_not_spend_attempt(self):
        s,j=self.attach()
        def frame(*args,**kwargs):
            self.service.set_automatic_enabled(False)
            return {'status':'selected','frame_path':'unused','time_seconds':10}
        with patch('publish_v2.select_reference_frame',side_effect=frame): self.service.prepare(j)
        self.assertEqual(self.gpt.calls,0);self.assertEqual(self.service.row('song_projects',s['id'])['cover_attempts'],0)
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'pending')

    def test_paused_upload_and_review_still_track_without_reposting(self):
        s,j=self.attach();self.service.tick();self.service.tick()
        self.assertEqual(self.bili.calls,1)
        self.service.set_automatic_enabled(False);self.bili.complete=True
        self.service.tick()
        done=self.service.row('publish_jobs',j['id'])
        self.assertEqual(done['status'],'completed');self.assertEqual(done['aid'],'123')
        self.assertEqual(done['bvid'],'BVtest');self.assertEqual(self.bili.calls,1)

    def test_double_enable_concurrently_keeps_cutover(self):
        self.service.set_automatic_enabled(False)
        states=[]
        threads=[threading.Thread(target=lambda:states.append(self.new_service().set_automatic_enabled(True))) for _ in range(4)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(len(states),4)
        self.assertTrue(all(state==states[0] for state in states))

    def test_completed_seed_survives_missing_file_and_never_reposts(self):
        s,j=self.attach()
        self.service.update('publish_jobs',j['id'],status='completed',aid='123')
        with self.db() as c:
            c.execute('UPDATE publish_jobs SET song_project_id=NULL WHERE id=?',(j['id'],))
        Path(j['video_path']).unlink()
        self.service.seed_completed()
        self.assertEqual(self.service.row('publish_jobs',j['id'])['song_project_id'],s['id'])
        self.attach(self.project('p2'))
        self.assertEqual(self.bili.calls,0);self.assertEqual(self.gpt.calls,0)

    def test_no_new_upload_when_auto_off(self):
        from dataclasses import replace
        s,j=self.attach();self.service.settings=replace(self.settings,auto_publish_enabled=False)
        self.service.tick();self.service.tick();self.service.tick()
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'ready')
        self.assertEqual(self.bili.calls,0)

    def test_old_outputs_mutable_updated_at_cannot_cross_watermark(self):
        p=self.project();p['output'].pop('finalized_at');p['updated_at']=time.time()+100
        s,j=self.attach(p);self.assertIsNone(j);self.assertEqual(self.gpt.calls,0)

    def test_auth_error_does_not_retry_or_modify_mp4(self):
        s,j=self.attach();before=Path(j['video_path']).read_bytes()
        with patch.object(self.gpt,'generate',side_effect=CoverError('HTTP 401')):
            self.service.tick();self.service.tick()
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'failed')
        self.assertEqual(self.service.row('song_projects',s['id'])['cover_attempts'],1)
        self.assertEqual(Path(j['video_path']).read_bytes(),before)

    def test_lost_known_task_does_not_resubmit(self):
        s,j=self.attach();self.service.tick();self.service.tick()
        with patch.object(self.bili,'get_upload_task',return_value=None):self.service.tick()
        self.assertEqual(self.service.row('publish_jobs',j['id'])['status'],'failed')
        self.service.tick();self.assertEqual(self.bili.calls,1)

    def test_late_artist_conflict_after_empty_first_artist(self):
        s,j=self.attach(self.project(artist=''))
        self.attach(self.project('p2',artist='A'))
        self.attach(self.project('p3',artist='B'))
        self.assertEqual(self.service.row('song_projects',s['id'])['conflict'],1)


class ClientTests(unittest.TestCase):
    def test_real_bili_wire(self):
        calls=[]
        def handler(req):
            calls.append((req.method,req.url.path))
            if req.url.path.endswith('/upload'): return httpx.Response(200,json={'taskId':'actual-task'})
            if req.url.path.endswith('/task'): return httpx.Response(200,json={'list':[],'runningTaskNum':0})
            if '/task/' in req.url.path: return httpx.Response(200,text='null')
            return httpx.Response(200,json={'archive':{'aid':123,'bvid':'BV1','state':0}})
        client=BililiveToolClient('http://test/api','secret',transport=httpx.MockTransport(handler))
        self.assertEqual(client.create_upload({'uid':1}), 'actual-task')
        self.assertEqual(client.list_upload_tasks(),[]); self.assertIsNone(client.get_upload_task('lost'))
        self.assertEqual(client.archive_detail(123,1)['archive']['aid'],123)
        self.assertIn(('POST','/api/bili/upload'),calls); client.close()

    def test_gpt_no_hidden_retries(self):
        with tempfile.TemporaryDirectory() as root:
            ref=Path(root)/'ref.png'; ref.write_bytes(b'test')
            calls=[]
            def handler(req): calls.append(req); return httpx.Response(500)
            with patch.dict('os.environ',{'COVER_API_KEY':'test-secret'}):
                client=GPTCoverClient(httpx.MockTransport(handler))
                with self.assertRaises(CoverError): client.generate(ref,'exact prompt')
            self.assertEqual(len(calls),1)
            self.assertIn(b'exact prompt',calls[0].content)
            self.assertIn(b'2048x1152',calls[0].content)

    def test_bad_image(self):
        with self.assertRaises(CoverError): image_bytes(b'not an image')


if __name__=='__main__': unittest.main()
