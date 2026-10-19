"""Read-only preflight first, then consistent backup; never edits publication rows."""
from pathlib import Path
import json,shutil,sqlite3,subprocess,sys

root=Path('/vol1/1000/docker/folia-video-studio');ops=root/'ops/bililive-season-fix-20261013'
bili=Path('/vol1/1000/docker/bililive-tool')
assert not (bili/'docker-compose.override.yml').exists(), 'Existing override requires preserving/merging first'
script='''
from publishing import PublishSettings,BililiveToolClient
import sqlite3,urllib.request,json
s=PublishSettings.from_env();cl=BililiveToolClient(s.bililive_base_url,s.bililive_passkey)
try:
 recorders=cl._client.get('/recorder/list').json()['payload']
 def check(value):
  if isinstance(value,dict):
   if 'providerId' in value and 'state' in value:assert value['state']=='idle' and not value.get('recordHandle'), 'Recorder active'
   for v in value.values():check(v)
  elif isinstance(value,list):
   for v in value:check(v)
 check(recorders)
 tasks=cl.list_upload_tasks()
 assert not any(t.get('type')=='bili' and t.get('status') not in ('completed','error','canceled','cancelled') for t in tasks),'Bili task active'
 health=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/automation/health'))
 assert not health['heavy_task_slot']['busy'],'Heavy task active'
 c=sqlite3.connect('file:/data/studio.db?mode=ro',uri=True)
 assert not c.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting') LIMIT 1").fetchone(),'Paid request active'
 c.close();print('RECORDERS_UPLOAD_AND_API_IDLE')
finally:cl.close()
'''
subprocess.run(['docker','exec','-i','folia-video-api','python','-'],input=script,text=True,check=True)
if '--check-only' in sys.argv:raise SystemExit(0)
backup=ops/'backup';backup.mkdir(exist_ok=False)
for base,prefix,files in ((root,'folia',('backend/publishing.py','backend/publish_v2.py','web/publish.js','web/index.html','compose.yaml','.env','docs/STATUS.md','docs/modules/automatic-publishing.md')),
                         (bili,'bililive',('docker-compose.yml','.env'))):
    for relative in files:
        source=base/relative
        if source.exists():
            target=backup/prefix/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
images={name:json.loads(subprocess.check_output(['docker','inspect',name]))[0]['Image'] for name in ('bililive-tools','folia-video-api','folia-video-web')}
(backup/'images.json').write_text(json.dumps(images),encoding='utf-8')
c=sqlite3.connect('file:'+str(root/'data/studio.db')+'?mode=ro',uri=True);d=sqlite3.connect(backup/'studio.db')
try:c.backup(d);assert d.execute('pragma integrity_check').fetchone()[0]=='ok'
finally:c.close();d.close()
print('BACKUP_INTEGRITY_OK')
