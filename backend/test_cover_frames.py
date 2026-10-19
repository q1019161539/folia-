import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageFilter
from cover_frames import frame_metrics, rank_candidates, sample_times, select_reference_frame, validate_region


def texture():
    rng = random.Random(23)
    image = Image.new('L', (320, 180))
    image.putdata([rng.randrange(40, 215) for _ in range(320*180)])
    return image


class CoverFramesTests(unittest.TestCase):
    def test_times_skip_edges(self):
        times = sample_times(100)
        self.assertEqual(len(times), 12)
        self.assertEqual((times[0], times[-1]), (10, 90))

    def test_invalid_inputs(self):
        for duration in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): sample_times(duration)
        with self.assertRaises(ValueError): sample_times(100, 100)
        for region in ([0, 0, 2, 1], [1, 0, 0, 1], [0, float('nan'), 1, 1], [0]):
            with self.assertRaises(ValueError): validate_region(region)

    def test_black_and_white_rejected(self):
        self.assertEqual(frame_metrics(Image.new('L', (320, 180), 0))['rejection'], 'too_dark')
        self.assertEqual(frame_metrics(Image.new('L', (320, 180), 255))['rejection'], 'too_bright')

    def test_blur_and_uniform_rejected(self):
        self.assertEqual(frame_metrics(Image.new('L', (320, 180), 128))['rejection'], 'too_blurry')
        self.assertGreater(frame_metrics(texture())['sharpness'], frame_metrics(texture().filter(ImageFilter.GaussianBlur(5)))['sharpness'])

    def test_roi_ignores_sharp_chat(self):
        image = texture()
        image.paste(128, (160, 0, 320, 180))
        self.assertEqual(frame_metrics(image, [.5, 0, 1, 1])['rejection'], 'too_blurry')
        self.assertEqual(frame_metrics(image, [0, 0, .5, 1])['rejection'], '')

    def test_duplicate_keeps_best(self):
        rows = [{'time_seconds': 10, 'score': 2, 'hash': '0000000000000001', 'rejection': ''},
                {'time_seconds': 20, 'score': 4, 'hash': '0000000000000000', 'rejection': ''}]
        self.assertEqual(rank_candidates(rows)[0]['time_seconds'], 20)
        self.assertEqual(rows[0]['duplicate_of'], 20)

    def test_tie_is_stable(self):
        rows = [{'time_seconds': t, 'score': 4, 'hash': '0000000000000000', 'rejection': ''} for t in (20, 10)]
        self.assertEqual(rank_candidates(rows)[0]['time_seconds'], 10)

    def test_selection_persists_and_reuses(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / 'source.mp4'
            video.write_bytes(b'untouched')
            before = video.stat()
            def extract(_video, _time, target, preview=False): texture().save(target)
            with patch('cover_frames.run') as probe, patch('cover_frames.extract_frame', side_effect=extract) as extraction:
                probe.return_value.stdout = b'{"format":{"duration":"100"}}'
                first = select_reference_frame(video, Path(root)/'out', streamer='test', regions={'test':[0,0,1,1]})
                self.assertEqual(first['status'], 'selected')
                self.assertEqual(extraction.call_count, 13)
                extraction.reset_mock()
                second = select_reference_frame(video, Path(root)/'out', streamer='test', regions={'test':[0,0,1,1]})
                self.assertTrue(second['cached'])
                extraction.assert_not_called()
                self.assertEqual(second['time_seconds'], first['time_seconds'])
                self.assertEqual((before.st_size, before.st_mtime_ns), (video.stat().st_size, video.stat().st_mtime_ns))
                self.assertEqual(video.read_bytes(), b'untouched')
                Path(first['frame_path']).write_bytes(b'corrupt')
                restored = select_reference_frame(video, Path(root)/'out', streamer='test', regions={'test':[0,0,1,1]})
                self.assertFalse(restored['cached'])

    def test_no_good_frame_needs_manual_review(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root)/'source.mp4'; video.write_bytes(b'untouched')
            def extract(_video, _time, target, preview=False): Image.new('L', (320,180), 0).save(target)
            with patch('cover_frames.run') as probe, patch('cover_frames.extract_frame', side_effect=extract) as extraction:
                probe.return_value.stdout = b'{"format":{"duration":"100"}}'
                result = select_reference_frame(video, Path(root)/'out')
                self.assertEqual(result['status'], 'manual_review')
                self.assertNotIn('frame_path', result)
                self.assertEqual(extraction.call_count, 12)
                self.assertTrue(select_reference_frame(video, Path(root)/'out')['cached'])

    def test_concurrent_lock_prevents_extraction(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root)/'source.mp4'; video.write_bytes(b'untouched')
            with patch('cover_frames.run') as probe, patch('cover_frames.extract_frame', side_effect=OSError('bad')):
                probe.return_value.stdout = b'{"format":{"duration":"100"}}'
                result = select_reference_frame(video, Path(root)/'out')
            folder = Path(result['manifest']).parent
            Path(result['manifest']).unlink()
            (folder/'selection.lock').write_text('123')
            with patch('cover_frames.extract_frame') as extraction:
                with self.assertRaises(FileExistsError): select_reference_frame(video, Path(root)/'out')
                extraction.assert_not_called()

    def test_source_change_not_cached(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root)/'source.mp4'; video.write_bytes(b'original')
            def extract(_video, _time, target, preview=False):
                texture().save(target)
                video.write_bytes(b'changed source')
            with patch('cover_frames.run') as probe, patch('cover_frames.extract_frame', side_effect=extract):
                probe.return_value.stdout = b'{"format":{"duration":"100"}}'
                with self.assertRaisesRegex(ValueError, 'source video changed'): select_reference_frame(video, Path(root)/'out')
            self.assertFalse(list((Path(root)/'out').glob('*/selection.json')))


if __name__ == '__main__': unittest.main()
