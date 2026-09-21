import tempfile
import unittest
from pathlib import Path

from recording_metadata import copy_recording_metadata_sidecar


class RecordingMetadataSidecarTest(unittest.TestCase):
    def test_clip_gets_small_metadata_sidecar_with_original_recording_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "11-10-43_直播.mp4"
            source.touch()
            source.with_suffix(".xml").write_text(
                '<?xml version="1.0"?><i><metadata>\n'
                "<platform>Bilibili</platform>\n"
                "<video_start_time>1789873845703</video_start_time>\n"
                "<room_title>直播标题</room_title>\n"
                "<user_name>主播</user_name>\n"
                "<room_id>2516117</room_id>\n"
                "</metadata><d>不会复制的弹幕</d></i>",
                encoding="utf-8",
            )
            clip = root / "歌曲切片" / "甜蜜配方.mp4"
            clip.parent.mkdir()
            clip.touch()

            target = copy_recording_metadata_sidecar(source, clip)

            self.assertEqual(target, clip.with_suffix(".xml"))
            content = target.read_text(encoding="utf-8")
            self.assertIn("<video_start_time>1789873845703</video_start_time>", content)
            self.assertIn("<room_id>2516117</room_id>", content)
            self.assertNotIn("不会复制的弹幕", content)

    def test_missing_source_xml_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "recording.mp4"
            source.touch()
            clip = root / "clip.mp4"
            clip.touch()
            self.assertIsNone(copy_recording_metadata_sidecar(source, clip))
            self.assertFalse(clip.with_suffix(".xml").exists())


if __name__ == "__main__":
    unittest.main()
