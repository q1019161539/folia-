"""Persistent font assets shared by preview and native video renders."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any
from fontTools.ttLib import TTFont, TTLibError


MAX_FONT_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".ttf", ".otf", ".woff2"}
BUILTIN_FONTS = [
    {"id": "builtin-sans", "family": "Noto Sans CJK SC", "label": "思源黑体", "style": "sans", "builtin": True},
    {"id": "builtin-serif", "family": "Noto Serif CJK SC", "label": "思源宋体", "style": "serif", "builtin": True},
    {"id": "builtin-mono", "family": "Noto Sans Mono CJK SC", "label": "中文等宽", "style": "mono", "builtin": True},
]


def _safe_family(value: str) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", "", str(value or "")).strip()
    return value[:100]


def validate_font_bytes(filename: str, content: bytes) -> tuple[str, str]:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("只支持 TTF、OTF 或 WOFF2 字体")
    if not content:
        raise ValueError("字体文件为空")
    if len(content) > MAX_FONT_BYTES:
        raise ValueError("字体文件不能超过 20 MB")
    signatures = {
        ".ttf": (b"\x00\x01\x00\x00", b"true", b"ttcf"),
        ".otf": (b"OTTO",),
        ".woff2": (b"wOF2",),
    }
    if not any(content.startswith(signature) for signature in signatures[suffix]):
        raise ValueError("字体文件头无效")
    try:
        font = TTFont(io.BytesIO(content), lazy=False)
        names = font["name"].names
        family = ""
        for name_id in (16, 1):
            for record in names:
                if record.nameID == name_id:
                    family = _safe_family(record.toUnicode())
                    if family:
                        break
            if family:
                break
        font.close()
    except (TTLibError, KeyError, ValueError, OSError) as exc:
        raise ValueError("字体结构无效") from exc
    if not family:
        raise ValueError("字体缺少字体族名")
    return suffix, family


def store_font(root: Path, filename: str, family: str, content: bytes) -> dict[str, Any]:
    suffix, embedded_family = validate_font_bytes(filename, content)
    family = _safe_family(family) or embedded_family
    digest = hashlib.sha256(content).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{digest}{suffix}"
    metadata_path = root / f"{digest}.json"
    deduplicated = path.exists()
    if not deduplicated:
        path.write_bytes(content)
    metadata = {
        "id": digest,
        "family": family,
        "label": family,
        "filename": Path(filename).name,
        "extension": suffix,
        "size": len(content),
        "builtin": False,
        "deduplicated": deduplicated,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def list_fonts(root: Path) -> list[dict[str, Any]]:
    result = [dict(item) for item in BUILTIN_FONTS]
    if not root.exists():
        return result
    for path in sorted(root.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            asset = root / f"{item['id']}{item['extension']}"
            if asset.is_file():
                result.append(item)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return result


def resolve_font(root: Path, font_id: str) -> tuple[Path, dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-f]{64}", str(font_id or "")):
        raise FileNotFoundError(font_id)
    metadata_path = root / f"{font_id}.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    path = root / f"{font_id}{metadata['extension']}"
    if not path.is_file():
        raise FileNotFoundError(font_id)
    return path, metadata
