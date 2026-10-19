"""Offline reference-frame selection. No network, identity edits or video writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageStat

VERSION = 'local-quality-v1'


def validate_region(region):
    if region is None:
        return [0.0, 0.0, 1.0, 1.0]
    if len(region) != 4 or any(not math.isfinite(float(v)) for v in region):
        raise ValueError('region must contain four finite normalized coordinates')
    x0, y0, x1, y1 = map(float, region)
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError('region must satisfy 0 <= left < right <= 1 and top < bottom')
    return [x0, y0, x1, y1]


def sample_times(duration, count=12):
    if not math.isfinite(duration) or duration <= 0 or not 2 <= count <= 24:
        raise ValueError('invalid duration or candidate count')
    return [round(duration * (0.1 + 0.8 * i / (count - 1)), 6) for i in range(count)]


def frame_metrics(image, region=None):
    """Score only the configured subject area, always at the same analysis scale."""
    x0, y0, x1, y1 = validate_region(region)
    width, height = image.size
    crop = image.crop((int(x0*width), int(y0*height), int(x1*width), int(y1*height)))
    if min(crop.size) < 16:
        raise ValueError('subject region is too small')
    gray = crop.convert('L').resize((160, 160), Image.Resampling.LANCZOS)
    pixels = list(gray.tobytes())
    mean = ImageStat.Stat(gray).mean[0]
    black = sum(v < 16 for v in pixels) / len(pixels)
    white = sum(v > 245 for v in pixels) / len(pixels)
    lap = [4*pixels[y*160+x] - pixels[y*160+x-1] - pixels[y*160+x+1]
           - pixels[(y-1)*160+x] - pixels[(y+1)*160+x]
           for y in range(1, 159) for x in range(1, 159)]
    average = sum(lap) / len(lap)
    sharpness = sum((v-average)**2 for v in lap) / len(lap)
    thumb = list(gray.resize((9, 8), Image.Resampling.LANCZOS).tobytes())
    dhash = sum(int(thumb[y*9+x] > thumb[y*9+x+1]) << (y*8+x)
                for y in range(8) for x in range(8))
    reason = ('too_dark' if mean < 25 or black > .85 else
              'too_bright' if mean > 235 or white > .85 else
              'too_blurry' if sharpness < 20 else '')
    # Brightness is a soft tie-breaker, not a reward for a pale face/background.
    score = math.log1p(sharpness) - abs(mean - 128) / 255
    return {'brightness': round(mean, 3), 'sharpness': round(sharpness, 3),
            'black_fraction': round(black, 4), 'white_fraction': round(white, 4),
            'hash': f'{dhash:016x}', 'score': round(score, 6), 'rejection': reason}


def rank_candidates(candidates):
    """Retain the strongest representative of perceptually similar subject crops."""
    kept = []
    for row in sorted(candidates, key=lambda r: (-r['score'], r['time_seconds'])):
        if row.get('rejection'):
            continue
        duplicate = next((other for other in kept
                          if (int(row['hash'], 16) ^ int(other['hash'], 16)).bit_count() <= 4), None)
        if duplicate:
            row['rejection'] = 'duplicate'
            row['duplicate_of'] = duplicate['time_seconds']
        else:
            kept.append(row)
    return kept


def run(command):
    return subprocess.run(command, check=True, capture_output=True, timeout=60)


def extract_frame(video, seconds, target, preview=False):
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
               '-threads', '1', '-ss', str(seconds), '-i', str(video),
               '-map', '0:v:0', '-frames:v', '1', '-an', '-threads', '1']
    if preview:
        command += ['-vf', 'scale=640:-2', '-filter_threads', '1']
    run(command + ['-n', str(target)])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_reference_frame(video, output_root, *, streamer='', regions=None, count=12):
    video = Path(video).resolve(strict=True)
    if not video.is_file():
        raise ValueError('video is not a file')
    region_configured = streamer in (regions or {})
    region = validate_region((regions or {}).get(streamer))
    before = video.stat()
    identity = {'version': VERSION, 'video': str(video), 'size': before.st_size,
                'mtime_ns': before.st_mtime_ns, 'region': region, 'count': count,
                'streamer': streamer, 'region_configured': region_configured}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    directory = Path(output_root).resolve() / key
    if directory == video or directory.is_relative_to(video):
        raise ValueError('output must be separate from source video')
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / 'selection.json'
    def cached_selection():
        if not manifest.exists():
            return None
        result = json.loads(manifest.read_text(encoding='utf-8'))
        selected = directory / result.get('frame_file', 'reference.png')
        if result.get('input') == identity and result.get('status') == 'manual_review':
            return {**result, 'cached': True, 'manifest': str(manifest)}
        if (result.get('input') == identity and result.get('status') == 'selected'
                and selected.is_file() and digest(selected) == result.get('frame_sha256')):
            return {**result, 'cached': True, 'frame_path': str(selected), 'manifest': str(manifest)}
        return None
    cached = cached_selection()
    if cached:
        return cached
    lock = directory / 'selection.lock'
    # Concurrent callers never perform a second extraction. A crash lock is explicit,
    # not silently stolen; remove only after verifying the old process has stopped.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        cached = cached_selection()
        if cached:
            return cached
        attempt = Path(tempfile.mkdtemp(prefix='attempt-', dir=directory))
        probe = json.loads(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'json', str(video)]).stdout)
        duration = float(probe['format']['duration'])
        candidates = []
        for index, seconds in enumerate(sample_times(duration, count)):
            target = attempt / f'candidate-{index:02d}.png'
            try:
                extract_frame(video, seconds, target, preview=True)
                with Image.open(target) as image:
                    metrics = frame_metrics(image, region)
                candidates.append({'time_seconds': seconds, 'file': str(target.relative_to(directory)), **metrics})
            except (subprocess.SubprocessError, OSError, ValueError) as exc:
                candidates.append({'time_seconds': seconds, 'score': -1, 'rejection': 'extraction_failed',
                                   'error_type': type(exc).__name__})
        ranked = rank_candidates(candidates)
        result = {'input': identity, 'duration_seconds': duration, 'candidates': candidates,
                  'status': 'manual_review', 'reason': 'no_acceptable_frame', 'cached': False}
        if ranked:
            winner = ranked[0]
            frame = attempt / 'reference.png'
            extract_frame(video, winner['time_seconds'], frame)
            with Image.open(frame) as image:
                image.load()
                if image.format != 'PNG' or min(image.size) < 16:
                    raise ValueError('invalid extracted reference')
                size = list(image.size)
            result.update(status='selected', reason='best_local_quality_after_deduplication',
                          time_seconds=winner['time_seconds'], dimensions=size,
                          frame_file=str(frame.relative_to(directory)), frame_sha256=digest(frame))
        after = video.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('source video changed while selecting')
        temporary = attempt / 'selection.json'
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(manifest)
        return {**result, 'manifest': str(manifest),
                **({'frame_path': str(directory / result['frame_file'])} if ranked else {})}
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--streamer', default='')
    parser.add_argument('--regions', help='UTF-8 JSON: streamer -> normalized [left,top,right,bottom]')
    args = parser.parse_args()
    regions = json.loads(Path(args.regions).read_text(encoding='utf-8')) if args.regions else {}
    print(json.dumps(select_reference_frame(args.video, args.output_root, streamer=args.streamer,
                                           regions=regions), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
