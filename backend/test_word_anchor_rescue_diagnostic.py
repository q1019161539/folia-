import unittest

from word_anchor_rescue_diagnostic import _cluster_occurrences, rescue_diagnostic


def provider_row(text, start):
    return {
        "text": text,
        "start_ms": start,
        "words": [
            {"text": character, "start_ms": start + index * 400, "end_ms": start + (index + 1) * 400}
            for index, character in enumerate(text)
        ],
    }


def live_segment(text, start):
    return {
        "text": text,
        "start_ms": start,
        "end_ms": start + 3000,
        "words": [
            {
                "text": character,
                "start_ms": start + index * 400,
                "end_ms": start + (index + 1) * 400,
                "timing_source": "qwen-forced-aligner",
            }
            for index, character in enumerate(text)
        ],
    }


class ClusterOccurrencesTests(unittest.TestCase):
    def test_nearby_points_join_one_cluster_far_points_split(self):
        points = [(1000, "a"), (1500, "b"), (60000, "c"), (60800, "d")]
        clusters = _cluster_occurrences(points, gap_ms=5000)
        self.assertEqual([sorted(c) for c in clusters], [["a", "b"], ["c", "d"]])

    def test_empty_input_yields_no_clusters(self):
        self.assertEqual(_cluster_occurrences([]), [])


class RescueDiagnosticTests(unittest.TestCase):
    def test_a_line_with_no_line_level_anchor_is_recovered_from_a_single_occurrence(self):
        # Mirrors the real 《离人赋》 shape: a lyric line whose only matching ASR
        # segment never won a line-level anchor (core/evidence empty for it),
        # but real Qwen word timing sits right there anyway.
        rows = [provider_row("我们的世界尽头", 10000)]
        asr = [live_segment("我们的世界尽头", 10400)]  # +400ms true offset
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs=set(), evidence_pairs=set())
        self.assertEqual(result["unanchored_lines"], 1)
        self.assertEqual(result["recoverable_unanchored_lines"], 1)
        self.assertEqual(result["multi_occurrence_lines"], 0)
        self.assertEqual(result["per_line_summary"][0]["status"], "recoverable")

    def test_a_line_already_anchored_is_not_counted_as_unanchored(self):
        rows = [provider_row("我们的世界尽头", 10000)]
        asr = [live_segment("我们的世界尽头", 10400)]
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs={(0, 0)}, evidence_pairs={(0, 0)})
        self.assertEqual(result["unanchored_lines"], 0)
        self.assertEqual(result["recoverable_unanchored_lines"], 0)
        self.assertNotIn(0, result["per_line_summary"])

    def test_a_repeated_chorus_produces_two_occurrences(self):
        # The exact real-world shape: the same line sung twice, at segments far
        # apart, neither of which won a line-level anchor.
        rows = [provider_row("我们的世界尽头在那一夜", 200000)]
        asr = [live_segment("我们的世界尽头在那一夜", 20400), live_segment("我们的世界尽头在那一夜", 200400)]
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs=set(), evidence_pairs=set())
        self.assertEqual(result["multi_occurrence_lines"], 1)
        self.assertEqual(result["per_line_summary"][0]["occurrence_count"], 2)
        # The second occurrence sits right at the expected time (200000ms) and
        # the first is 180s away -- a distance check alone can resolve this one.
        self.assertEqual(result["per_line_summary"][0]["status"], "multi_occurrence_resolvable")

    def test_two_occurrences_equally_far_from_expected_are_ambiguous(self):
        rows = [provider_row("我们的世界尽头在那一夜", 100000)]
        asr = [live_segment("我们的世界尽头在那一夜", 20400), live_segment("我们的世界尽头在那一夜", 180400)]
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs=set(), evidence_pairs=set())
        self.assertEqual(result["per_line_summary"][0]["status"], "ambiguous_multi_occurrence")
        self.assertEqual(result["ambiguous_occurrence_lines"], 1)

    def test_line_only_candidate_with_no_words_is_never_recoverable(self):
        rows = [{"text": "我们的世界尽头", "start_ms": 10000, "words": []}]
        asr = [{"text": "我们的世界尽头", "start_ms": 10400, "end_ms": 13400, "words": []}]
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs=set(), evidence_pairs=set())
        self.assertEqual(result["unanchored_lines"], 1)
        self.assertEqual(result["recoverable_unanchored_lines"], 0)
        self.assertEqual(result["per_line_summary"][0]["status"], "not_recoverable")

    def test_a_line_with_zero_character_overlap_is_not_recoverable(self):
        # Character sets share nothing at all -- this is the true-negative case,
        # not just a weak match.
        rows = [provider_row("我们的世界尽头在那一夜缠绵", 10000)]
        asr = [live_segment("青蛙睡觉打呼噜今天下雨了", 10400)]
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs=set(), evidence_pairs=set())
        self.assertFalse(result["rows"][0]["in_potentials"] if result["rows"] else False)
        self.assertEqual(result["recoverable_unanchored_lines"], 0)
        self.assertEqual(result["per_line_summary"][0]["status"], "not_recoverable")

    def test_two_incidental_shared_characters_no_longer_pass_the_rescue_bar(self):
        # This is the noise case the old MIN_EXACT_FOR_OCCURRENCE=2 bar let
        # through: two characters shared by coincidence (not a real match), the
        # same bar word_timeline uses when a pair was ALREADY chosen by the
        # line-level chain (where 2 is fine, since it's corroborating evidence
        # for a pair that's already trusted). A full-song blind search has no
        # such trust to lean on, so it needs both a higher anchor count and a
        # real fraction of the line covered -- MIN_WORD_ANCHORS_FOR_RESCUE_SEARCH
        # and MIN_LYRIC_COVERAGE_FOR_RESCUE_SEARCH exist to keep this out.
        rows = [provider_row("我们的世界尽头在那一夜缠绵", 10000)]
        asr = [live_segment("完全不相关的另一段文字内容", 10400)]  # shares "的" and "一" with the line above
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs=set(), evidence_pairs=set())
        self.assertEqual(result["per_line_summary"][0]["status"], "not_recoverable")
        # Below the rescue bar (and with no line-level text score either), this
        # pair carries no reportable signal at all -- it correctly never makes
        # it into rows, unlike the old MIN_EXACT_FOR_OCCURRENCE=2 bar which
        # would have surfaced it as a "recoverable" line-level match.
        self.assertTrue(all(r["tier"] is None for r in result["rows"]))

    def test_a_genuine_high_coverage_match_clears_the_rescue_bar_as_good_or_strong(self):
        # A real rescue: most of the line's characters land as exact word
        # anchors in one ASR segment, unlike the coincidental 2-character case
        # above. This is the shape ChatGPT's guidance was calibrated against
        # (word_anchor_count>=5 and lyric_coverage>=0.35).
        rows = [provider_row("我们的世界尽头在那一夜缠绵悱恻", 10000)]  # 15 valid chars
        asr = [live_segment("我们的世界尽头在那一夜缠绵悱恻", 10400)]  # full overlap
        result = rescue_diagnostic(rows, asr, shift_ms=0, core_pairs=set(), evidence_pairs=set())
        row = result["rows"][0]
        self.assertGreaterEqual(row["word_anchor_count"], 5)
        self.assertGreaterEqual(row["lyric_coverage"], 0.35)
        self.assertIn(row["tier"], ("good", "strong"))
        self.assertEqual(result["per_line_summary"][0]["status"], "recoverable")


if __name__ == "__main__":
    unittest.main()
