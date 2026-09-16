from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib import error, request


DEFAULT_MODEL = "qwen3-asr-flash"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"


def _language_code(language: str) -> str:
    normalized = language.strip().lower()
    return {
        "chinese": "zh",
        "中文": "zh",
        "english": "en",
        "japanese": "ja",
        "korean": "ko",
    }.get(normalized, normalized or "zh")


def _response_text(payload: dict[str, Any]) -> str:
    try:
        content = payload["output"]["choices"][0]["message"]["content"]
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    return str(item["text"]).strip()
        if isinstance(content, str):
            return content.strip()
    except (KeyError, IndexError, TypeError):
        pass
    raise RuntimeError(f"阿里云 ASR 返回中没有文字：{json.dumps(payload, ensure_ascii=False)[:800]}")


def _transcribe_file(path: Path, *, api_key: str, base_url: str, model: str, language: str) -> tuple[str, str | None]:
    data_url = "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    if len(data_url.encode("ascii")) > 10 * 1024 * 1024:
        raise ValueError("阿里云 qwen3-asr-flash 单块 Base64 数据不能超过 10 MB，请缩短 ASR 切块")
    body = json.dumps(
        {
            "model": model,
            "input": {"messages": [{"role": "user", "content": [{"audio": data_url}]}]},
            "parameters": {"asr_options": {"language": _language_code(language), "enable_itn": False}},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    endpoint = base_url.rstrip("/") + "/services/aigc/multimodal-generation/generation"
    http_request = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(http_request, timeout=600) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"阿里云 ASR 请求失败（HTTP {exc.code}）：{detail[:800]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"无法连接阿里云 ASR：{exc.reason}") from exc
    return _response_text(payload), payload.get("request_id")


def transcribe_chunks_aliyun(
    chunks: list[dict[str, object]],
    *,
    model_name: str = DEFAULT_MODEL,
    language: str = "Chinese",
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    base_url = os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL).strip()
    if not api_key:
        raise RuntimeError("尚未配置 DASHSCOPE_API_KEY，无法使用阿里云 ASR")
    output: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        path = Path(chunk["path"])
        for attempt in range(3):
            try:
                text, request_id = _transcribe_file(path, api_key=api_key, base_url=base_url, model=model_name, language=language)
                break
            except Exception as exc:
                if attempt == 2: raise RuntimeError(f"阿里云 ASR 第 {index + 1} 块连续失败 3 次：{exc}") from exc
        output.append(
            {
                "index": index,
                "path": str(path),
                "offset": float(chunk["offset"]),
                "duration": float(chunk["duration"]),
                "language": language,
                "text": text,
                "provider": "aliyun",
                "request_id": request_id,
            }
        )
        if progress:
            progress(index + 1, len(chunks))
    return output
