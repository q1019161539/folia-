"""Back up, build and deploy only Folia API/Web after idle checks; no key output."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from release import records

ROOT=Path('/vol1/1000/docker/folia-video-studio')
OPS=ROOT/'ops/gemini-primary-20261015'
BACKUP=OPS/'backup'
EXPECTED_IMAGE='sha256:da1fad223467772cc88cf4b23c83e8b3ae1f67164b3659cb5927661ce5ee5a0e'
FILES=('backend/cover_fallback.py','backend/publish_v2.py','backend/app.py','backend/test_cover_fallback.py',
       'backend/test_publish_v2.py','compose.yaml','web/publish.js','web/index.html','docs/STATUS.md','docs/modules/automatic-publishing.md')
EXPECTED={'backend/publish_v2.py':'f14754226bb68cc88291938b1d92b2559b106fa2a99acc77b1c119857cdd93c3',
          'backend/cover_fallback.py':'a30d13ebc51ee8c78c4f318422ed4c1b9a409d9e2fbfef52adf066bb46ae8907',
          'backend/app.py':'35de0a79960eb55169a5d57bbf2d229370aa535075bc3cf68df7ceccc43c1242',
          'compose.yaml':'12cb431d50318c0636965f0a76cd1d725bdbe5a0be9a0ed4b938d7b053119aea'}

def output(args):return subprocess.check_output(args,text=True).strip()
def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:18082'+path,timeout=15))
def preflight():
    assert output(['docker','inspect','folia-video-api','--format','{{.Image}}'])==EXPECTED_IMAGE,'API image changed'
    assert not get('/api/automation/health')['heavy_task_slot']['busy'],'Heavy task busy; do not interrupt'
    assert not get('/healthz')['render_busy'],'Render busy'
    with sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30) as c:
        assert not c.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting','uploading') LIMIT 1").fetchone(),'External request busy'
    for path,digest in EXPECTED.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,'Source changed: '+path

action=sys.argv[1]
if action=='prepare':
    preflight();BACKUP.mkdir(exist_ok=False)
    for relative in (*FILES,'.env','backend/Dockerfile'):
        dest=BACKUP/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,dest)
    (BACKUP/'.env').chmod(0o600)
    with sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30) as c:
        c.row_factory=sqlite3.Row
        (BACKUP/'authorized-jobs.json').write_text(json.dumps(records(c),ensure_ascii=False,indent=2),encoding='utf-8')
        with sqlite3.connect(BACKUP/'studio.db') as dest:
            c.backup(dest);assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    subprocess.run(['docker','tag',EXPECTED_IMAGE,'folia-api-before-gemini-primary:20261015'],check=True)
    web=output(['docker','inspect','folia-video-web','--format','{{.Image}}'])
    subprocess.run(['docker','tag',web,'folia-web-before-gemini-primary:20261015'],check=True)
    print('BACKUP_OK')
elif action=='build':
    assert (BACKUP/'studio.db').exists()
    for name,file in (('studio-api','Dockerfile'),('studio-web','Dockerfile.web')):
        subprocess.run(['docker','build','-f',str(OPS/file),'-t','folia-video-studio-'+name+':gemini-primary-20261015',str(OPS)],check=True)
    subprocess.run(['docker','run','--rm','--network','none','--entrypoint','python','-e','COVER_PRIMARY_PROVIDER=gemini',
        '-e','COVER_FALLBACK_ENABLED=1','-e','COVER_FALLBACK_API_KEY=offline-placeholder','folia-video-studio-studio-api:gemini-primary-20261015',
        '-c','import app; from cover_fallback import use_gemini_for_cover,primary_cover_configured; assert use_gemini_for_cover(0) and primary_cover_configured(); print("IMAGE_IMPORT_PRIMARY_OK")'],check=True)
elif action=='deploy':
    log=(OPS/'regression.log').read_text();assert 'Ran 147 tests' in log and log.rstrip().endswith('OK'),'Tests not passed'
    preflight()
    for relative in (*FILES,'.env'):assert (ROOT/relative).read_bytes()==(BACKUP/relative).read_bytes(),'Changed since backup: '+relative
    for relative in FILES[:8]:shutil.copy2(OPS/'stage'/relative,ROOT/relative)
    env=ROOT/'.env';lines=env.read_text().splitlines()
    lines=[line for line in lines if not line.startswith('COVER_PRIMARY_PROVIDER=')]
    lines.append('COVER_PRIMARY_PROVIDER=gemini')
    temp=ROOT/'.env.gemini-primary.partial';temp.write_text('\n'.join(lines)+'\n',encoding='utf-8');temp.chmod(0o600);temp.replace(env)
    for name in ('studio-api','studio-web'):
        subprocess.run(['docker','tag','folia-video-studio-'+name+':gemini-primary-20261015','folia-video-studio-'+name+':latest'],check=True)
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'up','-d','--no-deps','--no-build','studio-api','studio-web'],cwd=ROOT,check=True)
    for _ in range(40):
        try:
            control=get('/api/publish-v2/control')
            if get('/healthz')['ok'] and control.get('cover_primary_provider')=='gemini' and control['cover_configured']:break
        except Exception:pass
        time.sleep(1)
    else:raise RuntimeError('Health or primary-provider verification failed')
    result={'image':output(['docker','inspect','folia-video-api','--format','{{.Image}}']),
            'primary':control['cover_primary_provider'],'health':get('/healthz'),'tests':147}
    (OPS/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
else:raise ValueError('Unknown action')
