"""Scoped documentation/source mirror sync; refuses to overwrite unrelated changes."""
import hashlib
from pathlib import Path
import shutil

ROOT=Path('/vol1/1000/docker/folia-video-studio');OPS=ROOT/'ops/compilation-20261018';MIRROR=Path('/vol1/1000/docker/folia-git')
expected={'docs/STATUS.md':'0509c55d6c08acc52ba6a245141b8b0cb82172b95a5b239b45f50a44bb1541b2',
          'docs/README.md':'7a9bec208a12ccbd21f6886672a7aedb2907a5a2b591b95d1fc1c35b4ff67a71'}
for relative,digest in expected.items():
    for root in (ROOT,MIRROR):assert hashlib.sha256((root/relative).read_bytes()).hexdigest()==digest,'Document changed: '+str(root/relative)
new='docs/modules/song-compilations.md'
assert not (ROOT/new).exists() and not (MIRROR/new).exists(),'Module document already exists'
backup=OPS/'backup-docs';backup.mkdir(exist_ok=False)
for relative in expected:
    target=backup/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
for relative in (*expected,new):
    for root in (ROOT,MIRROR):
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OPS/'stage'/relative,target)
for name in ('compilation.py','launch.py','test_compilation.py','sync_docs.py','.gitignore'):
    target=MIRROR/'ops/compilation-20261018'/name
    assert not target.exists() or target.read_bytes()==(OPS/name).read_bytes(),'Existing mirror source differs'
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OPS/name,target)
print('DOCS_AND_SELECTED_OPS_SYNCED_NO_GIT_COMMIT_OR_PUSH')
