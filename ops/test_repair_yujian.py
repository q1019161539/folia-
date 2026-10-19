"""Offline safety checks for the explicit maintenance operation."""
import copy
import importlib.util
from pathlib import Path
import sqlite3
import unittest

spec=importlib.util.spec_from_file_location('repair',Path(__file__).with_name('repair-yujian-lyrics-and-repost.py'))
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)


class RepairChecks(unittest.TestCase):
    def setUp(self):
        self.good={'timing_confidence':'high','word_bootstrap_status':'accepted','shift_source':'word',
            'cross_model_conflict':False,'word_anchor_span_ms':155648,'word_anchor_lines':7,
            'word_anchor_count':54,'word_residual_p90_ms':266,'word_vs_line_shift_diff_ms':13}

    def test_valid_word_evidence(self): repair.assert_quality(self.good)

    def test_bad_old_axis_rejected(self):
        bad=copy.deepcopy(self.good);bad.update(timing_confidence='low',cross_model_conflict=True,
            word_residual_p90_ms=5435,word_vs_line_shift_diff_ms=5115)
        with self.assertRaises(AssertionError):repair.assert_quality(bad)

    def test_missing_quality_cannot_pass(self):
        bad=copy.deepcopy(self.good);del bad['timing_confidence']
        with self.assertRaises(KeyError):repair.assert_quality(bad)

    def test_each_safety_condition(self):
        for key,value in [('timing_confidence','low'),('word_bootstrap_status','far_from_line_shift'),
            ('shift_source','line'),('cross_model_conflict',True),('word_anchor_span_ms',48000),
            ('word_anchor_lines',4),('word_anchor_count',33),('word_residual_p90_ms',400),
            ('word_vs_line_shift_diff_ms',100)]:
            with self.subTest(key=key):
                bad=copy.deepcopy(self.good);bad[key]=value
                with self.assertRaises(AssertionError):repair.assert_quality(bad)

    def test_stable_distinct_operation_ids(self):
        self.assertEqual(len(repair.NEW_JOB),32);self.assertEqual(len(repair.NEW_PUBLISH),32)
        self.assertNotEqual(repair.NEW_JOB,repair.SOURCE)
        self.assertNotEqual(repair.NEW_PUBLISH,repair.OLD_PUBLISH)

    def test_atomic_master_transfer_preserves_old_result(self):
        c=sqlite3.connect(':memory:')
        c.execute('CREATE TABLE publish_jobs(id TEXT PRIMARY KEY,song_project_id TEXT,status TEXT,task TEXT,bvid TEXT,payload TEXT)')
        c.execute('CREATE UNIQUE INDEX one_master ON publish_jobs(song_project_id) WHERE song_project_id IS NOT NULL')
        c.execute('CREATE TABLE song_projects(id TEXT PRIMARY KEY,publish_job_id TEXT)')
        c.execute("INSERT INTO publish_jobs VALUES('old','song','completed','old-task','old-bv','old-payload')")
        c.execute("INSERT INTO publish_jobs VALUES('new',NULL,'preparing',NULL,NULL,'new-payload')")
        c.execute("INSERT INTO song_projects VALUES('song','old')");c.commit()
        with c:
            c.execute("UPDATE publish_jobs SET song_project_id=NULL WHERE id='old'")
            c.execute("UPDATE publish_jobs SET song_project_id='song',status='ready' WHERE id='new'")
            c.execute("UPDATE song_projects SET publish_job_id='new' WHERE id='song'")
        self.assertEqual(c.execute("SELECT status,task,bvid,payload FROM publish_jobs WHERE id='old'").fetchone(),
                         ('completed','old-task','old-bv','old-payload'))
        self.assertEqual(c.execute("SELECT count(*) FROM publish_jobs WHERE song_project_id='song'").fetchone()[0],1)


if __name__=='__main__':unittest.main()
