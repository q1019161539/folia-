from __future__ import annotations

import ctypes
import gc
from typing import Any, Callable

from .timestamps import make_segment, sentence_segments


DEFAULT_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"


def align_chunks(
    chunks: list[dict[str, Any]],
    *,
    model_name: str = DEFAULT_MODEL,
    language: str = "Chinese",
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    import torch
    from qwen_asr import Qwen3ForcedAligner

    torch.set_num_threads(max(1, min(10, torch.get_num_threads())))
    model = Qwen3ForcedAligner.from_pretrained(
        model_name,
        device_map="cpu",
        dtype=torch.float32,
    )
    output: list[dict[str, Any]] = []
    try:
        for index, chunk in enumerate(chunks):
            text = chunk["text"].strip()
            if not text:
                if progress:
                    progress(index + 1, len(chunks))
                continue
            result = model.align(
                audio=chunk["path"],
                text=text,
                language=language,
            )[0]
            grouped = sentence_segments(
                result.items,
                offset_seconds=float(chunk["offset"]),
                chunk_index=index,
            )
            if grouped:
                output.extend(grouped)
            else:
                output.append(
                    make_segment(
                        float(chunk["offset"]),
                        float(chunk["offset"]) + float(chunk["duration"]),
                        text,
                        chunk_index=index,
                    )
                )
            if progress:
                progress(index + 1, len(chunks))
    finally:
        del model
        gc.collect()
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass
    return output


def chunk_level_segments(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        make_segment(
            float(chunk["offset"]),
            float(chunk["offset"]) + float(chunk["duration"]),
            chunk["text"],
        )
        for chunk in chunks
        if chunk["text"].strip()
    ]
