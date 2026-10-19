"""Verify immutable resources and sync only release files, preserving other changes."""
import json
from pathlib import Path
import shutil
import sqlite3

root=Path('/vol1/1000/docker/folia-video-studio')
ops=root/'ops/cover-brackets-20261015'
backup=ops/'backup'
mirror=Path('/vol1/1000/docker/folia-git')
log=(ops/'regression.log').read_text()
assert 'Ran 144 tests' in log and log.rstrip().endswith('OK'),'Full regression did not pass'
old=sqlite3.connect(backup/'studio.db');old.row_factory=sqlite3.Row
now=sqlite3.connect('file:'+str(root/'data/studio.db')+'?mode=ro',uri=True);now.row_factory=sqlite3.Row
checked=0
for previous in old.execute("SELECT * FROM publish_jobs WHERE status='completed'"):
    current=now.execute('SELECT * FROM publish_jobs WHERE id=?',(previous['id'],)).fetchone()
    for key in ('source_job_id','identified_title','identified_artist','identity_source','video_path','cover_path',
                'title','description','tags_json','bililive_payload_json','bililive_task_id','aid','submit_attempts'):
        assert current[key]==previous[key],f'Historical resource changed: {previous["id"]}/{key}'
    checked+=1
assert old.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0]==now.execute("SELECT value FROM app_meta WHERE key='publish_v2_rollout'").fetchone()[0],'Rollout changed'
files=('backend/publish_v2.py','backend/test_publish_v2.py','docs/STATUS.md','docs/modules/automatic-publishing.md')
for relative in files:
    assert (mirror/relative).read_bytes()==(backup/relative).read_bytes(),'NAS Git copy changed: '+relative
for relative in files[2:]:
    assert (root/relative).read_bytes()==(backup/relative).read_bytes(),'Production doc changed: '+relative
for relative in files:
    target=backup/'git-mirror'/relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(mirror/relative,target)
    shutil.copy2(ops/'stage'/relative,root/relative)
    shutil.copy2(root/relative,mirror/relative)
for name in ('Dockerfile','deploy.py','finalize.py','run-tests.sh','.gitignore','.dockerignore'):
    target=mirror/'ops/cover-brackets-20261015'/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ops/name,target)
verification=json.loads((ops/'verification.json').read_text())
verification.update(completed_resources_unchanged=checked,rollout_unchanged=True,tests=144,nas_git_synced=True)
(ops/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(verification,ensure_ascii=False))
