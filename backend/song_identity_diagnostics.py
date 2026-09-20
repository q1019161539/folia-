"""Standalone A/B diagnostic for a second song-identification source (ACRCloud) against Shazam.

Not wired into the production pipeline (app.py/auto_standard_timeline_task) at all --
this only reads a media file and prints/returns a per-window report. Phase 1 per the
project's real bad case (值得(Dj版)/在他乡/胭脂扣, all wrong -- real song is 云汐《离人赋》):
find out whether ACRCloud is actually more reliable on the same clips before writing
any code that would let it touch a job's title or the standard-timeline pipeline.

Run directly: python song_identity_diagnostics.py <media_path> [--duration-ms N]
Credentials come from env vars ACRCLOUD_ACCESS_KEY / ACRCLOUD_ACCESS_SECRET / ACRCLOUD_HOST
(see .env.example) so nothing sensitive has to be pasted on a command line or committed.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROBE_MS = 30_000
STEP_MS = 25_000
MAX_WINDOWS = 48  # generous cap for a full-clip diagnostic scan; production's identify_song_shazam caps at 24 because it stops at the first hit and only needs to cover the clip once


@dataclass
class WindowResult:
    window_start_ms: int
    window_end_ms: int
    shazam_title: str = ""
    shazam_artist: str = ""
    shazam_error: str = ""
    acrcloud_title: str = ""
    acrcloud_artist: str = ""
    acrcloud_song_id: str = ""
    acrcloud_score: float | None = None
    acrcloud_error: str = ""
    # Captured but unused for now -- see acrcloud_identify's docstring note.
    acrcloud_sample_begin_ms: int | None = None
    acrcloud_db_begin_ms: int | None = None


def _extract_probe_wav(source: Path, offset_ms: int, probe_ms: int, out: Path) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(offset_ms / 1000), "-t", str(probe_ms / 1000), "-i", str(source),
             "-ac", "1", "-ar", "44100", "-vn", str(out)],
            check=True, capture_output=True, timeout=30,
        )
        return out.exists() and out.stat().st_size > 0
    except Exception:
        return False


async def _shazam_identify_async(wav_path: Path, timeout: int = 25) -> dict[str, Any] | None:
    from shazamio import Shazam
    shazam = Shazam()
    data = await asyncio.wait_for(shazam.recognize(str(wav_path)), timeout=timeout)
    track = (data or {}).get("track") or {}
    title = str(track.get("title") or "").strip()
    if not title:
        return None
    return {"title": title, "artist": str(track.get("subtitle") or "").strip()}


def shazam_identify(wav_path: Path) -> dict[str, Any] | None:
    """Runs in-process: this script has no other asyncio.run() call afterward for a
    fresh loop to collide with (that collision is why app.py's identify_song_shazam
    shells out to a subprocess instead -- see SHAZAM_PROBE_SCRIPT there)."""
    try:
        return asyncio.run(_shazam_identify_async(wav_path))
    except Exception:
        return None


def acrcloud_identify(wav_path: Path, access_key: str, access_secret: str, host: str, timeout: int = 15) -> dict[str, Any] | None:
    """ACRCloud's documented Identify REST API (https://docs.acrcloud.com/), not a
    reverse-engineered one: HMAC-SHA1 over a fixed string, multipart POST with the
    raw audio sample. Returns None on no-match or any request failure -- callers
    must treat that as "no opinion this window", never as a pipeline failure."""
    import httpx

    data = wav_path.read_bytes()
    timestamp = str(int(time.time()))
    string_to_sign = "\n".join(["POST", "/v1/identify", access_key, "audio", "1", timestamp])
    signature = base64.b64encode(
        hmac.new(access_secret.encode("ascii"), string_to_sign.encode("ascii"), hashlib.sha1).digest()
    ).decode("ascii")
    files = {"sample": ("sample.wav", data, "audio/wav")}
    fields = {
        "sample_bytes": str(len(data)),
        "access_key": access_key,
        "data_type": "audio",
        "signature_version": "1",
        "signature": signature,
        "timestamp": timestamp,
    }
    response = httpx.post(f"https://{host}/v1/identify", files=files, data=fields, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if int((payload.get("status") or {}).get("code", -1)) != 0:
        return None
    music = ((payload.get("metadata") or {}).get("music") or [])
    if not music:
        return None
    top = music[0]
    artists = top.get("artists") or []
    return {
        "title": str(top.get("title") or "").strip(),
        "artist": "/".join(str(a.get("name", "")) for a in artists if a.get("name")),
        "song_id": str((top.get("external_ids") or {}).get("isrc") or top.get("acrid") or ""),
        "score": top.get("score"),
        # Not used for alignment yet (B/C stay untouched per this task's scope), just
        # captured because it is a genuinely independent coarse anchor candidate for
        # later: sample_begin_time_offset_ms is where in *our probe window* the match
        # starts, db_begin_time_offset_ms is where in the *official track* it starts,
        # so (window_start_ms + sample_begin_time_offset_ms) - db_begin_time_offset_ms
        # would estimate the same shift_ms standard_timeline.score_timeline computes
        # from text matching, but from acoustic matching instead.
        "sample_begin_time_offset_ms": top.get("sample_begin_time_offset_ms"),
        "db_begin_time_offset_ms": top.get("db_begin_time_offset_ms"),
        "duration_ms": top.get("duration_ms"),
    }


def acrcloud_identify_window(
    source: Path, offset_ms: int, access_key: str, access_secret: str, host: str, probe_ms: int = PROBE_MS,
) -> dict[str, Any] | None:
    """One-shot convenience for callers outside this diagnostic script (production
    code wants a single opinion at a given offset, not a full-clip scan).

    Never raises: ffmpeg failure, network failure, bad credentials, or simply no
    match all return None, so a caller can silently fall back to its existing
    behavior (see this project's rule that a second identification source must
    never be able to fail the whole automated task).
    """
    return acrcloud_identify_window_result(
        source, offset_ms, access_key, access_secret, host, probe_ms
    )["hit"]


def acrcloud_identify_window_result(
    source: Path, offset_ms: int, access_key: str, access_secret: str, host: str, probe_ms: int = PROBE_MS,
) -> dict[str, Any]:
    """Return the hit plus an observable status for one production probe."""
    with tempfile.TemporaryDirectory(prefix="song_id_probe_") as tmp:
        wav = Path(tmp) / f"probe_{uuid.uuid4().hex}.wav"
        if not _extract_probe_wav(source, offset_ms, probe_ms, wav):
            return {"hit": None, "status": "extract_failed", "error": "ffmpeg 抽取音频窗口失败"}
        try:
            hit = acrcloud_identify(wav, access_key, access_secret, host)
            return {"hit": hit, "status": "hit" if hit else "no_match", "error": ""}
        except Exception as exc:
            return {"hit": None, "status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}


def scan_windows(
    source: Path,
    duration_ms: int,
    *,
    probe_ms: int = PROBE_MS,
    step_ms: int = STEP_MS,
    max_windows: int = MAX_WINDOWS,
    acrcloud_creds: tuple[str, str, str] | None = None,
    stop_at_first_agreement: bool = False,
) -> list[WindowResult]:
    """Walks the whole clip (never "first hit wins" -- diagnostic mode wants every
    window's raw result, per the project's explicit requirement). stop_at_first_agreement
    is an escape hatch for a future faster mode, off by default here."""
    offsets = list(range(0, max(1, duration_ms - 5000), step_ms))[:max_windows]
    rows: list[WindowResult] = []
    with tempfile.TemporaryDirectory(prefix="song_id_diag_") as tmp:
        tmp_dir = Path(tmp)
        for offset_ms in offsets:
            row = WindowResult(window_start_ms=offset_ms, window_end_ms=min(duration_ms, offset_ms + probe_ms))
            wav = tmp_dir / f"probe_{uuid.uuid4().hex}.wav"
            if not _extract_probe_wav(source, offset_ms, probe_ms, wav):
                row.shazam_error = row.acrcloud_error = "ffmpeg 抽取音频窗口失败"
                rows.append(row)
                continue
            try:
                try:
                    shazam_hit = shazam_identify(wav)
                    if shazam_hit:
                        row.shazam_title, row.shazam_artist = shazam_hit["title"], shazam_hit["artist"]
                except Exception as exc:
                    row.shazam_error = str(exc)[:200]
                if acrcloud_creds:
                    try:
                        acr_hit = acrcloud_identify(wav, *acrcloud_creds)
                        if acr_hit:
                            row.acrcloud_title, row.acrcloud_artist = acr_hit["title"], acr_hit["artist"]
                            row.acrcloud_song_id, row.acrcloud_score = acr_hit["song_id"], acr_hit["score"]
                        row.acrcloud_sample_begin_ms = acr_hit.get("sample_begin_time_offset_ms")
                        row.acrcloud_db_begin_ms = acr_hit.get("db_begin_time_offset_ms")
                    except Exception as exc:
                        row.acrcloud_error = str(exc)[:200]
            finally:
                wav.unlink(missing_ok=True)
            rows.append(row)
            if stop_at_first_agreement and row.shazam_title and row.shazam_title == row.acrcloud_title:
                break
    return rows


def format_report(rows: list[WindowResult]) -> str:
    def fmt(ms: int) -> str:
        return f"{ms // 60000}:{(ms % 60000) / 1000:05.1f}"

    lines = []
    for row in rows:
        lines.append(f"{fmt(row.window_start_ms)}-{fmt(row.window_end_ms)}")
        shazam = f"{row.shazam_title} - {row.shazam_artist}" if row.shazam_title else ("(无/" + row.shazam_error + ")" if row.shazam_error else "(无)")
        acr = f"{row.acrcloud_title} - {row.acrcloud_artist} [score={row.acrcloud_score}]" if row.acrcloud_title else ("(无/" + row.acrcloud_error + ")" if row.acrcloud_error else "(无)")
        lines.append(f"  Shazam:   {shazam}")
        lines.append(f"  ACRCloud: {acr}")
    # Summary: how often each provider's top title matches across all windows that got a hit
    from collections import Counter
    shazam_votes = Counter(f"{r.shazam_title} - {r.shazam_artist}" for r in rows if r.shazam_title)
    acr_votes = Counter(f"{r.acrcloud_title} - {r.acrcloud_artist}" for r in rows if r.acrcloud_title)
    lines.append("")
    lines.append(f"窗口总数: {len(rows)}")
    lines.append(f"Shazam 命中分布: {dict(shazam_votes)}")
    lines.append(f"ACRCloud 命中分布: {dict(acr_votes)}")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python song_identity_diagnostics.py <media_path> [--duration-ms N]", file=sys.stderr)
        sys.exit(1)
    source = Path(sys.argv[1])
    duration_ms = None
    if "--duration-ms" in sys.argv:
        duration_ms = int(sys.argv[sys.argv.index("--duration-ms") + 1])
    if duration_ms is None:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)],
            capture_output=True, text=True, timeout=30,
        )
        duration_ms = round(float(json.loads(probe.stdout)["format"]["duration"]) * 1000)
    access_key = os.getenv("ACRCLOUD_ACCESS_KEY", "")
    access_secret = os.getenv("ACRCLOUD_ACCESS_SECRET", "")
    host = os.getenv("ACRCLOUD_HOST", "")
    creds = (access_key, access_secret, host) if access_key and access_secret and host else None
    if not creds:
        print("(未设置 ACRCLOUD_ACCESS_KEY/ACRCLOUD_ACCESS_SECRET/ACRCLOUD_HOST，本次只跑 Shazam)", file=sys.stderr)
    rows = scan_windows(source, duration_ms, acrcloud_creds=creds)
    print(format_report(rows))


if __name__ == "__main__":
    main()
