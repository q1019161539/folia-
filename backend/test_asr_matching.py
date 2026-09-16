import unittest
from asr_matching import align


def segment(text, start, end, index):
    return {'line_id': index, 'text': text, 'start_ms': start, 'end_ms': end}


def run(lyrics, segments):
    return align(lyrics, segments, lambda s: [], lambda w: [])


class EvidenceMatchingTests(unittest.TestCase):
    def test_typo_and_partial_are_preserved(self):
        rows = run(['天昏地暗', '就算生命像尘埃分不开'], [segment('天宽地暗', 1000, 4000, 0), segment('就算生', 49000, 50500, 1), segment('像尘埃', 51000, 52500, 2)])
        self.assertEqual([r['text'] for r in rows], ['天昏地暗','就算生命像尘埃'])
        self.assertTrue(rows[1]['partial'])
        self.assertNotIn('分不开', rows[1]['text'])
        self.assertEqual(rows[1]['segment_ids'], [1,2])

    def test_missing_song_and_chat_do_not_become_lyrics(self):
        rows = run(['如果这天地','你的爱','时候'], [segment('谢谢你的灯牌', 73000, 75000, 0),segment('所以到时候周日你们来嘛', 120000, 125000, 1)])
        self.assertEqual(rows, [])

    def test_repeated_chorus_retains_both_occurrences(self):
        rows = run(['我们也许反而更相信爱'], [segment('我们也许反而更伤心爱',1000,5000,0),segment('我们也许反而更伤心爱',110000,114000,1)])
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['start_ms'] for r in rows], [1000,110000])
        self.assertTrue(all(r['text']=='我们也许反而更相信爱' for r in rows))

    def test_single_asr_segment_can_cover_two_lyric_lines(self):
        rows = run(['天昏地暗','世界可以忽然什么都没有'], [segment('天昏地暗世界可以忽然什么都没有',1000,9000,0)])
        self.assertEqual([r['text'] for r in rows], ['天昏地暗','世界可以忽然什么都没有'])
        self.assertLessEqual(rows[0]['end_ms'], rows[1]['start_ms'])

    def test_long_gap_not_filled(self):
        rows = run(['就算生命像尘埃分不开'], [segment('就算生',49000,50500,0),segment('像尘埃',71000,72500,1)])
        self.assertTrue(all(not(r['start_ms'] < 68000 and r['end_ms'] > 61000) for r in rows))
        self.assertTrue(all('分不开' not in r['text'] for r in rows))

    def test_unmatched_segment_prefix_does_not_discard_supported_suffix(self):
        rows = run(['我要你的全部', '赐我被你爱的天赋'], [segment('乱全部赐我被你爱的天赋', 0, 2200, 0)])
        self.assertEqual([r['text'] for r in rows], ['全部', '赐我被你爱的天赋'])

    def test_ordered_weak_segment_corrects_bad_asr_without_filling_a_gap(self):
        rows = run(['敏感又热烈', '只想霸占你的世界', '我可以付出一切代价'], [
            segment('敏感又热烈', 1000, 2200, 0),
            segment('这样霸诊的时间', 2200, 3600, 1),
            segment('我可以付出一切代价', 3600, 5200, 2),
        ])
        self.assertEqual([r['text'] for r in rows], ['敏感又热烈', '只想霸占你的世界', '我可以付出一切代价'])
        self.assertEqual(rows[1]['evidence_strength'], 'ordered-weak')
        self.assertGreater(rows[1]['end_ms'], rows[1]['start_ms'])

    def test_ordered_weak_segment_requires_a_recent_anchor(self):
        rows = run(['敏感又热烈', '只想霸占你的世界'], [
            segment('敏感又热烈', 1000, 2200, 0),
            segment('这样霸诊的时间', 12000, 13400, 1),
        ])
        self.assertEqual([r['text'] for r in rows], ['敏感又热烈'])

    def test_equal_length_ordered_line_survives_many_homophone_errors(self):
        rows = run(['我的刁蛮和任性恶名昭彰', '我偷丘比特的箭朝你投标枪'], [
            segment('我的刁明任性恶名昭昭', 1000, 2600, 0),
            segment('我投球别的剑唱头飘唱', 2600, 4300, 1),
        ])
        self.assertEqual(rows[-1]['text'], '我偷丘比特的箭朝你投标枪')
        self.assertEqual(rows[-1]['evidence_strength'], 'ordered-weak')

    def test_segment_prefix_is_kept_before_matching_following_line(self):
        rows = run(['我会把一切都献出', '我要你的全部', '赐我被你爱的天赋'], [
            segment('我会把一切都献出', 1000, 2500, 0),
            segment('我要爱的天赋', 2500, 5000, 1),
        ])
        self.assertEqual([r['text'] for r in rows], ['我会把一切都献出', '我要', '爱的天赋'])


if __name__ == '__main__': unittest.main()
