import unittest
from pathlib import Path
from unittest import mock

from song_identity_diagnostics import WindowResult, format_report, scan_windows


class SongIdentityDiagnosticsTests(unittest.TestCase):
    def test_format_report_lists_every_window_and_a_vote_summary(self):
        rows = [
            WindowResult(0, 30000, shazam_title="值得 (DJ版)", shazam_artist="邰正宵"),
            WindowResult(25000, 55000, shazam_title="在他乡", shazam_artist="汪六六",
                         acrcloud_title="离人赋", acrcloud_artist="云汐", acrcloud_score=95.0),
            WindowResult(50000, 80000, acrcloud_title="离人赋", acrcloud_artist="云汐", acrcloud_score=92.0),
        ]
        report = format_report(rows)
        self.assertIn("值得 (DJ版) - 邰正宵", report)
        self.assertIn("在他乡 - 汪六六", report)
        self.assertIn("离人赋 - 云汐", report)
        self.assertIn("窗口总数: 3", report)
        # The vote summary is what a reader actually judges stability from -- ACRCloud
        # agreeing twice on the same title should show up as a count of 2.
        self.assertIn("'离人赋 - 云汐': 2", report)

    def test_scan_windows_covers_the_whole_clip_without_stopping_at_the_first_hit(self):
        # Test mode per the project's explicit requirement: never "first hit wins"
        # here, unlike production's identify_song_shazam.
        calls = {"shazam": 0, "acrcloud": 0}

        def fake_extract(source, offset_ms, probe_ms, out):
            out.write_bytes(b"fake")
            return True

        def fake_shazam(wav_path):
            calls["shazam"] += 1
            return {"title": "离人赋", "artist": "云汐"}  # every window "hits" -- must still not stop early

        def fake_acrcloud(wav_path, access_key, access_secret, host):
            calls["acrcloud"] += 1
            return {"title": "离人赋", "artist": "云汐", "song_id": "1", "score": 90.0}

        with mock.patch("song_identity_diagnostics._extract_probe_wav", fake_extract), \
             mock.patch("song_identity_diagnostics.shazam_identify", fake_shazam), \
             mock.patch("song_identity_diagnostics.acrcloud_identify", fake_acrcloud):
            rows = scan_windows(Path("fake.mp4"), duration_ms=140_000, acrcloud_creds=("k", "s", "h"))
        # 140s clip, 25s step, 30s probe -> offsets 0,25,50,75,100,115(clamped by max(1,dur-5000)=135000) -> range(0,135000,25000) = [0,25000,...,125000] = 6 offsets
        self.assertEqual(len(rows), 6)
        self.assertEqual(calls["shazam"], 6)
        self.assertEqual(calls["acrcloud"], 6)
        self.assertTrue(all(r.shazam_title == "离人赋" for r in rows))

    def test_scan_windows_records_a_per_window_result_even_when_a_window_fails(self):
        def fake_extract_fails_second_window(source, offset_ms, probe_ms, out):
            return offset_ms == 0  # only the first window's ffmpeg extraction "succeeds"

        with mock.patch("song_identity_diagnostics._extract_probe_wav", fake_extract_fails_second_window), \
             mock.patch("song_identity_diagnostics.shazam_identify", return_value=None), \
             mock.patch("song_identity_diagnostics.acrcloud_identify", return_value=None):
            rows = scan_windows(Path("fake.mp4"), duration_ms=80_000, acrcloud_creds=("k", "s", "h"))
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[1].shazam_error)
        self.assertTrue(rows[1].acrcloud_error)

    def test_scan_windows_without_credentials_skips_acrcloud_but_still_runs_shazam(self):
        with mock.patch("song_identity_diagnostics._extract_probe_wav", lambda *a: True), \
             mock.patch("song_identity_diagnostics.shazam_identify", return_value={"title": "离人赋", "artist": "云汐"}), \
             mock.patch("song_identity_diagnostics.acrcloud_identify") as acr:
            rows = scan_windows(Path("fake.mp4"), duration_ms=30_000, acrcloud_creds=None)
        acr.assert_not_called()
        self.assertEqual(rows[0].shazam_title, "离人赋")
        self.assertEqual(rows[0].acrcloud_title, "")


if __name__ == "__main__":
    unittest.main()
