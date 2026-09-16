"""One-frame Tempera alpha/colour smoke test for an already running renderer."""

import json
import os
import subprocess
import urllib.request

from app import ChromiumPage


TOKEN = os.getenv("SMOKE_EXISTING_TOKEN", "studio-smoke-tempera")
THEME = {
    "name": "Smoke", "backgroundColor": "#000000", "primaryColor": "#ff3366",
    "accentColor": "#33ff99", "secondaryColor": "#71717a",
    "fontStyle": "sans", "animationIntensity": "normal",
}
CONFIG = {
    "activePlaybackContext": "main", "stageSource": None, "hasTrack": True,
    "song": None, "songArtist": None, "songAlbum": None, "coverUrl": None,
    "lyrics": {"lines": [{
        "id": "1", "fullText": "测试", "startTime": 0.0, "endTime": 4.0,
        "words": [
            {"text": "测", "startTime": 0.0, "endTime": 2.0},
            {"text": "试", "startTime": 2.0, "endTime": 4.0},
        ],
    }], "title": "", "artist": "", "isWordByWord": True},
    "theme": THEME, "subtitleTheme": THEME, "isDaylight": False,
    "visualizerMode": "tempera",
    "visualizerTunings": {"tempera": {
        "cameraIntensity": 1, "glyphMotion": 1, "glyphSettleStretch": 0.5,
        "showBlocks": False, "showDecor": True, "textInversion": False,
        "colorMode": "duo", "layerImages": [], "layerImageDepth": "back",
        "layerImageFrequency": 0.6, "enableTransitions": True,
        "textureResolution": 0.5, "postProcessEnabled": False,
        "postProcessTextureCompression": False, "postProcessGrain": 0.2,
        "postProcessContrast": 0, "postProcessRgbShift": 0,
        "postProcessVignette": 0.85, "postProcessLensDistortion": 0.3,
    }},
    "background": {"mode": "common", "transparent": True},
    "transparentBackground": True, "lyricsFontScale": 1, "subtitleFontScale": 1,
    "visualizerOpacity": 1, "subtitleOverlayOpacity": 1,
    "subtitleOverlayBackground": False, "showHarmonySubtitle": False,
    "harmonySubtitleBackground": False, "staticMode": False,
    "hideTranslationSubtitle": True, "showSubtitleTranslation": False,
    "subtitleContentMode": "none", "seed": "smoke",
    "studioTransform": {"x": 50, "y": 65}, "updatedAt": 0,
}


def send(method: str, path: str, body: dict) -> None:
    request = urllib.request.Request(
        "http://127.0.0.1:8091" + path,
        data=json.dumps(body).encode(), method=method,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request, timeout=10).read()


if not os.getenv("SMOKE_EXISTING_TOKEN"):
    send("PUT", f"/api/sessions/{TOKEN}", {"config": CONFIG})
    send("POST", f"/api/sessions/{TOKEN}/control", {
        "current_ms": 1500, "duration_ms": 4000, "playing": False,
        "audio": {"audioPower": 80, "bands": {
            "bass": 80, "lowMid": 80, "mid": 80, "vocal": 80, "treble": 80,
        }, "spectrum": [80] * 256},
    })
page = ChromiumPage(f"http://127.0.0.1:8091/obs?obs=1&token={TOKEN}", CONFIG["studioTransform"])
try:
    dom = page.call("Runtime.evaluate", {"expression": "JSON.stringify({canvas:document.querySelectorAll('canvas').length,root:document.getElementById('root')?.children.length||0,transform:document.getElementById('root')?.style.transform||''})", "returnByValue": True})
    png = page.screenshot()
    rgba = subprocess.check_output([
        "ffmpeg", "-v", "error", "-f", "image2pipe", "-i", "pipe:0",
        "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1",
    ], input=png)
    alpha = rgba[3::4]
    pink = sum(
        rgba[index] > 180 and rgba[index + 1] < 140 and rgba[index + 2] < 180 and rgba[index + 3] > 0
        for index in range(0, len(rgba), 4)
    )
    print(json.dumps({
        "pixels": len(alpha), "transparent": sum(value == 0 for value in alpha),
        "visible": sum(value > 0 for value in alpha),
        "transparent_ratio": round(sum(value == 0 for value in alpha) / len(alpha), 4),
        "pink_pixels": pink, "dom": dom.get("result", {}).get("value"),
        "exceptions": [event for event in page.events if event.get("method") == "Runtime.exceptionThrown"],
    }))
finally:
    page.close()
