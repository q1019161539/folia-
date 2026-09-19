import unittest

from standard_timeline import build_shifted_timeline
from word_timeline import (
    apply_hybrid_words,
    normalize_provider_rows,
    provider_char_count,
    score_provider_timeline,
    separation_retry_needed,
    word_anchor_coverage,
)


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


def jittered_segment(text, start, shift, jitters):
    """Like live_segment, but each character's time additionally carries its own
    jitters[i] offset -- for corrupting a subset of characters within an
    otherwise clean line without moving the line's own median far."""
    return {
        "text": text,
        "start_ms": start + shift + jitters[0],
        "end_ms": start + shift + jitters[-1] + 3000,
        "words": [
            {
                "text": character,
                "start_ms": start + shift + jitters[index] + index * 400,
                "end_ms": start + shift + jitters[index] + (index + 1) * 400,
                "timing_source": "qwen-forced-aligner",
            }
            for index, character in enumerate(text)
        ],
    }


SIX_CLEAN_LINES = ["春夏秋冬轮回", "东南西北方向", "喜怒哀乐情绪", "柴米油盐酱醋", "琴棋书画诗词", "梅兰竹菊四君"]
SIX_CLEAN_STARTS = [0, 20000, 40000, 60000, 80000, 100000]


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

    def test_lines_do_not_follow_a_drifting_performance_one_by_one(self):
        # A performance that drifts further out of step with every line: +5s,
        # +7s, +9s. This used to be followed line by line, each line taking its
        # own shift from its own characters (15000/27000/39000).
        #
        # That is deliberately given up. Measured across 64 shipped products,
        # every one that let lines move on their own ended up with overlapping
        # subtitles, while the clean ones have lines that sit still (90th
        # percentile deviation from neighbours: 7ms). Real drift of this size is
        # not what per-line movement was actually producing; it was producing
        # neighbouring lines up to 2.2s apart and 《胭脂妆》 shipping with 16
        # overlapping pairs. Tracking a genuinely drifting performance belongs to
        # a whole-song stretch, which moves every line coherently, not to each
        # line deciding for itself.
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
        self.assertEqual([line["local_shift_ms"] for line in timeline], [result["shift_ms"]] * 3)
        apply_hybrid_words(timeline, rows, result["word_anchors"], result["shift_ms"])
        self.assertEqual([line["start_ms"] for line in timeline], [15000, 25000, 35000])
        # The character times are still real Qwen times inside each line -- what
        # was removed is their ability to move the line itself.
        self.assertTrue(any(word["timing_source"] == "qwen-exact" for word in timeline[0]["words"]))

    def test_word_evidence_far_from_a_line_can_never_drag_it_onto_its_neighbour(self):
        # The 《胭脂妆》 failure shape: a line whose word-level evidence sits
        # seconds away from where the lyric sheet puts it. Dragging the line
        # there put two subtitles on screen at once for 1.2~1.9s, sixteen times
        # in one song, in a file that shipped as high confidence.
        rows = [provider_row("春风吹过山岗", 10000), provider_row("我们一起歌唱", 13000)]
        anchors = [
            {"lyric_index": 1, "standard_char_index": index, "kind": "exact",
             "qwen_start_ms": 9000 + index * 400, "qwen_end_ms": 9400 + index * 400,
             "provider_start_ms": 13000 + index * 400, "provider_end_ms": 13400 + index * 400}
            for index in range(6)
        ]
        timeline = build_shifted_timeline(rows, 0, 50000)
        starts_before = [line["start_ms"] for line in timeline]
        apply_hybrid_words(timeline, rows, anchors, 0)
        self.assertEqual([line["start_ms"] for line in timeline], starts_before)
        for left, right in zip(timeline, timeline[1:]):
            self.assertLessEqual(left["end_ms"], right["start_ms"])

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

    def test_segment_bias_no_longer_mass_rejects_a_lines_word_anchors(self):
        # Reproduces the exact 《和你一样》mechanism: a merged ASR segment biases
        # a line's own *coarse* (line-level) matched start away from its true
        # singing time, while every character's real Qwen timing stays exactly
        # where it was actually sung -- there is no real tempo drift here, only
        # two lines whose segment happened to start 2600ms into the previous
        # line's tail. The old filter compared each character against an
        # `expected` derived from that same biased coarse anchor (interpolated
        # over the evidence chain), so a line caught in the bias lost all of its
        # word evidence even though its own characters agreed with each other
        # perfectly: |3000 - 5600| = 2600ms > the old fixed 1800ms window.
        lines = ["春风吹过山岗", "我们一起歌唱", "直到夜色散场", "风起云涌变幻", "江山如此多娇"]
        starts = [0, 20000, 40000, 60000, 80000]
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        biased_lines = {1, 3}
        asr = [
            self._decoupled_segment(text, start, 5600 if i in biased_lines else 3000, 3000)
            for i, (text, start) in enumerate(zip(lines, starts))
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_bootstrap_status"], "accepted")
        self.assertEqual(result["shift_source"], "word")
        self.assertEqual(result["shift_ms"], 3000)
        self.assertEqual(result["word_anchor_lines"], 5)
        self.assertEqual(result["word_anchor_rejected_count"], 0)

    def test_bootstrap_needs_at_least_three_lines_before_it_overrides_the_line_shift(self):
        # Two internally-consistent lines is not enough evidence to promote a
        # global word shift over the line-level one (the safety valve requires
        # at least three) -- but each line still keeps its own anchors on its
        # own self-consistency regardless of whether the global vote succeeds.
        rows = [provider_row("春风吹过山岗", 0), provider_row("我们一起歌唱", 20000)]
        asr = [
            self._decoupled_segment("春风吹过山岗", 0, 3000, 3000),
            self._decoupled_segment("我们一起歌唱", 20000, 3000, 3000),
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_bootstrap_status"], "insufficient_lines")
        self.assertEqual(result["shift_source"], "line")
        self.assertEqual(result["word_anchor_rejected_count"], 0)
        # Corruption test 3: too little evidence to evaluate the word model at
        # all reads as "unavailable", not "low" -- there is no data to judge, as
        # opposed to data that disagrees with itself.
        self.assertEqual(result["timing_confidence"], "unavailable")

    def test_bootstrap_accepts_a_cluster_within_the_safety_margin(self):
        # A genuine segmentation-bias case (like the ~2600ms one on 《和你一样》)
        # still needs to clear the valve. This checks a disagreement close to but
        # under MAX_WORD_VS_LINE_SHIFT_DIFF_MS (5000ms) is still trusted.
        lines = ["春风吹过山岗", "我们一起歌唱", "直到夜色散场", "风起云涌变幻"]
        starts = [0, 20000, 40000, 60000]
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        asr = [self._decoupled_segment(text, start, 3000, 6800) for text, start in zip(lines, starts)]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_bootstrap_status"], "accepted")
        self.assertEqual(result["shift_source"], "word")

    def test_bootstrap_refuses_a_cluster_far_from_the_line_shift(self):
        # A tight, unanimous word-level cluster is still refused if it sits far
        # from the line-level shift -- that combination showed up for real on a
        # song with a chorus repeated three times, where four lines' word-level
        # consensus sat ~9000ms away from (and opposite in sign to) the
        # line-level shift while a fifth line's two levels agreed almost
        # exactly. That pattern means a timestamp base mismatch somewhere, not a
        # genuine multi-second performance offset, and the valve exists to keep
        # it from ever taking over the global shift. It must still be visible in
        # cluster_lines for diagnosis, and per-line filtering must not punish
        # lines for it.
        lines = ["春风吹过山岗", "我们一起歌唱", "直到夜色散场", "风起云涌变幻"]
        starts = [0, 20000, 40000, 60000]
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        asr = [self._decoupled_segment(text, start, 3000, 13000) for text, start in zip(lines, starts)]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_bootstrap_status"], "far_from_line_shift")
        self.assertEqual(result["word_dominant_cluster_line_count"], 4)
        self.assertEqual(result["shift_source"], "line")
        self.assertEqual(result["word_anchor_rejected_count"], 0)
        # This is the exact shape found on a real chorus-repeated-three-times song:
        # the word model's own candidate is reported (not hidden just because it
        # wasn't promoted), it disagrees with the line shift by the full 10000ms,
        # and yet the word anchors are perfectly self-consistent against their own
        # candidate -- "the word model disagrees with the line model" and "the word
        # model is unreliable" are different facts, and only the old single
        # effective-residual field could not tell them apart.
        self.assertEqual(result["word_model_shift_ms"], 13000)
        self.assertEqual(result["word_vs_line_shift_diff_ms"], 10000)
        self.assertEqual(result["word_model_median_abs_residual_ms"], 0)
        self.assertGreater(result["word_median_abs_residual_ms"], 9000)
        # Corruption test 4 (real-world instance): a whole-song offset between the
        # word and line models must never by itself read as a word quality problem.
        # The word model here is perfectly self-consistent, so timing_confidence
        # must stay high; only the orthogonal conflict flag may fire.
        self.assertEqual(result["timing_confidence"], "high")
        self.assertTrue(result["cross_model_conflict"])

    def _six_clean_lines(self, shift=5000):
        rows = [provider_row(text, start) for text, start in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS)]
        asr = [live_segment(text, start, shift) for text, start in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS)]
        return rows, asr

    def test_timing_confidence_is_high_on_six_clean_uniformly_shifted_lines(self):
        # The clean baseline the other corruption tests below are measured against.
        rows, asr = self._six_clean_lines()
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["timing_confidence"], "high")
        self.assertEqual(result["word_model_coverage_ratio"], 1.0)
        self.assertEqual(result["word_model_inlier_ratio_500"], 1.0)
        self.assertFalse(result["cross_model_conflict"])

    def test_corruption_1_scattered_character_jitter_degrades_confidence(self):
        # +-1200~1800ms jitter on a third of the characters, confined to two of
        # six otherwise-clean lines. Each jittered line's own *median* still
        # lands near the true shift (jitter is roughly balanced positive/
        # negative), so this specifically exercises spread (MAD/inlier), not
        # the cluster vote itself.
        rows = [provider_row(text, start) for text, start in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS)]
        clean = [0, 0, 0, 0, 0, 0]
        jitter_a = [1500, -1800, 1200, -900, 1600, -1400]
        jitter_b = [-1300, 1700, -1100, 1400, -1600, 900]
        jitter_sets = [jitter_a, jitter_b, clean, clean, clean, clean]
        asr = [
            jittered_segment(text, start, 5000, jitters)
            for text, start, jitters in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS, jitter_sets)
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        # MAD's own robustness (its breakdown point is 50%) means a third of the
        # population jittering does not have to move it off zero -- that is
        # correct behavior, not a blind spot, because inlier_ratio_500 exists
        # precisely to catch what a robust spread statistic is designed to
        # shrug off. Assert what actually has to change.
        self.assertLess(result["word_model_inlier_ratio_500"], 0.8)
        self.assertNotEqual(result["timing_confidence"], "high")

    def test_corruption_2_an_even_split_leaves_no_dominant_cluster(self):
        # Three lines genuinely shifted one way, three genuinely shifted another
        # (not a single outlier -- an even split). No cluster can cover >=60% of
        # six eligible lines, so this must read as a real disagreement (low),
        # not as insufficient evidence (unavailable): there is plenty of data,
        # it simply never agrees with itself.
        rows = [provider_row(text, start) for text, start in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS)]
        shifts = [5000, 5000, 5000, 11000, 11000, 11000]
        asr = [
            live_segment(text, start, shift)
            for text, start, shift in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS, shifts)
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_bootstrap_status"], "no_dominant_cluster")
        self.assertEqual(result["word_model_coverage_ratio"], 0.5)
        self.assertEqual(result["timing_confidence"], "low")

    def test_corruption_5_anchors_borrowed_from_the_wrong_occurrence(self):
        # Two of one line's six characters are swapped for times lifted from a
        # position 6000ms away (as if a repeated phrase pulled in the wrong
        # occurrence's timing for part of the line), the other four characters
        # and all other lines stay clean. A partial, localized corruption like
        # this should still show up in the aggregate spread/inlier numbers even
        # though it never dominates the vote.
        rows = [provider_row(text, start) for text, start in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS)]
        swapped = [0, 0, 6000, 6000, 0, 0]
        jitter_sets = [swapped, [0] * 6, [0] * 6, [0] * 6, [0] * 6, [0] * 6]
        asr = [
            jittered_segment(text, start, 5000, jitters)
            for text, start, jitters in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS, jitter_sets)
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        clean_result = score_provider_timeline(*self._six_clean_lines())
        # A 2-of-36-character corruption is a small minority, so a robust spread
        # statistic (MAD) is not expected to move -- inlier_ratio_500 is the one
        # built to notice a handful of anchors quietly missing their mark.
        self.assertLess(result["word_model_inlier_ratio_500"], clean_result["word_model_inlier_ratio_500"])
        self.assertGreaterEqual(result["word_model_mad_ms"], clean_result["word_model_mad_ms"])

    def test_new_confidence_fields_appear_without_changing_existing_routing(self):
        # Thin contract test: the new fields show up, and confidence_tier's
        # existing inputs (low_confidence/confidence) are untouched by any of
        # this -- match_confidence and timing_confidence are additions, not
        # replacements.
        rows, asr = self._six_clean_lines()
        result = score_provider_timeline(rows, asr, title_score=1)
        for field in (
            "word_model_inlier_ratio_500", "word_model_coverage_ratio",
            "timing_confidence", "match_confidence", "cross_model_conflict",
        ):
            self.assertIn(field, result)
        self.assertEqual(result["match_confidence"], "low" if result["low_confidence"] else "high")
        self.assertEqual(result["confidence"], "low" if result["low_confidence"] else "high")

    def test_line_level_evidence_alone_yields_high_confidence(self):
        lines = ["春风吹过山岗", "我们一起歌唱", "直到夜色散场"]
        starts = [0, 6000, 12000]
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        asr = [self._decoupled_segment(text, start, 800, 800, tag=False) for text, start in zip(lines, starts)]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_anchor_count"], 0)
        self.assertFalse(result["low_confidence"])


class SeparationRetryTriggerTest(unittest.TestCase):
    """《心之火》 matched 7 of its 432 characters against a mix the ASR could barely
    hear; read back from separated vocals it matched 80. 《读心术》 matched 78 of 449
    on the first pass and has nothing to gain. Coverage across 37 finished verbatim
    songs: median 10.3%, starved ones far below."""

    @staticmethod
    def row(text, start, per_char=300):
        return {"text": text, "start_ms": start,
                "end_ms": start + per_char * len(text),
                "words": [{"text": char, "start_ms": start + index * per_char,
                           "end_ms": start + (index + 1) * per_char}
                          for index, char in enumerate(text)]}

    def sheet(self, lines=10, text="我只想让你回到最初"):
        return [self.row(text, 10_000 + index * 4000) for index in range(lines)]

    def test_char_count_ignores_what_the_matcher_ignores(self):
        rows = [self.row("你好 世界！", 1000)]
        self.assertEqual(provider_char_count(rows), 4)

    def test_coverage_is_anchors_over_matchable_characters(self):
        rows = self.sheet(lines=10)
        self.assertEqual(provider_char_count(rows), 90)
        self.assertAlmostEqual(word_anchor_coverage(9, rows), 0.1)
        self.assertAlmostEqual(word_anchor_coverage(0, rows), 0.0)

    def test_a_starved_verbatim_song_is_worth_re_reading(self):
        rows = self.sheet(lines=10)
        self.assertTrue(separation_retry_needed("verbatim", 5, rows, 0.10))

    def test_a_well_covered_song_is_left_alone(self):
        rows = self.sheet(lines=10)
        self.assertFalse(separation_retry_needed("verbatim", 18, rows, 0.10))
        self.assertFalse(separation_retry_needed("verbatim", 9, rows, 0.10))

    def test_a_line_only_release_never_triggers_it(self):
        """No character times to match against, so a cleaner ASR changes nothing."""
        rows = self.sheet(lines=10)
        self.assertFalse(separation_retry_needed("line", 0, rows, 0.10))

    def test_a_zero_threshold_disables_the_retry(self):
        rows = self.sheet(lines=10)
        self.assertFalse(separation_retry_needed("verbatim", 0, rows, 0.0))

    def test_no_characters_means_no_verdict_rather_than_a_retry(self):
        self.assertIsNone(word_anchor_coverage(0, []))
        self.assertFalse(separation_retry_needed("verbatim", 0, [], 0.10))


if __name__ == "__main__":
    unittest.main()
