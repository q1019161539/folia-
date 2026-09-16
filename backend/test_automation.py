import json
import tempfile
import unittest
from pathlib import Path

from automation import automation_transcriber_payload, broadcaster_directories, eligible_recording, parse_ai_json, project_transcript, recording_choices, restore_completed_clip_paths, transcript_segments, validate_detected_songs


class AutomationHelpersTest(unittest.TestCase):
    def test_automatic_asr_disables_vad_without_changing_fixed_chunking(self):
        payload = automation_transcriber_payload("主播/录播.mp4", "auto-run")
        self.assertTrue(payload["no_vad"])
        self.assertEqual(payload["chunk_seconds"], 180)
        self.assertEqual(payload["input"], "主播/录播.mp4")
        self.assertEqual(payload["notification_mode"], "automation")

        resumed = automation_transcriber_payload("主播/录播.mp4", "auto-run", "asr")
        self.assertTrue(resumed["no_vad"])
        self.assertEqual(resumed["input"], "")

    def test_broadcaster_directories_are_dynamic_first_level_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "芒芒_Mou").mkdir()
            (root / "阿蕾蕾Aleilei").mkdir()
            (root / ".cache").mkdir()
            (root / "歌曲切片").mkdir()
            (root / "README.txt").write_text("not a directory", encoding="utf-8")
            self.assertEqual(
                {item["name"] for item in broadcaster_directories(root)},
                {"芒芒_Mou", "阿蕾蕾Aleilei"},
            )

    def test_eligible_recording_filters_type_size_and_clip_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / "主播" / "new.mp4"
            good.parent.mkdir()
            good.write_bytes(b"x" * 20)
            self.assertTrue(eligible_recording(good, root, 10))
            small = root / "主播" / "small.mp4"
            small.write_bytes(b"x")
            self.assertFalse(eligible_recording(small, root, 10))
            clip = root / "主播" / "歌曲切片" / "song.mp4"
            clip.parent.mkdir()
            clip.write_bytes(b"x" * 20)
            self.assertFalse(eligible_recording(clip, root, 10))

    def test_recording_choices_include_old_small_recordings_but_not_song_clips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broadcaster = root / "主播"
            old = broadcaster / "2026-01-01" / "old.mp4"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"old")
            clip = broadcaster / "2026-01-01" / "歌曲切片" / "song.mp4"
            clip.parent.mkdir()
            clip.write_bytes(b"clip")
            partial = broadcaster / "still.partial.mp4"
            partial.write_bytes(b"partial")
            self.assertEqual([item["path"] for item in recording_choices(broadcaster, root)], ["主播/2026-01-01/old.mp4"])

    def test_completed_clip_path_can_be_restored_without_recutting(self):
        songs = [{"title": "歌", "status": "failed", "clip_batch_id": "batch", "clip_name": "歌.mp4", "error": "old"}]
        items = [{"status": "completed", "output_name": "歌.mp4", "internal_path": "/media-output/主播/歌曲切片/歌.mp4"}]
        self.assertEqual(restore_completed_clip_paths(songs, "batch", items), 1)
        self.assertEqual(songs[0]["status"], "clipped")
        self.assertEqual(songs[0]["clip_path"], "/media-output/主播/歌曲切片/歌.mp4")
        self.assertNotIn("error", songs[0])

    def test_parse_fenced_json(self):
        self.assertEqual(parse_ai_json("```json\n{\"songs\": []}\n```")["songs"], [])

    def test_ai_ids_determine_times_and_low_confidence_is_skipped(self):
        segments = transcript_segments([
            {"text": "第一句", "start": 10, "end": 12},
            {"text": "第二句", "start": 70, "end": 72},
            {"text": "第三句", "start": 80, "end": 82},
        ])
        payload = {"songs": [
            {"title": "歌一", "start_segment_id": 0, "end_segment_id": 1, "confidence": .95},
            {"title": "歌二", "start_segment_id": 1, "end_segment_id": 2, "confidence": .5},
        ]}
        accepted, skipped = validate_detected_songs(payload, segments)
        self.assertEqual((accepted[0]["start_ms"], accepted[0]["end_ms"]), (10000, 72000))
        self.assertEqual(len(skipped), 1)

    def test_invalid_and_overlapping_ids_are_rejected(self):
        segments = transcript_segments([
            {"text": "一", "start_ms": 0, "end_ms": 50000},
            {"text": "二", "start_ms": 50000, "end_ms": 100000},
            {"text": "三", "start_ms": 100000, "end_ms": 150000},
        ])
        accepted, skipped = validate_detected_songs({"songs": [
            {"title": "A", "start_segment_id": 0, "end_segment_id": 1, "confidence": .9},
            {"title": "B", "start_segment_id": 1, "end_segment_id": 2, "confidence": .9},
            {"title": "C", "start_segment_id": 9, "end_segment_id": 10, "confidence": .9},
        ]}, segments)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(skipped), 2)

    def test_project_transcript_rebases_rows_and_words(self):
        segments = transcript_segments([
            {"text": "歌词", "start_ms": 10000, "end_ms": 12000, "words": [
                {"word": "歌", "start": 10, "end": 11}, {"word": "词", "start": 11, "end": 12}
            ]}
        ])
        projected = project_transcript(segments, 9000, 13000)
        self.assertEqual((projected[0]["start_ms"], projected[0]["end_ms"]), (1000, 3000))
        self.assertEqual(projected[0]["words"][0]["start_ms"], 1000)


if __name__ == "__main__":
    unittest.main()
