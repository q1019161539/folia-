import re
import sqlite3
import unittest
from pathlib import Path

from song_identity import (
    IDENTITY_SOURCES,
    backfill_identity,
    identity_fields,
    matched_candidate_fields,
    resolve_search_identity,
)

APP = Path(__file__).with_name("app.py").read_text(encoding="utf-8")


class IdentityOwnershipTest(unittest.TestCase):
    """《夏天的风》 was renamed 《夏日の風》 by the lyric sheet that matched it, the
    next run searched under that name, and the song's verbatim releases became
    unreachable. An audit of 46 songs found 21 identities rewritten this way."""

    def test_identification_stage_writes_identity(self):
        self.assertEqual(
            identity_fields("夏天的风", "温岚", "shazam"),
            {"identified_title": "夏天的风", "identified_artist": "温岚", "identity_source": "shazam"},
        )
        self.assertEqual(identity_fields("  夏天的风  ")["identified_title"], "夏天的风")

    def test_only_recognition_may_name_a_song(self):
        self.assertNotIn("candidate", IDENTITY_SOURCES)
        self.assertNotIn("lyric_candidate", IDENTITY_SOURCES)
        # A human picking a lyric sheet is the same judgement wearing a different
        # hat; letting it name the song would reopen the loop through the manual page.
        self.assertNotIn("manual", IDENTITY_SOURCES)
        for source in ("candidate", "manual", "user"):
            with self.assertRaises(ValueError):
                identity_fields("夏日の風", "", source)

    def test_manual_song_choice_never_writes_identity(self):
        choose = APP.split("def choose_song", 1)[1].split("@app.post", 1)[0]
        self.assertNotIn("title=body.title", choose)
        self.assertNotIn("artist=body.artist", choose)
        self.assertIn("matched_candidate_fields", choose)

    def test_candidate_details_are_reported_not_applied(self):
        fields = matched_candidate_fields(
            {"title": "夏日の風", "artist": "Landy Wen", "album": "溫式效應",
             "platform": "lrclib", "candidate_id": "lrclib:11087520"})
        self.assertEqual(fields["matched_title"], "夏日の風")
        self.assertEqual(fields["matched_candidate_id"], "lrclib:11087520")
        self.assertNotIn("title", fields)
        self.assertNotIn("identified_title", fields)


class SearchIdentityTest(unittest.TestCase):
    def test_search_uses_identified_name_even_when_display_title_drifted(self):
        job = {"title": "夏日の風", "artist": "Landy Wen",
               "identified_title": "夏天的风", "identified_artist": "温岚", "identity_source": "deepseek"}
        identity = resolve_search_identity(job)
        self.assertEqual(identity["title"], "夏天的风")
        self.assertEqual(identity["artist"], "温岚")
        self.assertEqual(identity["source"], "deepseek")

    def test_old_job_falls_back_but_says_so(self):
        identity = resolve_search_identity({"title": "夏日の風", "artist": "Landy Wen"})
        self.assertEqual(identity["title"], "夏日の風")
        self.assertEqual(identity["source"], "legacy_fallback")

    def test_backfill_only_from_a_recoverable_original(self):
        job = {"id": "j1", "title": "夏日の風", "identified_title": ""}
        recovered = backfill_identity(job, {"title": "夏天的风"})
        self.assertEqual(recovered["identified_title"], "夏天的风")
        self.assertEqual(recovered["identity_source"], "automation_history_backfill")

    def test_fingerprint_outranks_the_automation_guess(self):
        """《很任性》 was guessed 人人心 off a misheard chorus and Shazam corrected it.
        Replaying the automation record would reinstate the wrong name."""
        job = {"id": "j1", "title": "很任性 (Live)", "identified_title": ""}
        match = {"song_identity_primary_provider": "shazam", "song_identity_primary_title": "很任性 (Live)"}
        recovered = backfill_identity(job, {"title": "人人心"}, match)
        self.assertEqual(recovered["identified_title"], "很任性 (Live)")
        self.assertEqual(recovered["identity_source"], "shazam")

    def test_automation_guess_is_used_when_no_fingerprint_ran(self):
        job = {"id": "j1", "title": "夏日の風", "identified_title": ""}
        recovered = backfill_identity(job, {"title": "夏天的风"}, {"shazam": None})
        self.assertEqual(recovered["identified_title"], "夏天的风")
        self.assertEqual(recovered["identity_source"], "automation_history_backfill")

    def test_backfill_never_promotes_the_possibly_overwritten_title(self):
        job = {"id": "j1", "title": "夏日の風", "identified_title": ""}
        self.assertIsNone(backfill_identity(job, None))
        self.assertIsNone(backfill_identity(job, {"title": ""}))

    def test_backfill_leaves_an_existing_identity_alone(self):
        job = {"id": "j1", "title": "夏日の風", "identified_title": "夏天的风"}
        self.assertIsNone(backfill_identity(job, {"title": "另一个名字"}))

    def test_switching_candidates_changes_only_matched_fields(self):
        job = {"title": "夏天的风", "identified_title": "夏天的风", "identity_source": "deepseek"}
        before = resolve_search_identity(job)
        first = matched_candidate_fields({"title": "夏日の風", "candidate_id": "lrclib:11087520"})
        second = matched_candidate_fields({"title": "夏天的风", "candidate_id": "qq:140269"})
        self.assertEqual(resolve_search_identity(job), before)
        self.assertNotEqual(first["matched_candidate_id"], second["matched_candidate_id"])


class NoCandidateWriteBackTest(unittest.TestCase):
    """The loop can only come back by a candidate reaching job.title again, so the
    ban is asserted against the source itself rather than only against helpers."""

    def test_auto_timeline_does_not_write_title_or_artist(self):
        self.assertNotIn("title=candidate.get('title')", APP)
        self.assertNotIn("artist=candidate.get('artist')", APP)

    def test_jobs_insert_names_its_columns(self):
        self.assertNotIn("INSERT INTO jobs VALUES(", APP)

    def test_jobs_insert_runs_against_the_migrated_schema(self):
        create = re.search(r"(CREATE TABLE IF NOT EXISTS jobs\(.*?\))'", APP, re.S)
        statement = "".join(re.findall(r"'([^']*)'", re.search(r"JOB_INSERT=\((.*?)\)\n", APP, re.S).group(1)))
        connection = sqlite3.connect(":memory:")
        connection.execute(create.group(1))
        for column in ("identified_title", "identified_artist", "identity_source"):
            connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")
        connection.execute("ALTER TABLE jobs ADD COLUMN some_future_column TEXT")
        connection.execute(statement, ("j1", 1.0, 1.0, "song_review", "主播/歌.mp4", "local", "夏天的风", "",
                                       "", "{}", "{}", "", "{}", "夏天的风", "温岚", "deepseek"))
        row = connection.execute("SELECT title,identified_title,identity_source FROM jobs").fetchone()
        self.assertEqual(row, ("夏天的风", "夏天的风", "deepseek"))

    def test_candidate_search_starts_from_the_identified_name(self):
        collect = APP.split("async def collect_standard_timeline_candidates", 1)[1][:600]
        self.assertIn("resolve_search_identity(j)", collect)
        self.assertNotIn("title=str(j.get('title')", collect)


class HeavyWorkShareOneSlotTest(unittest.TestCase):
    """render_lock only ever answered "is another render running". On 2026-09-19
    this box stopped answering ping and had to be power-cycled with an ASR and a
    render overlapping on 15 GiB -- two locks each believing themselves safe."""

    def test_rendering_waits_for_the_same_slot_as_the_models(self):
        body = APP.split("def render_task(", 1)[1].split("def render_task_locked", 1)[0]
        self.assertIn("heavy_ai_slot(", body)
        self.assertIn("render_task_locked(", body)

    def test_the_render_body_no_longer_owns_the_lock_itself(self):
        body = APP.split("def render_task_locked(", 1)[1].split("@app.post('/api/jobs/{jid}/preview-video')", 1)[0]
        self.assertNotIn("render_lock.release()", body)
        self.assertNotIn("render_lock.acquire", body)

    def test_every_heavy_stage_names_the_same_slot(self):
        for marker in ("整场 ASR：", "逐字对齐：", "手动识别：", "渲染：", "人声分离重识别："):
            self.assertIn(marker, APP, marker)


class StandardTimelineIsFinalTest(unittest.TestCase):
    """A standard lyric row is finished the moment it is shifted. 《身骑白马》 carried
    ASR evidence on 2 of its 31 rows, and forced alignment still rewrote every box:
    《放下西凉 没人管》 went from the sheet's 6585ms to 3520ms while 《我一心只想 王宝钏》
    went from 9152ms to 12160ms -- rows the sheet itself had spaced evenly."""

    def test_forced_alignment_skips_rows_that_already_have_a_standard_timeline(self):
        stage = APP.split("def force_align_task_locked", 1)[1].split("if not candidates and not preserved", 1)[0]
        self.assertIn("fixed=has_standard_timeline(line)", stage)
        guard = stage.split("fixed=has_standard_timeline(line)", 1)[1].split("reliable_asr=", 1)[0]
        self.assertIn("if fixed:", guard)
        self.assertIn("preserved+=1; continue", guard)

    def test_the_widened_windows_for_standard_rows_are_gone(self):
        """1200/2500ms windows only ever existed to realign standard rows."""
        stage = APP.split("def force_align_task_locked", 1)[1].split("if not candidates and not preserved", 1)[0]
        self.assertNotIn("1200 if reliable_asr else 2500", stage)

    def test_a_standard_row_never_has_its_box_rewritten(self):
        write_back = APP.split("lines[index]['words']=words; lines[index]['anchors']=words", 1)[1][:400]
        self.assertIn("lines[index]['start_ms']=words[0]['start_ms']", write_back)
        stage = APP.split("def force_align_task_locked", 1)[1].split("if not candidates and not preserved", 1)[0]
        self.assertIn("'fixed_timeline':False", stage)


if __name__ == "__main__":
    unittest.main()
