import json
import tempfile
import unittest
from pathlib import Path
from recorder_identity import bind_identity, profile_paths, broadcaster_choices


class IdentityTests(unittest.TestCase):
    def test_rename_and_preserved_old_directory(self):
        old=[{'name':'旧名','platform':'bilibili','room_id':'123','paths':['旧名']}]
        saved=bind_identity('旧名','旧名','',old)
        new=[{'name':'完全新名','platform':'bilibili','room_id':'123','paths':['完全新名']}]
        bound=bind_identity('旧名','旧名',json.dumps(saved),new)
        self.assertEqual(bound['paths'],['完全新名','旧名'])
        self.assertEqual(bind_identity('旧名','旧名',json.dumps(bound),[]),bound)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in bound['paths']: (root/name).mkdir()
            roots=profile_paths({'path':'旧名','recorder_identity':bound},root)
            self.assertEqual([p.name for p in roots],['完全新名','旧名'])

    def test_ambiguous_directory_does_not_bind(self):
        entries=[{'name':'甲','platform':'bilibili','room_id':str(i),'paths':['共用']} for i in (1,2)]
        self.assertEqual(bind_identity('共用','共用','',entries),{})

    def test_alias_choices_are_deduplicated(self):
        entries=[{'name':'旧名','platform':'bilibili','room_id':'123','paths':['新名','旧名']}]
        choices=broadcaster_choices([{'name':x,'path':x} for x in ['旧名','新名','其他']],entries)
        self.assertEqual(len(choices),2)
        self.assertEqual(next(c for c in choices if c.get('room_id'))['path'],'新名')

    def test_paths_cannot_escape_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'media';root.mkdir()
            self.assertEqual(profile_paths({'path':'../','recorder_identity':{'paths':['/tmp','../']}},root),[])


if __name__=='__main__': unittest.main()
