from __future__ import annotations

import ctypes
import gc
import json
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODEL = "Qwen/Qwen3-ASR-0.6B"


def _matching_checkpoint(path: Path | None, chunks: list[dict[str, object]]) -> dict[int, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result = {}
    for row in rows if isinstance(rows, list) else []:
        try:
            index = int(row["index"])
            chunk = chunks[index]
            if (
                row.get("path") == str(Path(chunk["path"]))
                and abs(float(row.get("offset", -1)) - float(chunk["offset"])) < 0.001
                and abs(float(row.get("duration", -1)) - float(chunk["duration"])) < 0.001
            ):
                result[index] = row
        except (IndexError, KeyError, TypeError, ValueError):
            continue
    return result


def _save_checkpoint(path: Path | None, rows: list[dict[str, Any]]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _trim_memory() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def transcribe_chunks(
    chunks: list[dict[str, object]],
    *,
    model_name: str = DEFAULT_MODEL,
    language: str = "Chinese",
    max_new_tokens: int = 1024,
    progress: Callable[[int, int], None] | None = None,
    checkpoint_path: Path | None = None,
) -> list[dict[str, Any]]:
    completed = _matching_checkpoint(checkpoint_path, chunks)
    output: list[dict[str, Any]] = []
    model = None
    try:
        for index, chunk in enumerate(chunks):
            if index in completed:
                output.append(completed[index])
                if progress:
                    progress(index + 1, len(chunks))
                continue
            if model is None:
                import torch
                from qwen_asr import Qwen3ASRModel

                torch.set_num_threads(max(1, min(10, torch.get_num_threads())))
                model = Qwen3ASRModel.from_pretrained(
                    model_name,
                    device_map="cpu",
                    dtype=torch.float32,
                    max_inference_batch_size=1,
                    max_new_tokens=max_new_tokens,
                )
            path = Path(chunk["path"])
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    result = model.transcribe(audio=str(path), language=language)[0]
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt == 2:
                        raise RuntimeError(f"ASR 第 {index + 1} 块连续失败 3 次：{exc}") from exc
            else:
                raise RuntimeError(f"ASR 第 {index + 1} 块失败：{last_error}")
            output.append(
                {
                    "index": index,
                    "path": str(path),
                    "offset": float(chunk["offset"]),
                    "duration": float(chunk["duration"]),
                    "language": getattr(result, "language", language) or language,
                    "text": (getattr(result, "text", "") or "").strip(),
                }
            )
            _save_checkpoint(checkpoint_path, output)
            if progress:
                progress(index + 1, len(chunks))
    finally:
        if model is not None:
            del model
        _trim_memory()
    return output
