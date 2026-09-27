"""Render the pinned Folia OBS surface to an alpha MOV and composited MP4."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from websocket import create_connection


VERSION_INFO = json.loads((Path(__file__).with_name("folia-version.json")).read_text(encoding="utf-8"))
REVISION = VERSION_INFO["revision"]
RELEASE = VERSION_INFO["release"]
DOCKER_STACK = VERSION_INFO["docker_stack"]
TEXT_EDGE_PROFILE = VERSION_INFO["patch_profile"]
STATIC_ROOT = Path(os.getenv("FOLIA_STATIC_ROOT", "/usr/share/nginx/html")).resolve()
FONT_ROOT = Path(os.getenv("FONT_ROOT", "/fonts")).resolve()
IMAGE_ROOT = Path(os.getenv("IMAGE_ROOT", "/images")).resolve()
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/media/bililive")).resolve()
OUTPUT_ROOT = Path(os.getenv("OUTPUT_ROOT", "/output")).resolve()
PORT = int(os.getenv("RENDER_PORT", "8091"))
FPS, WIDTH, HEIGHT = 30, 1920, 1080
VALID_MODES = set(VERSION_INFO["modes"])

app = FastAPI(title="Folia Native Renderer", version="1.0.0")
state_lock = threading.Lock()
render_lock = threading.Lock()
sessions: dict[str, dict[str, Any]] = {}
render_jobs: dict[str, dict[str, Any]] = {}
cancel_events: dict[str, threading.Event] = {}
render_media: dict[str, Path] = {}


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_path(raw: str, root: Path, must_exist: bool = False) -> Path:
    path = Path(raw).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"路径超出允许目录：{root}")
    if must_exist and not path.is_file():
        raise ValueError("输入媒体不存在")
    return path


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("visualizerMode") not in VALID_MODES:
        raise ValueError("未知 Fonia 原生效果")
    config = dict(config)
    config["background"] = {"mode": "common", "transparent": True}
    config["transparentBackground"] = True
    assets = config.get("temperaLayerImageAssets") or []
    if not isinstance(assets, list) or len(assets) > 16:
        raise ValueError("Tempera 图片资产列表无效")
    for asset in assets:
        image_id = str(asset.get("id") or "") if isinstance(asset, dict) else ""
        url = str(asset.get("url") or "") if isinstance(asset, dict) else ""
        parts = url.split("/")
        project_id = parts[2] if len(parts) == 4 else ""
        if (len(image_id) != 64 or any(char not in "0123456789abcdef" for char in image_id)
                or len(project_id) != 32 or any(char not in "0123456789abcdef" for char in project_id)
                or url != f"/images/{project_id}/{image_id}"):
            raise ValueError("Tempera 图片地址无效")
        if not any((IMAGE_ROOT / project_id / f"{image_id}{suffix}").is_file() for suffix in (".png", ".jpg", ".webp")):
            raise ValueError(f"Tempera 图片缺失：{image_id[:12]}")
    config["updatedAt"] = now_ms()
    theme = dict(config.get("theme") or {})
    font_url = str(theme.get("studioFontAssetUrl") or "")
    if font_url and not font_url.startswith("/fonts/"):
        raise ValueError("自定义字体地址无效")
    config["theme"] = theme
    return config


def set_session(token: str, *, config: dict[str, Any] | None = None, clock: dict[str, Any] | None = None, audio: dict[str, Any] | None = None) -> None:
    with state_lock:
        session = sessions.setdefault(token, {"versions": {"config": 0, "clock": 0, "audio": 0}})
        for name, value in (("config", config), ("clock", clock), ("audio", audio)):
            if value is not None:
                session[name] = value
                session["versions"][name] += 1
        session["updated_at"] = time.time()


def get_session_snapshot(token: str) -> dict[str, Any]:
    with state_lock:
        session = sessions.get(token)
        if session is None:
            return {}
        # Updates replace config/clock/audio rather than mutating them. Only
        # the version counters need a copy before releasing the lock.
        return {**session, "versions": session["versions"].copy()}


@app.get("/healthz")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "revision": REVISION,
        "release": RELEASE,
        "docker_stack": DOCKER_STACK,
        "text_edge_profile": TEXT_EDGE_PROFILE,
        "render_busy": render_lock.locked(),
        "chromium": shutil.which("chromium") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }


@app.put("/api/sessions/{token}")
async def configure_session(token: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    try:
        config = validate_config(body.get("config") or body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    set_session(token, config=config)
    return {"ok": True, "token": token, "revision": REVISION}


@app.post("/api/sessions/{token}/control")
async def control_session(token: str, request: Request) -> dict[str, bool]:
    body = await request.json()
    supplied_clock = body.get("clock")
    clock = dict(supplied_clock) if isinstance(supplied_clock, dict) else {
        "currentTime": max(0, float(body.get("current_ms", 0)) / 1000),
        "duration": max(0, float(body.get("duration_ms", 0)) / 1000),
        "playerState": "PLAYING" if body.get("playing") else "PAUSED",
        "sentAtMs": now_ms(),
        "playbackRate": 1,
        "lyricOffsetMs": 0,
    }
    # Preview clocks are sampled in the same browser that consumes the SSE
    # event. Preserve that timestamp so Folia can compensate for HTTP/SSE
    # latency instead of treating an already stale position as current.
    try:
        clock["sentAtMs"] = float(clock.get("sentAtMs", now_ms()))
    except (TypeError, ValueError):
        clock["sentAtMs"] = now_ms()
    set_session(token, clock=clock, audio=body.get("audio"))
    return {"ok": True}


def sse_event(name: str, value: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}\n\n"


@app.get("/obs/events")
async def obs_events(token: str = "") -> StreamingResponse:
    async def stream():
        delivered = {"config": -1, "clock": -1, "audio": -1}
        heartbeat = time.monotonic()
        while True:
            snapshot = get_session_snapshot(token)
            versions = snapshot.get("versions") or {}
            for name in ("config", "clock", "audio"):
                if name in snapshot and versions.get(name, 0) != delivered[name]:
                    delivered[name] = versions.get(name, 0)
                    yield sse_event(name, snapshot[name])
            if time.monotonic() - heartbeat >= 10:
                heartbeat = time.monotonic()
                yield ": keepalive\n\n"
            await asyncio.sleep(0.01)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class OfflineAudio:
    """Approximate WebAudio AnalyserNode's pinned Folia FFT contract at output FPS."""

    def __init__(self, source: Path, start_seconds: float, duration_seconds: float):
        command = [
            "ffmpeg", "-v", "error", "-ss", f"{start_seconds:.3f}", "-t", f"{duration_seconds:.3f}",
            "-i", str(source), "-vn", "-ac", "1", "-ar", "44100", "-f", "f32le", "pipe:1",
        ]
        result = subprocess.run(command, capture_output=True)
        self.samples = np.frombuffer(result.stdout, dtype=np.float32) if result.returncode == 0 else np.zeros(1, dtype=np.float32)
        self.previous = np.zeros(1024, dtype=np.float32)
        self.window = np.hanning(2048).astype(np.float32)

    @staticmethod
    def process(value: float, boost: float = 2.0) -> float:
        return float(math.pow(max(0.0, min(1.0, value / 255.0)), boost) * 255.0)

    def frame(self, index: int) -> dict[str, Any]:
        center = round(index * 44100 / FPS)
        chunk = self.samples[center:center + 2048]
        if len(chunk) < 2048:
            chunk = np.pad(chunk, (0, 2048 - len(chunk)))
        magnitude = np.abs(np.fft.rfft(chunk * self.window))[:1024] / 1024
        db = 20 * np.log10(np.maximum(magnitude, 1e-7))
        current = np.clip((db + 100) * 255 / 70, 0, 255)
        self.previous = self.previous * 0.6 + current.astype(np.float32) * 0.4
        bins = np.rint(self.previous).astype(np.uint8)

        def energy(min_hz: float, max_hz: float) -> float:
            start, end = math.floor(min_hz / 21.5), math.floor(max_hz / 21.5)
            return float(np.mean(bins[start:end + 1])) if end >= start else 0.0

        bass, low_mid = energy(20, 150), energy(150, 400)
        mid, vocal, treble = energy(400, 1200), energy(1000, 3500), energy(3500, 12000)
        spectrum = np.rint(bins.reshape(256, 4).mean(axis=1)).astype(np.uint8).tolist()
        return {
            "audioPower": self.process((bass + low_mid) / 2, 3),
            "bands": {
                "bass": self.process(bass, 1.8), "lowMid": self.process(low_mid, 2),
                "mid": self.process(mid, 2), "vocal": self.process(vocal, 1.5),
                "treble": self.process(treble, 2),
            },
            "spectrum": spectrum,
            "sentAtMs": now_ms(),
        }


def available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class ChromiumPage:
    """Small synchronous Chrome DevTools client; avoids a musl browser-driver dependency."""

    def __init__(self, url: str, studio_transform: dict[str, Any] | None = None, *, headless: bool = True, display: str | None = None, port: int | None = None):
        self.events: list[dict[str, Any]] = []
        port = port or available_loopback_port()
        self.profile_dir = Path(tempfile.mkdtemp(prefix="folia-chromium-"))
        self.stderr_path = self.profile_dir / "chromium.stderr.log"
        self.stderr_file = self.stderr_path.open("wb")
        command = [
            "/usr/bin/chromium", "--no-sandbox", "--disable-dev-shm-usage",
            "--enable-webgl", "--ignore-gpu-blocklist", "--remote-allow-origins=*",
            "--hide-scrollbars", "--disable-infobars", "--no-first-run",
            f"--user-data-dir={self.profile_dir}",
            "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}",
        ]
        if headless:
            command.extend(["--headless=new", "about:blank"])
        else:
            command.extend(["--window-position=0,0", f"--window-size={WIDTH},{HEIGHT}", "--kiosk", f"--app={url}"])
        environment = os.environ.copy()
        if display:
            environment["DISPLAY"] = display
        self.debug_port = port
        self.process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=self.stderr_file)
        target = None
        for _ in range(200):
            if self.process.poll() is not None:
                break
            try:
                if headless:
                    request = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
                    with urllib.request.urlopen(request, timeout=1) as response: target = json.load(response)
                    break
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as response:
                    targets = json.load(response)
                target = next((item for item in targets if item.get("type") == "page"), None)
                if target:
                    break
            except Exception:
                time.sleep(0.05)
        if not target:
            self.stderr_file.flush()
            try: detail = self.stderr_path.read_text(encoding="utf-8", errors="replace")[-1200:].strip()
            except Exception: detail = ""
            self.close()
            raise RuntimeError("Chromium DevTools 启动失败" + (f"：{detail}" if detail else ""))
        self.target_id = target["id"]
        try:
            self.socket = create_connection(target["webSocketDebuggerUrl"], timeout=120)
        except Exception as exc:
            self.close()
            raise RuntimeError(f"Chromium DevTools 连接失败：{exc}") from exc
        self.message_id = 0
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Emulation.setDeviceMetricsOverride", {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1, "mobile": False})
        self.call("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        if headless:
            self.call("Page.navigate", {"url": url})
        for _ in range(1200):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as response: targets = json.load(response)
                if any(item.get("id") == self.target_id and item.get("title") == "Folia OBS" for item in targets): break
            except Exception:
                pass
            time.sleep(0.05)
        else:
            self.close(); raise RuntimeError("Fonia 原生页面加载超时")
        for _ in range(300):
            ready = self.evaluate("document.documentElement.dataset.studioFontReady === '1'")
            if ready:
                break
            time.sleep(0.05)
        else:
            self.close(); raise RuntimeError("Folia 字体加载超时")
        time.sleep(0.5)
        transform = studio_transform or {}
        x = max(0.0, min(100.0, float(transform.get("x", 50))))
        y = max(0.0, min(100.0, float(transform.get("y", 50))))
        self.call("Runtime.evaluate", {"expression": f"""
            (() => {{
              const apply = () => {{
                const root = document.getElementById('root');
                if (!root) return;
                root.style.width = '100vw'; root.style.height = '100vh';
                root.style.transform = 'translate({x - 50:.2f}vw,{y - 50:.2f}vh)';
              }};
              apply();
              new MutationObserver(apply).observe(document.documentElement, {{childList:true,subtree:true}});
            }})()
        """})

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.message_id += 1; wanted = self.message_id
        self.socket.send(json.dumps({"id": wanted, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == wanted:
                if message.get("error"): raise RuntimeError(f"CDP {method}: {message['error']}")
                return message.get("result") or {}
            self.events.append(message)

    def screenshot(self) -> bytes:
        result = self.call("Page.captureScreenshot", {"format": "png", "fromSurface": True, "captureBeyondViewport": False})
        return base64.b64decode(result["data"])

    def evaluate(self, expression: str, *, await_promise: bool = False) -> Any:
        result = self.call("Runtime.evaluate", {"expression": expression, "awaitPromise": await_promise, "returnByValue": True})
        exception = result.get("exceptionDetails")
        if exception:
            raise RuntimeError(f"浏览器脚本执行失败：{exception.get('text', 'unknown')}")
        return (result.get("result") or {}).get("value")

    def close(self) -> None:
        try:
            if hasattr(self, "socket"): self.socket.close()
        except Exception:
            pass
        if getattr(self, "process", None):
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                try: self.process.wait(timeout=5)
                except subprocess.TimeoutExpired: pass
        try: self.stderr_file.close()
        except Exception: pass
        profile = getattr(self, "profile_dir", None)
        if profile: shutil.rmtree(profile, ignore_errors=True)


def update_render(rid: str, **values: Any) -> None:
    with state_lock:
        render_jobs.setdefault(rid, {}).update(values, updated_at=time.time())


@app.get("/api/render-media/{rid}")
def render_media_file(rid: str) -> FileResponse:
    with state_lock:
        path = render_media.get(rid)
    if path is None or not path.is_file():
        raise HTTPException(404, "渲染媒体不存在")
    return FileResponse(path)


def terminate_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: pass


def render_fast_composite(
    rid: str,
    body: dict[str, Any],
    source: Path,
    mp4_path: Path,
    manifest_path: Path,
    config: dict[str, Any],
    start_seconds: float,
    duration_seconds: float,
    cancel: threading.Event,
) -> None:
    """Record the complete browser composition in real time; no alpha intermediate."""
    display_number = 90 + int(rid[:2], 16) % 100
    display = f":{display_number}"
    preroll = 0.6
    xvfb: subprocess.Popen[Any] | None = None
    recorder: subprocess.Popen[Any] | None = None
    page: ChromiumPage | None = None
    partial = mp4_path.with_name(mp4_path.name + ".partial")
    partial.unlink(missing_ok=True)
    try:
        update_render(rid, status="running", phase="启动快速成片画布", progress=2)
        xvfb = subprocess.Popen(
            ["Xvfb", display, "-screen", "0", f"{WIDTH}x{HEIGHT}x24", "-nolisten", "tcp", "-ac"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)
        if xvfb.poll() is not None:
            raise RuntimeError("快速成片虚拟画布启动失败")
        token = f"render-{rid}"
        analyser = OfflineAudio(source, start_seconds, duration_seconds)
        set_session(token, config=config, clock={
            "currentTime": start_seconds, "duration": start_seconds + duration_seconds,
            "playerState": "PAUSED", "sentAtMs": now_ms(), "playbackRate": 1, "lyricOffsetMs": 0,
        }, audio=analyser.frame(0))
        with state_lock:
            render_media[rid] = source
        page = ChromiumPage(
            f"http://127.0.0.1:{PORT}/obs?obs=1&token={token}",
            config.get("studioTransform"), headless=False, display=display,
        )
        page.evaluate(f"""
            new Promise((resolve, reject) => {{
              const video = document.createElement('video');
              video.id = 'studio-render-video'; video.muted = true; video.playsInline = true;
              video.src = '/api/render-media/{rid}';
              Object.assign(video.style, {{position:'fixed',inset:'0',width:'100vw',height:'100vh',objectFit:'contain',background:'#000',zIndex:'0'}});
              document.body.prepend(video);
              const root = document.getElementById('root');
              if (root) Object.assign(root.style, {{position:'fixed',inset:'0',zIndex:'1'}});
              const ready = () => {{ video.currentTime = {start_seconds:.6f}; }};
              video.addEventListener('loadedmetadata', ready, {{once:true}});
              video.addEventListener('seeked', () => resolve(true), {{once:true}});
              video.addEventListener('error', () => reject(new Error('视频加载失败')), {{once:true}});
              video.load();
            }})
        """, await_promise=True)
        audio_codec = ""
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(source)], capture_output=True, text=True)
        if probe.returncode == 0:
            audio_codec = probe.stdout.strip()
        audio_args = ["-c:a", "copy"] if audio_codec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
        recorder = subprocess.Popen([
            "ffmpeg", "-v", "error", "-y", "-f", "x11grab", "-draw_mouse", "0",
            "-framerate", str(FPS), "-video_size", f"{WIDTH}x{HEIGHT}", "-i", f"{display}.0",
            "-ss", f"{start_seconds:.3f}", "-t", f"{duration_seconds:.3f}", "-i", str(source),
            "-filter_complex", f"[0:v]trim=start={preroll}:duration={duration_seconds},setpts=PTS-STARTPTS,format=yuv420p[v]",
            "-map", "[v]", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast", "-threads:v", "4", "-crf", "18",
            *audio_args, "-t", f"{duration_seconds:.3f}", "-shortest", "-movflags", "+faststart", "-f", "mp4", str(partial),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        target = time.monotonic() + preroll
        while time.monotonic() < target:
            if cancel.is_set():
                raise RuntimeError("任务已中止")
            time.sleep(0.01)
        page.evaluate("document.getElementById('studio-render-video').play()", await_promise=True)
        started = time.monotonic()
        frame = 0
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= duration_seconds:
                break
            if cancel.is_set():
                raise RuntimeError("任务已中止")
            if recorder.poll() is not None:
                stderr = recorder.stderr.read().decode("utf-8", "replace") if recorder.stderr else ""
                raise RuntimeError(("快速成片录制失败：" + stderr)[-1800:])
            frame = min(math.floor(elapsed * FPS), max(0, math.ceil(duration_seconds * FPS) - 1))
            set_session(token, clock={
                "currentTime": start_seconds + elapsed, "duration": start_seconds + duration_seconds,
                "playerState": "PLAYING", "sentAtMs": now_ms(), "playbackRate": 1, "lyricOffsetMs": 0,
            }, audio=analyser.frame(frame))
            if frame % 15 == 0:
                update_render(rid, phase=f"快速录制成片 {elapsed:.1f}/{duration_seconds:.1f} 秒", progress=round(5 + 88 * elapsed / duration_seconds, 1))
            deadline = started + (frame + 1) / FPS
            time.sleep(max(0.001, min(0.02, deadline - time.monotonic())))
        update_render(rid, phase="封装 MP4", progress=95)
        code = recorder.wait(timeout=max(30, int(duration_seconds * 0.2)))
        stderr = recorder.stderr.read().decode("utf-8", "replace") if recorder.stderr else ""
        if code or not partial.is_file():
            raise RuntimeError(("快速成片封装失败：" + stderr)[-1800:])
        os.replace(partial, mp4_path)
        manifest = {
            "renderer": "folia-native-realtime-v1", "renderer_revision": REVISION,
            "text_edge_profile": TEXT_EDGE_PROFILE,
            "source": str(source), "output": str(mp4_path), "width": WIDTH, "height": HEIGHT,
            "fps": FPS, "start_ms": round(start_seconds * 1000), "duration_ms": round(duration_seconds * 1000),
            "output_mode": "fast", "config": config, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        update_render(rid, status="completed", phase="完成", progress=100, result={
            "path": str(mp4_path), "manifest_path": str(manifest_path), "size": mp4_path.stat().st_size,
            "output_mode": "fast",
        })
    finally:
        terminate_process(recorder)
        if page:
            page.close()
        terminate_process(xvfb)
        partial.unlink(missing_ok=True)
        with state_lock:
            render_media.pop(rid, None)


def render_worker(rid: str, body: dict[str, Any]) -> None:
    cancel = cancel_events[rid]
    acquired = False
    alpha_partial: Path | None = None
    mp4_partial: Path | None = None
    try:
        update_render(rid, status="queued", phase="等待独占渲染器")
        render_lock.acquire(); acquired = True
        if cancel.is_set(): raise RuntimeError("任务已中止")
        source = safe_path(str(body["source"]), MEDIA_ROOT, True)
        alpha_path = safe_path(str(body["alpha_output"]), OUTPUT_ROOT)
        mp4_path = safe_path(str(body["mp4_output"]), OUTPUT_ROOT)
        manifest_path = safe_path(str(body["manifest_output"]), OUTPUT_ROOT)
        for path in (alpha_path, mp4_path, manifest_path): path.parent.mkdir(parents=True, exist_ok=True)
        start_seconds = max(0.0, float(body.get("start_ms", 0)) / 1000)
        duration_seconds = max(0.034, float(body["duration_ms"]) / 1000)
        frame_count = max(1, math.ceil(duration_seconds * FPS))
        config = validate_config(body["config"])
        if body.get("output_mode") == "fast":
            render_fast_composite(rid, body, source, mp4_path, manifest_path, config, start_seconds, duration_seconds, cancel)
            return
        smooth = body.get("output_mode") == "smooth"
        if not smooth:
            required = int(duration_seconds / 60 * 3_000_000_000)
            if shutil.disk_usage(alpha_path.parent).free < required:
                raise RuntimeError(f"可用空间不足；本次透明中间片预计需要约 {required / 1e9:.1f} GB")
        token = f"render-{rid}"
        set_session(token, config=config)
        update_render(rid, status="running", phase="分析音频频谱", progress=1)
        analyser = OfflineAudio(source, start_seconds, duration_seconds)
        alpha_partial = None if smooth else alpha_path.with_name(alpha_path.name + ".partial")
        mp4_partial = mp4_path.with_name(mp4_path.name + ".partial")
        if alpha_partial: alpha_partial.unlink(missing_ok=True)
        mp4_partial.unlink(missing_ok=True)
        if smooth:
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(source)], capture_output=True, text=True)
            audio_args = ["-c:a", "copy"] if probe.returncode == 0 and probe.stdout.strip() == "aac" else ["-c:a", "aac", "-b:a", "192k"]
            encoder_command = [
                "ffmpeg", "-v", "error", "-y", "-ss", f"{start_seconds:.3f}", "-t", f"{duration_seconds:.3f}", "-i", str(source),
                "-f", "image2pipe", "-framerate", str(FPS), "-i", "pipe:0", "-filter_complex",
                f"[0:v]fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,tpad=stop_mode=clone:stop_duration=0.1,setpts=PTS-STARTPTS[base];[1:v]setpts=PTS-STARTPTS[fg];[base][fg]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]",
                "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-threads:v", "4", "-crf", "18", *audio_args,
                "-frames:v", str(frame_count), "-movflags", "+faststart", "-f", "mp4", str(mp4_partial),
            ]
        else:
            encoder_command = [
                "ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS),
                "-i", "pipe:0", "-frames:v", str(frame_count), "-an", "-c:v", "prores_ks",
                "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16", "-f", "mov", str(alpha_partial),
            ]
        encoder = subprocess.Popen(encoder_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        page = ChromiumPage(
            f"http://127.0.0.1:{PORT}/obs?obs=1&token={token}",
            config.get("studioTransform"),
        )
        try:
            for index in range(frame_count):
                if cancel.is_set(): raise RuntimeError("任务已中止")
                absolute = start_seconds + index / FPS
                audio = analyser.frame(index)
                clock = {
                    "currentTime": absolute, "duration": start_seconds + duration_seconds,
                    "playerState": "PLAYING", "sentAtMs": now_ms(), "playbackRate": 0.000000001,
                    "lyricOffsetMs": 0,
                }
                set_session(token, clock=clock, audio=audio)
                if smooth:
                    page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))", await_promise=True)
                else:
                    time.sleep(0.003)
                png = page.screenshot()
                assert encoder.stdin is not None
                encoder.stdin.write(png)
                if index % 15 == 0:
                    label = "逐帧合成 MP4" if smooth else "生成透明帧"
                    update_render(rid, phase=f"{label} {index + 1}/{frame_count}", progress=round(2 + (96 if smooth else 83) * (index + 1) / frame_count, 1))
        finally:
            page.close()
        assert encoder.stdin is not None
        encoder.stdin.close()
        stderr = encoder.stderr.read().decode("utf-8", "replace") if encoder.stderr else ""
        code = encoder.wait()
        if smooth:
            if code or not mp4_partial.is_file(): raise RuntimeError(("逐帧 MP4 合成失败：" + stderr)[-1800:])
            os.replace(mp4_partial, mp4_path)
            manifest = {
                "renderer": "folia-native-frames-v1", "renderer_revision": REVISION,
                "text_edge_profile": TEXT_EDGE_PROFILE,
                "source": str(source), "output": str(mp4_path), "width": WIDTH, "height": HEIGHT,
                "fps": FPS, "frames": frame_count, "start_ms": round(start_seconds * 1000),
                "duration_ms": round(duration_seconds * 1000), "output_mode": "smooth",
                "config": config, "created_at": datetime.now(timezone.utc).isoformat(),
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            update_render(rid, status="completed", phase="完成", progress=100, result={
                "path": str(mp4_path), "manifest_path": str(manifest_path),
                "size": mp4_path.stat().st_size, "output_mode": "smooth",
            })
            return
        assert alpha_partial is not None
        if code or not alpha_partial.is_file(): raise RuntimeError(("透明 MOV 编码失败：" + stderr)[-1800:])
        os.replace(alpha_partial, alpha_path)
        update_render(rid, phase="合成原视频与原声音轨", progress=88)
        audio_codec = ""
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(source)], capture_output=True, text=True)
        if probe.returncode == 0: audio_codec = probe.stdout.strip()
        audio_args = ["-c:a", "copy"] if audio_codec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
        composite = [
            "ffmpeg", "-v", "error", "-y", "-ss", f"{start_seconds:.3f}", "-t", f"{duration_seconds:.3f}", "-i", str(source),
            "-i", str(alpha_path), "-filter_complex",
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setpts=PTS-STARTPTS[base];[1:v]setpts=PTS-STARTPTS[fg];[base][fg]overlay=0:0:format=auto,format=yuv420p[v]",
            "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", *audio_args,
            "-shortest", "-movflags", "+faststart", "-f", "mp4", str(mp4_partial),
        ]
        result = subprocess.run(composite, capture_output=True, text=True)
        if result.returncode or not mp4_partial.is_file(): raise RuntimeError(("MP4 合成失败：" + result.stderr)[-1800:])
        os.replace(mp4_partial, mp4_path)
        manifest = {
            "renderer": "folia-native-browser-v1", "renderer_revision": REVISION,
            "text_edge_profile": TEXT_EDGE_PROFILE,
            "source": str(source), "alpha_output": str(alpha_path), "output": str(mp4_path),
            "width": WIDTH, "height": HEIGHT, "fps": FPS, "frames": frame_count,
            "start_ms": round(start_seconds * 1000), "duration_ms": round(duration_seconds * 1000),
            "alpha_codec": "prores_ks", "alpha_profile": 4, "alpha_pixel_format": "yuva444p12le",
            "alpha_has_audio": False, "config": config, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        update_render(rid, status="completed", phase="完成", progress=100, result={
            "path": str(mp4_path), "alpha_path": str(alpha_path), "manifest_path": str(manifest_path),
            "size": mp4_path.stat().st_size, "alpha_size": alpha_path.stat().st_size,
        })
    except Exception as exc:
        if alpha_partial: alpha_partial.unlink(missing_ok=True)
        if mp4_partial: mp4_partial.unlink(missing_ok=True)
        update_render(rid, status="cancelled" if cancel.is_set() else "failed", phase="已中止" if cancel.is_set() else "失败", error=str(exc)[:2000])
    finally:
        if acquired: render_lock.release()


@app.post("/api/renders")
async def start_render(request: Request) -> dict[str, Any]:
    body = await request.json()
    rid = uuid.uuid4().hex
    render_jobs[rid] = {"id": rid, "status": "queued", "phase": "已创建", "progress": 0, "created_at": time.time()}
    cancel_events[rid] = threading.Event()
    threading.Thread(target=render_worker, args=(rid, body), daemon=True, name=f"folia-render-{rid[:8]}").start()
    return render_jobs[rid]


@app.get("/api/renders/{rid}")
def render_status(rid: str) -> dict[str, Any]:
    with state_lock:
        if rid not in render_jobs: raise HTTPException(404, "渲染任务不存在")
        return dict(render_jobs[rid])


@app.post("/api/renders/{rid}/cancel")
def cancel_render(rid: str) -> dict[str, Any]:
    event = cancel_events.get(rid)
    if event is None: raise HTTPException(404, "渲染任务不存在")
    event.set(); update_render(rid, phase="正在中止")
    return render_status(rid)


@app.get("/images/{project_id}/{image_id}")
def image_asset(project_id: str, image_id: str):
    if (len(project_id) != 32 or any(char not in "0123456789abcdef" for char in project_id)
            or len(image_id) != 64 or any(char not in "0123456789abcdef" for char in image_id)):
        raise HTTPException(404, "图片不存在")
    for suffix, media_type in ((".png", "image/png"), (".jpg", "image/jpeg"), (".webp", "image/webp")):
        path = IMAGE_ROOT / project_id / f"{image_id}{suffix}"
        if path.is_file():
            return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})
    raise HTTPException(404, "图片不存在")


@app.get("/fonts/{font_id}")
def font_asset(font_id: str):
    if not all(char in "0123456789abcdef" for char in font_id) or len(font_id) != 64:
        raise HTTPException(404, "字体不存在")
    for suffix, media_type in ((".ttf", "font/ttf"), (".otf", "font/otf"), (".woff2", "font/woff2")):
        path = (FONT_ROOT / f"{font_id}{suffix}").resolve()
        if path.is_file() and FONT_ROOT in path.parents:
            return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})
    raise HTTPException(404, "字体不存在")


app.mount("/assets", StaticFiles(directory=STATIC_ROOT / "assets"), name="assets")


@app.get("/{path:path}")
def static_files(path: str):
    candidate = (STATIC_ROOT / path).resolve()
    if candidate != STATIC_ROOT and STATIC_ROOT in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(STATIC_ROOT / "index.html")
