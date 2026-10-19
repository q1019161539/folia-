"""Scoped full-reference library release with idle checks and immutable-history audit."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT=Path('/vol1/1000/docker/folia-video-studio');OPS=ROOT/'ops/reference-full-20261015';BACKUP=OPS/'backup'
DATA=ROOT/'data/cover-references'
IMAGE='sha256:f6c5c7dab10096dc550491285df556e94b459c82dc3a2d15083dec2528627582'
FILES=('backend/cover_fallback.py','backend/publish_v2.py','backend/test_cover_fallback.py','backend/test_publish_v2.py',
       'docs/STATUS.md','docs/modules/automatic-publishing.md','docs/DECISIONS.md')
def out(args):return subprocess.check_output(args,text=True).strip()
def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:18082'+path,timeout=15))
def idle():
    assert out(['docker','inspect','folia-video-api','--format','{{.Image}}'])==IMAGE,'API image changed'
    assert not get('/api/automation/health')['heavy_task_slot']['busy'],'Heavy task busy; do not interrupt'
    assert not get('/healthz')['render_busy'],'Render busy'
    with sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30) as c:
        assert not c.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting','uploading') LIMIT 1").fetchone(),'Publish request in progress'

action=sys.argv[1]
if action=='prepare':
    # A read-only consistent backup and image build do not interrupt an active ASR.
    # The strict idle gate remains immediately before any runtime source/config change.
    assert out(['docker','inspect','folia-video-api','--format','{{.Image}}'])==IMAGE,'API image changed'
    BACKUP.mkdir(exist_ok=False)
    for relative in (*FILES,'compose.yaml','.env','backend/Dockerfile','data/cover-references/references.json'):
        dest=BACKUP/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,dest)
    (BACKUP/'.env').chmod(0o600)
    with sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30) as c:
        with sqlite3.connect(BACKUP/'studio.db') as dest:
            c.backup(dest);assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    subprocess.run(['docker','tag',IMAGE,'folia-api-before-full-reference:20261015'],check=True)
    print('BACKUP_OK_NO_SERVICE_CHANGE')
elif action=='build':
    assert (BACKUP/'studio.db').exists()
    subprocess.run(['docker','build','-t','folia-video-studio-studio-api:full-reference-20261015',str(OPS)],check=True)
    subprocess.run(['docker','run','--rm','--network','none','--entrypoint','python','folia-video-studio-studio-api:full-reference-20261015',
        '-c','import app; from cover_fallback import HALF_BODY_INSTRUCTION; assert "也可以采用全身构图" in HALF_BODY_INSTRUCTION; print("IMAGE_IMPORT_OK")'],check=True)
elif action=='deploy':
    log=(OPS/'regression.log').read_text();assert 'Ran 19 tests' in log and log.rstrip().endswith('OK')
    idle()
    for relative in FILES:assert (ROOT/relative).read_bytes()==(BACKUP/relative).read_bytes(),'Source changed: '+relative
    assert (DATA/'references.json').read_bytes()==(BACKUP/'data/cover-references/references.json').read_bytes(),'Reference configuration changed'
    assert not (DATA/'full-v1').exists(),'Asset release already exists; do not overwrite'
    review=json.loads((OPS/'stage/assets/reviewed.json').read_text())
    assert sum(x['has_microphone'] for x in review)==5 and sum(x['active'] for x in review)==6
    for group in ('normal','q'):
        for source in (OPS/'stage/assets'/group).glob('*.png'):
            record=next(x for x in review if x['name']==source.name)
            assert not record['has_microphone']
            assert hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256']
    shutil.copytree(OPS/'stage/assets',DATA/'full-v1')
    for relative in FILES[:4]:shutil.copy2(OPS/'stage'/relative,ROOT/relative)
    temp=DATA/'references.full.partial';shutil.copy2(DATA/'full-v1/references.json',temp);temp.replace(DATA/'references.json')
    subprocess.run(['docker','tag','folia-video-studio-studio-api:full-reference-20261015','folia-video-studio-studio-api:latest'],check=True)
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'up','-d','--no-deps','--no-build','studio-api'],cwd=ROOT,check=True)
    for _ in range(40):
        try:
            health=get('/healthz')
            if health['ok']:break
        except Exception:pass
        time.sleep(1)
    else:raise RuntimeError('API health failed')
    (OPS/'verification.json').write_text(json.dumps({'image':out(['docker','inspect','folia-video-api','--format','{{.Image}}']),
        'health':health,'tests':19,'normal_active':6,'q_inactive':5,'mic_excluded':5},ensure_ascii=False,indent=2),encoding='utf-8')
    print('DEPLOYED_API_ONLY')
else:raise ValueError('Unknown action')
