import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.asr import _save_checkpoint, transcribe_chunks
from app.notify import automation_notification
from app.outputs import write_outputs
from app.publish import publish_recording_outputs, publish_song_analysis, recording_output_directory
from app.timestamps import sentence_segments


class TimestampWordTests(unittest.TestCase):
    def test_automation_notifications_include_broadcaster_recording_and_result(self):
        title, content = automation_notification({
            "event": "clips_completed",
            "broadcaster": "芒芒_Mou",
            "recording": "测试录播.mp4",
            "completed_count": 2,
            "failed_count": 1,
            "clips": ["第一首.mp4", "第二首.mp4"],
            "output_path": "/video/歌曲切片",
        })
        self.assertEqual(title, "Folia 自动流程切片完成")
        self.assertIn("主播：芒芒_Mou", content)
        self.assertIn("录播：测试录播.mp4", content)
        self.assertIn("切片：成功 2，失败 1", content)
        self.assertIn("输出目录：/video/歌曲切片", content)

    def test_automation_outputs_completed_notification(self):
        title, content = automation_notification({
            "event": "outputs_completed",
            "broadcaster": "赛蒂娅Sentia",
            "recording": "只唱1h.mp4",
            "completed_count": 2,
            "outputs": ["第一首_folia_overlay.mp4", "第二首_folia_overlay.mp4"],
            "output_path": "/vol1/1000/video/Folia成片/赛蒂娅Sentia/2026-09-14",
        })
        self.assertEqual(title, "Folia 自动流程成品处理完成")
        self.assertIn("成品：成功 2，失败 0，跳过 0", content)
        self.assertIn("第一首_folia_overlay.mp4", content)
        self.assertIn("输出目录：/vol1/1000/video/Folia成片", content)

    def test_recording_outputs_use_broadcaster_date_and_recording_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            internal, work, friendly = root / "jobs" / "opaque-id", root / "work" / "opaque-id", root / "recordings"
            internal.mkdir(parents=True)
            work.mkdir(parents=True)
            (internal / "transcript.txt").write_text("歌词\n", encoding="utf-8")
            job = {"input_relative": "小红泡-管珩心/2026-09-13/11-10-22_【爱唱歌的】傲娇小红帽.mp4"}
            target = publish_recording_outputs(job, internal, work, friendly)
            self.assertEqual(target, recording_output_directory(job["input_relative"], friendly))
            self.assertEqual((target / "11-10-22_【爱唱歌的】傲娇小红帽.txt").read_text(encoding="utf-8"), "歌词\n")

    def test_failed_asr_checkpoint_gets_named_partial_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            internal, work, friendly = root / "jobs" / "id", root / "work" / "id", root / "recordings"
            internal.mkdir(parents=True)
            work.mkdir(parents=True)
            (work / "asr_chunks.json").write_text('[{"text":"第一句"},{"text":"第二句"}]', encoding="utf-8")
            job = {"input_relative": "主播/日期/录播.mp4"}
            target = publish_recording_outputs(job, internal, work, friendly)
            self.assertEqual((target / "录播_未完成.txt").read_text(encoding="utf-8"), "第一句\n第二句\n")

    def test_song_analysis_writes_json_and_clip_parser_compatible_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = {"input_relative": "主播/2026-09-13/录播.mp4"}
            paths = publish_song_analysis(job, {"model": "deepseek-v4-flash", "songs": [{"title": "测试歌", "confidence": .9, "start_ms": 61000, "end_ms": 125000, "start_segment_id": 1, "end_segment_id": 8}], "skipped": []}, root)
            document = __import__("json").loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(document["timestamp_source"], "local-asr-segment-ids")
            self.assertIn("1. 测试歌 00:01:01 - 00:02:05", Path(paths["timeline"]).read_text(encoding="utf-8"))

    def test_asr_checkpoint_is_reused_without_loading_model(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "asr_chunks.json"
            chunk_path = str(Path(directory) / "chunk-0.wav")
            chunks = [{"path": chunk_path, "offset": 12.0, "duration": 3.0}]
            saved = [{"index": 0, "path": chunk_path, "offset": 12.0, "duration": 3.0, "language": "Chinese", "text": "歌词"}]
            _save_checkpoint(checkpoint, saved)
            progress = []
            self.assertEqual(transcribe_chunks(chunks, checkpoint_path=checkpoint, progress=lambda done, total: progress.append((done, total))), saved)
            self.assertEqual(progress, [(1, 1)])

    def test_sentence_segments_preserve_absolute_word_times(self):
        items = [
            SimpleNamespace(text="你", start_time=0.10, end_time=0.35),
            SimpleNamespace(text="好", start_time=0.36, end_time=0.70),
        ]
        rows = sentence_segments(items, offset_seconds=12.5, chunk_index=3)
        self.assertEqual(rows[0]["text"], "你好")
        self.assertEqual(rows[0]["chunk_index"], 3)
        self.assertEqual(rows[0]["words"][0]["start_ms"], 12600)
        self.assertEqual(rows[0]["words"][-1]["end_ms"], 13200)

    def test_write_outputs_adds_segment_ids_and_word_file(self):
        segments = [{
            "start": 1.0,
            "end": 2.0,
            "start_text": "00:00:01.000",
            "end_text": "00:00:02.000",
            "text": "歌词",
            "chunk_index": 1,
            "words": [{"text": "歌", "start_ms": 1000, "end_ms": 1500}],
        }]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_outputs(output, segments, {})
            self.assertIn('"segment_id": 0', (output / "transcript.jsonl").read_text(encoding="utf-8"))
            words = (output / "transcript_words.jsonl").read_text(encoding="utf-8")
            self.assertIn('"timing_source": "qwen-forced-aligner"', words)
            self.assertIn('"start_ms": 1000', words)


if __name__ == "__main__":
    unittest.main()
