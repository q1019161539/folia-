"""User-authorized interruption/retry of exactly the pre-identified active ASR run."""
import json
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request

ROOT=Path('/vol1/1000/docker/folia-video-studio');OPS=ROOT/'ops/reference-full-20261015'
RUN='14e3da799687468594b42f72d11a80fd'
def row():
    with sqlite3.connect('file:'+str(ROOT/'data/studio.db')+'?mode=ro',uri=True,timeout=30) as c:
        c.row_factory=sqlite3.Row;return dict(c.execute('SELECT * FROM automation_runs WHERE id=?',(RUN,)).fetchone())
def post(action):
    req=urllib.request.Request('http://127.0.0.1:18082/api/automation/runs/'+RUN+'/'+action,data=b'{}',headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=60))
if sys.argv[1]=='cancel':
    current=row()
    assert current['profile_id']=='bc87122ccfbb4403a15efafb3ae01cc6' and '/17-07-16_' in current['source']
    target=OPS/'backup/interrupted-run.json';assert not target.exists(),'Interruption already recorded'
    target.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    if current['status'] not in ('completed','completed_with_errors','cancelled','failed'):
        post('cancel')
    for _ in range(25):
        current=row()
        if current['status'] in ('cancelled','failed','completed','completed_with_errors'):break
        time.sleep(1)
    print(json.dumps({'run':RUN,'status':current['status'],'stage':current['stage'],'transcriber_job_id':current['transcriber_job_id']},ensure_ascii=False))
elif sys.argv[1]=='resume':
    original=json.loads((OPS/'backup/interrupted-run.json').read_text());current=row()
    for key in ('source','profile_id','transcriber_job_id'):assert current[key]==original[key]
    if current['status'] in ('cancelled','failed'):
        post('retry');action='existing retry entry'
    elif current['status'] in ('completed','completed_with_errors'):
        action='already completed; no duplicate retry'
    else:raise AssertionError('Not a safe terminal state to retry')
    current=row();result={'run':RUN,'action':action,'status':current['status'],'stage':current['stage'],
        'transcriber_job_id':current['transcriber_job_id']}
    (OPS/'backup/resumed-run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
