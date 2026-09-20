import unittest
from pathlib import Path
from unittest.mock import patch

import app


def hit(title, score=100):
    return {"title": title, "artist": "歌手", "score": score, "song_id": title}


class AcrcloudRecheckTest(unittest.TestCase):
    @patch.object(app, "ACRCLOUD_ACCESS_KEY", "key")
    @patch.object(app, "ACRCLOUD_ACCESS_SECRET", "secret")
    @patch.object(app, "ACRCLOUD_HOST", "example.invalid")
    @patch("app.acrcloud_identify_window_result")
    def test_fast_path_stops_at_first_hit_and_low_confidence_recheck_continues(self, identify):
        identify.side_effect = [
            {"hit": hit("有你相随"), "status": "hit", "error": ""},
            {"hit": hit("爱你不是两三天", 92), "status": "hit", "error": ""},
            {"hit": None, "status": "error", "error": "Timeout: probe timed out"},
            {"hit": hit("爱你不是两三天", 96), "status": "hit", "error": ""},
        ]

        first, trace = app.identify_song_acrcloud(Path("clip.mp4"), 120000, {})

        self.assertEqual(first["title"], "有你相随")
        self.assertEqual(identify.call_count, 1)
        consensus, trace = app.recheck_song_acrcloud(Path("clip.mp4"), 120000, trace, {})
        self.assertEqual(consensus["title"], "爱你不是两三天")
        self.assertEqual(consensus["agreement_count"], 2)
        self.assertEqual(identify.call_count, 4)
        self.assertEqual([row["offset_ms"] for row in trace["windows"]], [0, 25000, 50000, 75000])
        self.assertEqual(trace["windows"][2]["status"], "error")
        self.assertIn("Timeout", trace["windows"][2]["error"])


if __name__ == "__main__":
    unittest.main()
