"""Estimate when an automated run will finish, from what past runs actually took.

Two things this deliberately refuses to do.

It does not estimate the whole run at the moment ASR starts. How long a run
takes is dominated by how many songs it finds, and at that point no song has
been found yet: across 13 completed runs the same recording size took anywhere
from 25 to 92 minutes per GB. A single number there would look precise and be
wrong, so ASR is estimated on its own and the rest only once the song count is
known.

It does not measure ASR against file size either. An hour of audio is an hour of
work whether the recording is 1GB or 4GB; only the bitrate differs. Estimates
are therefore built on the real-time factor -- processing seconds per second of
audio -- and on measured stage durations that exclude time spent queueing, since
waiting for another render to finish says nothing about how fast this one runs.
"""
from __future__ import annotations

import statistics
from typing import Any

# Below this many past measurements the spread is meaningless and the estimate
# says so rather than inventing a number.
MIN_SAMPLES = 10
# Reported as a range, from the middle of past runs to their slow end, so the
# figure reads as the expectation it is rather than as a promise.
LOW_PERCENTILE = 0.5
HIGH_PERCENTILE = 0.8


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _estimate(samples: list[float], scale: float, kind: str) -> dict[str, Any]:
    if len(samples) < MIN_SAMPLES:
        return {"kind": kind, "reliable": False, "sample_count": len(samples)}
    low = _percentile(samples, LOW_PERCENTILE) * scale
    high = _percentile(samples, HIGH_PERCENTILE) * scale
    return {
        "kind": kind,
        "reliable": True,
        "sample_count": len(samples),
        "low_seconds": int(round(low)),
        "high_seconds": int(round(max(high, low))),
    }


def asr_samples(history: list[dict[str, Any]]) -> list[float]:
    """Real-time factor of each past ASR stage: seconds spent per second of audio."""
    out = []
    for run in history:
        timings = run.get("timings") or {}
        started, finished = timings.get("asr_started_at"), timings.get("asr_finished_at")
        audio = run.get("audio_duration_sec") or 0
        if started and finished and audio and finished > started:
            out.append((finished - started) / audio)
    return out


def per_song_samples(history: list[dict[str, Any]]) -> list[float]:
    """Seconds of real work per finished song, with queue waiting removed.

    A song that sat behind another render for twenty minutes did not take twenty
    minutes to make, and folding that in would teach the estimator to predict
    other people's queues.
    """
    out = []
    for run in history:
        timings = run.get("timings") or {}
        started = timings.get("songs_started_at")
        finished = timings.get("songs_finished_at")
        count = int(run.get("song_count") or 0)
        waited = float(run.get("render_wait_seconds") or 0)
        if started and finished and count > 0 and finished > started:
            worked = (finished - started) - waited
            if worked > 0:
                out.append(worked / count)
    return out


def estimate_asr(audio_duration_sec: float, history: list[dict[str, Any]]) -> dict[str, Any]:
    if audio_duration_sec <= 0:
        return {"kind": "asr", "reliable": False, "sample_count": 0}
    return _estimate(asr_samples(history), audio_duration_sec, "asr")


def estimate_songs(song_count: int, history: list[dict[str, Any]]) -> dict[str, Any]:
    """Time still needed once the songs are known. Excludes render queueing,
    which is why the notification says the estimate slips if a queue forms."""
    if song_count <= 0:
        return {"kind": "songs", "reliable": False, "sample_count": 0}
    estimate = _estimate(per_song_samples(history), float(song_count), "songs")
    estimate["song_count"] = song_count
    return estimate


def summarize_history(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Diagnostic view of what the estimator currently has to work with."""
    asr, songs = asr_samples(runs), per_song_samples(runs)
    return {
        "asr_sample_count": len(asr),
        "song_sample_count": len(songs),
        "asr_rtf_median": round(statistics.median(asr), 4) if asr else None,
        "seconds_per_song_median": round(statistics.median(songs)) if songs else None,
        "ready": len(asr) >= MIN_SAMPLES,
    }
