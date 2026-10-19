"""Verify whole-PNG runtime inputs and preserve old cover/upload results; no AI POST."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import urllib.request

ROOT=Path('/vol1/1000/docker/folia-video-studio');OPS=ROOT/'ops/reference-full-20261015';BACKUP=OPS/'backup'
FILES=('backend/cover_fallback.py','backend/publish_v2.py','backend/test_cover_fallback.py','backend/test_publish_v2.py',
       'docs/STATUS.md','docs/modules/automatic-publishing.md','docs/DECISIONS.md')
mirror=Path('/vol1/1000/docker/folia-git')
script='''import hashlib,json
from pathlib import Path
from PIL import Image
from cover_fallback import provided_reference,HALF_BODY_INSTRUCTION
config=json.loads(Path('/data/cover-references/references.json').read_text())
pool=config['bilibili:2516117']['references'];assert len(pool)==6
assert all(x['has_microphone'] is False and '/normal/' in x['path'] for x in pool)
results=[]
for key in ('song-one','song-two'):
 frame=provided_reference('bilibili:2516117','/tmp/folia-reference-full-verification',selection_key=key)
 assert frame['crop'] is None and frame['type']=='provided-transparent-full'
 source=next(x for x in pool if x['sha256']==frame['source_sha256'])
 assert Path(source['path']).read_bytes()==Path(frame['frame_path']).read_bytes()
 with Image.open(frame['frame_path']) as im:dimensions=list(im.size)
 results.append({'reference_id':frame['reference_id'],'dimensions':dimensions,'sha256':frame['frame_sha256'],'byte_identical':True})
assert provided_reference('bilibili:25984441','/tmp/folia-reference-full-verification',selection_key='song') is None
assert '也可以采用全身构图' in HALF_BODY_INSTRUCTION
print(json.dumps(results))
'''
refs=json.loads(subprocess.check_output(['docker','exec','-i','folia-video-api','python','-'],input=script,text=True))
old=sqlite3.connect(BACKUP/'studio.db');old.row_factory=sqlite3.Row
current=sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30);current.row_factory=sqlite3.Row
checked=0
for before in old.execute("SELECT * FROM publish_jobs WHERE status='completed'"):
    after=current.execute('SELECT * FROM publish_jobs WHERE id=?',(before['id'],)).fetchone()
    for key in ('source_job_id','identified_title','identified_artist','identity_source','video_path','cover_path','title',
                'description','tags_json','bililive_payload_json','bililive_task_id','aid','submit_attempts'):
        assert after[key]==before[key],f'Historical data changed: {before["id"]}/{key}'
    checked+=1
for before in old.execute("SELECT * FROM song_projects WHERE cover_path IS NOT NULL"):
    after=current.execute('SELECT * FROM song_projects WHERE id=?',(before['id'],)).fetchone()
    for key in ('cover_path','cover_sha256','cover_attempts','original_cover_path','cover_prompt','reference_json'):
        assert after[key]==before[key],f'Existing successful cover changed: {before["id"]}/{key}'
assert old.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0]==current.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0]
original=json.loads((BACKUP/'interrupted-run.json').read_text())
run=current.execute('SELECT * FROM automation_runs WHERE id=?',(original['id'],)).fetchone()
for key in ('profile_id','source','transcriber_run_id'):assert run[key]==original[key]
for relative in FILES:
    assert (mirror/relative).read_bytes()==(BACKUP/relative).read_bytes(),'NAS Git copy changed: '+relative
for relative in FILES[4:]:assert (ROOT/relative).read_bytes()==(BACKUP/relative).read_bytes(),'Production document changed: '+relative
for relative in FILES:
    target=BACKUP/'git-mirror'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(mirror/relative,target)
    if relative.startswith('docs/'):shutil.copy2(OPS/'stage'/relative,ROOT/relative)
    shutil.copy2(ROOT/relative,mirror/relative)
for name in ('Dockerfile','deploy.py','interrupt_resume.py','finalize.py','inspect_assets.py','prepare_library.py','run-tests.sh','.gitignore','.dockerignore'):
    target=mirror/'ops/reference-full-20261015'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OPS/name,target)
result=json.loads((OPS/'verification.json').read_text())
result.update(runtime_references=refs,completed_resources_unchanged=checked,successful_covers_unchanged=True,
    rollout_unchanged=True,asr={'id':run['id'],'status':run['status'],'stage':run['stage'],'transcriber_job_id':run['transcriber_job_id']},nas_git_synced=True)
(OPS/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
