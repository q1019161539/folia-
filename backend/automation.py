"""Pure helpers for the durable recording-to-video automation pipeline."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MIN_RECORDING_BYTES = 1024 ** 3


def automation_transcriber_payload(
    input_path: str, run_id: str, stage: str = "all", chunk_seconds: int = 180
) -> dict[str, Any]:
    """Build the sentence-timed ASR request used by automatic recording jobs.

    Speech VAD is intentionally disabled here: singing is not reliably classified
    as speech, so skipping non-speech regions can remove whole verses.  Fixed-size
    chunks are still processed sequentially and keep the original source offsets.
    """
    if stage not in {"all", "asr", "align"}:
        raise ValueError(f"不支持的自动转录阶段：{stage}")
    return {
        "input": input_path if stage == "all" else "",
        "stage": stage,
        "run_id": run_id,
        "chunk_seconds": int(chunk_seconds),
        "asr_engine": "whisper",
        "skip_alignment": True,
        "no_vad": True,
        "notification_mode": "automation",
    }


def broadcaster_directories(root: Path) -> list[dict[str, str]]:
    """Return current first-level recording folders as broadcaster choices."""
    try:
        children = list(root.iterdir())
    except OSError:
        return []
    result = []
    for path in children:
        try:
            if not path.is_dir() or path.name.startswith(".") or path.name == "歌曲切片":
                continue
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        result.append({"name": path.name, "path": relative})
    return sorted(result, key=lambda item: item["name"].casefold())


def recording_choices(root: Path, media_root: Path, limit: int = 200) -> list[dict[str, Any]]:
    """List existing source recordings without treating generated song clips as inputs."""
    try:
        resolved_root = root.resolve()
        resolved_media = media_root.resolve()
        resolved_root.relative_to(resolved_media)
    except (OSError, ValueError):
        return []
    result = []
    try:
        for path in resolved_root.rglob("*.mp4"):
            try:
                relative = path.resolve().relative_to(resolved_media)
                if "歌曲切片" in relative.parts or ".partial" in path.name.lower() or not path.is_file():
                    continue
                stat = path.stat()
                if stat.st_size <= 0:
                    continue
                result.append({"name": path.name, "path": relative.as_posix(), "size": stat.st_size, "mtime": stat.st_mtime})
            except (OSError, ValueError):
                continue
    except OSError:
        return []
    result.sort(key=lambda item: (-item["mtime"], item["path"].casefold()))
    return result[: max(1, min(int(limit), 1000))]


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def eligible_recording(path: Path, root: Path, minimum_bytes: int = MIN_RECORDING_BYTES) -> bool:
    """Accept finalized MP4 recordings only, never generated song clips."""
    try:
        relative = path.resolve().relative_to(root.resolve())
        return (
            path.is_file()
            and path.suffix.lower() == ".mp4"
            and path.stat().st_size >= minimum_bytes
            and "歌曲切片" not in relative.parts
            and ".partial" not in path.name.lower()
        )
    except (OSError, ValueError):
        return False


def transcript_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, row in enumerate(rows):
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        start_ms = int(round(float(row.get("start_ms", float(row.get("start", 0)) * 1000))))
        end_ms = int(round(float(row.get("end_ms", float(row.get("end", row.get("start", 0))) * 1000))))
        if end_ms <= start_ms:
            continue
        result.append({**row, "segment_id": index, "text": text, "start_ms": start_ms, "end_ms": end_ms})
    return result


def transcript_for_ai(segments: list[dict[str, Any]]) -> str:
    def clock(value: int) -> str:
        seconds = max(0, value // 1000)
        return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"

    return "\n".join(
        f"[{row['segment_id']}] {clock(row['start_ms'])}-->{clock(row['end_ms'])} {row['text']}"
        for row in segments
    )


def parse_ai_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1)
    else:
        first, last = text.find("{"), text.rfind("}")
        if first >= 0 and last > first:
            text = text[first : last + 1]
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("AI 返回值不是 JSON 对象")
    return result


def validate_detected_songs(
    payload: dict[str, Any],
    segments: list[dict[str, Any]],
    minimum_confidence: float = 0.8,
    minimum_duration_ms: int = 45_000,
    maximum_duration_ms: int = 15 * 60_000,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve AI segment IDs locally; timestamps from the model are never trusted."""
    by_id = {int(row["segment_id"]): row for row in segments}
    accepted, skipped = [], []
    last_end = -1
    raw_songs = payload.get("songs") or []
    if not isinstance(raw_songs, list):
        raise ValueError("AI songs 字段不是数组")
    for position, raw in enumerate(raw_songs):
        reason = ""
        try:
            title = str(raw.get("title", "")).strip()
            confidence = float(raw.get("confidence", 0))
            first = int(raw.get("start_segment_id"))
            last = int(raw.get("end_segment_id"))
            if not title or title.lower() in {"unknown", "未知", "不确定"}:
                reason = "歌名不确定"
            elif confidence < minimum_confidence:
                reason = f"AI 置信度 {confidence:.2f} 低于 {minimum_confidence:.2f}"
            elif first not in by_id or last not in by_id or last < first:
                reason = "ASR 句段 ID 无效"
            else:
                start_ms, end_ms = by_id[first]["start_ms"], by_id[last]["end_ms"]
                duration = end_ms - start_ms
                if duration < minimum_duration_ms:
                    reason = "演唱片段过短，不视为完整歌曲"
                elif duration > maximum_duration_ms:
                    reason = "演唱范围异常过长"
                elif start_ms < last_end:
                    reason = "与上一首歌曲范围重叠"
                else:
                    accepted.append(
                        {
                            "index": len(accepted),
                            "title": title,
                            "confidence": round(confidence, 3),
                            "start_segment_id": first,
                            "end_segment_id": last,
                            "start_ms": start_ms,
                            "end_ms": end_ms,
                            "reason": str(raw.get("reason", ""))[:200],
                            "status": "detected",
                        }
                    )
                    last_end = end_ms
        except (TypeError, ValueError):
            reason = "AI 返回字段格式无效"
        if reason:
            skipped.append({"position": position, "title": str(raw.get("title", "")), "reason": reason})
    return accepted, skipped


def project_transcript(
    segments: list[dict[str, Any]], clip_start_ms: int, clip_end_ms: int
) -> list[dict[str, Any]]:
    """Move full-recording ASR rows onto an exact-visible clip timeline."""
    projected = []
    for row in segments:
        start = max(clip_start_ms, int(row["start_ms"]))
        end = min(clip_end_ms, int(row["end_ms"]))
        if end <= start:
            continue
        words = []
        for word in row.get("words") or []:
            ws = int(round(float(word.get("start_ms", float(word.get("start", 0)) * 1000))))
            we = int(round(float(word.get("end_ms", float(word.get("end", word.get("start", 0))) * 1000))))
            ws, we = max(clip_start_ms, ws), min(clip_end_ms, we)
            if we > ws:
                words.append({"text": word.get("text", word.get("word", "")), "start_ms": ws - clip_start_ms, "end_ms": we - clip_start_ms, "probability": word.get("probability", 1), "timing_source": word.get("timing_source", "")})
        item = {
            "line_id": len(projected),
            "text": row["text"],
            "start_ms": start - clip_start_ms,
            "end_ms": end - clip_start_ms,
            "confidence": round(float(row.get("confidence", 0.75)), 2),
            "status": "asr",
            "segment_ids": [int(row["segment_id"])],
            "words": words,
            "timing_precision": "word" if words else "segment",
            "source_start_ms": int(row["start_ms"]),
            "source_end_ms": int(row["end_ms"]),
        }
        projected.append(item)
    return projected


def restore_completed_clip_paths(
    songs: list[dict[str, Any]], batch_id: str, batch_items: list[dict[str, Any]]
) -> int:
    """Reconnect completed clip files to songs after an interrupted hand-off."""
    by_name = {
        str(item.get("output_name") or ""): item
        for item in batch_items
        if item.get("status") == "completed" and item.get("internal_path")
    }
    restored = 0
    for song in songs:
        if song.get("clip_path") or song.get("clip_batch_id") != batch_id:
            continue
        item = by_name.get(str(song.get("clip_name") or ""))
        if not item:
            continue
        song["clip_path"] = str(item["internal_path"])
        song["status"] = "clipped"
        song.pop("error", None)
        restored += 1
    return restored
