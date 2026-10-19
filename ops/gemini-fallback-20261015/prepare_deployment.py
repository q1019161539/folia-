"""Back up and check idle before the scoped API-only update. Never print secrets."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import urllib.request

root=Path('/vol1/1000/docker/folia-video-studio')
health=json.load(urllib.request.urlopen('http://127.0.0.1:18082/api/automation/health',timeout=15))
assert not health['heavy_task_slot']['busy'], 'Heavy task in progress; do not restart API'
basic=json.load(urllib.request.urlopen('http://127.0.0.1:18082/healthz',timeout=15))
assert basic['ok'] and not basic['render_busy'], 'Render busy'
c=sqlite3.connect('file:'+str(root/'data/studio.db')+'?mode=ro',uri=True,timeout=15)
assert not c.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting','uploading') LIMIT 1").fetchone(), 'Publish active'
expected={'backend/publish_v2.py':'2bc50f7ee17771f227488aea232db4b9a6f9d749ed2b6a6f67b009cb0abd7d4e',
          'backend/app.py':'cb6defc14825f19682a21e83d3cdbab4b65a7c02c795c152075dbe6edeb41e12'}
for file,digest in expected.items():
    assert hashlib.sha256((root/file).read_bytes()).hexdigest()==digest, 'Source changed; reconcile before applying update'
backup=root/'ops/gemini-fallback-20261015/backup'
backup.mkdir(exist_ok=False)
for file in ('backend/publish_v2.py','backend/app.py','backend/Dockerfile','compose.yaml','.env','docs/STATUS.md','docs/modules/automatic-publishing.md','docs/DECISIONS.md'):
    target=backup/file;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/file,target)
(backup/'.env').chmod(0o600)
destination=sqlite3.connect(backup/'studio.db');c.backup(destination)
assert destination.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
destination.close();c.close()
print(json.dumps({'backup':str(backup),'idle':True,'integrity':'ok'}))
