"""NAS-side fixed-target driver. Waits normally; no restart/preemption/deletion.

One job and one submission only. Stops on a terminal render failure or an
uncertain upload response. Successful cover/title are reused by repair.py.
"""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path('/vol1/1000/docker/folia-yujian-repair-20261008')
API='folia-video-api'
JOB='b37c38a07a61575f978955555942d471'
PUB='0815fcdd605b57aa8a1bf40f9eb89a59'
log_path=ROOT/'runner.jsonl'


def event(**data):
    data['time']=time.time()
    with log_path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(data,ensure_ascii=False)+'\n')


def action(name,stdin=None):
    result=subprocess.run(['docker','exec','-i',API,'python','/tmp/repair-yujian.py',name],
        input=json.dumps(stdin) if stdin is not None else '',capture_output=True,text=True,timeout=120)
    if result.returncode:
        # Do not copy unfiltered remote tracebacks/HTTP bodies into persistent logs.
        raise RuntimeError('Maintenance action failed: '+name+' (exit '+str(result.returncode)+')')
    return json.loads(result.stdout)


def verify_paths(snapshot):
    p=snapshot['publish'];payload=snapshot['record']['shared_receipt'] if snapshot['record'].get('shared_receipt') else None
    # Exact mounts confirmed by live deployment; no MP4 copy is performed.
    video='/app/Folia成片/'+str(Path(p['video_path']).relative_to('/output'))
    cover='/app/Folia成片/'+str(Path(p['cover_path']).relative_to('/output'))
    assert JOB in Path(video).parent.name
    code='''const fs=require('fs'),crypto=require('crypto');const [video,cover]=process.argv.slice(1);
      for(const p of [video,cover])if(!p.startsWith('/app/Folia成片/'))throw Error('outside share');
      const vs=fs.statSync(video),cs=fs.statSync(cover);
      console.log(JSON.stringify({video:{path:video,size:vs.size,file:vs.isFile()},
        cover:{path:cover,size:cs.size,file:cs.isFile(),sha256:crypto.createHash('sha256').update(fs.readFileSync(cover)).digest('hex')}}));'''
    r=subprocess.run(['docker','exec','bililive-tools','node','-e',code,video,cover],
                     capture_output=True,text=True,timeout=30)
    assert r.returncode==0,'BililiveTool shared paths not readable'
    receipt=json.loads(r.stdout);action('verify_shared',receipt)
    event(stage='shared_paths_verified',video_size=receipt['video']['size'],cover_sha256=receipt['cover']['sha256'])


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'runner.lock').open('a',encoding='utf-8') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        run_locked()


def run_locked():
    (ROOT/'runner.pid').write_text(str(os.getpid()),encoding='utf-8')
    event(stage='started',job_id=JOB,publish_id=PUB)
    deadline=time.monotonic()+12*3600
    previous=None
    while time.monotonic()<deadline:
        s=action('snapshot');status=s['status'];n=s['native'];p=s['publish']
        observed=(status,n.get('status'),int(n.get('progress') or 0)//10,p.get('status'),p.get('bvid'))
        if observed!=previous:
            event(stage='progress',job_status=status,render_status=n.get('status'),
                  render_progress=n.get('progress'),publish_status=p.get('status'),bvid=p.get('bvid'))
            previous=observed
        if n.get('status') in ('failed','cancelled') or status=='failed':
            event(stage='stopped_render_failure',render_id=n.get('id'),error=n.get('error'))
            return
        if status=='aligned':
            action('render')
        elif n.get('status')=='completed' and status!='completed':
            action('recover_render')
        elif status=='completed':
            if not p.get('id'):
                action('prepare');continue
            assert p['id']==PUB
            if p.get('aid'):
                action('poll')
                final=action('snapshot')['publish']
                event(stage='completed',**final)
                (ROOT/'result.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
                return
            if p.get('bililive_task_id'):
                action('poll')
            elif p.get('status')=='ready' and not p.get('submit_attempts'):
                verify_paths(s);action('deleted');accepted=action('submit')
                event(stage='accepted',**accepted)
            elif p.get('status') in ('submitting','failed') or p.get('submit_attempts'):
                event(stage='stopped_needs_inspection',publish_status=p.get('status'),
                      submit_attempts=p.get('submit_attempts'))
                return  # Never blindly repeat upload or reset a task ID.
            else:
                raise RuntimeError('Unexpected maintenance preparation status; stop safely')
        time.sleep(20)
    event(stage='stopped_wait_timeout')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        event(stage='stopped_error',error_type=type(exc).__name__,message=str(exc))
        sys.exit(1)
