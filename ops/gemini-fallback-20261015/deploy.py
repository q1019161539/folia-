"""Scoped API-only deploy. Preconditions checked again immediately before restart."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.request

root=Path('/vol1/1000/docker/folia-video-studio')
stage=root/'ops/gemini-fallback-20261015/stage'
backup=root/'ops/gemini-fallback-20261015/backup'
assert (backup/'studio.db').is_file() and (backup/'.env').is_file(), 'Backup missing'
health=json.load(urllib.request.urlopen('http://127.0.0.1:18082/api/automation/health',timeout=15))
assert not health['heavy_task_slot']['busy'], 'Heavy task in progress'
assert not json.load(urllib.request.urlopen('http://127.0.0.1:18082/healthz',timeout=15))['render_busy'], 'Render busy'
c=sqlite3.connect('file:'+str(root/'data/studio.db')+'?mode=ro',uri=True,timeout=15)
assert not c.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting','uploading') LIMIT 1").fetchone(), 'External request in progress'
c.close()
for name in ('backend/publish_v2.py','backend/app.py','compose.yaml','backend/Dockerfile'):
    assert (root/name).read_bytes()==(backup/name).read_bytes(), 'Source changed during maintenance'
old=subprocess.check_output(['docker','inspect','folia-video-api','--format','{{.Image}}'],text=True).strip()
expected=subprocess.check_output(['docker','image','inspect','folia-api-before-gemini:20261015','--format','{{.Id}}'],text=True).strip()
assert old==expected, 'Running API image changed'
files=['backend/cover_fallback.py','backend/publish_v2.py','backend/app.py','backend/Dockerfile',
       'backend/test_cover_fallback.py','backend/test_publish_v2.py','compose.yaml','docs/modules/automatic-publishing.md']
for name in files:
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stage/name,target)
subprocess.run(['docker','tag','folia-video-studio-studio-api:gemini-fallback-20261015','folia-video-studio-studio-api:latest'],check=True)
subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'up','-d','--no-deps','--no-build','studio-api'],cwd=root,check=True)
for index in range(25):
    try:
        health=json.load(urllib.request.urlopen('http://127.0.0.1:18082/healthz',timeout=5))
        if health.get('ok'):break
    except Exception:pass
    time.sleep(1)
else:raise RuntimeError('API health check failed; preserve backup and diagnose')
print(json.dumps({'deployed_image':subprocess.check_output(['docker','inspect','folia-video-api','--format','{{.Image}}'],text=True).strip(),'health':health,'updated_service':'studio-api'},ensure_ascii=False))
