import unittest

from standard_timeline import (
    anchor_residual_stats,
    anchor_trend_stats,
    build_shifted_timeline,
    candidate_pool_quality,
    choose_best_timeline_candidate,
    clamp_forced_words,
    estimate_untimed_timeline,
    find_suspect_anchor_regions,
    is_high_confidence,
    lyric_render_window,
    max_anchor_drift_ms,
    parse_lrc,
    plain_lyric_lines,
    build_review_assessment,
    confidence_output_folder,
    is_lyric_metadata,
    resolve_deepseek_full_realign,
    score_timeline,
    song_identity_suspicious,
)


def asr(text, start, index):
    return {"text": text, "start_ms": start, "end_ms": start + 1200, "line_id": index}


class StandardTimelineTests(unittest.TestCase):
    def test_lrc_offset_multiple_tags_and_metadata(self):
        rows = parse_lrc("[offset:+120]\n[ar:歌手]\n[00:01.20][00:03.450]第一句\n[00:05.00]作词：某人\n[00:06.00]古筝 : 某人\n[00:07.00]录音师：某人\n[00:08.00]出品人：某人\n")
        self.assertEqual([(x["start_ms"], x["text"]) for x in rows], [(1320, "第一句"), (3570, "第一句")])

    def test_provider_intros_not_treated_as_lyrics(self):
        values = [
            "合音：甲/乙", "乐队统筹：某人", "灯光设计：某人", "录音室：Studio",
            "混音室：凃惠源音乐工作室",
            "原唱：千百顺", "翻唱：某人", "主唱：某人",
            "MIDI程序：韦伟", "和声演唱：王笑文", "口哨：王佩君",
            "录音棚：好听音乐", "混音棚：大陆桥声音工作室",
            "木吉他：某人", "【未经著作权人许可 不得翻唱翻录或使用】",
            "「释放你的音乐才华，AI作歌就选Vemus未音APP！」",
        ]
        self.assertTrue(all(is_lyric_metadata(value) for value in values))
        self.assertTrue(is_lyric_metadata("心之火 - F.I.R.飞儿乐团/彭佳慧", "心之火", "F.I.R.飞儿乐团 / 彭佳慧"))
        self.assertFalse(is_lyric_metadata("爱是一场漫长旅行", "心之火", "彭佳慧"))

    def test_a_high_tier_song_can_still_need_checking_first(self):
        # 《胭脂妆》 shipped as tier=high with match and timing confidence both
        # high, and carried sixteen places where two subtitle lines were on
        # screen at once. The tier describes the evidence behind the alignment,
        # not the result, so it is recorded as a fact and may never lower the
        # level -- otherwise exactly this song would be filed as "no risk".
        assessment = build_review_assessment({
            "confidence_tier": "high", "match_confidence": "high", "timing_confidence": "high",
            "cross_model_conflict": True, "word_vs_line_shift_diff_ms": 2234,
            "core_anchor_count": 9, "core_span_ms": 174768, "mad_ms": 1065,
            "timing_type": "verbatim",
        })
        self.assertEqual(assessment["review_level"], "critical")
        codes = [item["code"] for item in assessment["review_reasons"]]
        self.assertIn("timing_model_conflict", codes)
        conflict = next(i for i in assessment["review_reasons"] if i["code"] == "timing_model_conflict")
        self.assertEqual(conflict["facts"]["model_delta_ms"], 2234)

    def test_a_wrong_song_name_outranks_everything_else(self):
        assessment = build_review_assessment({
            "song_identity_suspicious": True, "song_identity_primary_title": "风花雪月",
            "lyric_title": "黯然销魂", "lyric_artist": "离音",
            "core_anchor_count": 4, "core_span_ms": 80100, "mad_ms": 64,
            "timing_type": "verbatim",
        })
        self.assertEqual(assessment["review_level"], "critical")
        identity = next(i for i in assessment["review_reasons"] if i["code"] == "song_identity_suspicious")
        self.assertEqual(identity["facts"]["lyric_title"], "黯然销魂")

    def test_thin_evidence_is_worth_a_look_but_is_not_an_alarm(self):
        assessment = build_review_assessment({
            "core_anchor_count": 2, "core_span_ms": 4000, "mad_ms": 120,
            "timing_type": "verbatim",
        })
        self.assertEqual(assessment["review_level"], "warning")
        weak = next(i for i in assessment["review_reasons"] if i["code"] == "weak_anchor_evidence")
        self.assertEqual(weak["facts"], {"anchor_count": 2, "anchor_span_ms": 4000})

    def test_a_measurement_that_was_never_taken_is_not_a_bad_measurement(self):
        # Reports written before mad_ms and core_span_ms existed carry neither.
        # Reading the absence as zero flagged 80 of 86 finished songs, including
        # ones with 18 and 36 anchors, as short of evidence.
        assessment = build_review_assessment({"core_anchor_count": 18, "timing_type": "verbatim"})
        self.assertEqual(assessment["review_level"], "normal")
        self.assertEqual(build_review_assessment({})["review_level"], "normal")

    def test_a_sound_song_raises_nothing(self):
        # 《香水有毒》's real numbers -- the baseline everyone agrees is good.
        assessment = build_review_assessment({
            "confidence_tier": "high", "core_anchor_count": 18, "core_span_ms": 244000,
            "mad_ms": 319, "timing_type": "verbatim",
        })
        self.assertEqual(assessment, {"review_level": "normal", "review_reasons": []})

    def test_low_confidence_output_folder_no_longer_claims_deepseek_ran(self):
        # The classic render path put everything that was not 'high' into
        # 'DeepSeek版'. With the full-song realign switched off, 纵容 and
        # 风花雪月 were filed there with full_realign_used=False -- the folder
        # named a step that never ran, which is how it looked like DeepSeek was
        # still working. Both render paths now share this one function.
        self.assertEqual(confidence_output_folder(
            {"timeline_match": {"confidence_tier": "local", "low_confidence": True}}), "低置信")
        self.assertEqual(confidence_output_folder(
            {"timeline_match": {"confidence_tier": "high", "low_confidence": False}}), "高置信")
        # A job aligned before the switch-off really did go through DeepSeek, so
        # its folder keeps saying so.
        self.assertEqual(confidence_output_folder(
            {"timeline_match": {"confidence_tier": "deepseek"}}), "DeepSeek版")

    def test_output_folder_falls_back_when_the_tier_was_never_recorded(self):
        self.assertEqual(confidence_output_folder({"timeline_match": {"low_confidence": True}}), "低置信")
        self.assertEqual(confidence_output_folder({"timeline_match": {}}), "高置信")
        self.assertEqual(confidence_output_folder({}), "高置信")
        self.assertEqual(confidence_output_folder(None), "高置信")

    def test_bare_singer_labels_are_not_lyrics(self):
        # Real rows from shipped products. A duet sheet marks who sings what;
        # the label row carries no lyric and is published with a near-zero
        # duration (《坏女孩》's 男：/女： are 1ms each), so it flashes on screen
        # between real lines.
        for value in ["男：", "女：", "合：", "Rap：", "谷嘉诚：", "赵露思：",
                      "阳：", "宿：", "阳(宿低八)：", "Sasablue："]:
            self.assertTrue(is_lyric_metadata(value), value)

    def test_credit_labels_with_names_after_them_are_not_lyrics(self):
        # Also real rows. The existing role list matched only exact prefixes, so
        # compounds like 人声录音 and 缩混工程师 slipped through and shipped.
        for value in ["混缩：黄文文", "伴唱 : 沙栩帆", "人声录音 : Sleepinkid@源音创乐",
                      "制作统筹 : Ocd/刘京", "商务统筹 : 陈亦心", "宣传发行 : 叶增辉",
                      "联合出品 : 无忧音乐", "录音工程：刘宇航", "混音工程：牛翊宁",
                      "母带工程：牛翊宁", "总策划：张葛", "封面：拂言", "题字：许舟晚",
                      "戏腔：单色凌", "制作公司：Hikoon Music", "原曲：离人赋 - 云汐",
                      "推广：+7", "键盘/合成器：ericjuu", "音乐制作发行：哇唧唧哇",
                      "混音/母带：LBI 利比", "缩混工程师：赵靖"]:
            self.assertTrue(is_lyric_metadata(value), value)

    def test_a_sung_line_behind_a_singer_label_survives(self):
        # The one counter-example in the whole corpus: a part label followed by
        # real lyrics, sung for 6.5 seconds. Filtering every colon-bearing row
        # would delete it.
        self.assertFalse(is_lyric_metadata("合：能够让我们相偎相依"))
        # A colon inside an ordinary line must not make it metadata either.
        self.assertFalse(is_lyric_metadata("我想对你说：我一直都在"))
        self.assertFalse(is_lyric_metadata("他转身说：再见"))

    def test_interlude_markers_are_not_lyrics(self):
        for value in ["Music", "music", "间奏", "（间奏）", "[前奏]", "尾奏", "Solo"]:
            self.assertTrue(is_lyric_metadata(value), value)
        self.assertFalse(is_lyric_metadata("音乐响起的时候"))

    def test_high_confidence_candidate_beats_higher_scoring_low_confidence(self):
        items = [
            {"title_similarity": 1.0, "result": {"score": 315, "low_confidence": True, "anchors": list(range(12))}},
            {"title_similarity": 1.0, "result": {"score": 296, "low_confidence": False, "anchors": list(range(11))}},
        ]
        self.assertIs(choose_best_timeline_candidate(items), items[1])

    def test_verbatim_release_beats_line_only_remix_of_the_same_title(self):
        # Real 《很任性》 case: the original artist's word-timed release scored
        # higher but read low-confidence against a live cover, while a line-only
        # remix upload of the same title read high-confidence and took the pick.
        items = [
            {"candidate": {"timing_type": "verbatim"}, "title_similarity": 1.0,
             "result": {"score": 148.7, "low_confidence": True, "anchors": list(range(6))}},
            {"candidate": {"timing_type": "line"}, "title_similarity": 1.0,
             "result": {"score": 147.2, "low_confidence": False, "anchors": list(range(6))}},
        ]
        self.assertIs(choose_best_timeline_candidate(items), items[0])

    def test_verbatim_preference_does_not_cross_to_another_song(self):
        # A word-timed release of a different song must not outrank the correct
        # title just for being verbatim.
        items = [
            {"candidate": {"timing_type": "verbatim"}, "title_similarity": 0.4,
             "result": {"score": 300, "low_confidence": False, "anchors": list(range(9))}},
            {"candidate": {"timing_type": "line"}, "title_similarity": 1.0,
             "result": {"score": 150, "low_confidence": False, "anchors": list(range(6))}},
        ]
        self.assertIs(choose_best_timeline_candidate(items), items[1])

    def test_repeated_chorus_uses_consistent_later_offset(self):
        lrc = parse_lrc("[00:10.00]一起看海\n[00:14.00]等风吹来\n[01:10.00]一起看海\n[01:14.00]等风吹来\n[01:20.00]只有这次结尾")
        result = score_timeline(lrc, [asr("一起看海", 5000, 0), asr("等风吹来", 9000, 1), asr("只有这次结尾", 15000, 2)])
        self.assertEqual(result["shift_ms"], -65000)
        self.assertEqual([x["lyric_index"] for x in result["evidence_anchors"]], [2, 3, 4])

    def test_shifted_timeline_keeps_unrecognized_rows(self):
        lrc = parse_lrc("[00:10.00]甲乙丙丁\n[00:14.00]漏识别的一句\n[00:18.00]戊己庚辛")
        result = score_timeline(lrc, [asr("甲乙丙丁", 5000, 0), asr("戊己庚辛", 13000, 1)])
        rows = build_shifted_timeline(lrc, result["shift_ms"], 20000, anchors=result["evidence_anchors"])
        self.assertEqual([x["text"] for x in rows], ["甲乙丙丁", "漏识别的一句", "戊己庚辛"])
        self.assertTrue(all(a["end_ms"] <= b["start_ms"] for a, b in zip(rows, rows[1:])))

    def test_shifted_timeline_moves_every_line_by_one_shift(self):
        # A performance that drifts (5s / 7s / 9s late) keeps the release's own
        # rhythm: every line moves by the median shift, nobody gets bent toward a
        # neighbouring anchor. Note the core chain here holds a single anchor --
        # a 1800ms tolerance cannot span 5s..9s of drift -- while the evidence
        # chain reaches all three lines and hangs their ASR rows on them.
        lrc = parse_lrc(
            "[00:10.00]第一段独特歌词\n"
            "[00:20.00]中间一句歌词\n"
            "[00:30.00]最后一段独特歌词"
        )
        result = score_timeline(lrc, [
            asr("第一段独特歌词", 15000, 0),
            asr("中间一句歌词", 27000, 1),
            asr("最后一段独特歌词", 39000, 2),
        ])
        rows = build_shifted_timeline(lrc, result["shift_ms"], 50000, anchors=result["evidence_anchors"])
        shift = result["shift_ms"]
        self.assertEqual([row["start_ms"] - row["standard_start_ms"] for row in rows], [shift] * 3)
        self.assertEqual([row["local_shift_ms"] for row in rows], [shift] * 3)
        self.assertEqual([row.get("asr_start_ms") for row in rows], [15000, 27000, 39000])
        self.assertEqual(len(result["core_anchors"]), 1)
        self.assertEqual(len(result["evidence_anchors"]), 3)

    def test_unrecognized_line_keeps_its_place_in_the_shifted_sheet(self):
        lrc = parse_lrc(
            "[00:10.00]开头锚点歌词\n"
            "[00:20.00]没有识别的一句\n"
            "[00:30.00]结尾锚点歌词"
        )
        result = score_timeline(lrc, [
            asr("开头锚点歌词", 15000, 0),
            asr("结尾锚点歌词", 39000, 1),
        ])
        rows = build_shifted_timeline(lrc, result["shift_ms"], 50000, anchors=result["evidence_anchors"])
        self.assertEqual([row["start_ms"] - row["standard_start_ms"] for row in rows], [result["shift_ms"]] * 3)
        self.assertEqual(rows[1]["segment_ids"], [])

    def test_max_anchor_drift_reports_worst_section(self):
        anchors = [{"delta_ms": 5000}, {"delta_ms": 7000}, {"delta_ms": 12000}]
        self.assertEqual(max_anchor_drift_ms(anchors, 7000), 5000)
        self.assertEqual(max_anchor_drift_ms([], 7000), 0)
        self.assertEqual(max_anchor_drift_ms(None, 7000), 0)

    def test_one_outlier_anchor_does_not_spoil_the_robust_statistics(self):
        # The exact shape that used to cost a well-aligned song: nine anchors tight
        # around the shift, one mis-matched 4300ms away. median_abs and MAD stay
        # small; only the maximum blows up, which is why nothing may judge on it.
        anchors = [{"delta_ms": 7000 + d} for d in (-400, -200, -100, 0, 100, 150, 250, 300, 400, 4300)]
        stats = anchor_residual_stats(anchors, 7000)
        self.assertLess(stats["median_abs_residual_ms"], 300)
        self.assertLess(stats["mad_ms"], 500)
        self.assertEqual(max_anchor_drift_ms(anchors, 7000), 4300)

    def test_residual_p90_is_the_worst_anchor_below_ten_anchors(self):
        # Documents the trap rather than endorsing it: for n <= 9 the p90 index
        # lands on the last element, so p90 *is* the maximum. Nothing may gate on
        # it; it is reported so runs can be compared.
        for count in (6, 9):
            anchors = [{"delta_ms": 7000} for _ in range(count - 1)] + [{"delta_ms": 9500}]
            self.assertEqual(anchor_residual_stats(anchors, 7000)["residual_p90_ms"], 2500)
        ten = [{"delta_ms": 7000} for _ in range(9)] + [{"delta_ms": 9500}]
        self.assertEqual(anchor_residual_stats(ten, 7000)["residual_p90_ms"], 0)

    def test_live_cover_residuals_no_longer_force_low_confidence(self):
        # A live cover sitting ~2s off the studio release across a long span is a
        # normal performance difference, not a failed match. It used to trip
        # `p90 > 1500` and hand the whole batch to DeepSeek.
        lrc = parse_lrc(
            "[00:10.00]第一段独特的歌词\n[00:40.00]第二段另外的歌词\n[01:10.00]第三段再换一句词\n"
            "[01:40.00]第四段接着往下唱\n[02:10.00]第五段结尾的歌词"
        )
        result = score_timeline(lrc, [
            asr("第一段独特的歌词", 8300, 0),
            asr("第二段另外的歌词", 38400, 1),
            asr("第三段再换一句词", 70000, 2),
            asr("第四段接着往下唱", 101700, 3),
            asr("第五段结尾的歌词", 131750, 4),
        ])
        self.assertEqual(len(result["core_anchors"]), 5)
        self.assertGreater(result["residual_p90_ms"], 1500)
        self.assertFalse(result["low_confidence"])

    def test_verbatim_end_is_not_held_through_an_instrumental_break(self):
        # A verbatim release publishes the last line before an interlude with an
        # end that runs to the next sung line. Taken at face value it parked one
        # line of 《坏女孩》on screen for 32 seconds across the break.
        lrc = [
            {"text": "第一句", "start_ms": 10_000, "end_ms": 13_000},
            {"text": "第二句", "start_ms": 13_000, "end_ms": 16_000},
            {"text": "间奏前最后一句", "start_ms": 16_000, "end_ms": 49_000},
            {"text": "间奏后第一句", "start_ms": 49_000, "end_ms": 52_000},
        ]
        rows = build_shifted_timeline(lrc, 0, 60_000)
        durations = [row["end_ms"] - row["start_ms"] for row in rows]
        self.assertEqual(durations[:2], [3000, 3000])
        self.assertLessEqual(durations[2], 4500)
        self.assertEqual(durations[3], 3000)

    def test_trend_stats_separate_a_steady_drift_from_plain_scatter(self):
        # Same MAD, opposite meanings. A performance running steadily late gives
        # long baselines that agree on direction and a slope that absorbs most of
        # the spread; mis-matched anchors give neither, and no amount of
        # stretching would help them.
        ramp = [{"lrc_start_ms": t, "delta_ms": d} for t, d in
                zip(range(10_000, 190_000, 30_000), (-1500, -900, -300, 300, 900, 1500))]
        jitter = [{"lrc_start_ms": t, "delta_ms": d} for t, d in
                  zip(range(10_000, 190_000, 30_000), (1300, -1600, 800, -1400, 1700, -900))]
        drifting = anchor_trend_stats(ramp, 0)
        scattered = anchor_trend_stats(jitter, 0)
        self.assertEqual(drifting["direction_support"], 1.0)
        self.assertGreater(drifting["drift_over_span_ms"], 2500)
        self.assertGreater(drifting["mad_improvement_ratio"], 0.9)
        self.assertLess(scattered["direction_support"], 0.75)
        self.assertLess(scattered["mad_improvement_ratio"], 0.3)

    def test_trend_stats_ignore_short_baselines_and_tiny_chains(self):
        # Two anchors three seconds apart differing by 400ms imply an absurd rate;
        # only baselines of at least max(20s, 20% of span) may vote on the slope.
        close = [{"lrc_start_ms": t, "delta_ms": d} for t, d in ((10_000, 0), (13_000, 400), (16_000, -300))]
        self.assertEqual(anchor_trend_stats(close, 0)["long_baseline_pairs"], 0)
        self.assertEqual(anchor_trend_stats([{"lrc_start_ms": 0, "delta_ms": 0}], 0)["long_baseline_pairs"], 0)
        self.assertEqual(anchor_trend_stats(None, 0)["drift_over_span_ms"], 0)

    def _pool_item(self, anchor_count):
        return {"result": {"core_anchors": [{"lyric_index": 0}] * anchor_count}}

    def test_candidate_pool_quality_matches_the_real_zhide_lirenfu_case(self):
        # 12 candidates searched under a fingerprint-misidentified title: 8 score
        # zero, the best of the rest clears exactly one anchor -- the real
        # 《值得 (Dj版)》/《离人赋》 case.
        pool = [self._pool_item(1)] * 4 + [self._pool_item(0)] * 8
        quality = candidate_pool_quality(pool)
        self.assertEqual(quality, {"candidate_count": 12, "zero_score_count": 8, "zero_score_ratio": round(2 / 3, 4), "best_anchor_count": 1})
        self.assertTrue(song_identity_suspicious(quality))

    def test_candidate_pool_quality_handles_the_untimed_anchor_count_shape(self):
        # align_standard_lyrics's fallback result carries "anchor_count", not
        # "core_anchors" -- the pool quality helper has to read both shapes.
        pool = [{"result": {"anchor_count": 0}}, {"result": {"anchor_count": 2}}, {"result": {"anchor_count": 0}}]
        quality = candidate_pool_quality(pool)
        self.assertEqual(quality["best_anchor_count"], 2)
        self.assertEqual(quality["zero_score_count"], 2)

    def test_song_identity_suspicious_needs_both_a_weak_winner_and_a_mostly_dead_pool(self):
        # A single weak candidate among otherwise-reasonable ones is "a mediocre
        # lyric version", not "the wrong song" -- suspicion needs the whole pool
        # to have collapsed together, not just the winner to be unimpressive.
        weak_winner_healthy_pool = candidate_pool_quality([self._pool_item(2), self._pool_item(8), self._pool_item(6)])
        self.assertFalse(song_identity_suspicious(weak_winner_healthy_pool))
        strong_winner_dead_pool = candidate_pool_quality([self._pool_item(5)] + [self._pool_item(0)] * 9)
        self.assertFalse(song_identity_suspicious(strong_winner_dead_pool))
        self.assertFalse(song_identity_suspicious(candidate_pool_quality([])))

    def test_song_identity_suspicious_thresholds_are_configurable(self):
        quality = candidate_pool_quality([self._pool_item(3)] + [self._pool_item(0)] * 3)
        self.assertEqual(quality["zero_score_ratio"], 0.75)
        self.assertFalse(song_identity_suspicious(quality))  # best_anchor_count == 3, not < 3
        self.assertTrue(song_identity_suspicious(quality, min_anchor_count=4))
        self.assertFalse(song_identity_suspicious(quality, max_zero_score_ratio=0.9))

    def test_sparse_anchors_still_report_regions_without_condemning_the_song(self):
        # A normally sparse match -- anchors on the 1st and 8th line of a 9-line
        # sheet -- still raises sparse_gap. That is why the caller may only log
        # it: the song itself is perfectly well aligned.
        lrc = parse_lrc("".join("[00:%02d.00]第%d句独特的歌词内容\n" % (10 + i * 5, i) for i in range(9)))
        anchors = [
            {"lyric_index": 0, "asr_index": 0, "asr_start_ms": 10_000, "asr_end_ms": 13_000, "lyric_text": lrc[0]["text"]},
            {"lyric_index": 7, "asr_index": 7, "asr_start_ms": 45_000, "asr_end_ms": 48_000, "lyric_text": lrc[7]["text"]},
        ]
        segments = [asr(row["text"], 10_000 + i * 5000, i) for i, row in enumerate(lrc)]
        regions = find_suspect_anchor_regions(anchors, lrc, segments)
        self.assertEqual([r["reason"] for r in regions], ["sparse_gap"])

    def test_core_and_evidence_anchors_are_returned_separately(self):
        lrc = parse_lrc("[00:10.00]甲乙丙丁戊己\n[00:20.00]庚辛壬癸子丑\n[00:30.00]寅卯辰巳午未")
        result = score_timeline(lrc, [
            asr("甲乙丙丁戊己", 15000, 0),
            asr("庚辛壬癸子丑", 25000, 1),
            asr("寅卯辰巳午未", 35000, 2),
        ])
        self.assertNotIn("anchors", result)
        self.assertGreaterEqual(len(result["evidence_anchors"]), len(result["core_anchors"]))
        self.assertEqual(result["core_anchor_count"], len(result["core_anchors"]))
        self.assertEqual(result["evidence_anchor_count"], len(result["evidence_anchors"]))

    def test_shifted_timeline_does_not_hold_line_through_long_instrumental_gap(self):
        lrc = parse_lrc(
            "[00:10.000]第一句\n[00:15.000]第二句\n[00:20.000]第三句\n"
            "[00:25.000]间奏前\n[00:42.000]间奏后"
        )
        rows = build_shifted_timeline(lrc, 0, 50000)
        before_gap = next(row for row in rows if row["text"] == "间奏前")
        self.assertEqual(before_gap["end_ms"], 30000)
        self.assertFalse(any(row["start_ms"] < 38000 and row["end_ms"] > 32000 for row in rows))

    def test_single_anchor_is_low_confidence(self):
        lrc = parse_lrc("[00:10.00]独特的一句话")
        result = score_timeline(lrc, [asr("独特的一句话", 3000, 0)])
        self.assertEqual(result["core_anchor_count"], 1)
        self.assertTrue(result["low_confidence"])

    def test_zero_anchor_is_rejected(self):
        result = score_timeline(parse_lrc("[00:10.00]歌词"), [asr("主播聊天", 3000, 0)])
        self.assertEqual(result["evidence_anchors"], [])

    def test_untimed_interpolation_is_complete_and_monotonic(self):
        lyrics = plain_lyric_lines("第一句\n漏掉的第二句\n第三句\n结尾")
        evidence = [
            {"standard_line_index": 0, "asr_start_ms": 2000, "segment_ids": [0]},
            {"standard_line_index": 2, "asr_start_ms": 10000, "segment_ids": [2]},
        ]
        rows = estimate_untimed_timeline(lyrics, evidence, 18000)
        self.assertEqual([x["text"] for x in rows], lyrics)
        self.assertTrue(all(a["end_ms"] <= b["start_ms"] for a, b in zip(rows, rows[1:])))
        self.assertTrue(all(0 <= x["start_ms"] < x["end_ms"] <= 18000 for x in rows))

    def test_qwen_words_are_clamped_to_fixed_line(self):
        words = [{"text": "你", "start_ms": 700, "end_ms": 1700}, {"text": "好", "start_ms": 2800, "end_ms": 3400}]
        result = clamp_forced_words(words, 1000, 3000)
        self.assertEqual("".join(item["text"] for item in result), "你好")
        self.assertGreaterEqual(result[0]["start_ms"], 1000)
        self.assertLessEqual(result[-1]["end_ms"], 3000)

    def test_final_render_window_keeps_five_seconds_around_lyrics(self):
        rows = [{"start": 28000, "end": 32000}, {"start": 90000, "end": 95000}]
        self.assertEqual(lyric_render_window(rows, 120000), (23000, 100000))

    def test_final_render_window_does_not_pad_beyond_source(self):
        rows = [{"start": 3000, "end": 98000}]
        self.assertEqual(lyric_render_window(rows, 100000), (0, 100000))

    def test_suspect_regions_empty_when_anchors_look_normal(self):
        lines = [{"start_ms": i * 5000, "text": "四个字词"} for i in range(6)]
        anchors = [
            {"lyric_index": i, "asr_index": i, "asr_start_ms": i * 5000, "asr_end_ms": i * 5000 + 1200, "lyric_text": "四个字词"}
            for i in range(6)
        ]
        segments = [{"start_ms": a["asr_start_ms"], "end_ms": a["asr_end_ms"], "text": "四个字词"} for a in anchors]
        self.assertEqual(find_suspect_anchor_regions(anchors, lines, segments), [])

    def test_suspect_regions_flags_long_duration_anchor(self):
        lines = [{"start_ms": i * 5000, "text": "四个字词"} for i in range(3)]
        anchors = [
            {"lyric_index": 0, "asr_index": 0, "asr_start_ms": 0, "asr_end_ms": 1200, "lyric_text": "四个字词"},
            {"lyric_index": 1, "asr_index": 1, "asr_start_ms": 5000, "asr_end_ms": 11300, "lyric_text": "四个字词"},
            {"lyric_index": 2, "asr_index": 2, "asr_start_ms": 12000, "asr_end_ms": 13200, "lyric_text": "四个字词"},
        ]
        segments = [{"start_ms": a["asr_start_ms"], "end_ms": a["asr_end_ms"], "text": a["lyric_text"]} for a in anchors]
        regions = find_suspect_anchor_regions(anchors, lines, segments)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["reason"], "long_duration")
        self.assertEqual((regions[0]["lyric_start"], regions[0]["lyric_end"]), (1, 2))

    def test_suspect_regions_flags_sparse_gap(self):
        lines = [{"start_ms": i * 5000, "text": "四个字词"} for i in range(8)]
        anchors = [
            {"lyric_index": 0, "asr_index": 0, "asr_start_ms": 0, "asr_end_ms": 1200, "lyric_text": "四个字词"},
            {"lyric_index": 6, "asr_index": 5, "asr_start_ms": 30000, "asr_end_ms": 31200, "lyric_text": "四个字词"},
        ]
        segments = [{"start_ms": i * 5000, "end_ms": i * 5000 + 1200, "text": "杂音或没对上"} for i in range(6)]
        regions = find_suspect_anchor_regions(anchors, lines, segments)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["reason"], "sparse_gap")
        self.assertEqual((regions[0]["lyric_start"], regions[0]["lyric_end"]), (1, 6))
        self.assertEqual((regions[0]["segment_start"], regions[0]["segment_end"]), (1, 4))

    def test_suspect_regions_long_duration_at_end_falls_back_to_line_count(self):
        lines = [{"start_ms": i * 5000, "text": "四个字词"} for i in range(5)]
        anchors = [
            {"lyric_index": 0, "asr_index": 0, "asr_start_ms": 0, "asr_end_ms": 1200, "lyric_text": "四个字词"},
            {"lyric_index": 4, "asr_index": 1, "asr_start_ms": 20000, "asr_end_ms": 26300, "lyric_text": "四个字词"},
        ]
        segments = [{"start_ms": 0, "end_ms": 1200, "text": "四个字词"}, {"start_ms": 20000, "end_ms": 26300, "text": "四个字词"}]
        regions = find_suspect_anchor_regions(anchors, lines, segments)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["reason"], "long_duration")
        self.assertEqual(regions[0]["lyric_end"], 5)

    def test_suspect_regions_caps_to_max_regions(self):
        indexes = [0, 1, 3, 6, 10, 15, 21, 28]
        lines = [{"start_ms": i * 5000, "text": "四个字词"} for i in range(30)]
        anchors = [
            {"lyric_index": li, "asr_index": position, "asr_start_ms": position * 5000, "asr_end_ms": position * 5000 + 5000, "lyric_text": "四个字词"}
            for position, li in enumerate(indexes)
        ]
        segments = [{"start_ms": a["asr_start_ms"], "end_ms": a["asr_end_ms"], "text": "四个字词"} for a in anchors]
        regions = find_suspect_anchor_regions(anchors, lines, segments)
        self.assertEqual(len(regions), 5)
        self.assertTrue(all(r["reason"] == "long_duration" for r in regions))
        spans = sorted(r["lyric_end"] - r["lyric_start"] for r in regions)
        self.assertEqual(spans, [3, 4, 5, 6, 7])

    def test_is_high_confidence(self):
        self.assertTrue(is_high_confidence({"low_confidence": False}))
        self.assertFalse(is_high_confidence({"low_confidence": True}))
        self.assertFalse(is_high_confidence({}))

    def test_full_realign_accepts_valid_lines_and_sorts_by_start(self):
        lines = [{"text": "第0行"}, {"text": "第1行"}, {"text": "第2行"}]
        payload = {"lines": [
            {"index": 2, "text": "第2行", "start_ms": 9000, "end_ms": 9500},
            {"index": 0, "text": "第0行", "start_ms": 5000, "end_ms": 5500},
        ]}
        resolved = resolve_deepseek_full_realign(payload, lines, asr_min_ms=4000, asr_max_ms=10000)
        self.assertEqual([item["standard_line_index"] for item in resolved], [0, 2])
        self.assertEqual(resolved[0]["start_ms"], 5000)

    def test_full_realign_clamps_to_real_asr_range(self):
        lines = [{"text": "第0行"}]
        payload = {"lines": [{"index": 0, "text": "第0行", "start_ms": 100, "end_ms": 99999}]}
        resolved = resolve_deepseek_full_realign(payload, lines, asr_min_ms=5000, asr_max_ms=20000)
        self.assertEqual(resolved[0]["start_ms"], 5000)
        self.assertEqual(resolved[0]["end_ms"], 20000)

    def test_full_realign_rejects_out_of_range_index_and_bad_types(self):
        lines = [{"text": "第0行"}]
        payload = {"lines": [
            {"index": 5, "text": "不存在的行", "start_ms": 1000, "end_ms": 2000},
            {"index": 0, "text": "第0行", "start_ms": "not-a-number", "end_ms": 2000},
            {"index": 0},
        ]}
        self.assertEqual(resolve_deepseek_full_realign(payload, lines, asr_min_ms=0, asr_max_ms=5000), [])

    def test_full_realign_falls_back_to_local_lyric_text_when_missing(self):
        lines = [{"text": "本地文本"}]
        payload = {"lines": [{"index": 0, "start_ms": 1000, "end_ms": 2000}]}
        resolved = resolve_deepseek_full_realign(payload, lines, asr_min_ms=0, asr_max_ms=5000)
        self.assertEqual(resolved[0]["text"], "本地文本")

    def test_full_realign_handles_malformed_payload(self):
        self.assertEqual(resolve_deepseek_full_realign({}, [{"text": "x"}], 0, 1000), [])
        self.assertEqual(resolve_deepseek_full_realign({"lines": "not-a-list"}, [{"text": "x"}], 0, 1000), [])
        self.assertEqual(resolve_deepseek_full_realign(None, [{"text": "x"}], 0, 1000), [])


if __name__ == "__main__":
    unittest.main()
