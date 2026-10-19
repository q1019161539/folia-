"""NAS host runner: one verified existing archive, no upload/API-cover requests."""
import json,subprocess,time,urllib.request
from pathlib import Path

root=Path('/vol1/1000/docker/folia-video-studio');ops=root/'ops/bililive-season-fix-20261013'
preflight='''
from publishing import PublishSettings,BililiveToolClient
import sqlite3,json,urllib.request
s=PublishSettings.from_env();client=BililiveToolClient(s.bililive_base_url,s.bililive_passkey)
try:
 def check(x):
  if isinstance(x,dict):
   if 'providerId' in x and 'state' in x:assert x['state']=='idle' and not x.get('recordHandle'),'Recorder active'
   for v in x.values():check(v)
  elif isinstance(x,list):
   for v in x:check(v)
 check(client._client.get('/recorder/list').json())
 assert not any(t.get('type')=='bili' and t.get('status') not in ('completed','error','canceled','cancelled') for t in client.list_upload_tasks()),'Upload active'
 assert not json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/automation/health'))['heavy_task_slot']['busy'],'Heavy task active'
 c=sqlite3.connect('file:/data/studio.db?mode=ro',uri=True)
 assert not c.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting') LIMIT 1").fetchone(),'Paid request active'
 c.close();print('SCOPED_TEST_PREFLIGHT_IDLE')
finally:client.close()
'''
def api_code(code):
    return subprocess.run(['docker','exec','-i','folia-video-api','python','-'],input=code,text=True,check=True)
api_code(preflight)
api_code((ops/'test-existing-yuyuan.py').read_text(encoding='utf-8'))
input_file=root/'data/publish-template-backups/collection-test-20261013-fdcec4448cff4006992da76861c301b9/verified-input.json'
receipt=json.loads(input_file.read_text(encoding='utf-8'))
assert receipt['aid']==117432995808958 and receipt['uid']==181647901 and receipt['seasonId']==9133790
code="""const {createQueue}=require('/app/backend/folia-season-jobs.cjs');
const queue=createQueue({root:'/app/data/folia-season-jobs',startTimer:false,getClient:()=>{throw Error('utility must never make SDK requests');}});
const job=queue.enqueue(JSON.parse(process.argv[1]));console.log(JSON.stringify({aid:job.aid,status:job.status,attempts:job.attempts}));queue.close();"""
subprocess.run(['docker','exec','bililive-tools','node','-e',code,json.dumps(receipt,ensure_ascii=False)],check=True)
api_code(preflight) # Check again directly before restarting the recording/uploader process.
subprocess.run(['docker','compose','restart','fullstack'],cwd='/vol1/1000/docker/bililive-tool',check=True)
subprocess.run(['docker','tag','sha256:663fe6235585ce981416b6abda3ce0d96801d5cd90c1b706c431d0785bbaf8da','folia-api-before-existing-collection-test:20261013'],check=True)
subprocess.run(['cp',str(root/'backend/publish_v2.py'),str(ops/'backup/publish_v2-before-existing-test.py')],check=True)
subprocess.run(['cp',str(ops/'backend/publish_v2.py'),str(root/'backend/publish_v2.py')],check=True)
subprocess.run(['docker','tag','folia-video-studio-studio-api:collection-existing-test-20261013','folia-video-studio-studio-api:latest'],check=True)
subprocess.run(['docker','compose','up','-d','--no-deps','--no-build','studio-api'],cwd=root,check=True)
print('ONE_EXISTING_ARCHIVE_QUEUED_NO_REUPLOAD')
