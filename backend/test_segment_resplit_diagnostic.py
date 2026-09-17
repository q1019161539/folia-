import unittest

from segment_resplit_diagnostic import (
    CLEAR_GAP_MS,
    _boundary_between,
    collect_occurrences,
    normalize_lyric_text,
    required_anchors,
    resplit_diagnostic,
)


def provider_row(text, start, step=400):
    return {
        "text": text,
        "start_ms": start,
        "words": [
            {"text": ch, "start_ms": start + i * step, "end_ms": start + (i + 1) * step}
            for i, ch in enumerate(text)
        ],
    }


def qwen_segment(pieces, start_ms, end_ms=None, step=400):
    """pieces: list of (text, gap_before_ms). One ASR segment whose Qwen
    characters run consecutively, with an optional silence before each piece."""
    words, cursor = [], start_ms
    for text, gap_before in pieces:
        cursor += gap_before
        for ch in text:
            words.append({"text": ch, "start_ms": cursor, "end_ms": cursor + step,
                          "timing_source": "qwen-forced-aligner"})
            cursor += step
    return {
        "text": "".join(text for text, _ in pieces),
        "start_ms": start_ms,
        "end_ms": end_ms if end_ms is not None else cursor,
        "words": words,
    }


class ThresholdTests(unittest.TestCase):
    def test_short_lines_are_not_asked_for_impossible_coverage(self):
        # A flat bar of 5 would demand 83% of a 6-char line -- the exact reason
        # 《很任性》 produced no proposals at all before the scaled rule.
        self.assertEqual(required_anchors(6), 4)
        self.assertEqual(required_anchors(4), 4)

    def test_long_lines_stay_reachable(self):
        self.assertEqual(required_anchors(30), 8)
        self.assertEqual(required_anchors(14), 5)

    def test_normalization_ignores_spacing_and_punctuation(self):
        self.assertEqual(normalize_lyric_text("一个人很寂寞 另一个很洒脱"),
                         normalize_lyric_text("一个人很寂寞，另一个很洒脱"))


class BoundaryTests(unittest.TestCase):
    def test_a_real_silence_is_preferred_over_the_midpoint(self):
        chars = [{"start_ms": 1000, "end_ms": 1400}, {"start_ms": 3000, "end_ms": 3400}]
        result = _boundary_between(chars, 1400, 3000)
        self.assertEqual(result["method"], "gap_strong")
        self.assertEqual(result["gap_ms"], 1600)
        self.assertEqual(result["boundary_ms"], 2200)

    def test_without_a_real_pause_it_falls_back_to_the_midpoint(self):
        # Consecutive chorus lines often have no pause at all between them --
        # the cut still lands somewhere, but the report must say it was a guess.
        chars = [{"start_ms": 1000, "end_ms": 1400}, {"start_ms": 1500, "end_ms": 1900}]
        result = _boundary_between(chars, 1400, 1500)
        self.assertEqual(result["method"], "midpoint")
        self.assertLess(result["gap_ms"], CLEAR_GAP_MS)
        self.assertEqual(result["boundary_ms"], 1450)


class ResplitDiagnosticTests(unittest.TestCase):
    def test_two_distinct_lyric_texts_inside_one_segment_produce_a_cut(self):
        rows = [provider_row("我们的世界尽头在那一夜", 0), provider_row("你送的胭脂扣是我心头", 20000)]
        asr = [qwen_segment([("我们的世界尽头在那一夜", 0), ("你送的胭脂扣是我心头", 1200)], 10000)]
        result = resplit_diagnostic(rows, asr)
        self.assertEqual(result["proposed_segment_count"], 1)
        self.assertEqual(result["proposed_cut_count"], 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["cuts"][0]["method"], "gap_strong")
        first_end = proposal["occurrences"][0]["last_ms"]
        second_start = proposal["occurrences"][1]["first_ms"]
        self.assertTrue(first_end < proposal["cuts"][0]["boundary_ms"] < second_start)

    def test_repeated_chorus_copies_fold_into_one_occurrence(self):
        # The real 《很任性》/《离人赋》 shape: the standard lyrics write the same
        # chorus line several times, so several lyric_index values all match the
        # same sung moment. That is one occurrence with several possible owners,
        # not several pieces of evidence -- and on its own it cannot cut.
        chorus = "你送的胭脂扣是我心头"
        rows = [provider_row(chorus, 0), provider_row("中间隔开的另外一句话", 5000),
                provider_row(chorus, 10000), provider_row(chorus, 30000)]
        asr = [qwen_segment([(chorus, 0)], 10000)]
        result = resplit_diagnostic(rows, asr)
        occurrences = collect_occurrences(rows, asr)[0]
        same_text = [o for o in occurrences if o["canonical_text"] == normalize_lyric_text(chorus)]
        self.assertEqual(len(same_text), 1)
        self.assertEqual(same_text[0]["candidate_lyric_indexes"], [0, 2, 3])
        self.assertEqual(result["proposed_segment_count"], 0)

    def test_a_single_occurrence_never_proposes_a_cut(self):
        rows = [provider_row("我们的世界尽头在那一夜", 0)]
        asr = [qwen_segment([("我们的世界尽头在那一夜", 0), ("完全不相干的一段闲话", 1500)], 10000)]
        result = resplit_diagnostic(rows, asr)
        self.assertEqual(result["proposed_segment_count"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "not_enough_normal_occurrences")

    def test_a_short_line_joins_once_two_normal_occurrences_agree(self):
        # 《很任性》 asr[12]: "很任性的执着" is heard as "人人心的执着", leaving only
        # 3 matching characters -- too weak to cut on its own, but real structure
        # once the segment is already proven to hold two other lyric texts.
        rows = [provider_row("我们的世界尽头在那一夜", 0),
                provider_row("很任性的执着", 20000),
                provider_row("你送的胭脂扣是我心头", 40000)]
        asr = [qwen_segment([("我们的世界尽头在那一夜", 0), ("人人心的执着", 1200),
                             ("你送的胭脂扣是我心头", 1200)], 10000)]
        result = resplit_diagnostic(rows, asr)
        self.assertEqual(result["proposed_segment_count"], 1)
        self.assertEqual(result["proposed_cut_count"], 2)
        self.assertEqual(result["bridge_used_count"], 1)
        strengths = [ps["strength"] for ps in result["proposals"][0]["pseudo_segments"]]
        self.assertEqual(strengths, ["normal", "bridge", "normal"])

    def test_short_lines_alone_can_never_trigger_a_split(self):
        # Same weak evidence, but with no normal-strength occurrence to
        # corroborate the segment -- nothing may be cut.
        rows = [provider_row("很任性的执着", 0), provider_row("很任性的哭着", 20000)]
        asr = [qwen_segment([("人人心的执着", 0), ("人人心的哭着", 1200)], 10000)]
        result = resplit_diagnostic(rows, asr)
        self.assertEqual(result["proposed_segment_count"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "not_enough_normal_occurrences")

    def test_a_line_anchored_elsewhere_may_still_prove_this_segment(self):
        # Split evidence deliberately does NOT respect the line-level chain's
        # attribution: a chorus line placed at segment 0 by the chain can still
        # show that the same text was sung inside segment 1. What it must not do
        # is claim this position IS that lyric_index -- hence candidates only.
        rows = [provider_row("我们的世界尽头在那一夜", 0), provider_row("你送的胭脂扣是我心头", 20000)]
        asr = [qwen_segment([("我们的世界尽头在那一夜", 0)], 10000),
               qwen_segment([("我们的世界尽头在那一夜", 0), ("你送的胭脂扣是我心头", 1500)], 60000)]
        result = resplit_diagnostic(rows, asr)
        proposals = {p["asr_index"]: p for p in result["proposals"]}
        self.assertIn(1, proposals)
        self.assertEqual(proposals[1]["pseudo_segments"][0]["candidate_lyric_indexes"], [0])

    def test_an_occurrence_whose_span_swallows_another_cannot_be_cut_between(self):
        # A line whose few matched characters are scattered across the whole
        # segment has a huge span and a midpoint that can sit >700ms from a
        # tight neighbour's -- centre distance alone would call them separate
        # and then place a boundary inside both. On real songs that produced
        # overlapping and even negative-length pseudo-segments (和你一样 -2720ms),
        # so the spans themselves have to clear before a cut is defined.
        scattered = "的一个我是你那有在了着"  # common characters, spread over everything
        rows = [provider_row(scattered, 0),
                provider_row("我们的世界尽头在那一夜", 20000),
                provider_row("你送的胭脂扣是我心头", 40000)]
        asr = [qwen_segment([("我们的世界尽头在那一夜", 0), ("你送的胭脂扣是我心头", 1200)], 10000)]
        result = resplit_diagnostic(rows, asr)
        for proposal in result["proposals"]:
            edges = [ps["start_ms"] for ps in proposal["pseudo_segments"]]
            edges += [proposal["pseudo_segments"][-1]["end_ms"]]
            self.assertEqual(edges, sorted(edges))
            for ps in proposal["pseudo_segments"]:
                self.assertGreater(ps["end_ms"], ps["start_ms"])
            for left, right in zip(proposal["occurrences"], proposal["occurrences"][1:]):
                self.assertGreater(right["first_ms"], left["last_ms"])

    def test_a_segment_with_no_qwen_characters_yields_nothing(self):
        rows = [provider_row("我们的世界尽头在那一夜", 0)]
        asr = [{"text": "我们的世界尽头在那一夜", "start_ms": 10000, "end_ms": 14000, "words": []}]
        result = resplit_diagnostic(rows, asr)
        self.assertEqual(result["occurrence_count"], 0)
        self.assertEqual(result["proposed_segment_count"], 0)


if __name__ == "__main__":
    unittest.main()
