import unittest

from pipeline_eta import MIN_SAMPLES, estimate_asr, estimate_songs, per_song_samples, summarize_history


def asr_run(audio_sec, elapsed_sec):
    return {"audio_duration_sec": audio_sec,
            "timings": {"asr_started_at": 1000.0, "asr_finished_at": 1000.0 + elapsed_sec}}


def song_run(count, elapsed_sec, waited_sec=0.0):
    return {"song_count": count, "render_wait_seconds": waited_sec,
            "timings": {"songs_started_at": 500.0, "songs_finished_at": 500.0 + elapsed_sec}}


class EtaTests(unittest.TestCase):
    def test_too_few_samples_says_so_instead_of_guessing(self):
        # The existing 22 runs cannot support an estimate: they only record when
        # a run was created and last touched, which includes time spent queueing
        # behind someone else's render.
        result = estimate_asr(3600, [asr_run(3600, 1800) for _ in range(MIN_SAMPLES - 1)])
        self.assertFalse(result["reliable"])
        self.assertNotIn("low_seconds", result)

    def test_estimate_scales_with_audio_length_not_file_size(self):
        history = [asr_run(3600, 1800) for _ in range(MIN_SAMPLES)]
        one_hour = estimate_asr(3600, history)
        two_hours = estimate_asr(7200, history)
        self.assertTrue(one_hour["reliable"])
        self.assertEqual(one_hour["low_seconds"], 1800)
        self.assertEqual(two_hours["low_seconds"], 3600)

    def test_the_range_runs_from_typical_to_slow(self):
        history = [asr_run(3600, 1200 + 100 * i) for i in range(MIN_SAMPLES)]
        result = estimate_asr(3600, history)
        self.assertLessEqual(result["low_seconds"], result["high_seconds"])
        self.assertGreater(result["high_seconds"], 1200)

    def test_queue_waiting_is_not_counted_as_work(self):
        # Twenty minutes spent waiting for another render to release the lock is
        # not twenty minutes of making this song; counting it would teach the
        # estimator to predict other runs' queues.
        waited = song_run(4, elapsed_sec=2400, waited_sec=1200)
        self.assertEqual(per_song_samples([waited]), [300.0])

    def test_a_run_that_was_only_queueing_contributes_nothing(self):
        self.assertEqual(per_song_samples([song_run(3, elapsed_sec=600, waited_sec=600)]), [])

    def test_song_estimate_needs_the_song_count(self):
        history = [song_run(4, 1200) for _ in range(MIN_SAMPLES)]
        self.assertFalse(estimate_songs(0, history)["reliable"])
        ready = estimate_songs(8, history)
        self.assertTrue(ready["reliable"])
        self.assertEqual(ready["song_count"], 8)
        self.assertEqual(ready["low_seconds"], 2400)

    def test_history_summary_reports_readiness(self):
        self.assertFalse(summarize_history([])["ready"])
        summary = summarize_history([asr_run(3600, 1800) for _ in range(MIN_SAMPLES)])
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["asr_rtf_median"], 0.5)


if __name__ == "__main__":
    unittest.main()
