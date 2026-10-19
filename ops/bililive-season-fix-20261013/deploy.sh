#!/bin/sh
set -eu
task_root=/vol1/1000/docker/folia-video-studio
task_ops="$task_root/ops/bililive-season-fix-20261013"
task_bili=/vol1/1000/docker/bililive-tool
test "$(docker inspect bililive-tools --format '{{.Image}}')" = 'sha256:fd4ce39cb5f8da4b7b6fd7591d522ab17eeb878bfaac6c9da9621ab785e85e2b'
test "$(docker inspect folia-video-api --format '{{.Image}}')" = 'sha256:b6f3dc885b05cdeaaf8ec2c1883dd65b632558793809f559d0aca1406d753ece'
python3 -c 'from pathlib import Path; assert Path("/vol1/1000/docker/folia-video-studio/ops/bililive-season-fix-20261013/full-tests.log").read_text().strip().endswith("OK")'
python3 "$task_ops/backup.py"
task_changed=0
rollback() {
 task_code=$?
 if [ "$task_code" -ne 0 ] && [ "$task_changed" = 1 ]; then
  # Restore service images/config, never restore a stale database or publication IDs.
  cp "$task_ops/backup/folia/backend/publishing.py" "$task_root/backend/publishing.py"
  cp "$task_ops/backup/folia/backend/publish_v2.py" "$task_root/backend/publish_v2.py"
  cp "$task_ops/backup/folia/web/publish.js" "$task_root/web/publish.js"
  cp "$task_ops/backup/folia/web/index.html" "$task_root/web/index.html"
  docker tag folia-video-studio-studio-api:cover-prompt-20261012 folia-video-studio-studio-api:latest
  docker tag folia-web-before-season:20261013 folia-video-studio-studio-web:latest
  cd "$task_root"
  docker compose up -d --no-deps --no-build studio-api studio-web
  # Keep the explicit override recoverable, do not remove records/assets.
  cp "$task_ops/rollback.override.yaml" "$task_bili/docker-compose.override.yml"
  cd "$task_bili"
  docker compose up -d --no-deps --no-build fullstack
 fi
}
trap rollback EXIT
cp "$task_ops/bililive.override.yaml" "$task_bili/docker-compose.override.yml"
task_changed=1
cd "$task_bili"
docker compose up -d --no-deps --no-build fullstack
# Wait for the authenticated addon readiness before enabling new Folia snapshots.
docker exec -i folia-video-api python - <<'PY'
import time
from publishing import PublishSettings,BililiveToolClient
s=PublishSettings.from_env();client=BililiveToolClient(s.bililive_base_url,s.bililive_passkey,timeout=3)
try:
 for _ in range(20):
  try:
   r=client._client.get('/bili/folia-season/capabilities')
   if r.status_code==200 and r.json()=={'version':1,'durable':True}:break
  except Exception:pass
  time.sleep(1)
 else:raise RuntimeError('BililiveTool collection addon not ready')
 print('BILI_ADDON_READY')
finally:client.close()
PY
cd "$task_root"
cp "$task_ops/backend/publishing.py" backend/publishing.py
cp "$task_ops/backend/publish_v2.py" backend/publish_v2.py
cp "$task_ops/web/publish.js" web/publish.js
cp "$task_ops/web/index.html" web/index.html
docker tag folia-video-studio-studio-api:season-fix-20261013 folia-video-studio-studio-api:latest
docker tag folia-video-studio-studio-web:season-fix-20261013 folia-video-studio-studio-web:latest
docker compose up -d --no-deps --no-build studio-api studio-web
python3 - <<'PY'
import urllib.request,json,time
for _ in range(20):
 try:
  if json.load(urllib.request.urlopen('http://127.0.0.1:18082/healthz',timeout=2)).get('ok'):break
 except Exception:pass
 time.sleep(1)
else:raise RuntimeError('New API health check failed')
print('API_HEALTH_OK')
PY
task_changed=0
printf 'COLLECTION_FIX_DEPLOYED\n'
