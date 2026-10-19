import hashlib
from pathlib import Path
import shutil

runtime=Path('/vol1/1000/docker/folia-video-studio');mirror=Path('/vol1/1000/docker/folia-git')
ops=runtime/'ops/publish-yaobaobao02-20261019'
expected={'docs/STATUS.md':'54ceabc90ebbaf747e85435f9143a9d5dd3b51d5fa8fd8446d147bfabd10f440',
 'docs/modules/automatic-publishing.md':'084d4d2c97b9951e6e366c29e6fea68c52bd050d2ba85ea7df2cbd73c6dfd7cb'}
for root in (runtime,mirror):
 for rel,old in expected.items():
  assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==old,'Concurrent change: '+str(root/rel)
for root in (runtime,mirror):
 for rel in expected:
  backup=ops/'backup-docs'/root.name/rel;backup.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(root/rel,backup);shutil.copy2(ops/'stage-docs'/rel,root/rel)
target=mirror/'ops/publish-yaobaobao02-20261019';target.mkdir(parents=True,exist_ok=True)
for name in ('once.py','test_once.py','sync_docs.py','README.md','.gitignore'):
 p=target/name
 assert not p.exists() or p.read_bytes()==(ops/name).read_bytes(),'Unexpected existing file: '+str(p)
 shutil.copy2(ops/name,p)
print('Only scoped source/docs synchronized; no Git commit or push')
