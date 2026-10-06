from __future__ import annotations

import ctypes
import gc
import json
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODEL = "Qwen/Qwen3-ASR-0.6B"
WHISPER_ENGINE = "whisper"


def _matching_checkpoint(
    path: Path | None, chunks: list[dict[str, object]], *, engine: str = "local", model: str = DEFAULT_MODEL
) -> dict[int, dict[str, Any]]:
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
                and row.get("asr_engine", "local") == engine
                and row.get("asr_model", DEFAULT_MODEL) == model
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
    completed = _matching_checkpoint(checkpoint_path, chunks, engine="local", model=model_name)
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
                    "asr_engine": "local",
                    "asr_model": model_name,
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


def _whisper_request(path: Path, worker_url: str) -> dict[str, Any]:
    boundary = "folia-" + uuid.uuid4().hex
    fields = {"language": "zh", "vad_filter": "false", "word_timestamps": "false"}
    body = bytearray()
    for key, value in fields.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        'Content-Type: audio/wav\r\n\r\n'.encode()
    )
    body.extend(path.read_bytes())
    body.extend(f'\r\n--{boundary}--\r\n'.encode())
    request = urllib.request.Request(
        worker_url.rstrip("/") + "/recognize", data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=1800) as response:
        return json.load(response)


def transcribe_chunks_whisper(
    chunks: list[dict[str, object]], *, worker_url: str, progress: Callable[[int, int], None] | None = None,
    checkpoint_path: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    with urllib.request.urlopen(worker_url.rstrip("/") + "/healthz", timeout=30) as response:
        model_name = str(json.load(response).get("model") or "large-v3-turbo")
    completed = _matching_checkpoint(checkpoint_path, chunks, engine=WHISPER_ENGINE, model=model_name)
    output: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if index in completed:
            output.append(completed[index])
        else:
            path = Path(chunk["path"])
            for attempt in range(3):
                try:
                    result = _whisper_request(path, worker_url)
                    break
                except Exception as exc:
                    if attempt == 2:
                        raise RuntimeError(f"Faster-Whisper 第 {index + 1} 块连续失败 3 次：{exc}") from exc
                    time.sleep(3)
            duration = float(chunk["duration"])
            native_segments = []
            for segment in result.get("segments") or []:
                start = max(0.0, min(duration, float(segment.get("start", 0))))
                end = max(start, min(duration, float(segment.get("end", 0))))
                text = str(segment.get("text") or "").strip()
                if text and end > start:
                    native_segments.append({"start": start, "end": end, "text": text})
            row = {
                "index": index, "path": str(path), "offset": float(chunk["offset"]), "duration": duration,
                "language": str(result.get("language") or "zh"),
                "text": " ".join(item["text"] for item in native_segments),
                "segments": native_segments, "asr_engine": WHISPER_ENGINE, "asr_model": model_name,
            }
            output.append(row)
            _save_checkpoint(checkpoint_path, output)
        if progress:
            progress(index + 1, len(chunks))
    return output, model_name
