"""Run on the NAS; fallback key arrives via stdin, never command arguments/logs."""
import hashlib
import json
from pathlib import Path
import sys

root=Path('/vol1/1000/docker/folia-video-studio')
secret=json.load(sys.stdin)['fallback_key']
assert secret.startswith('sk-') and '\n' not in secret and '\r' not in secret
asset=root/'data/cover-references/xiaohongpao-normal.png'
digest=hashlib.sha256(asset.read_bytes()).hexdigest()
assert digest=='bb19b18aa05d45a0a0b8a24e25161208d87a69f6d6bf8a22087e8f0e56fa1efa', 'Original reference mismatch'
config={'bilibili:2516117':{'path':'/data/cover-references/xiaohongpao-normal.png','sha256':digest,'crop':[1500,350,2680,1250]}}
(asset.parent/'references.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
updates={'COVER_FALLBACK_ENABLED':'1','COVER_FALLBACK_BASE_URL':'https://www.codex789.com/v1',
         'COVER_FALLBACK_MODEL':'gemini-3-pro-image-preview','COVER_FALLBACK_API_KEY':secret,
         'COVER_FALLBACK_PROXY':'','COVER_REFERENCE_CONFIG':'/data/cover-references/references.json'}
env=root/'.env'
lines=env.read_text(encoding='utf-8').splitlines()
kept=[line for line in lines if line.split('=',1)[0] not in updates]
env.write_text('\n'.join(kept+[key+'='+value for key,value in updates.items()])+'\n',encoding='utf-8')
env.chmod(0o600)
print(json.dumps({'fallback_enabled':True,'identity':'bilibili:2516117','reference_sha256':digest,'key_configured':True}))
