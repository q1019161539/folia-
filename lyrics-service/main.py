from __future__ import annotations

import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from LDDC.common.models import Artist, LyricsType, SearchType, SongInfo, Source
from LDDC.core.api.lyrics import get_lyrics, search


app = FastAPI(title="Folia LDDC lyrics service")
LDDC_REF = os.getenv("LDDC_REF", "unknown")
SOURCE_MAP = {
    "qq": Source.QM,
    "kugou": Source.KG,
    "netease": Source.NE,
    "lrclib": Source.LRCLIB,
}
SOURCE_NAMES = {value: key for key, value in SOURCE_MAP.items()}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    sources: list[str] = Field(default_factory=lambda: list(SOURCE_MAP))
    limit_per_source: int = Field(default=3, ge=1, le=10)


class LyricsRequest(BaseModel):
    candidate_ref: str = Field(min_length=4, max_length=8192)


def song_payload(song: SongInfo) -> dict[str, Any]:
    return {
        "source": SOURCE_NAMES[song.source],
        "title": song.title or "",
        "subtitle": song.subtitle or "",
        "artist": list(song.artist or []),
        "album": song.album or "",
        "duration": song.duration,
        "id": song.id,
        "mid": song.mid,
        "hash": song.hash,
    }


def encode_ref(song: SongInfo) -> str:
    raw = json.dumps(song_payload(song), ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_ref(value: str) -> SongInfo:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        data = json.loads(raw)
        source = SOURCE_MAP[str(data["source"])]
        return SongInfo(
            source=source,
            title=str(data.get("title") or "") or None,
            subtitle=str(data.get("subtitle") or "") or None,
            artist=Artist(data.get("artist") or []),
            album=str(data.get("album") or "") or None,
            duration=int(data["duration"]) if data.get("duration") is not None else None,
            id=str(data["id"]) if data.get("id") is not None else None,
            mid=str(data["mid"]) if data.get("mid") is not None else None,
            hash=str(data["hash"]) if data.get("hash") is not None else None,
        )
    except Exception as exc:
        raise ValueError("无效的歌词候选引用") from exc


def serialize_candidate(song: SongInfo) -> dict[str, Any]:
    source = SOURCE_NAMES[song.source]
    return {
        "candidate_id": f"{source}:{song.id or song.mid or song.hash or encode_ref(song)[-16:]}",
        "candidate_ref": encode_ref(song),
        "platform": source,
        "song_id": str(song.id or song.mid or song.hash or ""),
        "title": song.title or "",
        "subtitle": song.subtitle or "",
        "artist": " / ".join(song.artist or []),
        "album": song.album or "",
        "duration_ms": int(song.duration or 0),
        "timing_type": "unknown",
        "word_coverage": 0.0,
    }


def search_source(source_name: str, query: str, limit: int) -> tuple[str, list[dict[str, Any]], str]:
    source = SOURCE_MAP[source_name]
    try:
        result = search(source, query, SearchType.SONG, 1)
        return source_name, [serialize_candidate(song) for song in list(result)[:limit]], "ok"
    except Exception as exc:
        return source_name, [], f"{type(exc).__name__}: {str(exc)[:180]}"


def normalized_length(value: str) -> int:
    return len(re.sub(r"[^0-9A-Za-z\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+", "", value))


def serialize_lyrics(song: SongInfo) -> dict[str, Any]:
    lyrics = get_lyrics(song)
    original = lyrics.get("orig") or []
    rows = []
    timed_characters = 0
    total_characters = 0
    has_line_time = False
    for line_index, line in enumerate(original):
        words = []
        text_parts = []
        for word_index, word in enumerate(line.words):
            text = str(word.text)
            text_parts.append(text)
            length = normalized_length(text)
            total_characters += length
            if word.start is not None and word.end is not None and int(word.end) > int(word.start):
                timed_characters += length
            words.append({
                "word_index": word_index,
                "text": text,
                "start_ms": int(word.start) if word.start is not None else None,
                "end_ms": int(word.end) if word.end is not None else None,
            })
        line_start = line.start
        line_end = line.end
        if line_start is None and words:
            line_start = words[0]["start_ms"]
        if line_end is None and words:
            line_end = words[-1]["end_ms"]
        has_line_time = has_line_time or line_start is not None
        rows.append({
            "line_index": line_index,
            "text": "".join(text_parts).strip(),
            "start_ms": int(line_start) if line_start is not None else None,
            "end_ms": int(line_end) if line_end is not None else None,
            "words": words,
        })
    word_coverage = timed_characters / total_characters if total_characters else 0.0
    lyric_type = lyrics.types.get("orig")
    timing_type = "verbatim" if lyric_type == LyricsType.VERBATIM and timed_characters else ("line" if has_line_time else "plain")
    return {
        "candidate": serialize_candidate(song),
        "platform": SOURCE_NAMES[song.source],
        "timing_type": timing_type,
        "word_coverage": round(word_coverage, 4),
        "rows": [row for row in rows if row["text"]],
        "tags": {str(key): str(value) for key, value in lyrics.tags.items()},
        "lddc_ref": LDDC_REF,
    }


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "lddc_ref": LDDC_REF, "sources": list(SOURCE_MAP)}


@app.post("/v1/search")
def search_lyrics(body: SearchRequest) -> dict[str, Any]:
    requested = list(dict.fromkeys(name.lower() for name in body.sources if name.lower() in SOURCE_MAP))
    if not requested:
        raise HTTPException(400, "没有可用歌词来源")
    candidates: list[dict[str, Any]] = []
    statuses: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(requested)) as executor:
        futures = [executor.submit(search_source, source, body.query.strip(), body.limit_per_source) for source in requested]
        for future in as_completed(futures):
            source, items, status = future.result()
            candidates.extend(items)
            statuses[source] = status
    order = {name: index for index, name in enumerate(requested)}
    candidates.sort(key=lambda item: (order.get(item["platform"], 99), item["title"], item["artist"]))
    return {"query": body.query.strip(), "candidates": candidates, "platforms": statuses, "lddc_ref": LDDC_REF}


@app.post("/v1/lyrics")
def resolve_lyrics(body: LyricsRequest) -> dict[str, Any]:
    try:
        song = decode_ref(body.candidate_ref)
        return serialize_lyrics(song)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"LDDC 获取歌词失败：{type(exc).__name__}: {str(exc)[:300]}") from exc
