from __future__ import annotations

import re
from typing import Any, Iterable


SENTENCE_END = re.compile(r"[。！？!?；;]$")


def format_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def make_segment(
    start: float,
    end: float,
    text: str,
    *,
    words: list[dict[str, Any]] | None = None,
    chunk_index: int | None = None,
) -> dict[str, Any]:
    start = round(max(0.0, float(start)), 3)
    end = round(max(start, float(end)), 3)
    segment = {
        "start": start,
        "end": end,
        "start_text": format_timestamp(start),
        "end_text": format_timestamp(end),
        "text": text.strip(),
    }
    if words:
        segment["words"] = words
    if chunk_index is not None:
        segment["chunk_index"] = chunk_index
    return segment


def sentence_segments(
    items: Iterable[Any],
    *,
    offset_seconds: float,
    chunk_index: int | None = None,
    max_characters: int = 35,
    max_gap_seconds: float = 1.5,
) -> list[dict[str, Any]]:
    """Group Qwen forced-aligner characters/words into readable sentences."""
    output: list[dict[str, Any]] = []
    current: list[Any] = []

    def flush() -> None:
        if not current:
            return
        text = "".join(str(item.text) for item in current).strip()
        if text:
            words = [
                {
                    "text": str(item.text),
                    "start_ms": round((offset_seconds + float(item.start_time)) * 1000),
                    "end_ms": round((offset_seconds + float(item.end_time)) * 1000),
                    "timing_source": "qwen-forced-aligner",
                }
                for item in current
                if str(item.text)
            ]
            output.append(
                make_segment(
                    offset_seconds + float(current[0].start_time),
                    offset_seconds + float(current[-1].end_time),
                    text,
                    words=words,
                    chunk_index=chunk_index,
                )
            )
        current.clear()

    for item in items:
        text = str(item.text)
        if current and float(item.start_time) - float(current[-1].end_time) > max_gap_seconds:
            flush()
        current.append(item)
        joined_length = sum(len(str(part.text)) for part in current)
        if SENTENCE_END.search(text) or joined_length >= max_characters:
            flush()
    flush()
    return output
