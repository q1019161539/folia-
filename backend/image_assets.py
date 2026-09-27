"""Validated, persistent image assets for Folia's Tempera image pool."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_EDGE = 2048
MAX_POOL_IMAGES = 16
FORMATS = {"PNG": (".png", "image/png"), "JPEG": (".jpg", "image/jpeg"), "WEBP": (".webp", "image/webp")}
IMAGE_ID = re.compile(r"[0-9a-f]{64}\Z")
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def store_image(root: Path, filename: str, content: bytes) -> dict[str, Any]:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("图片不能为空且不能超过 10 MB")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in FORMATS or source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("只支持不超过 4000 万像素的 PNG、JPEG 或 WebP 图片")
            image = ImageOps.exif_transpose(source)
            image.load()
            suffix, _ = FORMATS[source.format]
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            if suffix == ".jpg":
                image = image.convert("RGB")
            else:
                image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
            output = io.BytesIO()
            if suffix == ".jpg":
                image.save(output, format="JPEG", quality=90, optimize=True)
            elif suffix == ".webp":
                image.save(output, format="WEBP", quality=90, method=4)
            else:
                image.save(output, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("图片文件无法解码") from exc
    data = output.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{digest}{suffix}"
    metadata_path = root / f"{digest}.json"
    if not path.exists():
        path.write_bytes(data)
    if metadata_path.exists():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    name = Path(filename or "图片").name[:100]
    item = {"id": digest, "name": name, "extension": suffix, "size": len(data), "width": image.width, "height": image.height}
    metadata_path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    return item


def resolve_image(root: Path, image_id: str) -> tuple[Path, dict[str, Any]]:
    if not IMAGE_ID.fullmatch(str(image_id or "")):
        raise FileNotFoundError(image_id)
    item = json.loads((root / f"{image_id}.json").read_text(encoding="utf-8"))
    if item.get("id") != image_id or item.get("extension") not in {v[0] for v in FORMATS.values()}:
        raise FileNotFoundError(image_id)
    path = root / f"{image_id}{item['extension']}"
    if not path.is_file():
        raise FileNotFoundError(image_id)
    return path, item


def list_images(root: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        try:
            _, item = resolve_image(root, path.stem)
            result.append(item)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return result


def resolve_tempera_pool(root: Path, raw: Any, project_id: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not isinstance(raw, list) or len(raw) > MAX_POOL_IMAGES:
        raise ValueError("Tempera 图片池最多 16 张")
    placements: list[dict[str, Any]] = []
    assets: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Tempera 图片设置无效")
        image_id = str(entry.get("id") or "")
        if image_id in seen:
            continue
        try:
            _, item = resolve_image(root, image_id)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"Tempera 图片缺失：{image_id[:12]}") from exc
        seen.add(image_id)
        align = entry.get("align", "free")
        vertical = entry.get("verticalAlign", "bottom")
        if align not in {"left", "center", "right", "free"} or vertical not in {"top", "center", "bottom", "free"}:
            raise ValueError("Tempera 图片位置无效")
        try:
            scale = float(entry.get("scale", 0.7))
            opacity = float(entry.get("opacity", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tempera 图片大小或透明度无效") from exc
        if not (0.1 <= scale <= 1.5 and 0 <= opacity <= 1):
            raise ValueError("Tempera 图片大小或透明度超出范围")
        placements.append({"id": image_id, "name": item["name"], "align": align, "verticalAlign": vertical, "scale": scale, "opacity": opacity})
        assets.append({"id": image_id, "name": item["name"], "url": f"/images/{project_id}/{image_id}"})
    return placements, assets
