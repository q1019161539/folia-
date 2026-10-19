"""Read-only business verification and scoped source/document mirror sync."""
import base64
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import urllib.request
ROOT=Path('/vol1/1000/docker/folia-video-studio')
OPS=ROOT/'ops/gemini-primary-20261015'
FILES=('backend/cover_fallback.py','backend/publish_v2.py','backend/app.py','backend/test_cover_fallback.py',
       'backend/test_publish_v2.py','compose.yaml','web/publish.js','web/index.html','docs/STATUS.md','docs/modules/automatic-publishing.md')
backup=OPS/'backup';mirror=Path('/vol1/1000/docker/folia-git')
original=json.loads((backup/'authorized-jobs.json').read_text())
old=sqlite3.connect(backup/'studio.db');old.row_factory=sqlite3.Row
current=sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30);current.row_factory=sqlite3.Row
checked=0
for before in old.execute("SELECT * FROM publish_jobs WHERE status='completed'"):
    after=current.execute('SELECT * FROM publish_jobs WHERE id=?',(before['id'],)).fetchone()
    for key in ('source_job_id','identified_title','identified_artist','identity_source','video_path','cover_path','title',
                'description','tags_json','bililive_payload_json','bililive_task_id','aid','submit_attempts'):
        assert after[key]==before[key],f'Historical data changed: {before["id"]}/{key}'
    checked+=1
assert old.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0]==current.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0]
jobs=[]
for entry in original:
    before=entry['job'];after=dict(current.execute('SELECT * FROM publish_jobs WHERE id=?',(before['id'],)).fetchone())
    song=dict(current.execute('SELECT * FROM song_projects WHERE id=?',(after['song_project_id'],)).fetchone())
    for key in ('source_job_id','automation_run_id','identified_title','identified_artist','identity_source','video_path',
                'video_size','video_mtime','streamer','bililive_preset_id','bililive_uid','title','title_generation_json'):
        assert before[key]==after[key],'Authorized input changed: '+key
    assert entry['song']['cover_attempts']<=song['cover_attempts']<=10
    if song['cover_attempts']>entry['song']['cover_attempts']:
        assert song['cover_model']=='gemini-3-pro-image-preview'
        ref=json.loads(song['reference_json']);assert ref['type']=='provided-transparent-halfbody' and ref['broadcaster_key']=='bilibili:2516117'
    jobs.append({key:after[key] for key in ('id','identified_title','status','bililive_task_id','aid','bvid','publish_error','collection_status')}|
                {key:song[key] for key in ('cover_attempts','cover_status','cover_model','cover_dimensions_json')})

# Read the authenticated Web using its existing runtime password, never display credentials.
env=dict(x.split('=',1) for x in json.loads(subprocess.check_output(['docker','inspect','folia-video-web'],text=True))[0]['Config']['Env'] if '=' in x)
credential=base64.b64encode(('folia:'+env['STUDIO_PASSWORD']).encode()).decode()
for path,marker in (('/',b'20261015-gemini-primary'),('/publish.js?v=20261015-gemini-primary','Gemini'.encode())):
    req=urllib.request.Request('http://127.0.0.1:18081'+path,headers={'Authorization':'Basic '+credential})
    with urllib.request.urlopen(req,timeout=20) as response:assert marker in response.read()
for relative in FILES:
    assert (mirror/relative).read_bytes()==(backup/relative).read_bytes(),'NAS Git copy changed: '+relative
for relative in FILES[8:]:assert (ROOT/relative).read_bytes()==(backup/relative).read_bytes(),'Production doc changed: '+relative
decision='docs/DECISIONS.md'
assert (ROOT/decision).read_bytes()==(mirror/decision).read_bytes(),'Decision doc diverged'
shutil.copy2(ROOT/decision,backup/'docs/DECISIONS.md')
for relative in (*FILES,decision):
    target=backup/'git-mirror'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(mirror/relative,target)
    if relative.startswith('docs/'):shutil.copy2(OPS/'stage'/relative,ROOT/relative)
    shutil.copy2(ROOT/relative,mirror/relative)
for name in ('Dockerfile','Dockerfile.web','deploy.py','release.py','finalize.py','run-tests.sh','test-ui.cjs','.gitignore','.dockerignore'):
    target=mirror/'ops/gemini-primary-20261015'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OPS/name,target)
result=json.loads((OPS/'verification.json').read_text())
result.update(completed_resources_unchanged=checked,rollout_unchanged=True,web_http_checked=True,jobs=jobs,nas_git_synced=True)
(OPS/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
