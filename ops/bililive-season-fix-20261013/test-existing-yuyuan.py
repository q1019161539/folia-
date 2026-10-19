"""Explicit one-archive maintenance test authorized 2026-10-13; never an uploader."""
import hashlib,json,sqlite3,subprocess,time
from pathlib import Path
from publishing import PublishSettings,BililiveToolClient

ID='fdcec4448cff4006992da76861c301b9'
AID='117432995808958'
UID=181647901
db_path=Path('/data/studio.db')
backup_root=Path('/data/publish-template-backups/collection-test-20261013-'+ID)
backup_root.mkdir(exist_ok=True)
connection=sqlite3.connect(db_path,timeout=30);connection.row_factory=sqlite3.Row
job=dict(connection.execute('SELECT * FROM publish_jobs WHERE id=?',(ID,)).fetchone())
assert job['aid']==AID and job['bililive_uid']==UID and job['status']=='completed'
assert job['identified_title']=='游园惊梦' and job['bililive_task_id']
payload=json.loads(job['bililive_payload_json']);assert payload['config']['seasonId']==9133790
settings=PublishSettings.from_env();client=BililiveToolClient(settings.bililive_base_url,settings.bililive_passkey)
try:
    client.collection_capabilities()
    archives=client._request('GET','/bili/archives',params={'uid':UID,'pn':1,'ps':10}).json()
    matches=[a for a in archives.get('arc_audits',[]) if str((a.get('Archive') or {}).get('aid'))==AID]
    assert len(matches)==1,'Target is not present uniquely in the current archive listing'
    archive=matches[0]['Archive'];assert archive['mid']==UID and archive['title']==job['title']
    cids=matches[0]['cid_list'];assert len(cids)==1 and isinstance(cids[0],int) and cids[0]>0
    seasons=client._request('GET','/bili/seasons',params={'uid':UID}).json()
    target=next(s for s in seasons['seasons'] if s['season']['id']==9133790)
    sections=target['sections']['sections'];assert any(s['id']==10204569 for s in sections)
    receipt={'uid':UID,'aid':int(AID),'cid':cids[0],'seasonId':9133790,'sectionId':10204569,
             'title':job['title'],'taskId':job['bililive_task_id']}
    (backup_root/'verified-input.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    before=backup_root/'publish-job-before.json'
    if not before.exists():
        before.write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
        snapshot=sqlite3.connect(backup_root/'studio-before.db')
        try:connection.backup(snapshot)
        finally:snapshot.close()
    assert job['collection_status'] is None or job['collection_status'] in ('pending','retry','joined'), 'Unexpected existing collection state'
    connection.execute("UPDATE publish_jobs SET collection_status='pending',collection_error='显式单稿合集测试，等待恢复队列',next_collection_at=0,updated_at=? WHERE id=? AND aid=?",(time.time(),ID,AID))
    connection.commit()
    # The host runner will atomically enqueue exactly this checked receipt inside BililiveTool.
    print(json.dumps({'publish_job_id':ID,'verified_receipt':receipt,'frozen_payload_sha256':hashlib.sha256(job['bililive_payload_json'].encode()).hexdigest()},ensure_ascii=False))
finally:client.close();connection.close()
