"""Pure helpers for the pinned Folia native browser renderer."""

from __future__ import annotations

from typing import Any


FOLIA_RELEASE = "v0.7.7"
FOLIA_DOCKER_STACK = "1.0.26"
FOLIA_RENDERER_REVISION = "80c073490482303d4283d1d5205be7707c96179d"
FOLIA_PATCH_PROFILE = "studio-font-outline-v1"

FOLIA_EFFECTS = [
    {"mode": "sonnet", "label": "商籁", "description": "电影分镜与光束歌词"},
    {"mode": "tempera", "label": "Tempera", "description": "拼贴色块与动态排版"},
    {"mode": "classic", "label": "Luminous", "description": "Folia 经典逐字流光"},
    {"mode": "cadenza", "label": "Mindscape", "description": "沉浸式空间歌词"},
    {"mode": "partita", "label": "云阶", "description": "层叠云阶歌词"},
    {"mode": "fume", "label": "Fume", "description": "文章式烟雾排版"},
    {"mode": "tilt", "label": "Tilt", "description": "倾斜动态字阵"},
    {"mode": "claddagh", "label": "Claddagh", "description": "环形轨道歌词"},
    {"mode": "monet", "label": "Monet", "description": "海报歌词与频谱"},
    {"mode": "pendolo", "label": "Pendolo", "description": "钟摆式歌词"},
    {"mode": "cappella", "label": "Cappella", "description": "合唱角色气泡"},
    {"mode": "diorama", "label": "镜台", "description": "三维镜台歌词"},
    {"mode": "still", "label": "Still", "description": "克制静态排版"},
]
FOLIA_EFFECT_MODES = {item["mode"] for item in FOLIA_EFFECTS}

SONNET_PREVIEW_TUNING = {
    "cameraIntensity": 1, "typographyMotion": 1, "mgDensity": 1,
    "showOnlyText": False, "showGuide": True, "showBackgroundMg": True,
    "showFixedGeo": True, "showGiantDecorativeText": True,
    "showBackgroundDecor": True, "enableTransitions": True,
    "outerFrameMode": "full", "textureResolution": 0.75,
    "postProcessEnabled": False, "postProcessGrain": 0.2,
    "postProcessContrast": 0, "postProcessRgbShift": 0,
    "postProcessHalftone": 0, "postProcessVignette": 0.85,
    "postProcessLensDistortion": 0.3, "postProcessLensDispersion": 0.6,
}

TEMPERA_DEFAULT_TUNING = {
    "cameraIntensity": 1,
    "glyphMotion": 1,
    "glyphSettleStretch": 0.5,
    "colorMode": "duo",
    "showBlocks": True,
    "showDecor": True,
    "textInversion": True,
    "layerImages": [],
    "layerImageDepth": "back",
    "layerImageFrequency": 0.6,
    "enableTransitions": True,
    "textureResolution": 1.5,
    "postProcessEnabled": True,
    "postProcessTextureCompression": False,
    "postProcessGrain": 0.2,
    "postProcessContrast": 0,
    "postProcessRgbShift": 0,
    "postProcessVignette": 0.85,
    "postProcessLensDistortion": 0.3,
}

TEMPERA_FOREGROUND_TUNING = {
    "showBlocks": False,
    "textInversion": False,
    "colorMode": "duo",
    # Tempera's transition wipe briefly paints an opaque full-frame paper
    # layer. It is part of the scene background, not the lyric foreground.
    "enableTransitions": False,
}

DEFAULT_FOLIA_SETTINGS: dict[str, Any] = {
    "schema_version": 1,
    "renderer_revision": FOLIA_RENDERER_REVISION,
    "mode": "classic",
    "seed": "folia-video-studio",
    "lyrics_font_scale": 1.0,
    "subtitle_font_scale": 1.0,
    "visualizer_opacity": 1.0,
    "font_asset_id": None,
    "text_outline": {"enabled": True, "width_px": 3.0, "color": "#000000", "scope": "primary"},
    "position_x": 50.0,
    "position_y": 50.0,
    "theme": {
        "name": "Midnight Default",
        "backgroundColor": "#09090b",
        "primaryColor": "#f4f4f5",
        "accentColor": "#f4f4f5",
        "secondaryColor": "#71717a",
        "fontStyle": "sans",
        "fontFamily": "Noto Sans CJK SC",
        "fontWeight": 700,
        "animationIntensity": "normal",
    },
    "visualizer_tunings": {},
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "keep_alpha_mov": True,
    "alpha_mov_audio": False,
}


def normalized_folia_settings(raw: dict[str, Any] | None, seed: str = "folia-video-studio") -> dict[str, Any]:
    raw = raw or {}
    result = {**DEFAULT_FOLIA_SETTINGS, **raw}
    result["theme"] = {**DEFAULT_FOLIA_SETTINGS["theme"], **(raw.get("theme") or {})}
    result["visualizer_tunings"] = raw.get("visualizer_tunings") or {}
    result["text_outline"] = {**DEFAULT_FOLIA_SETTINGS["text_outline"], **(raw.get("text_outline") or {})}
    result["renderer_revision"] = FOLIA_RENDERER_REVISION
    result["schema_version"] = 1
    result["mode"] = result["mode"] if result["mode"] in FOLIA_EFFECT_MODES else "classic"
    result["seed"] = str(result.get("seed") or seed)
    result["width"], result["height"], result["fps"] = 1920, 1080, 30
    result["keep_alpha_mov"], result["alpha_mov_audio"] = True, False
    result["lyrics_font_scale"] = max(0.5, min(2.0, float(result.get("lyrics_font_scale", 1))))
    result["subtitle_font_scale"] = max(0.5, min(2.0, float(result.get("subtitle_font_scale", 1))))
    result["visualizer_opacity"] = max(0.0, min(1.0, float(result.get("visualizer_opacity", 1))))
    result["font_asset_id"] = str(result.get("font_asset_id") or "") or None
    outline = result["text_outline"]
    outline["enabled"] = bool(outline.get("enabled", True))
    outline["width_px"] = max(0.0, min(12.0, float(outline.get("width_px", 3))))
    color = str(outline.get("color") or "#000000")
    outline["color"] = color if len(color) == 7 and color.startswith("#") else "#000000"
    outline["scope"] = "primary"
    result["position_x"] = max(0.0, min(100.0, float(result.get("position_x", 50))))
    result["position_y"] = max(0.0, min(100.0, float(result.get("position_y", 50))))
    intensity = result["theme"].get("animationIntensity")
    if intensity not in {"calm", "normal", "chaotic"}:
        result["theme"]["animationIntensity"] = "normal"
    return result


def _timed_words(line: dict[str, Any], offset_ms: int, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    text = str(line.get("text") or "")
    words = line.get("words") or []
    valid = (
        line.get("timing_precision") in {"forced-character", "corrected-character"}
        and words
        and "".join(str(item.get("text") or "") for item in words) == text
    )
    if valid:
        return [
            {
                "text": str(item.get("text") or ""),
                "startTime": (int(item.get("start_ms", start_ms)) + offset_ms) / 1000,
                "endTime": (int(item.get("end_ms", end_ms)) + offset_ms) / 1000,
            }
            for item in words
        ]
    chars = list(text)
    span = max(1, end_ms - start_ms)
    return [
        {
            "text": char,
            "startTime": (start_ms + round(span * index / max(1, len(chars)))) / 1000,
            "endTime": (start_ms + round(span * (index + 1) / max(1, len(chars)))) / 1000,
        }
        for index, char in enumerate(chars)
    ]


def build_folia_config(
    job: dict[str, Any],
    settings: dict[str, Any] | None = None,
    timeline_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Translate the studio's millisecond timeline into Folia's OBS contract."""
    alignment = job.get("alignment") or {}
    source_lines = alignment.get("lines", []) if isinstance(alignment, dict) else alignment
    offset_ms = int(alignment.get("offset_ms", 0)) if isinstance(alignment, dict) else 0
    cfg = normalized_folia_settings(settings or (job.get("style") or {}).get("folia"), str(job.get("id") or "folia-video-studio"))
    rows = timeline_rows or [
        {
            "line": line,
            "start": int(line.get("start_ms", 0)) + offset_ms,
            "end": int(line.get("end_ms", 0)) + offset_ms,
        }
        for line in source_lines
        if not line.get("deleted") and str(line.get("text") or "").strip()
    ]
    folia_lines = []
    for index, row in enumerate(rows):
        line = row["line"]
        start_ms, end_ms = int(row["start"]), max(int(row["start"]) + 1, int(row["end"]))
        words = _timed_words(line, offset_ms, start_ms - offset_ms, end_ms - offset_ms)
        folia_lines.append(
            {
                "id": str(line.get("line_id", index)),
                "words": words,
                "startTime": start_ms / 1000,
                "endTime": end_ms / 1000,
                "fullText": str(line.get("text") or ""),
            }
        )
    theme = dict(cfg["theme"])
    theme["studioTextOutline"] = dict(cfg["text_outline"])
    if cfg.get("font_asset_id"):
        theme["studioFontAssetUrl"] = f"/fonts/{cfg['font_asset_id']}"
    tunings = dict(cfg["visualizer_tunings"])
    song = {"id": str(job.get("id") or "studio"), "name": str(job.get("title") or "现场演唱")}
    song_artist = str(job.get("artist") or "现场演唱")
    song_album = "Folia 歌词视频工坊"
    if cfg["mode"] == "tempera":
        supplied = tunings.get("tempera") if isinstance(tunings.get("tempera"), dict) else {}
        tunings["tempera"] = {**TEMPERA_DEFAULT_TUNING, **supplied, **TEMPERA_FOREGROUND_TUNING}
        primary = str(theme.get("primaryColor") or "#f4f4f5").lstrip("#")
        try:
            red, green, blue = (int(primary[i:i + 2], 16) for i in (0, 2, 4))
            luminance = red * .2126 + green * .7152 + blue * .0722
            theme["backgroundColor"] = "#000000" if luminance >= 128 else "#ffffff"
        except (ValueError, TypeError):
            pass
        # Tempera's metadata poster is itself a full-frame opaque composition.
        song = None
        song_artist = None
        song_album = None
    return {
        "activePlaybackContext": "main",
        "stageSource": None,
        "hasTrack": True,
        "song": song,
        "songArtist": song_artist,
        "songAlbum": song_album,
        "coverUrl": None,
        "lyrics": {
            "lines": folia_lines,
            "title": str(job.get("title") or "现场演唱"),
            "artist": str(job.get("artist") or "现场演唱"),
            "isWordByWord": True,
        },
        "theme": theme,
        "subtitleTheme": theme,
        "isDaylight": False,
        "visualizerMode": cfg["mode"],
        "visualizerTunings": tunings,
        # The shell is always transparent. Visualizers with their own opaque
        # scene ground (currently Tempera) are converted to foreground-only
        # above while preserving their text/decor animation layers.
        "background": {"mode": "common", "transparent": True},
        "transparentBackground": True,
        "lyricsFontScale": cfg["lyrics_font_scale"],
        "subtitleFontScale": cfg["subtitle_font_scale"],
        "visualizerOpacity": cfg["visualizer_opacity"],
        "subtitleOverlayOpacity": 1,
        "subtitleOverlayBackground": True,
        "showHarmonySubtitle": True,
        "harmonySubtitleBackground": True,
        "staticMode": False,
        "hideTranslationSubtitle": True,
        "showSubtitleTranslation": False,
        "subtitleContentMode": "none",
        "seed": cfg["seed"],
        "studioTransform": {"x": cfg["position_x"], "y": cfg["position_y"]},
        "updatedAt": 0,
    }


def apply_folia_preview_profile(config: dict[str, Any]) -> dict[str, Any]:
    """Keep export exact while making the embedded browser preview affordable."""
    result = dict(config)
    tunings = dict(result.get("visualizerTunings") or {})
    if result.get("visualizerMode") == "sonnet":
        supplied = tunings.get("sonnet") if isinstance(tunings.get("sonnet"), dict) else {}
        sonnet = {**SONNET_PREVIEW_TUNING, **supplied}
        sonnet["textureResolution"] = min(0.75, max(0.5, float(sonnet.get("textureResolution", 0.75))))
        sonnet["postProcessEnabled"] = False
        sonnet["showOnlyText"] = False
        tunings["sonnet"] = sonnet
    elif result.get("visualizerMode") == "tempera":
        supplied = tunings.get("tempera") if isinstance(tunings.get("tempera"), dict) else {}
        tempera = dict(supplied)
        tempera["textureResolution"] = min(0.5, max(0.35, float(tempera.get("textureResolution", 0.5))))
        tempera["postProcessEnabled"] = False
        tunings["tempera"] = tempera
    result["visualizerTunings"] = tunings
    result["previewProfile"] = "balanced"
    return result


def apply_folia_fast_profile(config: dict[str, Any]) -> dict[str, Any]:
    """Keep real-time capture within the NAS software-rendering budget."""
    result = dict(config)
    tunings = dict(result.get("visualizerTunings") or {})
    if result.get("visualizerMode") == "tempera":
        supplied = tunings.get("tempera") if isinstance(tunings.get("tempera"), dict) else {}
        tempera = dict(supplied)
        tempera["textureResolution"] = min(0.5, max(0.35, float(tempera.get("textureResolution", 0.5))))
        tempera["postProcessEnabled"] = False
        tunings["tempera"] = tempera
        result["renderProfile"] = "tempera-realtime"
    result["visualizerTunings"] = tunings
    return result
