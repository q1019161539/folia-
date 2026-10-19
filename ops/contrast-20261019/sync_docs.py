"""Sync only this task's source/docs, after checking pre-edit documentation hashes."""
import hashlib
from pathlib import Path
import shutil

runtime=Path('/vol1/1000/docker/folia-video-studio')
mirror=Path('/vol1/1000/docker/folia-git')
ops=runtime/'ops/contrast-20261019'
expected={'docs/STATUS.md':'ada6899c32aea169335728351240842b9ca5f14ade49a96ea182c715309f15e4',
          'docs/modules/batch-clips.md':'6611afb0c2d3dd914eb2ae3b5cc49b264235f4753f333098b715fd86957b4eb6'}
for root in (runtime,mirror):
    for rel,old in expected.items():
        assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==old,'Changed concurrently: '+str(root/rel)
for root in (runtime,mirror):
    for rel in expected:
        backup=ops/'backup-docs'/root.name/rel
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/rel,backup)
        shutil.copy2(ops/'stage-docs'/rel,root/rel)
        print('Synced',root/rel)
target=mirror/'ops/contrast-20261019';target.mkdir(parents=True,exist_ok=True)
for name in ('edit.py','launch.py','refine.py','test_edit.py','sync_docs.py','README.md','.gitignore'):
    p=target/name
    assert not p.exists() or p.read_bytes()==(ops/name).read_bytes(),'Unexpected mirror file: '+str(p)
    shutil.copy2(ops/name,p)
print('Only selected task files synced; no git commit or push')
