"""Release exactly the backed-up four jobs only after the fallback API is live."""
import json
from pathlib import Path
import sqlite3
import subprocess
import urllib.request

root=Path('/vol1/1000/docker/folia-video-studio')
control=json.load(urllib.request.urlopen('http://127.0.0.1:18082/api/publish-v2/control',timeout=15))
assert control.get('cover_fallback_configured') is True, 'New fallback API not configured/live'
assert control.get('cover_max_attempts')==10 and control.get('cover_fallback_after_failures')==5
running=subprocess.check_output(['docker','inspect','folia-video-api','--format','{{.Image}}'],text=True).strip()
expected=subprocess.check_output(['docker','image','inspect','folia-video-studio-studio-api:gemini-fallback-20261015','--format','{{.Id}}'],text=True).strip()
assert running==expected, 'Wrong API image'
backup=root/'data/publish-template-backups/gemini-fallback-20261015'
records=json.loads((backup/'deferred-jobs.json').read_text(encoding='utf-8'))['rows']
c=sqlite3.connect(root/'data/studio.db',timeout=15);c.row_factory=sqlite3.Row
c.execute('BEGIN IMMEDIATE')
for original in records:
    row=c.execute('SELECT * FROM publish_jobs WHERE id=?',(original['id'],)).fetchone()
    assert row and row['status']=='pending' and row['failure_stage']=='cover'
    assert not any(row[k] for k in ('submit_attempts','bililive_task_id','aid','bvid','publish_result'))
    for key in ('source_job_id','automation_run_id','identified_title','identified_artist','identity_source',
                'video_path','video_size','video_mtime','streamer','bililive_preset_id','bililive_uid','title','title_generation_json'):
        assert row[key]==original[key], 'Protected job data changed: '+key
    song=c.execute('SELECT * FROM song_projects WHERE id=?',(row['song_project_id'],)).fetchone()
    assert 5<song['cover_attempts']<10 and not song['cover_path'], 'Budget or cache changed'
    c.execute('UPDATE publish_jobs SET next_retry_at=0 WHERE id=?',(row['id'],))
c.commit();c.close()
(backup/'released.json').write_text(json.dumps({'released_ids':[x['id'] for x in records],'counter_reset':False},indent=2),encoding='utf-8')
print(json.dumps({'released_ids':[x['id'] for x in records],'counter_reset':False}))
