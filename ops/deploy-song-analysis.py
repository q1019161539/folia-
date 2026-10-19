"""Narrow, backed-up switch. Do not restart ASR/Qwen/render/upload services."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.request

ROOT = Path('/vol1/1000/docker/folia-video-studio')
GIT = Path('/vol1/1000/docker/folia-git')
STAGE = Path('/vol1/1000/docker/folia-song-analysis-20261008')
BACKUP = Path('/vol1/1000/docker/folia-video-studio-backups/20261008-song-analysis-sol')
EXPECTED = {'backend/app.py': 'be8860def2da54346206ab5ee49e4050e1951a847fa60af36ccd78165f8ea71b',
            'backend/Dockerfile': '2a5193d9b84475afe3d5ec81cb880d2b689495f1c6258d613a2c27dd920f7c0c',
            'compose.yaml': '2f8c0698f4e992fd5e5e16c2380f9b51093d8e88e166c47eae9501c156faab8e',
            'web/automation.js': '4567b53b1587f6cb558002eae18d50c55655cd24732cd2d18b44aaaec6593413',
            'web/index.html': '8ce3ba9269aacb8c3396b38c2206075c4cb2cd690081eb5308a9b81fb9fa2b97'}
FILES = list(EXPECTED) + ['backend/song_analysis.py', 'backend/test_song_analysis.py']
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path, body=None):
    req = urllib.request.Request('http://127.0.0.1:18082' + path,
        data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with http.open(req, timeout=25) as response:
        return json.load(response)


def connect():
    c = sqlite3.connect(ROOT / 'data/studio.db', timeout=20)
    c.row_factory = sqlite3.Row
    return c


def identity(name):
    return subprocess.check_output(['docker', 'inspect', name, '--format', '{{.Id}} {{.State.StartedAt}}'], text=True).strip()


def safe_window():
    slot = api('/api/automation/health')['heavy_task_slot']
    assert not slot['busy'] or slot['holder'].startswith(('逐帧重制：','整场 ASR：')), 'Busy local Qwen/render; no update'
    c = connect()
    assert not c.execute("SELECT 1 FROM clip_batches WHERE status IN ('queued','running','cancelling') LIMIT 1").fetchone(), 'Active clips'
    assert not c.execute("SELECT 1 FROM publish_jobs WHERE status IN ('preparing','submitting') LIMIT 1").fetchone(), 'Active publish preparation/submission'
    assert not c.execute("SELECT 1 FROM automation_runs WHERE status='running' AND stage='analyzing' LIMIT 1").fetchone(), 'Analysis request in flight'
    active_asr=[]
    for run in c.execute("SELECT id,transcriber_job_id,transcript FROM automation_runs WHERE status='running'"):
        if json.loads(run['transcript'] or '[]'):
            continue
        job_id=run['transcriber_job_id']; assert job_id, 'ASR handoff not yet durable'
        code="import urllib.request,json;print(json.dumps(json.load(urllib.request.urlopen('http://transcriber:8080/api/jobs/"+job_id+"',timeout=15))))"
        job=json.loads(subprocess.check_output(['docker','exec','folia-video-api','python','-c',code],text=True,timeout=20))
        assert job['status'] in ('queued','running','completed'), 'ASR is not safely resumable'
        assert job['options']['asr_engine']=='whisper' and job['options']['skip_alignment'], 'Incompatible ASR'
        active_asr.append({'run_id':run['id'],'task_id':job_id})
    # Ordinary render/ASR tasks are not assumed restart-safe. The only allowed
    # heavy task is an external revision with an already durable renderer ID.
    for row in c.execute("SELECT id,updated_at,output FROM jobs WHERE status='rendering' AND id NOT IN (SELECT job_id FROM render_revisions WHERE status='running')"):
        # Explicitly inspected old Sept-16 stale row: no renderer (404), unchanged
        # for >22 days. Leave its database state/media untouched. Every other
        # ordinary render still blocks this deployment.
        assert row['id']=='48ad2c8ca27c4d3da84b66496627f818' and time.time()-row['updated_at']>86400, 'Ordinary render active'
        rid=json.loads(row['output'])['render_id']
        code="import urllib.request,urllib.error\ntry:\n urllib.request.urlopen('http://folia-renderer:8091/api/renders/"+rid+"',timeout=10);raise RuntimeError('Renderer exists')\nexcept urllib.error.HTTPError as e:\n assert e.code==404"
        subprocess.run(['docker','exec','folia-video-api','python','-c',code],check=True,timeout=20)
    renders = []
    for row in c.execute("SELECT r.job_id,j.output FROM render_revisions r JOIN jobs j ON j.id=r.job_id WHERE r.status='running'"):
        rid = json.loads(row['output'] or '{}').get('render_id')
        assert rid, 'No durable render ID'
        code = "import urllib.request,json;print(json.dumps(json.load(urllib.request.urlopen('http://folia-renderer:8091/api/renders/" + rid + "',timeout=10))))"
        state = json.loads(subprocess.check_output(['docker', 'exec', 'folia-video-api', 'python', '-c', code], text=True, timeout=20))
        assert state['status'] == 'running' and float(state.get('progress') or 0) < 80, 'No safe render window'
        renders.append({'job_id': row['job_id'], 'render_id': rid})
    if slot['busy'] and slot['holder'].startswith('逐帧重制：'):
        assert renders, 'Unidentified external renderer'
    if slot['busy'] and slot['holder'].startswith('整场 ASR：'):
        assert active_asr and not renders, 'Unknown ASR or concurrent revision'
    c.close()
    return renders


for name in FILES:
    target = ROOT / name
    if name in EXPECTED:
        assert hashlib.sha256(target.read_bytes()).hexdigest() == EXPECTED[name], name + ' changed'
        assert target.read_bytes() == (GIT / name).read_bytes(), 'Unrelated Git edit: ' + name
    else:
        assert not target.exists() and not (GIT / name).exists(), 'New file already exists'
    assert (STAGE / Path(name).name).is_file()

live = json.loads((STAGE / 'live-result.json').read_text())
assert live['read_only'] and live['analysis']['provider'] == 'title-api'
assert live['analysis']['requested_model'] == 'gpt-6.1-sol' and live['analysis']['status'] == 'completed'
assert (STAGE / 'offline-tests-passed').is_file()
control = api('/api/publish-v2/control')
renders = safe_window()
unchanged = {n: identity(n) for n in ('folia-video-native-renderer', 'folia-video-ai', 'folia-video-transcriber', 'bililive-tools')}
BACKUP.mkdir(mode=0o700)
for name in list(EXPECTED) + ['.env']:
    destination = BACKUP / name; destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / name, destination)
    if name == '.env': os.chmod(destination, 0o600)
c = connect()
with sqlite3.connect(BACKUP / 'studio.db') as dest:
    c.backup(dest)
c.close()
for service in ('studio-api', 'studio-web'):
    subprocess.run(['docker', 'tag', 'folia-video-studio-' + service,
                    'folia-before-song-analysis-' + service + ':20261008'], check=True)

# Last check immediately before recreation; with a <80% known revision running,
# queued local work cannot obtain the heavy slot before the short API update.
safe_window()
held=[]
held_restored=False
holder=api('/api/automation/health')['heavy_task_slot'].get('holder') or ''
# Avoid the startup race between the ASR reconnecting thread and a new revision.
# This is a brief operational queue hold, not a new runtime scheduling feature.
# Save/restore only pending rows; running/failed/completed jobs are untouched.
if holder.startswith('整场 ASR：'):
    c=connect()
    c.execute('BEGIN IMMEDIATE')
    assert not c.execute("SELECT 1 FROM render_revisions WHERE status='running' LIMIT 1").fetchone()
    held=[dict(r) for r in c.execute("SELECT job_id,status,error FROM render_revisions WHERE status='pending'")]
    (BACKUP/'held-revisions.json').write_text(json.dumps(held,ensure_ascii=False,indent=2))
    c.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)",('maintenance:song-analysis-deploy',json.dumps({'held':held,'backup':str(BACKUP)},ensure_ascii=False)))
    for row in held:
        c.execute("UPDATE render_revisions SET status='failed',error='maintenance:song-analysis-deploy' WHERE job_id=? AND status='pending'",(row['job_id'],))
    c.commit();c.close()

def restore_held():
    global held_restored
    c=connect();c.execute('BEGIN IMMEDIATE')
    for row in held:
        current=c.execute('SELECT status,error FROM render_revisions WHERE job_id=?',(row['job_id'],)).fetchone()
        assert tuple(current)==('failed','maintenance:song-analysis-deploy'), 'Held revision changed'
        c.execute('UPDATE render_revisions SET status=?,error=? WHERE job_id=?',(row['status'],row['error'],row['job_id']))
    c.execute("DELETE FROM app_meta WHERE key='maintenance:song-analysis-deploy'")
    c.commit();c.close()
    held_restored=True

try:
    api('/api/publish-v2/control', {'enabled': False})
    for name in FILES:
        shutil.copy2(STAGE / Path(name).name, ROOT / name)
    env_path=ROOT / '.env'; env_text=env_path.read_text()
    for key, value in (('SONG_ANALYSIS_MODEL','gpt-6.1-sol'), ('SONG_ANALYSIS_TIMEOUT_SECONDS','600')):
        env_text, count=re.subn(r'(?m)^'+key+r'=.*$', key+'='+value, env_text)
        assert count<=1, 'Duplicate analysis setting'
        if not count: env_text=env_text.rstrip('\n')+'\n'+key+'='+value+'\n'
    env_path.write_text(env_text,encoding='utf-8'); os.chmod(env_path,0o600)
    subprocess.run(['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), 'config', '--quiet'], check=True)
    for service, tag in (('studio-api', 'folia-song-analysis-api:20261008'), ('studio-web', 'folia-song-analysis-web:20261008')):
        subprocess.run(['docker', 'tag', tag, 'folia-video-studio-' + service], check=True)
    subprocess.run(['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), 'up', '-d', '--no-deps', '--no-build', 'studio-api', 'studio-web'], check=True)
    for _ in range(30):
        try:
            config = api('/api/automation/profiles')
            assert config['model'] == 'gpt-6.1-sol' and config['primary_configured'] and config['fallback_configured']
            assert api('/healthz')['ok']
            break
        except Exception:
            time.sleep(2)
    else:
        raise RuntimeError('API unhealthy')
    if held:
        for _ in range(30):
            slot=api('/api/automation/health')['heavy_task_slot']
            if slot['busy'] and slot['holder'].startswith('整场 ASR：'):
                break
            time.sleep(1)
        else:
            raise RuntimeError('ASR not yet reconnected; keep revision hold for inspection')
        restore_held()
    assert unchanged == {n: identity(n) for n in unchanged}, 'External service was restarted'
    c = connect(); assert c.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    for item in renders:
        row = c.execute('SELECT output FROM jobs WHERE id=?', (item['job_id'],)).fetchone()
        assert json.loads(row['output'])['render_id'] == item['render_id'], 'External render ID lost'
    old = sqlite3.connect(BACKUP / 'studio.db'); old.row_factory = sqlite3.Row
    for row in old.execute('SELECT id,identified_title,identified_artist,identity_source FROM jobs'):
        assert tuple(row) == tuple(c.execute('SELECT id,identified_title,identified_artist,identity_source FROM jobs WHERE id=?', (row['id'],)).fetchone()), 'Identity changed'
    for row in old.execute("SELECT id,transcriber_job_id FROM automation_runs WHERE status='running' AND transcriber_job_id!=''"):
        assert row['transcriber_job_id']==c.execute('SELECT transcriber_job_id FROM automation_runs WHERE id=?',(row['id'],)).fetchone()[0], 'ASR task ID changed'
    old.close(); c.close()
    for name in FILES:
        shutil.copy2(ROOT / name, GIT / name)
    subprocess.run(['git', '-C', str(GIT), 'diff', '--check'], check=True)
    # Restore the exact previous publishing enablement/scope; no historical retries.
    restored = api('/api/publish-v2/control', {'enabled': bool(control['enabled'])})
    for key in ('cutover', 'allowlist', 'authorized_render_batches'):
        assert restored['rollout'].get(key) == control['rollout'].get(key)
    result = {'primary': config['model'], 'fallback': config['fallback_model'],
              'backup': str(BACKUP), 'external_services_unchanged': list(unchanged),
              'preserved_renders': renders, 'publish_enabled': restored['enabled'],
              'live_segments': 1442, 'live_accepted': len(live['accepted']),
              'live_seconds': live['elapsed_seconds']}
    result['held_revisions_restored']=len(held)
    (BACKUP / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False), flush=True)
except Exception:
    # No database rollback: active external work may have legitimately advanced.
    for name in EXPECTED: shutil.copy2(BACKUP / name, ROOT / name)
    shutil.copy2(BACKUP / '.env', ROOT / '.env'); os.chmod(ROOT / '.env',0o600)
    for service in ('studio-api', 'studio-web'):
        subprocess.run(['docker', 'tag', 'folia-before-song-analysis-' + service + ':20261008',
                        'folia-video-studio-' + service], check=True)
    subprocess.run(['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), 'up', '-d', '--no-deps', '--no-build', 'studio-api', 'studio-web'], check=True)
    if held and not held_restored:
        for _ in range(30):
            slot=api('/api/automation/health')['heavy_task_slot']
            if slot['busy'] and slot['holder'].startswith('整场 ASR：'):
                restore_held();break
            time.sleep(1)
    # Keep new source files as recoverable staged artifacts; old code doesn't import
    # them. Do not reset tasks or resume publishing on an unverified rollback.
    raise
