from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_outputs(output_dir: Path, segments: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "transcript.jsonl").open("w", encoding="utf-8") as stream:
        for segment_id, segment in enumerate(segments):
            segment["segment_id"] = segment_id
            stream.write(json.dumps(segment, ensure_ascii=False) + "\n")
    word_path = output_dir / "transcript_words.jsonl"
    if any(segment.get("words") for segment in segments):
        with word_path.open("w", encoding="utf-8") as stream:
            for segment_id, segment in enumerate(segments):
                for word_index, word in enumerate(segment.get("words") or []):
                    stream.write(
                        json.dumps(
                            {
                                "segment_id": segment_id,
                                "word_index": word_index,
                                "chunk_index": segment.get("chunk_index"),
                                "text": str(word.get("text", "")),
                                "start_ms": int(word.get("start_ms", 0)),
                                "end_ms": int(word.get("end_ms", 0)),
                                "timing_source": str(word.get("timing_source") or "qwen-forced-aligner"),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
    else:
        word_path.unlink(missing_ok=True)
    (output_dir / "transcript.txt").write_text(
        "\n".join(
            f"{segment['start_text']} --> {segment['end_text']}  {segment['text']}"
            for segment in segments
        )
        + ("\n" if segments else ""),
        encoding="utf-8",
    )
    write_json(output_dir / "stats.json", stats)
