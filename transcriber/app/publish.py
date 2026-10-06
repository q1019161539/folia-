from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


def _component(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return cleaned or "未命名录播"


def recording_output_directory(input_relative: str, root: Path) -> Path:
    source = Path(input_relative)
    parents = [_component(part) for part in source.parent.parts if part not in {"", ".", ".."}]
    return root.joinpath(*parents, _component(source.stem))


def _atomic_copy(source: Path, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def publish_recording_outputs(job: dict[str, Any], internal_output: Path, work_dir: Path, friendly_root: Path) -> Path:
    destination = recording_output_directory(str(job.get("input_relative", "录播.mp4")), friendly_root)
    destination.mkdir(parents=True, exist_ok=True)
    stem = _component(Path(str(job.get("input_relative", "录播.mp4"))).stem)
    mappings = {
        "transcript.txt": f"{stem}.txt",
        "transcript.jsonl": f"{stem}.jsonl",
        "transcript_words.jsonl": f"{stem}_逐字.jsonl",
        "stats.json": f"{stem}_统计.json",
        "job.log": f"{stem}.log",
    }
    for source_name, target_name in mappings.items():
        source = internal_output / source_name
        if source.is_file():
            _atomic_copy(source, destination / target_name)
    if (internal_output / "transcript.jsonl").is_file() and not (internal_output / "transcript_words.jsonl").is_file():
        (destination / f"{stem}_逐字.jsonl").unlink(missing_ok=True)
    checkpoint = work_dir / "asr_chunks.json"
    if not (internal_output / "transcript.txt").is_file() and checkpoint.is_file():
        try:
            rows = json.loads(checkpoint.read_text(encoding="utf-8"))
            text = "\n".join(str(row.get("text", "")).strip() for row in rows if str(row.get("text", "")).strip())
            temporary = destination / f"{stem}_未完成.txt.tmp"
            temporary.write_text(text + ("\n" if text else ""), encoding="utf-8")
            os.replace(temporary, destination / f"{stem}_未完成.txt")
            _atomic_copy(checkpoint, destination / f"{stem}_ASR断点.json")
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return destination


def _clock(milliseconds: Any) -> str:
    seconds = max(0, int(round(float(milliseconds or 0) / 1000)))
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def publish_song_analysis(job: dict[str, Any], payload: dict[str, Any], friendly_root: Path) -> dict[str, str]:
    destination = recording_output_directory(str(job.get("input_relative", "录播.mp4")), friendly_root)
    destination.mkdir(parents=True, exist_ok=True)
    stem = _component(Path(str(job.get("input_relative", "录播.mp4"))).stem)
    json_path = destination / f"{stem}_歌曲分析.json"
    text_path = destination / f"{stem}_歌曲时间轴.txt"
    document = {
        "recording": job.get("input_relative", ""),
        "model": str(payload.get("model", "")),
        "timestamp_source": "local-asr-segment-ids",
        "minimum_confidence": payload.get("minimum_confidence"),
        "padding_seconds": payload.get("padding_seconds"),
        "songs": payload.get("songs") if isinstance(payload.get("songs"), list) else [],
        "skipped": payload.get("skipped") if isinstance(payload.get("skipped"), list) else [],
    }
    temporary_json = json_path.with_suffix(json_path.suffix + ".tmp")
    temporary_json.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_json, json_path)
    lines = [
        f"录播：{document['recording']}",
        f"分析模型：{document['model']}",
        "时间戳：由本地程序根据 ASR segment_id 换算，非 AI 生成",
        "",
    ]
    accepted = [song for song in document["songs"] if song.get("start_ms") is not None and song.get("end_ms") is not None]
    for index, song in enumerate(accepted, 1):
        lines.append(f"{index}. {song.get('title', '未知歌曲')} {_clock(song.get('start_ms'))} - {_clock(song.get('end_ms'))}  置信度 {float(song.get('confidence', 0)):.2f}")
        if song.get("reason"):
            lines.append(f"   依据：{song['reason']}")
    if document["skipped"]:
        lines.extend(["", "未采用的候选："])
        for item in document["skipped"]:
            lines.append(f"- {item.get('title') or '未命名'}：{item.get('reason') or '未通过校验'}")
    temporary_text = text_path.with_suffix(text_path.suffix + ".tmp")
    temporary_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary_text, text_path)
    return {"json": str(json_path), "timeline": str(text_path)}
