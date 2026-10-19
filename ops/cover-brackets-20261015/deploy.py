"""Scoped cover-prompt release; no AI calls, queue mutations or media writes."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.request

ROOT=Path('/vol1/1000/docker/folia-video-studio')
OPS=ROOT/'ops/cover-brackets-20261015'
EXPECTED_IMAGE='sha256:782d977de3d5966f6fa0454b0e95977f0895dbdda7124f0a3b6fb4b8fa200f81'
EXPECTED={
    'backend/publish_v2.py':'a864b3cacd9d00d0e9ad7abcce234f868d3f80bacf2ff27a219d246bbe31e24c',
    'backend/test_publish_v2.py':'d9c7598580b4d044e2134f33e1619aebc3147ed1f37082d646f20b3f086264d0',
}
def command(args):
    return subprocess.check_output(args,text=True).strip()
def health(path):
    return json.load(urllib.request.urlopen('http://127.0.0.1:18082'+path,timeout=15))
def preflight():
    assert command(['docker','inspect','folia-video-api','--format','{{.Image}}'])==EXPECTED_IMAGE,'API image changed'
    assert not health('/api/automation/health')['heavy_task_slot']['busy'],'Heavy task busy; do not interrupt'
    assert not health('/healthz')['render_busy'],'Render busy'
    with sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30) as db:
        assert not db.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting','uploading') LIMIT 1").fetchone(),'External request busy'
    for relative,expected in EXPECTED.items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected,'Source changed: '+relative

preflight()
backup=OPS/'backup';backup.mkdir(exist_ok=False)
for relative in (*EXPECTED,'compose.yaml','.env','docs/STATUS.md','docs/modules/automatic-publishing.md'):
    target=backup/relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/relative,target)
(backup/'.env').chmod(0o600)
with sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30) as source:
    with sqlite3.connect(backup/'studio.db') as dest:
        source.backup(dest);assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
subprocess.run(['docker','tag',EXPECTED_IMAGE,'folia-api-before-cover-brackets:20261015'],check=True)
subprocess.run(['docker','build','-t','folia-video-studio-studio-api:cover-brackets-20261015',str(OPS)],check=True)
subprocess.run(['docker','run','--rm','--network','none','--entrypoint','python','folia-video-studio-studio-api:cover-brackets-20261015',
    '-c','import app; from publish_v2 import PROMPT; from cover_fallback import HALF_BODY_INSTRUCTION; p=PROMPT.format(song="鱼仔"); assert "《" not in p; assert "书名号可加可不加" in p; assert "半身近景" in HALF_BODY_INSTRUCTION; print("IMAGE_PROMPT_IMPORT_OK")'],check=True)
preflight()
for relative in EXPECTED:shutil.copy2(OPS/'stage'/relative,ROOT/relative)
subprocess.run(['docker','tag','folia-video-studio-studio-api:cover-brackets-20261015','folia-video-studio-studio-api:latest'],check=True)
subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'up','-d','--no-deps','--no-build','studio-api'],cwd=ROOT,check=True)
for _ in range(30):
    try:
        result=health('/healthz')
        if result.get('ok'):break
    except Exception:pass
    time.sleep(1)
else:raise RuntimeError('API health failed; preserve backup and diagnose')
result={'health':result,'image':command(['docker','inspect','folia-video-api','--format','{{.Image}}']),
        'scope':'studio-api only; no queue reset, paid test or historical repost'}
(OPS/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
