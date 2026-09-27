import unittest

from standard_timeline import build_shifted_timeline
from word_timeline import (
    _qwen_chars,
    apply_shifted_provider_words,
    normalize_provider_rows,
    provider_char_count,
    score_provider_timeline,
    separation_retry_needed,
    separation_retry_trigger,
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
    def test_reversed_word_start_excludes_row_from_alignment_and_output(self):
        row = provider_row("春风吹过", 10000)
        row["words"][2]["start_ms"] = 10100  # third character precedes the second
        live = live_segment("春风吹过", 10000)
        result = score_provider_timeline([row], [live])
        self.assertEqual(result["word_anchor_count"], 0)
        timeline = build_shifted_timeline([row], 5000, 30000)
        counts = apply_shifted_provider_words(timeline, [row], 5000)
        self.assertEqual(timeline[0]["words"], [])
        self.assertEqual(counts["rejected"], len(row["text"]))

    def test_reversed_qwen_word_start_excludes_segment(self):
        segment = live_segment("春风吹过", 10000)
        segment["words"][2]["start_ms"] = segment["words"][1]["start_ms"] - 100
        self.assertEqual(_qwen_chars(segment), [])

    def test_two_exact_characters_do_not_make_a_line_vote(self):
        rows = [provider_row(text, start) for text, start in zip(SIX_CLEAN_LINES[:3], SIX_CLEAN_STARTS[:3])]
        segments = [live_segment(text[:2], start) for text, start in zip(SIX_CLEAN_LINES[:3], SIX_CLEAN_STARTS[:3])]
        result = score_provider_timeline(rows, segments)
        self.assertEqual(result["word_eligible_line_count"], 0)

    def test_zero_duration_forced_words_cannot_vote_for_offset(self):
        # Real 金风玉蝶 separated ASR collapsed many consecutive characters at
        # 02:03.360. They identify a character, but provide no character time.
        segment = {
            "words": [
                {"text": "而", "start_ms": 123360, "end_ms": 123360, "timing_source": "qwen-forced-aligner"},
                {"text": "我", "start_ms": 123360, "end_ms": 123360, "timing_source": "qwen-forced-aligner"},
                {"text": "唱", "start_ms": 123920, "end_ms": 124080, "timing_source": "qwen-forced-aligner"},
            ],
        }
        self.assertEqual([item["char"] for item in _qwen_chars(segment)], ["唱"])

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

    def test_selected_verbatim_timeline_uses_only_provider_times_plus_global_shift(self):
        row = provider_row("春风吹过", 10000)
        asr = live_segment("春风过", 10000)
        score = score_provider_timeline([row], [asr])
        timeline = build_shifted_timeline([row], 5000, 30000, anchors=score.get("evidence_anchors"))
        counts = apply_shifted_provider_words(timeline, [row], 5000)
        self.assertEqual("".join(word["text"] for word in timeline[0]["words"]), "春风吹过")
        self.assertEqual(counts["qwen_exact"], 0)
        self.assertEqual(counts["qwen_corrected"], 0)
        self.assertGreater(counts["lddc_standard"], 0)
        self.assertEqual(
            [(word["start_ms"], word["end_ms"]) for word in timeline[0]["words"]],
            [(15000, 15400), (15400, 15800), (15800, 16200), (16200, 16600)],
        )
        self.assertEqual(timeline[0]["anchors"], [])
        self.assertEqual(timeline[0]["word_timing_source"], "provider-global-shift")

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
        apply_shifted_provider_words(timeline, rows, result["shift_ms"])
        self.assertEqual([line["start_ms"] for line in timeline], [15000, 25000, 35000])
        self.assertTrue(all(word["timing_source"] != "qwen-exact" for line in timeline for word in line["words"]))
        self.assertEqual(result["timing_model"], "word_unresolved")

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
        apply_shifted_provider_words(timeline, rows, 0)
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
        self.assertEqual(result["shift_source"], "word_unresolved")
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

    def test_bootstrap_promotes_four_of_six_tight_lines_far_from_line_shift(self):
        # Four of six independent line votes clear the requested >60% rule.
        # The other two lines disagree, so this exercises the share calculation
        # rather than the trivial four-of-four case.
        lines = SIX_CLEAN_LINES
        starts = SIX_CLEAN_STARTS
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        asr = [self._decoupled_segment(text, start, 3000, 13000 if index < 4 else 3000)
               for index, (text, start) in enumerate(zip(lines, starts))]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_bootstrap_status"], "accepted_far")
        self.assertEqual(result["word_eligible_line_count"], 6)
        self.assertEqual(result["word_dominant_cluster_line_count"], 4)
        self.assertEqual(result["shift_source"], "word")
        self.assertEqual(result["word_model_shift_ms"], 13000)
        self.assertEqual(result["word_vs_line_shift_diff_ms"], 10000)
        self.assertTrue(result["cross_model_conflict"])

    def test_bootstrap_promotes_a_large_tight_cluster_despite_the_distance(self):
        """《决定不想你》(6 lines, 5798ms away) and 《不为谁而作的歌》 (7 lines,
        7259ms) were both refused on distance alone, and both were confirmed
        better by eye once re-shifted. Enough lines agreeing tightly among
        themselves now outweighs the distance from a line shift that -- on these
        songs -- was itself built on text_score 0.13 anchor pairs."""
        lines = ["春风吹过山岗", "我们一起歌唱", "直到夜色散场",
                 "风起云涌变幻", "星河倒悬如练", "晨光照亮归途"]
        starts = [0, 20000, 40000, 60000, 80000, 100000]
        rows = [provider_row(text, start) for text, start in zip(lines, starts)]
        asr = [self._decoupled_segment(text, start, 3000, 13000) for text, start in zip(lines, starts)]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_bootstrap_status"], "accepted_far")
        self.assertEqual(result["shift_source"], "word")
        self.assertEqual(result["word_dominant_cluster_line_count"], 6)
        self.assertEqual(result["word_model_shift_ms"], 13000)
        self.assertEqual(result["effective_shift_ms"], 13000)

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

    def test_corruption_1_reversed_character_times_are_excluded(self):
        # The large jitters reverse character order in two of six segments.
        # Those segments must contribute no word anchors.
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
        self.assertEqual(result["word_eligible_line_count"], 4)
        self.assertEqual(result["word_anchor_lines"], 4)

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

    def test_corruption_5_wrong_occurrence_reverses_time_and_is_excluded(self):
        # Borrowed timestamps from another occurrence reverse word order in one
        # segment. Its entire word sequence is excluded from the vote.
        rows = [provider_row(text, start) for text, start in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS)]
        swapped = [0, 0, 6000, 6000, 0, 0]
        jitter_sets = [swapped, [0] * 6, [0] * 6, [0] * 6, [0] * 6, [0] * 6]
        asr = [
            jittered_segment(text, start, 5000, jitters)
            for text, start, jitters in zip(SIX_CLEAN_LINES, SIX_CLEAN_STARTS, jitter_sets)
        ]
        result = score_provider_timeline(rows, asr, title_score=1)
        self.assertEqual(result["word_eligible_line_count"], 5)
        self.assertEqual(result["word_anchor_lines"], 5)

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


class SeparationTriggersAreIndependentTest(unittest.TestCase):
    """The sparse-anchor rule used to sit inside the match-suspect branch, so a
    confidently matched song could never reach it. Across the 21 songs of
    赛蒂娅 2026-09-21 the coverage number was never computed once -- every one of
    them reported not_needed_high_confidence with coverage None."""

    def test_a_doubtful_match_asks_for_vocals_on_its_own(self):
        self.assertEqual(separation_retry_trigger(True, False), "match_suspect")

    def test_sparse_anchors_ask_for_vocals_even_when_the_match_is_certain(self):
        """《心之火》: named beyond doubt, 7 anchors out of 432 characters."""
        self.assertEqual(separation_retry_trigger(False, True), "sparse_word_anchors")

    def test_both_reasons_are_reported_together(self):
        self.assertEqual(separation_retry_trigger(True, True), "both")

    def test_neither_reason_leaves_the_clip_alone(self):
        self.assertEqual(separation_retry_trigger(False, False), "")

    def test_unstable_word_model_asks_for_vocals_above_coverage_threshold(self):
        self.assertEqual(separation_retry_trigger(False, False, True), "word_model_unstable")


if __name__ == "__main__":
    unittest.main()
