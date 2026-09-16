from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def extract_pcm(input_path: Path, output_path: Path, limit_seconds: float | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if limit_seconds is not None:
        command += ["-t", f"{limit_seconds:.3f}"]
    command += [
        "-i",
        str(input_path),
        "-map",
        "0:a:0?",
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    run(command)


def detect_voice_regions(input_path: Path, duration: float, *, noise_db: int = -38, min_silence: float = 0.45) -> list[tuple[float, float]]:
    """Return non-silent regions in source time; never rewrite the source timeline."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(input_path), "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silence_start: float | None = None; regions: list[tuple[float, float]] = []; cursor = 0.0; in_silence = False
    for line in result.stderr.splitlines():
        match = re.search(r"silence_start: ([0-9.]+)", line)
        if match:
            silence_start = float(match.group(1)); regions.append((cursor, silence_start)); in_silence = True; continue
        match = re.search(r"silence_end: ([0-9.]+)", line)
        if match: cursor = float(match.group(1)); in_silence = False
    if silence_start is None: return [(0.0, duration)]
    if not in_silence and cursor < duration: regions.append((cursor, duration))
    return [(max(0.0,start), min(duration,end)) for start,end in regions if end-start >= 0.12]


def extract_voice_regions(input_path: Path, regions: list[tuple[float, float]], output_dir: Path, chunk_seconds: int = 180) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[dict[str, object]] = []
    index = 0
    for region_start, region_end in regions:
        start = region_start
        while start < region_end:
            end = min(region_end, start + chunk_seconds)
            path = output_dir / f"voice-{index:04d}.wav"
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{end-start:.3f}", "-i", str(input_path), "-map", "0:a:0?", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(path)])
            chunks.append({"path": path, "offset": start, "duration": end-start}); index += 1; start = end
    return chunks


def normalize_pcm(input_path: Path, output_path: Path) -> None:
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def split_audio(input_path: Path, chunks_dir: Path, chunk_seconds: int) -> list[dict[str, object]]:
    chunks_dir.mkdir(parents=True, exist_ok=True)
    for old in chunks_dir.glob("chunk-*.wav"):
        old.unlink()
    pattern = chunks_dir / "chunk-%04d.wav"
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-reset_timestamps",
            "1",
            "-c:a",
            "pcm_s16le",
            str(pattern),
        ]
    )
    chunks: list[dict[str, object]] = []
    offset = 0.0
    for path in sorted(chunks_dir.glob("chunk-*.wav")):
        duration = probe_duration(path)
        chunks.append({"path": path, "offset": offset, "duration": duration})
        offset += duration
    return chunks
