"""Cheap post-clip screening, not a singer/voice identity classifier."""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import subprocess

VERSION = 'quiet-clip-v2-any'
DEFAULT_MEAN_DB = -30.0
DEFAULT_PEAK_DB = -15.0


def gate_settings():
    enabled = os.getenv('PERFORMANCE_GATE_ENABLED', '1') == '1'
    mean = float(os.getenv('PERFORMANCE_GATE_MEAN_DB', str(DEFAULT_MEAN_DB)))
    peak = float(os.getenv('PERFORMANCE_GATE_PEAK_DB', str(DEFAULT_PEAK_DB)))
    if not all(math.isfinite(value) and -100 <= value <= -5 for value in (mean, peak)) or mean >= peak:
        raise ValueError('切片响度筛查阈值无效')
    return {'enabled': enabled, 'mean_db': mean, 'peak_db': peak, 'logic': 'any'}


def parse_volume(stderr: str):
    matches = dict(re.findall(r'(mean_volume|max_volume):\s*(-inf|[-+]?\d+(?:\.\d+)?)\s*dB', stderr))
    if set(matches) != {'mean_volume', 'max_volume'}:
        raise RuntimeError('无法取得切片音频电平，已停止后续处理，请重试或人工核对')
    return {key: -120.0 if value == '-inf' else float(value) for key, value in matches.items()}


def decide_volume(mean_db: float, peak_db: float, settings: dict):
    if not all(math.isfinite(value) and value <= 0 for value in (mean_db, peak_db)):
        raise RuntimeError('切片音频电平无效，已停止后续处理')
    # Fail closed for quiet clips: either low average OR low peak is sufficient.
    skip = mean_db <= settings['mean_db'] or peak_db <= settings['peak_db']
    return {'decision': 'skip' if skip else 'pass',
            'reason_code': 'suspected_quiet_background' if skip else 'audio_level_pass',
            'mean_db': mean_db, 'peak_db': peak_db,
            'reason': (f'疑似低响度背景音乐/演唱不足，跳过后续流程（平均 {mean_db:.1f} dB，峰值 {peak_db:.1f} dB）'
                       if skip else '响度筛查通过；此结果不证明主播本人演唱')}


def screen_clip(path, previous=None, settings=None):
    settings = gate_settings() if settings is None else settings
    if not settings['enabled']:
        return {'version': VERSION, 'decision': 'disabled', 'reason': '切片响度筛查已关闭', 'settings': settings}
    path = Path(path).resolve()
    if not path.is_file():
        raise RuntimeError('切片文件不存在，无法进行演唱筛查')
    stat = path.stat()
    fingerprint = {'path': str(path), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    if previous and previous.get('version') == VERSION and previous.get('input') == fingerprint and previous.get('settings') == settings and previous.get('decision') in ('pass', 'skip'):
        return previous
    try:
        result = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-threads', '1', '-i', str(path),
                                 '-map', '0:a:0', '-vn', '-sn', '-dn', '-af', 'volumedetect', '-f', 'null', '-'],
                                capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('切片音频筛查不可用或超时，已停止后续处理，请重试') from exc
    if result.returncode:
        raise RuntimeError('切片音频解码失败或没有音轨，已停止后续处理，请核对源文件')
    values = parse_volume(result.stderr)
    return {'version': VERSION, 'input': fingerprint, 'settings': settings,
            **decide_volume(values['mean_volume'], values['max_volume'], settings)}
