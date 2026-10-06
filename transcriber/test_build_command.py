import unittest

from web import build_command


def job(**options):
    base = {"chunk_seconds": 180, "separation_model": "mdx_q", "asr_source": "mix",
            "asr_engine": "local", "skip_separation": True}
    base.update(options)
    return {"input": "/input/主播/歌.mp4", "stage": "all", "run_id": "r1", "options": base}


class BuildCommandTest(unittest.TestCase):
    """main.py defaults to skipping separation, so omitting the flag is not the
    same as asking for it. A request that said separate_vocals once ran an
    ordinary ASR over the original mix, and the only sign was
    separation_seconds: 0.0 in the stats afterwards."""

    def test_asking_for_separation_passes_the_flag_that_turns_it_on(self):
        command = build_command(job(skip_separation=False, asr_source="vocals"))
        self.assertIn("--with-separation", command)
        self.assertNotIn("--skip-separation", command)
        self.assertIn("vocals", command)

    def test_the_default_still_skips_separation_explicitly(self):
        command = build_command(job())
        self.assertIn("--skip-separation", command)
        self.assertNotIn("--with-separation", command)

    def test_the_two_flags_are_never_sent_together(self):
        for skip in (True, False):
            command = build_command(job(skip_separation=skip))
            self.assertEqual(
                sum(1 for item in command if item in ("--skip-separation", "--with-separation")), 1)

    def test_no_vad_and_alignment_flags_are_unaffected(self):
        command = build_command(job(skip_separation=False, no_vad=True, skip_alignment=False))
        self.assertIn("--no-vad", command)
        self.assertNotIn("--skip-alignment", command)

    def test_automation_whisper_uses_sentence_timing_without_global_aligner(self):
        command = build_command(job(asr_engine="whisper", no_vad=True, skip_alignment=True))
        self.assertEqual(command[command.index("--asr-engine") + 1], "whisper")
        self.assertIn("--no-vad", command)
        self.assertIn("--skip-alignment", command)


if __name__ == "__main__":
    unittest.main()
