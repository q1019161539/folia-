"""Read-only identity bridge to bililive-tools recording history."""
import json
import sqlite3
import threading
import time
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path, PurePosixPath

_lock = threading.Lock()
_cached = (0, [])


def recording_start_time(source, identity=None, database='/recorder-data/app.db'):
    """Read recording start (milliseconds), never file mtime or render time.

    BililiveTool history retains .flv after conversion to .mp4; match only the
    exact relative directory/stem and known recording extensions. Missing history
    falls back to the recorder's YYYY-MM-DD/HH-mm-ss_name path, in Shanghai time.
    """
    path = PurePosixPath(str(source or '').replace('\\', '/'))
    if path.is_absolute() or '..' in path.parts or len(path.parts) < 3 or path.suffix.lower() != '.mp4':
        raise ValueError('原录播路径无效，无法确定录播开始时间')
    filenames = ['/app/video/' + str(path.with_suffix(extension)) for extension in ('.mp4', '.flv', '.ts', '.mkv')]
    query = ('SELECT h.record_start_time FROM record_history h JOIN streamer s ON s.id=h.streamer_id '
             'WHERE h.video_file IN (?,?,?,?)')
    values = list(filenames)
    identity = identity or {}
    if identity.get('platform') and identity.get('room_id'):
        query += ' AND lower(s.platform)=? AND CAST(s.room_id AS TEXT)=?'
        values += [str(identity['platform']).lower(), str(identity['room_id'])]
    rows = []
    try:
        with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as c:
            rows = c.execute(query, values).fetchall()
    except (sqlite3.Error, OSError):
        pass  # Recorder history may not exist for legacy recordings.
    timestamps = set()
    for row in rows:
        try:
            value = int(row[0])
            if value > 0:
                started = datetime.fromtimestamp(value / 1000, ZoneInfo('Asia/Shanghai'))
                if 2000 <= started.year <= 2100:
                    timestamps.add(value)
        except (ValueError, TypeError, OverflowError, OSError):
            continue
    if len(timestamps) > 1:
        raise ValueError('同一原录播有多个不同开始时间，请人工核对')
    if timestamps:
        return datetime.fromtimestamp(next(iter(timestamps)) / 1000, ZoneInfo('Asia/Shanghai'))
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.parent.name) and re.match(r'^\d{2}-\d{2}-\d{2}(?:_|$)', path.stem):
        try:
            started = datetime.strptime(path.parent.name + ' ' + path.stem[:8], '%Y-%m-%d %H-%M-%S')
            if 2000 <= started.year <= 2100:
                return started.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        except ValueError:
            pass
    raise ValueError('缺少可靠的录播开始时间，请核对录播记录或原文件日期/时间命名')


def recorder_catalog(database):
    global _cached
    with _lock:
        if time.monotonic() - _cached[0] < 30:
            return _cached[1]
        try:
            with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as c:
                streamers = c.execute('SELECT id,name,room_id,platform FROM streamer').fetchall()
                recordings = c.execute('SELECT streamer_id,video_file FROM record_history ORDER BY id DESC').fetchall()
            entries = {sid: {'name': name, 'platform': str(platform).lower(), 'room_id': str(room), 'paths': []} for sid, name, room, platform in streamers}
            for sid, filename in recordings:
                # Accept only the recorder's known container media prefix.
                if sid not in entries or not str(filename).startswith('/app/video/'):
                    continue
                parts = PurePosixPath(str(filename)[len('/app/video/'):]).parts
                if len(parts) < 2 or any(p in ('.', '..') for p in parts) or parts[0] == '歌曲切片':
                    continue
                aliases = entries[sid]['paths']
                if parts[0] not in aliases:
                    aliases.append(parts[0])
            result = list(entries.values())
        except (sqlite3.Error, OSError):
            result = []
        _cached = (time.monotonic(), result)
        return result


def bind_identity(path, name, saved, catalog):
    try:
        identity = json.loads(saved or '{}')
    except (ValueError, TypeError):
        identity = {}
    if identity.get('room_id'):
        matches = [e for e in catalog if e['platform'] == identity.get('platform') and e['room_id'] == identity['room_id']]
    else:
        matches = [e for e in catalog if path in e['paths'] or path == e['name'] or name == e['name']]
    if len(matches) == 1:
        entry = matches[0]
        paths = list(dict.fromkeys(entry['paths'] + identity.get('paths', []) + [path]))
        return {'platform': entry['platform'], 'room_id': entry['room_id'], 'paths': paths}
    return identity


def profile_paths(profile, media):
    paths = profile.get('recorder_identity', {}).get('paths', []) + [profile['path']]
    roots = []
    for relative in dict.fromkeys(paths):
        root = (media / relative).resolve()
        if root != media.resolve() and media.resolve() in root.parents and root.is_dir():
            roots.append(root)
    return roots


def broadcaster_choices(folders, catalog):
    result = []
    consumed = set()
    for entry in catalog:
        aliases = [p for p in entry['paths'] if any(f['path'] == p for f in folders)]
        # Do not attribute a shared directory to either identity.
        aliases = [p for p in aliases if sum(p in e['paths'] for e in catalog) == 1]
        if not aliases:
            continue
        path = aliases[0]
        result.append({'name': path, 'path': path, 'room_id': entry['room_id'], 'platform': entry['platform']})
        consumed.update(aliases)
    result.extend(f for f in folders if f['path'] not in consumed)
    return sorted(result, key=lambda e: e['name'].casefold())
