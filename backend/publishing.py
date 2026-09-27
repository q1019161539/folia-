"""Phase 1 preparation for publishing rendered Folia clips through BililiveTool.

This module deliberately has no upload method.  Phase 1 may read a preset and
validate a merged config, but it cannot create a BililiveTool upload task.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont


class PublishPrepareError(RuntimeError):
    """A deterministic preparation error that must not be retried automatically."""


class PublishRetryableError(RuntimeError):
    """A temporary BililiveTool/network error that may be retried."""


@dataclass(frozen=True)
class PublishSettings:
    enabled: bool
    auto_publish_enabled: bool
    bililive_base_url: str
    bililive_passkey: str
    bililive_uid: int
    bililive_preset_id: str
    output_root: Path
    output_legacy_root: Path
    bililive_output_root: Path
    bililive_output_legacy_root: Path
    cover_template_root: Path
    cover_output_root: Path
    retry_base_seconds: int = 60
    reconcile_lookback_seconds: int = 86400

    @classmethod
    def from_env(cls) -> "PublishSettings":
        def flag(name: str, default: str = "0") -> bool:
            return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

        raw_uid = os.getenv("BILILIVETOOL_UID", "0").strip()
        try:
            uid = int(raw_uid or "0")
        except ValueError:
            uid = 0
        output_root = Path(os.getenv("OUTPUT_ROOT", "/output")).resolve()
        return cls(
            enabled=flag("PUBLISH_ENABLED"),
            auto_publish_enabled=flag("AUTO_PUBLISH_ENABLED"),
            bililive_base_url=os.getenv("BILILIVETOOL_BASE_URL", "http://host.docker.internal:2333/api").rstrip("/"),
            bililive_passkey=os.getenv("BILILIVETOOL_PASSKEY", "").strip(),
            bililive_uid=uid,
            bililive_preset_id=os.getenv("BILILIVETOOL_PRESET_ID", "").strip(),
            output_root=output_root,
            output_legacy_root=Path(os.getenv("OUTPUT_LEGACY_ROOT", "/output-legacy")).resolve(),
            bililive_output_root=Path(os.getenv("BILILIVETOOL_OUTPUT_ROOT", "/app/Folia成片")),
            bililive_output_legacy_root=Path(os.getenv("BILILIVETOOL_OUTPUT_LEGACY_ROOT", "/app/历史Folia成片")),
            cover_template_root=Path(os.getenv("COVER_TEMPLATE_ROOT", "/cover-templates")).resolve(),
            cover_output_root=Path(os.getenv("COVER_OUTPUT_ROOT", str(output_root / "publish" / "covers"))).resolve(),
            retry_base_seconds=max(10, int(os.getenv("PUBLISH_RETRY_BASE_SECONDS", "60"))),
            reconcile_lookback_seconds=max(300, int(os.getenv("PUBLISH_RECONCILE_LOOKBACK_SECONDS", "86400"))),
        )


def streamer_from_source(source: str) -> str:
    parts = Path(str(source or "")).parts
    if parts and parts[0].lower() in {"bilibili", "douyin", "huya", "douyu"} and len(parts) > 1:
        return parts[1].strip()
    return parts[0].strip() if parts else ""


def build_title(streamer: str, identified_title: str, max_length: int = 80) -> str:
    streamer = str(streamer or "").strip()
    identified_title = str(identified_title or "").strip()
    if not identified_title:
        raise PublishPrepareError("缺少 identified_title，不允许使用歌词候选或显示标题兜底")
    if not streamer:
        raise PublishPrepareError("无法从录播路径确定主播名")
    suffix = f"《{identified_title}》｜直播翻唱"
    title = streamer + suffix
    if len(title) <= max_length:
        return title
    available = max_length - len(suffix)
    if available <= 0:
        raise PublishPrepareError("identified_title 过长，无法在不改写歌名的前提下生成投稿标题")
    compact_streamer = streamer[:available] if available <= 1 else streamer[: available - 1] + "…"
    return compact_streamer + suffix


def build_description(streamer: str, identified_title: str, identified_artist: str) -> str:
    rows = [f"主播：{streamer}", f"曲目：《{identified_title}》"]
    if str(identified_artist or "").strip():
        rows.append(f"原唱/歌手：{str(identified_artist).strip()}")
    rows.append("本视频为直播翻唱切片，由 Folia 自动切歌并制作歌词视频。")
    return "\n".join(rows)


def build_tags(streamer: str, identified_title: str, identified_artist: str, limit: int = 10) -> list[str]:
    result: list[str] = []
    for value in (streamer, identified_title, identified_artist, "直播翻唱", "翻唱"):
        tag = str(value or "").strip()
        if tag and tag not in result:
            result.append(tag)
    return result[:limit]


def stable_template_index(streamer: str, identified_title: str, template_count: int) -> int:
    if template_count <= 0:
        raise PublishPrepareError("封面模板库为空")
    digest = hashlib.sha256((str(streamer) + "\0" + str(identified_title)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % template_count


def list_cover_templates(root: Path) -> list[Path]:
    generic = root / "generic"
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted(path for path in generic.iterdir() if path.is_file() and path.suffix.lower() in allowed) if generic.is_dir() else []


def choose_cover_template(root: Path, streamer: str, identified_title: str) -> Path:
    templates = list_cover_templates(root)
    return templates[stable_template_index(streamer, identified_title, len(templates))]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_lines(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_lines: int = 2) -> tuple[list[str], Any]:
    for size in range(190, 71, -6):
        font = _font(size)
        lines: list[str] = []
        current = ""
        for char in text:
            candidate = current + char
            if current and draw.textbbox((0, 0), candidate, font=font, stroke_width=4)[2] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
        if len(lines) <= max_lines:
            return lines, font
    raise PublishPrepareError("歌名过长，无法在封面上完整排版")


def render_cover(template: Path, destination: Path, identified_title: str, streamer: str) -> Path:
    if not identified_title.strip():
        raise PublishPrepareError("缺少 identified_title，无法生成封面")
    try:
        with Image.open(template) as raw:
            image = raw.convert("RGB")
    except Exception as exc:
        raise PublishPrepareError(f"封面模板无法读取：{template}") from exc
    target_ratio = 16 / 9
    ratio = image.width / image.height
    if ratio > target_ratio:
        width = round(image.height * target_ratio)
        left = (image.width - width) // 2
        image = image.crop((left, 0, left + width, image.height))
    elif ratio < target_ratio:
        height = round(image.width / target_ratio)
        top = (image.height - height) // 2
        image = image.crop((0, top, image.width, top + height))
    image = image.resize((1920, 1080), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle((115, 170, 1805, 910), radius=46, fill=(0, 0, 0, 108))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    lines, title_font = _fit_lines(draw, identified_title.strip(), 1540)
    line_boxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=5) for line in lines]
    heights = [box[3] - box[1] for box in line_boxes]
    spacing = 28
    total_height = sum(heights) + spacing * (len(lines) - 1)
    y = 475 - total_height // 2
    for line, box, height in zip(lines, line_boxes, heights):
        width = box[2] - box[0]
        draw.text(((1920 - width) // 2, y), line, font=title_font, fill="white", stroke_width=5, stroke_fill=(0, 0, 0))
        y += height + spacing
    streamer_font = _font(64)
    streamer_box = draw.textbbox((0, 0), streamer, font=streamer_font, stroke_width=3)
    draw.text(((1920 - (streamer_box[2] - streamer_box[0])) // 2, 790), streamer, font=streamer_font, fill=(236, 236, 236), stroke_width=3, stroke_fill=(0, 0, 0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        image.save(destination, "JPEG", quality=92, optimize=True)
        with Image.open(destination) as check:
            check.verify()
        if destination.stat().st_size <= 0:
            raise OSError("生成文件为空")
        with Image.open(destination) as check:
            if check.size != (1920, 1080):
                raise OSError(f"封面尺寸错误：{check.size}")
    except Exception as exc:
        raise PublishPrepareError(f"封面生成失败：{exc}") from exc
    return destination


def map_to_bililive_path(path: Path, settings: PublishSettings) -> str:
    resolved = path.resolve()
    mappings = (
        (settings.output_legacy_root, settings.bililive_output_legacy_root),
        (settings.output_root, settings.bililive_output_root),
    )
    for source_root, target_root in mappings:
        try:
            relative = resolved.relative_to(source_root)
        except ValueError:
            continue
        return (target_root / relative).as_posix()
    raise PublishPrepareError(f"文件不在可共享的 Folia 成片目录内：{resolved}")


def preset_description_template(preset: dict[str, Any], fallback: str) -> str:
    config = preset.get("config")
    if not isinstance(config, dict):
        raise PublishPrepareError("BililiveTool preset 缺少 config")
    return str(config.get("desc") or "").strip() or fallback


def merge_preset_config(preset: dict[str, Any], title: str, description: str, tags: list[str], cover_path: str) -> dict[str, Any]:
    config = copy.deepcopy(preset.get("config"))
    if not isinstance(config, dict):
        raise PublishPrepareError("BililiveTool preset 缺少 config")
    config.update({"title": title, "desc": description, "tag": list(tags), "cover": cover_path})
    return config


def build_payload(uid: int, video_path: str, part_title: str, config: dict[str, Any]) -> dict[str, Any]:
    if uid <= 0:
        raise PublishPrepareError("BILILIVETOOL_UID 未配置")
    return {
        "uid": uid,
        "videos": [{"path": video_path, "title": part_title}],
        "config": copy.deepcopy(config),
        "options": {"removeOriginAfterUploadCheck": False},
    }


def retry_delay_seconds(attempt: int, base_seconds: int = 60) -> int:
    return min(3600, max(10, base_seconds) * (2 ** max(0, min(attempt - 1, 6))))


class BililiveToolClient:
    def __init__(self, base_url: str, passkey: str, timeout: float = 20.0, transport: httpx.BaseTransport | None = None):
        if not passkey:
            raise PublishPrepareError("BILILIVETOOL_PASSKEY 未配置")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": passkey},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise PublishRetryableError(f"BililiveTool 暂时无法访问：{exc}") from exc
        if response.status_code >= 500:
            raise PublishRetryableError(f"BililiveTool HTTP {response.status_code}：{response.text[:500]}")
        return response

    def get_video_preset(self, preset_id: str) -> dict[str, Any]:
        if not preset_id:
            raise PublishPrepareError("BILILIVETOOL_PRESET_ID 未配置")
        response = self._request("GET", f"/preset/video/{preset_id}")
        if response.status_code != 200:
            raise PublishPrepareError(f"读取 BililiveTool preset 失败（HTTP {response.status_code}）：{response.text[:500]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise PublishPrepareError("BililiveTool preset 返回了非法 JSON") from exc
        if not isinstance(data, dict):
            raise PublishPrepareError("BililiveTool preset 返回结构无效")
        return data

    def list_video_presets(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/preset/video")
        if response.status_code != 200:
            raise PublishPrepareError(f"读取 BililiveTool preset 列表失败（HTTP {response.status_code}）：{response.text[:500]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise PublishPrepareError("BililiveTool preset 列表返回了非法 JSON") from exc
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise PublishPrepareError("BililiveTool preset 列表返回结构无效")
        return data

    def format_description(self, template: str, options: dict[str, Any]) -> str:
        response = self._request("POST", "/bili/formatDesc", json={"template": template, "options": options})
        if response.status_code != 200:
            raise PublishPrepareError(f"BililiveTool 简介模板格式化失败（HTTP {response.status_code}）：{response.text[:500]}")
        description = response.text.strip()
        if not description:
            raise PublishPrepareError("BililiveTool 简介模板格式化结果为空")
        return description

    def validate_upload_config(self, config: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", "/bili/validUploadParams", json=config)
        result = {"status_code": response.status_code, "body": response.text}
        if response.status_code == 400:
            raise PublishPrepareError(f"BililiveTool 投稿参数校验失败：{response.text[:1000]}")
        if response.status_code != 200 or response.text.strip() != "success":
            raise PublishPrepareError(f"BililiveTool 投稿参数校验返回异常：HTTP {response.status_code} {response.text[:1000]}")
        return result


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
