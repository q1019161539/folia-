import unittest

from standard_timeline import build_shifted_timeline
from word_timeline import apply_hybrid_words, normalize_provider_rows, score_provider_timeline


def provider_row(text, start):
    return {
        "text": text,
        "start_ms": start,
        "end_ms": start + 3000,
        "words": [
            {"text": character, "start_ms": start + index * 400, "end_ms": start + (index + 1) * 400}
            for index, character in enumerate(text)
        ],
    }


def live_segment(text, start, shift=5000):
    return {
        "text": text,
        "start_ms": start + shift,
        "end_ms": start + shift + 3000,
        "words": [
            {
                "text": character,
                "start_ms": start + shift + index * 400,
                "end_ms": start + shift + (index + 1) * 400,
                "timing_source": "qwen-forced-aligner",
            }
            for index, character in enumerate(text)
        ],
    }


class WordTimelineTests(unittest.TestCase):
    def test_qwen_words_refine_global_shift_and_raise_confidence(self):
        rows = [
            provider_row("春风吹过山岗", 10000),
            provider_row("我们一起歌唱", 20000),
            provider_row("直到夜色散场", 30000),
        ]
        asr = [
            live_segment("春风吹过山岗", 10000),
            live_segment("我们一起歌唱", 20000),
            live_segment("直到夜色散场", 30000),
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["shift_ms"], 5000)
        self.assertGreaterEqual(result["word_anchor_count"], 18)
        self.assertFalse(result["low_confidence"])

    def test_hybrid_uses_qwen_and_standard_for_missing_character(self):
        row = provider_row("春风吹过", 10000)
        asr = live_segment("春风过", 10000)
        score = score_provider_timeline([row], [asr])
        timeline = build_shifted_timeline([row], 5000, 30000, anchors=score.get("evidence_anchors"))
        counts = apply_hybrid_words(timeline, [row], score.get("word_anchors") or [], 5000)
        self.assertEqual("".join(word["text"] for word in timeline[0]["words"]), "春风吹过")
        self.assertGreater(counts["qwen_exact"], 0)
        self.assertGreater(counts["lddc_standard"], 0)
        self.assertTrue(all(timeline[0]["start_ms"] <= word["start_ms"] < word["end_ms"] <= timeline[0]["end_ms"] for word in timeline[0]["words"]))

    def test_hybrid_keeps_late_live_word_anchors_with_local_drift(self):
        rows = [
            provider_row("春风吹过山岗", 10000),
            provider_row("我们一起歌唱", 20000),
            provider_row("直到夜色散场", 30000),
        ]
        asr = [
            live_segment("春风吹过山岗", 10000, 5000),
            live_segment("我们一起歌唱", 20000, 7000),
            live_segment("直到夜色散场", 30000, 9000),
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertGreaterEqual(result["word_anchor_count"], 18)
        timeline = build_shifted_timeline(rows, result["shift_ms"], 50000, anchors=result["evidence_anchors"])
        # The sheet is placed by one whole-song shift, then the real Qwen character
        # times pull each line onto where it was actually sung -- so a verbatim
        # candidate still follows a drifting performance line by line.
        self.assertEqual([line["local_shift_ms"] for line in timeline], [result["shift_ms"]] * 3)
        apply_hybrid_words(timeline, rows, result["word_anchors"], result["shift_ms"])
        self.assertEqual([line["start_ms"] for line in timeline], [15000, 27000, 39000])

    def test_metadata_filter_and_untimed_rows(self):
        rows = normalize_provider_rows([
            {"text": "作词：某人", "start_ms": 0, "words": []},
            {"text": "真正歌词", "start_ms": None, "words": []},
        ], lambda text: text.startswith("作词"))
        self.assertEqual([row["text"] for row in rows], ["真正歌词"])

    def _decoupled_segment(self, text, lrc_start, coarse_delta, char_delta, tag=True):
        """An ASR segment whose coarse (line-level) start and per-character (word-level)
        timing carry independently chosen offsets -- lets a test show line-level text
        matching failing for its own reasons (short anchor span here) while the
        character-level Qwen evidence for the same rows stays internally consistent."""
        return {
            "text": text,
            "start_ms": lrc_start + coarse_delta,
            "end_ms": lrc_start + coarse_delta + 3000,
            "words": [
                {
                    "text": character,
                    "start_ms": lrc_start + char_delta + index * 400,
                    "end_ms": lrc_start + char_delta + (index + 1) * 400,
                    **({"timing_source": "qwen-forced-aligner"} if tag else {}),
                }
                for index, character in enumerate(text)
            ],
        }

    LONG_LINE = "一二三四五六七八九十甲乙丙丁戊己庚辛壬癸"  # 20 characters

    def test_word_evidence_does_not_decide_confidence(self):
        # Five lines whose line-level anchor span stays under score_timeline's own
        # 10s bar, while the word-level evidence is as strong as it gets: dozens of
        # exact character matches across every line, zero residual. Confidence must
        # still read low. Word anchors are timing material and a ranking bonus, not
        # a vote -- a live cover drifts from the studio master character by
        # character, so this verdict tracked how closely one performance followed
        # one master rather than whether the lyrics were the right ones.
        lines = ["春风吹过山岗", "我们一起歌唱", "直到夜色散场", "风起云涌变幻", self.LONG_LINE]
        starts = [0, 2000, 4000, 6000, 8500]
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        asr = [self._decoupled_segment(text, start, 800, 800) for text, start in zip(lines, starts)]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertLess(result["anchor_span_ms"], 10000)
        self.assertGreaterEqual(result["word_anchor_count"], 24)
        self.assertEqual(result["word_residual_p90_ms"], 0)
        self.assertTrue(result["low_confidence"])
        self.assertEqual(result["confidence"], "low")

    def test_line_level_evidence_alone_yields_high_confidence(self):
        lines = ["春风吹过山岗", "我们一起歌唱", "直到夜色散场"]
        starts = [0, 6000, 12000]
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        asr = [self._decoupled_segment(text, start, 800, 800, tag=False) for text, start in zip(lines, starts)]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_anchor_count"], 0)
        self.assertFalse(result["low_confidence"])


if __name__ == "__main__":
    unittest.main()
