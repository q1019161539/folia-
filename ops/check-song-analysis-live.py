"""Read-only acceptance: use cached whole ASR, never enqueue clips or uploads."""
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, '/tmp/folia-song-analysis-check')
sys.path.append('/app')
from song_analysis import SongAnalysisClient, SongAnalysisError

c = sqlite3.connect('file:/data/studio.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
row = c.execute('SELECT id,source,transcript FROM automation_runs WHERE id=?',
                ('6b5a474cf0ee48b59fe72587d135bdf7',)).fetchone()
assert row and row['transcript'], 'Cached whole ASR missing'
segments = json.loads(row['transcript'])
assert segments and all(isinstance(s, dict) and 'segment_id' in s for s in segments)
client = SongAnalysisClient()
print(json.dumps({'mode': 'read-only-analysis', 'source_run': row['id'],
                  'segments': len(segments), 'config': client.public_config()}, ensure_ascii=False), flush=True)
started = time.monotonic()
try:
    accepted, skipped, record = client.detect(segments, .8)
    result = {'source_run': row['id'], 'read_only': True, 'accepted': accepted, 'skipped': skipped,
              'analysis': record, 'elapsed_seconds': round(time.monotonic()-started, 3)}
    Path('/tmp/folia-song-analysis-check/live-result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'accepted': len(accepted), 'skipped': len(skipped),
                      'titles': [s['title'] for s in accepted], 'analysis': record,
                      'elapsed_seconds': result['elapsed_seconds']}, ensure_ascii=False), flush=True)
    if record['fallback_used']:
        raise SystemExit(2)
except SongAnalysisError as exc:
    print(str(exc), flush=True)
    raise SystemExit(1)
