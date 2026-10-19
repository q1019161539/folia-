"""NAS launcher: isolated low-priority CPU worker; no service restarts or Bili calls."""
import json
from pathlib import Path
import subprocess
import sys

OPS=Path('/vol1/1000/docker/folia-video-studio/ops/compilation-20261018')
info=json.loads(subprocess.check_output(['docker','inspect','folia-video-api'],text=True))[0]
mounts={item['Destination']:item['Source'] for item in info['Mounts']}
output=Path(mounts['/output']);work=output/'小红泡-管珩心/歌曲长篇合集/2026-10-18'
assert work.resolve().is_relative_to(output.resolve()) and (work/'manifest.json').is_file()
network=next(name for name in info['NetworkSettings']['Networks'] if name.endswith('_studio'))
action=sys.argv[1];assert action in ('test','preview','render')
args=['docker','run','--cpus','1','--cpu-shares','128','--memory','2g','--pids-limit','128',
      '--entrypoint','python','-e','COMPILATION_DIR=/compilation','-v',str(OPS)+':/task:ro',
      '-v',str(output)+':/output:ro','-v',str(work)+':/compilation']
if '/output-legacy' in mounts:args+=['-v',mounts['/output-legacy']+':/output-legacy:ro']
if action=='test':
    args+=['--rm','--network','none',info['Image'],'/task/test_compilation.py']
    with (OPS/'tests.log').open('w') as log:
        result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT)
    print((OPS/'tests.log').read_text()[-4000:]);sys.exit(result.returncode)
name='folia-xhp-compilation-'+action+'-20261018'
existing=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
if existing.returncode==0:
    item=json.loads(existing.stdout)[0]
    assert item['Config'].get('Labels',{}).get('folia.compilation')=='20261018','Name belongs to another task'
    print(json.dumps({'container':name,'state':item['State']['Status'],'already_exists':True}));sys.exit(0)
args+=['-d','--network',network,'--name',name,'--label','folia.compilation=20261018',info['Image'],'/task/compilation.py',action]
container=subprocess.check_output(args,text=True).strip()
print(json.dumps({'container':name,'id':container,'work':str(work),'cpus':1,'guard':'pause FFmpeg while production heavy task is busy','action':action},ensure_ascii=False))
