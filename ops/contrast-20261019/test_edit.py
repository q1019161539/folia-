import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import edit


class EditorialTests(unittest.TestCase):
    def test_bounds_and_runtime(self):
        self.assertEqual(len({s[0] for s in edit.SHOTS}),len(edit.SHOTS))
        self.assertTrue(all(0<=s[2]<s[3] for s in edit.SHOTS))
        self.assertTrue(100<sum(s[3]-s[2] for s in edit.SHOTS)<140)
        ids=[s[0] for s in edit.SHOTS]
        self.assertLess(ids.index('fifteen'),ids.index('five'))
        self.assertLess(ids.index('five'),ids.index('angry'))

    def test_ass_time_and_escape(self):
        self.assertEqual(edit.ass_time(61.239),'0:01:01.24')
        self.assertEqual(edit.ass_time(-1),'0:00:00.00')
        self.assertNotIn('{',edit.clean('{\\pos(1,2)}text'))

    def test_npc_not_labeled_as_streamer(self):
        shot=dict(zip(('id','source','start','end','label','theme'),edit.SHOTS[9]))
        m={'sources':{'C':{'transcript':[{'start':1950.064,'end':1951.944,'text':'凭什么','segment_id':933}]}}}
        with tempfile.TemporaryDirectory() as td,patch.object(edit,'ROOT',Path(td)):
            p=edit.captions(m,shot,9)
            data=p.read_text(encoding='utf-8')
            self.assertIn(',Sister,',data)
            self.assertIn('妹妹：凭什么',data)

    def test_cannot_mutate_started_timeline(self):
        with tempfile.TemporaryDirectory() as td,patch.object(edit,'ROOT',Path(td)):
            (Path(td)/'manifest.json').write_text(json.dumps({'shots':[]}),encoding='utf-8')
            (Path(td)/'00-hook.mkv').touch()
            with self.assertRaises(AssertionError):edit.prepare()


if __name__=='__main__':unittest.main()
