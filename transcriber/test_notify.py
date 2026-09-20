import json
import os
import unittest
from unittest.mock import patch

from app.notify import MAX_NOTIFICATION_BYTES, automation_notification, notify_wecom


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return json.dumps(self.payload).encode("utf-8")


def song(title, level="normal", reasons=None, state="completed", reason=None):
    return {"title": title, "review_level": level, "review_reasons": reasons or [],
            "state": state, "reason": reason}


class OutputsNotificationTests(unittest.TestCase):
    def base(self, songs, **extra):
        payload = {"event": "outputs_completed", "broadcaster": "小红泡", "recording": "2026-09-17",
                   "completed_count": sum(1 for s in songs if s["state"] == "completed"),
                   "failed_count": sum(1 for s in songs if s["state"] == "failed"),
                   "skipped_count": sum(1 for s in songs if s["state"] == "skipped"),
                   "songs": songs, "output_path": "/output/2026-09-17"}
        payload.update(extra)
        return automation_notification(payload)

    def test_a_recording_without_songs_still_says_so(self):
        """The pipeline used to return early here and send nothing, leaving
        "transcribing done" as the last word -- unreadable against a hung run."""
        _, content = self.base([], output_path="")
        self.assertIn("🔇 本场未检出歌曲", content)
        self.assertIn("结果：成功 0｜失败 0｜跳过 0", content)
        self.assertNotIn("✅ 其余", content)

    def test_the_no_songs_line_stays_out_of_a_normal_run(self):
        _, content = self.base([song("歌一"), song("歌二")])
        self.assertNotIn("未检出歌曲", content)

    def test_normal_songs_are_counted_not_listed(self):
        # A dozen healthy songs listed by name would bury the one that needs
        # opening, which is the whole point of the message.
        _, content = self.base([song(f"歌{i}") for i in range(12)])
        self.assertIn("✅ 其余 12 首未发现明显风险", content)
        self.assertNotIn("歌7", content)

    def test_a_song_needing_attention_is_named_with_its_reason(self):
        _, content = self.base([
            song("胭脂妆", "critical", [{"code": "timing_model_conflict",
                                        "facts": {"model_delta_ms": 2234}}]),
            song("香水有毒"),
        ])
        self.assertIn("🔴 优先检查 1 首", content)
        self.assertIn("《胭脂妆》", content)
        self.assertIn("两套时间轴结果相差约 2.2 秒", content)

    def test_a_wrong_song_name_says_both_names(self):
        _, content = self.base([
            song("风花雪月", "critical", [{"code": "song_identity_suspicious", "facts": {
                "primary_title": "风花雪月", "lyric_title": "黯然销魂"}}]),
        ])
        self.assertIn("识别为《风花雪月》，歌词更像《黯然销魂》", content)

    def test_weak_evidence_is_explained_in_plain_numbers(self):
        _, content = self.base([
            song("离人赋", "warning", [{"code": "weak_anchor_evidence",
                                       "facts": {"anchor_count": 3, "anchor_span_ms": 116100}}]),
        ])
        self.assertIn("仅 3 处可靠对应，覆盖约 116 秒", content)
        self.assertNotIn("mad", content.lower())

    def test_raw_measurements_never_reach_the_reader(self):
        _, content = self.base([
            song("某首", "warning", [{"code": "anchor_consistency_poor", "facts": {"mad_ms": 1065}}]),
        ])
        self.assertIn("时间轴一致性较差", content)
        self.assertNotIn("1065", content)

    def test_songs_that_produced_nothing_say_why(self):
        _, content = self.base([
            song("太短的歌", state="skipped", reason="clip_too_short"),
            song("炸了的歌", state="failed", reason="render_failed"),
        ])
        self.assertIn("⏭ 未产出 2 首", content)
        self.assertIn("切片时长过短，已跳过", content)
        self.assertIn("成片生成失败", content)

    def test_trimming_keeps_the_problems_and_the_directory(self):
        # Forty songs with long names would blow the budget. What must survive
        # is the header, the 🔴 block and the output directory -- a plain slice
        # of the finished string would cut exactly those from the tail.
        songs = [song("风花雪月", "critical", [{"code": "song_identity_suspicious", "facts": {
            "primary_title": "风花雪月", "lyric_title": "黯然销魂"}}])]
        songs += [song("很长很长的歌名" * 6, "warning",
                       [{"code": "anchor_consistency_poor", "facts": {}}]) for _ in range(40)]
        _, content = self.base(songs)
        self.assertLessEqual(len(content.encode("utf-8")), MAX_NOTIFICATION_BYTES)
        self.assertIn("🔴 优先检查", content)
        self.assertIn("《风花雪月》", content)
        self.assertIn("/output/2026-09-17", content)

    def test_deepseek_is_no_longer_mentioned(self):
        # The old template told the reader a song had been "AI 辅助对齐" whenever
        # local confidence was low -- inferred, never observed, and wrong ever
        # since the full-song realign was switched off.
        _, content = self.base([song("某首", "warning",
                                     [{"code": "weak_anchor_evidence", "facts": {}}])])
        self.assertNotIn("DeepSeek", content)
        self.assertNotIn("AI", content)


class StageNotificationTests(unittest.TestCase):
    def test_start_says_how_long_the_recording_is_and_when_asr_should_end(self):
        _, content = automation_notification({
            "event": "asr_started", "broadcaster": "小红泡", "recording": "2026-09-17",
            "audio_duration_sec": 7980,
            "asr_eta": {"reliable": True, "low_seconds": 1800, "high_seconds": 2700},
        })
        self.assertIn("录播时长：2 小时 13 分", content)
        self.assertIn("预计转写完成：约", content)
        self.assertIn("～", content)

    def test_an_unreliable_estimate_says_so_rather_than_inventing_one(self):
        _, content = automation_notification({
            "event": "asr_started", "broadcaster": "小红泡", "recording": "x",
            "audio_duration_sec": 3600, "asr_eta": {"reliable": False, "sample_count": 2},
        })
        self.assertIn("历史样本不足", content)

    def test_queue_notice_explains_that_nothing_is_stuck(self):
        _, content = automation_notification({
            "event": "render_queue_waiting", "broadcaster": "小红泡", "recording": "x",
            "song_title": "红色高跟鞋", "completed_count": 4, "total_count": 11,
            "wait_seconds": 125,
        })
        self.assertIn("已完成 4 / 11 首", content)
        self.assertIn("《红色高跟鞋》", content)
        self.assertIn("已等待：2 分钟", content)
        self.assertIn("没有卡住", content)

    def test_clips_notice_lists_only_the_failures(self):
        _, content = automation_notification({
            "event": "clips_completed", "broadcaster": "小红泡", "recording": "x",
            "completed_count": 13, "failed_count": 1, "failed_titles": ["某首歌"],
            "elapsed_seconds": 108,
        })
        self.assertIn("成功 13，失败 1", content)
        self.assertIn("失败：某首歌", content)
        self.assertIn("切片耗时：1 分钟", content)

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(ValueError):
            automation_notification({"event": "something_else"})


class WeComDeliveryTests(unittest.TestCase):
    @patch.dict(os.environ, {"WECOM_WEBHOOK_URL": "https://example.invalid/hook"})
    @patch("app.notify.time.sleep")
    @patch("app.notify.urlopen")
    def test_http_200_with_wecom_error_is_retried_and_reported(self, mocked_open, _sleep):
        mocked_open.return_value = FakeResponse({"errcode": 93000, "errmsg": "robot has been stopped"})

        result = notify_wecom("标题", "正文")

        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"], 3)
        self.assertIn("93000", result["error"])
        self.assertEqual(mocked_open.call_count, 3)

    @patch.dict(os.environ, {"WECOM_WEBHOOK_URL": "https://example.invalid/hook"})
    @patch("app.notify.urlopen")
    def test_wecom_success_is_returned_after_one_attempt(self, mocked_open):
        mocked_open.return_value = FakeResponse({"errcode": 0, "errmsg": "ok"})

        result = notify_wecom("标题", "正文")

        self.assertEqual(result, {"ok": True, "status": "sent", "attempts": 1})
        self.assertEqual(mocked_open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
