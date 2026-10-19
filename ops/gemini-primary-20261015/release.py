"""Explicit 10-job cover recovery after Gemini-primary deployment; never reset counts."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import urllib.request

ROOT=Path('/vol1/1000/docker/folia-video-studio')
OPS=ROOT/'ops/gemini-primary-20261015'
IDS=('e86dfdf7732d41458274d1475f0ba001','73518e155d7a49938c494db1be66c587',
     '7fd48e1c68374e5bb08b4c03dfeba184','fd980b637419407b985543faaef930cc',
     'e8ca8790cc4d4419be7977260890638f','375adf685c0c4cb081ecff822d99cfdd',
     '4ca30371f01f4eb4bc54ed0c07549d13','43fdc211d05e4541ba1802cf1bbc9ac3',
     '6e520dcdd7a2419e8838a8fb7cfc960d','1dee39ce2e934982b75b3070f614cee1')

def records(c):
    rows=[]
    for pid in IDS:
        row=dict(c.execute('SELECT * FROM publish_jobs WHERE id=?',(pid,)).fetchone())
        song=dict(c.execute('SELECT * FROM song_projects WHERE id=?',(row['song_project_id'],)).fetchone())
        assert row['status']=='failed' and row['failure_stage']=='cover' and row['pipeline_version']==2
        assert row['publish_error']=='GPT 生图 HTTP 403，请检查服务或账号额度'
        assert not any(row[k] for k in ('submit_attempts','bililive_task_id','aid','bvid','publish_result','bililive_payload_json','cover_path'))
        assert song['broadcaster_key']=='bilibili:2516117' and not song['cover_path'] and not song['conflict']
        assert 0<song['cover_attempts']<=5
        rows.append({'job':row,'song':song})
    return rows

def main():
    assert not (OPS/'released.json').exists(),'Already released; do not repeat'
    control=json.load(urllib.request.urlopen('http://127.0.0.1:18082/api/publish-v2/control',timeout=15))
    assert control['cover_primary_provider']=='gemini' and control['cover_configured'] and control['cover_max_attempts']==10
    original=json.loads((OPS/'backup/authorized-jobs.json').read_text())
    with sqlite3.connect(ROOT/'data/studio.db',timeout=30) as c:
        c.row_factory=sqlite3.Row;c.execute('BEGIN IMMEDIATE')
        current=records(c)
        assert current==original,'Authorized input changed; diagnose before requeue'
        for entry in current:
            row=entry['job']
            # Check real media stat in API path without copying multi-GB MP4s.
            path=Path('/vol2/1000/video/Folia成片')/Path(row['video_path']).relative_to('/output')
            stat=path.stat();assert stat.st_size==row['video_size'] and stat.st_mtime==row['video_mtime']
            c.execute("UPDATE publish_jobs SET status='pending',next_retry_at=0,updated_at=? WHERE id=?",(time.time(),row['id']))
    result={'released_ids':list(IDS),'counter_reset':False,'provider':'gemini','at':time.time()}
    (OPS/'released.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
