"""Cached-lyric MP4 revisions, with an explicit optional publishing hand-off."""
import copy
import json
import time
import uuid
from collections import Counter
from pathlib import Path

from publish_v2 import broadcaster_key, normalized_title, safe_error


def init_schema(c):
    columns = {r[1] for r in c.execute('PRAGMA table_info(jobs)')}
    for name in ('render_revision_parent_id', 'render_revision_batch_id'):
        if name not in columns:
            c.execute(f'ALTER TABLE jobs ADD COLUMN {name} TEXT')
    if 'render_revision_publish' not in columns:
        c.execute('ALTER TABLE jobs ADD COLUMN render_revision_publish INTEGER NOT NULL DEFAULT 0')
    c.execute('''CREATE TABLE IF NOT EXISTS render_revisions(
        job_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, source_job_id TEXT NOT NULL,
        profile_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        created_at REAL NOT NULL, updated_at REAL NOT NULL, error TEXT,
        publish_status TEXT NOT NULL DEFAULT 'not_requested', publish_error TEXT,
        UNIQUE(batch_id,source_job_id))''')
    revision_columns={r[1] for r in c.execute('PRAGMA table_info(render_revisions)')}
    for name, definition in (('publish_status', "TEXT NOT NULL DEFAULT 'not_requested'"), ('publish_error', 'TEXT'), ('priority_at','REAL NOT NULL DEFAULT 0')):
        if name not in revision_columns: c.execute(f'ALTER TABLE render_revisions ADD COLUMN {name} {definition}')


class RenderRevisions:
    def __init__(self, db, get_job, get_profile, resolve_output, media_root):
        self.db, self.get_job, self.get_profile = db, get_job, get_profile
        self.resolve_output, self.media_root = resolve_output, Path(media_root).resolve()

    def posted_keys(self, c, profile):
        # An accepted upload is conservatively excluded even before AID arrives.
        rows = c.execute('''SELECT p.identified_title FROM publish_jobs p
            LEFT JOIN automation_runs r ON r.id=p.automation_run_id
            LEFT JOIN song_projects s ON s.id=p.song_project_id
            WHERE (r.profile_id=? OR s.broadcaster_key=? OR p.streamer=?)
            AND (p.bililive_task_id IS NOT NULL AND p.bililive_task_id!=''
                 OR p.aid IS NOT NULL AND p.aid!='' OR p.bvid IS NOT NULL AND p.bvid!=''
                 OR p.status='completed')''',
            (profile['id'], broadcaster_key(profile), profile.get('publish_streamer') or profile['name']))
        return {normalized_title(r[0]) for r in rows if r[0]}

    def create(self, profile_id, project_ids, enqueue_publish=False):
        if not project_ids or len(project_ids) > 200 or len(set(project_ids)) != len(project_ids):
            raise ValueError('请选择 1–200 个互不重复的原项目')
        profile = self.get_profile(profile_id)
        if (profile.get('style') or {}).get('effect') != 'folia-native':
            raise ValueError('主播规则需要配置 Folia 原生效果')
        projects = [self.get_job(jid) for jid in project_ids]
        batch = uuid.uuid4().hex
        now = time.time()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            origins = {s['project_id'] for r in c.execute('SELECT songs FROM automation_runs WHERE profile_id=?', (profile_id,))
                       for s in json.loads(r[0] or '[]') if s.get('project_id')}
            posted = self.posted_keys(c, profile)
            seen = set()
            for j in projects:
                al, out = j.get('alignment') or {}, j.get('output') or {}
                key = normalized_title(j.get('identified_title'))
                source = (self.media_root / j['source']).resolve()
                if j['id'] not in origins or j.get('render_revision_parent_id'):
                    raise ValueError('项目不属于所选主播的原自动成片')
                if j['status'] != 'completed' or out.get('sample') is not False or not key:
                    raise ValueError('项目必须是有权威歌曲身份的完整成片')
                if key in posted or key in seen:
                    raise ValueError('已投稿歌曲或重复歌曲不能加入重制')
                if (al.get('timeline_match') or {}).get('song_identity_suspicious') or not al.get('lines'):
                    raise ValueError('歌曲身份可疑或缺少缓存歌词时间轴')
                if not self.resolve_output(out.get('path') or '').is_file() or not source.is_file() or self.media_root not in source.parents:
                    raise ValueError('原成片或源切片不存在或超出媒体范围')
                if c.execute("SELECT 1 FROM render_revisions WHERE source_job_id=? AND status IN ('pending','running')", (j['id'],)).fetchone():
                    raise ValueError('这个项目已有未完成的重制任务')
                seen.add(key)
            # Snapshot raw columns; never reconstruct identity from display title or lyric metadata.
            columns = [r[1] for r in c.execute('PRAGMA table_info(jobs)')]
            for j in projects:
                raw = dict(c.execute('SELECT * FROM jobs WHERE id=?', (j['id'],)).fetchone())
                jid = uuid.uuid4().hex
                style = copy.deepcopy(j['style'] if j['style'].get('effect') == 'folia-native' else profile['style'])
                style['folia'] = style.get('folia') or {}
                style['folia']['keep_alpha_mov'] = False
                raw.update(id=jid, created_at=now, updated_at=now, status='queued', error='', output=None,
                           style=json.dumps(style, ensure_ascii=False), render_revision_parent_id=j['id'], render_revision_batch_id=batch,
                           render_revision_publish=int(enqueue_publish))
                c.execute('INSERT INTO jobs('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')', tuple(raw[k] for k in columns))
                c.execute('INSERT INTO render_revisions(job_id,batch_id,source_job_id,profile_id,status,created_at,updated_at,publish_status) VALUES(?,?,?,?,?,?,?,?)',
                          (jid, batch, j['id'], profile_id, 'pending', now, now, 'pending' if enqueue_publish else 'not_requested'))
            c.commit()
        return {'batch_id': batch, 'count': len(projects), 'output_mode': 'smooth', 'keep_mov': False, 'enqueue_publish': enqueue_publish}

    def items(self, batch_id=None):
        with self.db() as c:
            rows = c.execute('SELECT * FROM render_revisions'+(' WHERE batch_id=?' if batch_id else '')+' ORDER BY created_at, rowid', (batch_id,) if batch_id else ()).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            j = self.get_job(item['job_id'])
            item.update(title=j.get('identified_title'), output=j.get('output'), project_status=j['status'])
            items.append(item)
        return {'items': items, 'counts': dict(Counter(item['status'] for item in items))}

    def set_status(self, jid, status, error=''):
        with self.db() as c:
            c.execute('UPDATE render_revisions SET status=?,error=?,updated_at=? WHERE job_id=?', (status, error, time.time(), jid))
            c.commit()

    def next_item(self):
        with self.db() as c:
            row = c.execute("SELECT * FROM render_revisions WHERE status IN ('running','pending') ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END,priority_at DESC,created_at,rowid LIMIT 1").fetchone()
        return dict(row) if row else None

    def publish_next(self, handoff):
        with self.db() as c:
            row=c.execute("SELECT * FROM render_revisions WHERE status='completed' AND publish_status='pending' ORDER BY priority_at DESC,created_at,rowid LIMIT 1").fetchone()
        if not row: return
        item=dict(row)
        try:
            published=handoff(item)
        except Exception as exc:
            # A publish hand-off error is independent of the completed MP4 and can be retried explicitly.
            with self.db() as c:
                c.execute("UPDATE render_revisions SET publish_status='failed',publish_error=?,updated_at=? WHERE job_id=?",(safe_error(exc),time.time(),item['job_id']))
            raise
        with self.db() as c:
            c.execute('UPDATE render_revisions SET publish_status=?,publish_error=?,updated_at=? WHERE job_id=?',
                      ('enqueued' if published else 'ineligible','' if published else '未满足高置信、歌曲身份或主播模板条件',time.time(),item['job_id']))

    def execute(self, item, render, resume):
        jid = item['job_id']
        job = self.get_job(jid)
        with self.db() as c:
            posted = self.posted_keys(c, self.get_profile(item['profile_id']))
        if normalized_title(job.get('identified_title')) in posted:
            self.set_status(jid, 'skipped', '这首歌曲已接受投稿，跳过重制')
            return False
        self.set_status(jid, 'running')
        if job['status'] == 'completed' and (job.get('output') or {}).get('output_mode') == 'smooth':
            self.set_status(jid, 'completed')
            return True
        if (job.get('output') or {}).get('render_id'):
            resume(jid)  # Never start a second renderer for a durable render ID.
        else:
            render(jid)
        job = self.get_job(jid)
        output=job.get('output') or {}; path=Path(output.get('path') or '')
        if job['status'] != 'completed' or output.get('output_mode')!='smooth' or path.suffix.lower()!='.mp4' or not path.is_file() or not path.stat().st_size:
            raise RuntimeError(job.get('error') or '逐帧重制没有成功输出 MP4')
        self.set_status(jid, 'completed')
        return True
