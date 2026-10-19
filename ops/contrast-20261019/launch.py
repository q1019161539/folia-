"""Run isolated editor with source/DB read-only and one new writable output directory."""
import json
from pathlib import Path
import subprocess
import sqlite3
import sys

OPS=Path('/vol1/1000/docker/folia-video-studio/ops/contrast-20261019')
info=json.loads(subprocess.check_output(['docker','inspect','folia-video-api'],text=True))[0]
mounts={x['Destination']:x['Source'] for x in info['Mounts']}
root=Path(mounts['/media-output']).resolve()
edit=(root/'小红泡-管珩心/2026-10-19/歌曲切片/温柔教练_反差精剪_v1').resolve()
assert edit.is_relative_to(root) and len(edit.relative_to(root).parts)==4
edit.mkdir(parents=True,exist_ok=True)
records=edit/'source-records.json'
if not records.exists():
    c=sqlite3.connect('file:'+str(Path(mounts['/data'])/'studio.db')+'?mode=ro',uri=True,timeout=20)
    ids={'A':'bb7f52c750104d038615d56ad6316027','B':'cfeb008f758a4759ad3366547f03f9dc','C':'4fc7dff4534a49b48b19eb495393b174'}
    snapshot={}
    for key,rid in ids.items():
        row=c.execute('SELECT source,transcript FROM automation_runs WHERE id=?',(rid,)).fetchone()
        snapshot[key]={'run_id':rid,'source':row[0],'transcript':json.loads(row[1])}
    c.close()
    records.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
action=sys.argv[1];assert action in ('inspect','smoke','render','refine')
if action=='refine':
    state=json.loads(subprocess.check_output(['docker','inspect','folia-xhp-contrast-render-20261019']))[0]['State']
    assert state['Status']=='exited' and state['ExitCode']==0,'Base render is not finished'
    assert (edit/'result.json').is_file()
args=['docker','run','--cpus','1','--cpu-shares','128','--memory','2g','--pids-limit','128','--network','none',
      '--entrypoint','python','-v',str(OPS)+':/task:ro','-v',mounts['/media/bililive']+':/sources:ro',
      '-v',str(edit)+':/edit']
if action in ('inspect','smoke'):args+=['--rm']
else:
    name='folia-xhp-contrast-'+action+'-20261019'
    old=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
    if old.returncode==0:
        print(json.dumps({'existing':True,'state':json.loads(old.stdout)[0]['State']['Status'],'directory':str(edit)},ensure_ascii=False));sys.exit(0)
    args+=['-d','--name',name,'--label','folia.contrast=20261019']
args+=([info['Image'],'/task/refine.py'] if action=='refine' else [info['Image'],'/task/edit.py',action])
subprocess.run(args,check=True)
print(json.dumps({'directory':str(edit),'action':action},ensure_ascii=False))
