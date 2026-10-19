import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from recorder_identity import recording_start_time


class RecordingTimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/'recorder.db'
        self.source='芒芒_Mou/2026-10-07/23-50-00_标题.mp4'
        self.identity={'platform':'bilibili','room_id':'25984441'}
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE streamer(id INTEGER,platform TEXT,room_id TEXT)')
            c.execute('CREATE TABLE record_history(streamer_id INTEGER,video_file TEXT,record_start_time INTEGER)')
            c.execute('INSERT INTO streamer VALUES(1,?,?)',('bilibili','25984441'))

    def tearDown(self): self.tmp.cleanup()

    def insert(self,started,sid=1):
        with sqlite3.connect(self.db) as c:
            c.execute('INSERT INTO record_history VALUES(?,?,?)',(sid,'/app/video/'+self.source.replace('.mp4','.flv'),int(started.timestamp()*1000)))

    def resolve(self): return recording_start_time(self.source,self.identity,self.db)

    def test_history_milliseconds_and_conversion(self):
        started=datetime(2026,10,7,23,50,9,123000,tzinfo=ZoneInfo('Asia/Shanghai'))
        self.insert(started)
        self.assertEqual(self.resolve(),started)

    def test_filename_when_history_missing(self):
        self.assertEqual(self.resolve().isoformat(),'2026-10-07T23:50:00+08:00')

    def test_read_only_history(self):
        before=self.db.read_bytes(); self.resolve(); self.assertEqual(self.db.read_bytes(),before)

    def test_renamed_streamer_and_wrong_identity(self):
        with sqlite3.connect(self.db) as c: c.execute('INSERT INTO streamer VALUES(2,?,?)',('bilibili','other'))
        self.insert(datetime(2026,10,8,tzinfo=ZoneInfo('Asia/Shanghai')),sid=2)
        self.assertEqual(self.resolve().day,7)

    def test_ambiguous_history_stops(self):
        self.insert(datetime(2026,10,7,23,50,tzinfo=ZoneInfo('Asia/Shanghai')))
        self.insert(datetime(2026,10,8,tzinfo=ZoneInfo('Asia/Shanghai')))
        with self.assertRaisesRegex(ValueError,'多个不同'): self.resolve()

    def test_cross_midnight_never_uses_end_or_mtime(self):
        self.insert(datetime(2026,10,7,23,50,tzinfo=ZoneInfo('Asia/Shanghai')))
        self.assertEqual(self.resolve().strftime('%Y.%m.%d'),'2026.10.07')

    def test_invalid_or_unknown_path_rejected(self):
        for path in ('主播/无日期/video.mp4','主播/2026-02-30/09-00-00_video.mp4','主播/2026-10-07/25-00-00_video.mp4','../主播/2026-10-07/09-00-00_video.mp4','/app/video/主播/2026-10-07/09-00-00_video.mp4'):
            with self.subTest(path=path),self.assertRaises(ValueError): recording_start_time(path,database=self.db)

    def test_missing_db_filename_fallback(self):
        self.assertEqual(recording_start_time(self.source,database=self.db.with_name('missing.db')).isoformat(),'2026-10-07T23:50:00+08:00')
        self.assertFalse(self.db.with_name('missing.db').exists())


if __name__=='__main__': unittest.main()
