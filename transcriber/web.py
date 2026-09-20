from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request, send_from_directory

from app.notify import automation_notification, notify_wecom
from app.publish import publish_recording_outputs, publish_song_analysis, recording_output_directory


INPUT_ROOT = Path(os.environ.get("FOLIA_INPUT_ROOT", "/input")).resolve()
WORK_ROOT = Path(os.environ.get("FOLIA_WORK_ROOT", "/work/jobs")).resolve()
OUTPUT_ROOT = Path(os.environ.get("FOLIA_OUTPUT_ROOT", "/output/jobs")).resolve()
OUTPUT_DISPLAY_ROOT = os.environ.get("FOLIA_OUTPUT_DISPLAY_ROOT", str(OUTPUT_ROOT))
WORK_DISPLAY_ROOT = os.environ.get("FOLIA_WORK_DISPLAY_ROOT", str(WORK_ROOT))
LOCAL_WORKER_URL = os.environ.get("FOLIA_LOCAL_WORKER_URL", "http://local-worker:8001").rstrip("/")
FRIENDLY_OUTPUT_ROOT = Path(os.environ.get("FOLIA_FRIENDLY_OUTPUT_ROOT", str(OUTPUT_ROOT.parent / "recordings"))).resolve()
FRIENDLY_OUTPUT_DISPLAY_ROOT = Path(os.environ.get("FOLIA_FRIENDLY_OUTPUT_DISPLAY_ROOT", str(FRIENDLY_OUTPUT_ROOT)))
VIDEO_EXTENSIONS = {".mp4", ".flv", ".mkv", ".mov", ".ts", ".m4v", ".webm"}
DOWNLOADS = {"transcript.jsonl", "transcript_words.jsonl", "transcript.txt", "stats.json", "job.log", "job.json"}
WORK_DOWNLOADS = {"audio.wav", "vocals.wav", "instrumental.wav", "vocals_16k.wav", "asr_chunks.json"}
STAGES = {"all", "extract", "asr", "align"}

app = Flask(__name__, static_folder="web", static_url_path="/assets")
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
job_queue: queue.Queue[str] = queue.Queue()
active_processes: dict[str, subprocess.Popen[str]] = {}
processes_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def input_file(relative: str) -> Path:
    candidate = (INPUT_ROOT / relative.lstrip("/\\")).resolve()
    if not inside(candidate, INPUT_ROOT) or not candidate.is_file():
        raise ValueError("录播文件不存在或不在允许的输入目录中")
    if candidate.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("当前文件类型不是支持的录播格式")
    return candidate


def clean_run_id(value: str, source: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")[:64]
    if cleaned:
        return cleaned
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(source).stem).strip("-")[:32] or "recording"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{digest}"


def source_from_run(run_id: str, stage: str) -> Path:
    cleaned = clean_run_id(run_id, "recording")
    if not run_id or cleaned != run_id:
        raise ValueError("请输入有效的已有任务 ID")
    work_dir = (WORK_ROOT / run_id).resolve()
    if not inside(work_dir, WORK_ROOT) or not work_dir.is_dir():
        raise ValueError("找不到这个任务的过程文件目录")
    required = work_dir / ("asr_chunks.json" if stage == "align" else "audio.wav")
    if not required.is_file():
        label = "ASR 转录结果" if stage == "align" else "提取后的 audio.wav"
        raise ValueError(f"这个任务缺少{label}")
    job_file = OUTPUT_ROOT / run_id / "job.json"
    try:
        previous = json.loads(job_file.read_text(encoding="utf-8"))
        relative = str(previous.get("input_relative", ""))
    except (OSError, json.JSONDecodeError):
        relative = ""
    if not relative:
        raise ValueError("过程文件存在，但任务记录中没有原视频路径")
    return input_file(relative)


def save_job(job: dict[str, Any]) -> None:
    directory = OUTPUT_ROOT / job["run_id"]
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "job.json.tmp"
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(directory / "job.json")


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    result = dict(job)
    result["downloads"] = [
        name for name in sorted(DOWNLOADS) if (OUTPUT_ROOT / job["run_id"] / name).is_file()
    ]
    result["work_downloads"] = [
        name for name in sorted(WORK_DOWNLOADS) if (WORK_ROOT / job["run_id"] / name).is_file()
    ]
    result["internal_output_path"] = str(Path(OUTPUT_DISPLAY_ROOT) / job["run_id"])
    result["output_path"] = str(recording_output_directory(str(job.get("input_relative", "录播.mp4")), FRIENDLY_OUTPUT_DISPLAY_ROOT))
    result["work_path"] = str(Path(WORK_DISPLAY_ROOT) / job["run_id"])
    return result


def build_command(job: dict[str, Any]) -> list[str]:
    options = job["options"]
    command = [
        sys.executable,
        "main.py",
        job["input"],
        "--stage",
        job["stage"],
        "--work-dir",
        str(WORK_ROOT / job["run_id"]),
        "--output-dir",
        str(OUTPUT_ROOT / job["run_id"]),
        "--chunk-seconds",
        str(options["chunk_seconds"]),
        "--separation-model",
        options["separation_model"],
        "--asr-source",
        options["asr_source"],
        "--asr-engine",
        options["asr_engine"],
    ]
    if options.get("test_minutes"):
        command += ["--test-minutes", str(options["test_minutes"])]
    if options.get("skip_separation"):
        command.append("--skip-separation")
    else:
        # main.py defaults to skipping, so leaving the flag off is not the same
        # as asking for separation -- it is asking for nothing. A request that
        # said separate_vocals ran an ordinary ASR over the original mix instead,
        # and the only sign was separation_seconds: 0.0 in the stats afterwards.
        command.append("--with-separation")
    if options.get("skip_alignment"):
        command.append("--skip-alignment")
    if options.get("no_vad"):
        command.append("--no-vad")
    return command


def release_studio_ai_models(job: dict[str, Any]) -> None:
    options = job.get("options") or {}
    if job.get("stage") not in {"all", "asr"} or options.get("asr_engine") != "local":
        return
    request = urllib.request.Request(LOCAL_WORKER_URL + "/unload", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=300) as response:
        if response.status >= 300:
            raise RuntimeError(f"释放视频工坊 AI 模型失败：HTTP {response.status}")


def worker() -> None:
    while True:
        job_id = job_queue.get()
        with jobs_lock:
            job = jobs[job_id]
            if job["status"] != "queued":
                job_queue.task_done()
                continue
            job["status"] = "running"
            job["started_at"] = now()
            save_job(job)
        output_dir = OUTPUT_ROOT / job["run_id"]
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "job.log"
        command = build_command(job)
        try:
            with log_path.open("a", encoding="utf-8") as log:
                if job.get("stage") in {"all", "asr"} and (job.get("options") or {}).get("asr_engine") == "local":
                    log.write(f"[{now()}] releasing idle studio AI models before ASR\n")
                    log.flush()
                    release_studio_ai_models(job)
                log.write(f"\n[{now()}] {' '.join(command)}\n")
                log.flush()
                process = subprocess.Popen(
                    command,
                    cwd=Path(__file__).resolve().parent,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    start_new_session=os.name != "nt",
                )
                with processes_lock:
                    active_processes[job_id] = process
                with jobs_lock:
                    cancel_requested = job["status"] == "cancelling"
                if cancel_requested:
                    terminate_process(process)
                assert process.stdout is not None
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    match = re.match(r"^\[folia-progress\]\s+(\d+)\s+(.*)$", line.strip())
                    if match:
                        with jobs_lock:
                            job["progress"] = int(match.group(1))
                            job["progress_label"] = match.group(2)
                            save_job(job)
                    else:
                        demucs = re.search(r"(\d+)%\|", line)
                        if demucs and job.get("progress_label") == "正在分离人声和伴奏":
                            separated = int(demucs.group(1))
                            with jobs_lock:
                                job["progress"] = round(
                                    4 + 26 * separated / 100
                                    if job["stage"] == "all"
                                    else 5 + 90 * separated / 100
                                )
                                save_job(job)
                return_code = process.wait()
            with jobs_lock:
                cancelled = job["status"] in {"cancelling", "cancelled"}
                job["status"] = "cancelled" if cancelled else ("completed" if return_code == 0 else "failed")
                job["return_code"] = return_code
                if cancelled:
                    job["progress_label"] = "任务已中止"
                elif return_code == 0:
                    job["progress"] = 100
                    job["progress_label"] = "处理完成"
                else:
                    job["error"] = (
                        "处理进程被系统强制终止（SIGKILL），可能内存不足"
                        if return_code == -9
                        else f"处理进程异常退出，返回码 {return_code}"
                    )
                    job["progress_label"] = job["error"]
        except Exception as exc:
            with jobs_lock:
                if job["status"] in {"cancelling", "cancelled"}:
                    job["status"] = "cancelled"
                    job["progress_label"] = "任务已中止"
                else:
                    job["status"] = "failed"
                    job["error"] = f"{type(exc).__name__}: {exc}"
                    job["progress_label"] = "处理失败"
        finally:
            with processes_lock:
                active_processes.pop(job_id, None)
            with jobs_lock:
                job["finished_at"] = now()
                stats_path = output_dir / "stats.json"
                if stats_path.is_file():
                    try:
                        job["stats"] = json.loads(stats_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        pass
                friendly = publish_recording_outputs(job, output_dir, WORK_ROOT / job["run_id"], FRIENDLY_OUTPUT_ROOT)
                job["friendly_output_path"] = str(friendly)
                save_job(job)
                notification = {
                    "status": job["status"],
                    "input": job.get("input_relative", job.get("input", "")),
                    "run_id": job.get("run_id", ""),
                    "error": job.get("error", ""),
                    "output_path": str(recording_output_directory(str(job.get("input_relative", "录播.mp4")), FRIENDLY_OUTPUT_DISPLAY_ROOT)),
                }
            if notification["status"] in {"completed", "failed"} and job.get("options", {}).get("notification_mode") != "automation":
                detail = [
                    f"任务：{notification['run_id']}",
                    f"输入：{notification['input']}",
                    f"输出目录：{notification['output_path']}",
                ]
                if notification["error"]:
                    detail.append(f"错误：{notification['error'][:500]}")
                notify_wecom(
                    "Fonia ASR 处理完成" if notification["status"] == "completed" else "Fonia ASR 处理失败",
                    "\n".join(detail),
                )
            job_queue.task_done()


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        pass


def load_jobs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_ROOT.glob("*/job.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if job.get("status") in {"queued", "running", "cancelling"}:
                job["status"] = "interrupted"
            job.setdefault("progress", 100 if job.get("status") == "completed" else 0)
            job.setdefault("progress_label", job.get("status", "未知状态"))
            friendly = publish_recording_outputs(job, path.parent, WORK_ROOT / job["run_id"], FRIENDLY_OUTPUT_ROOT)
            job["friendly_output_path"] = str(friendly)
            save_job(job)
            jobs[job["id"]] = job
        except (OSError, KeyError, json.JSONDecodeError):
            continue


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/config")
def config():
    return jsonify(
        {
            "input_root": str(INPUT_ROOT),
            "output_root": OUTPUT_DISPLAY_ROOT,
            "work_root": WORK_DISPLAY_ROOT,
            "cpu_only": True,
            "aliyun_asr_configured": bool(os.environ.get("DASHSCOPE_API_KEY", "").strip()),
        }
    )


@app.get("/api/files")
def files():
    relative = request.args.get("path", "").strip("/\\")
    directory = (INPUT_ROOT / relative).resolve()
    if not inside(directory, INPUT_ROOT) or not directory.is_dir():
        abort(404)
    entries = []
    for item in sorted(directory.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
        if item.name.startswith("."):
            continue
        if item.is_dir() or item.suffix.lower() in VIDEO_EXTENSIONS:
            stat = item.stat()
            entries.append(
                {
                    "name": item.name,
                    "path": item.relative_to(INPUT_ROOT).as_posix(),
                    "type": "directory" if item.is_dir() else "video",
                    "size": stat.st_size if item.is_file() else None,
                    "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
    parent = Path(relative).parent.as_posix() if relative else None
    if parent == ".":
        parent = ""
    return jsonify({"path": relative, "parent": parent, "entries": entries})


@app.get("/api/work-runs")
def work_runs():
    stage = request.args.get("stage", "asr")
    required_name = "asr_chunks.json" if stage == "align" else "audio.wav"
    entries = []
    if not WORK_ROOT.is_dir():
        return jsonify(entries)
    for directory in WORK_ROOT.iterdir():
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        required = directory / required_name
        if not required.is_file():
            continue
        source_name = ""
        try:
            previous = json.loads((OUTPUT_ROOT / directory.name / "job.json").read_text(encoding="utf-8"))
            source_name = Path(str(previous.get("input_relative", ""))).name
        except (OSError, json.JSONDecodeError):
            pass
        stat = required.stat()
        entries.append(
            {
                "run_id": directory.name,
                "source_name": source_name,
                "required_file": required_name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    entries.sort(key=lambda item: item["modified"], reverse=True)
    return jsonify(entries)


@app.post("/api/jobs")
def create_job():
    payload = request.get_json(force=True) or {}
    try:
        stage = str(payload.get("stage", "all"))
        if stage not in STAGES:
            raise ValueError("未知处理模块")
        requested_run_id = str(payload.get("run_id", "")).strip()
        input_value = str(payload.get("input", "")).strip()
        source = input_file(input_value) if input_value else source_from_run(requested_run_id, stage)
        run_id = clean_run_id(str(payload.get("run_id", "")), str(source))
        chunk_seconds = int(payload.get("chunk_seconds", 180))
        if not 30 <= chunk_seconds <= 180:
            raise ValueError("切块长度必须在 30 到 180 秒之间")
        test_minutes = payload.get("test_minutes")
        test_minutes = float(test_minutes) if test_minutes not in (None, "", 0, "0") else None
        if test_minutes is not None and test_minutes <= 0:
            raise ValueError("测试分钟数必须大于 0")
        separation_model = str(payload.get("separation_model", "htdemucs"))
        if separation_model not in {"htdemucs", "mdx_q"}:
            raise ValueError("未知分离模型")
        # Separation stays off for everything that does not ask for it by name:
        # it costs ~9 GiB peak and about 1.5x realtime on top of the ASR, which is
        # why the workbench never offers it. The studio asks for it on one clip at
        # a time, only when a song's word anchors came back too sparse to align
        # on, and only while holding the single big-model slot.
        separate_vocals = bool(payload.get("separate_vocals", False))
        asr_source = "vocals" if separate_vocals else "mix"
        asr_engine = str(payload.get("asr_engine", "local"))
        if asr_engine not in {"local", "aliyun"}:
            raise ValueError("未知 ASR 引擎")
        if asr_engine == "aliyun" and not os.environ.get("DASHSCOPE_API_KEY", "").strip():
            raise ValueError("阿里云 ASR 尚未配置 API Key")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    job_id = f"{run_id}-{stage}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    job = {
        "id": job_id,
        "run_id": run_id,
        "stage": stage,
        "status": "queued",
        "input": str(source),
        "input_relative": source.relative_to(INPUT_ROOT).as_posix(),
        "created_at": now(),
        "started_at": None,
        "finished_at": None,
        "progress": 0,
        "progress_label": "等待执行",
        "options": {
            "test_minutes": test_minutes,
            "chunk_seconds": chunk_seconds,
            "separation_model": separation_model,
            "asr_source": asr_source,
            "asr_engine": asr_engine,
            "skip_separation": not separate_vocals,
            "skip_alignment": bool(payload.get("skip_alignment", False)),
            "no_vad": bool(payload.get("no_vad", False)),
            "notification_mode": "automation" if payload.get("notification_mode") == "automation" else "default",
        },
    }
    with jobs_lock:
        jobs[job_id] = job
        save_job(job)
    job_queue.put(job_id)
    return jsonify(public_job(job)), 202


@app.post("/api/notifications/automation")
def notify_automation():
    payload = request.get_json(force=True) or {}
    try:
        title, content = automation_notification(payload)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    delivery = notify_wecom(title, content)
    status = 200 if delivery.get("ok") or delivery.get("status") == "not_configured" else 502
    return jsonify(delivery), status


@app.post("/api/jobs/<job_id>/cancel")
def cancel_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)
        if job["status"] == "queued":
            job["status"] = "cancelled"
            job["progress_label"] = "任务已中止"
            job["finished_at"] = now()
            save_job(job)
            return jsonify(public_job(job))
        if job["status"] != "running":
            return jsonify({"error": "只有等待中或处理中的任务可以中止"}), 409
        job["status"] = "cancelling"
        job["progress_label"] = "正在中止任务"
        save_job(job)
    with processes_lock:
        process = active_processes.get(job_id)
    if process is not None:
        terminate_process(process)
    return jsonify(public_job(job)), 202


@app.get("/api/jobs")
def list_jobs():
    with jobs_lock:
        ordered = sorted(jobs.values(), key=lambda item: item["created_at"], reverse=True)
        return jsonify([public_job(item) for item in ordered[:30]])


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)
        return jsonify(public_job(job))


@app.get("/api/jobs/<job_id>/log")
def get_log(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)
        path = OUTPUT_ROOT / job["run_id"] / "job.log"
    if not path.is_file():
        return jsonify({"log": "等待任务启动……"})
    text = path.read_text(encoding="utf-8", errors="replace")
    return jsonify({"log": text[-30000:]})


@app.post("/api/jobs/<job_id>/song-analysis")
def save_song_analysis(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)
        snapshot = dict(job)
    payload = request.get_json(force=True) or {}
    if not isinstance(payload.get("songs", []), list) or not isinstance(payload.get("skipped", []), list):
        return jsonify({"error": "songs 和 skipped 必须是数组"}), 400
    paths = publish_song_analysis(snapshot, payload, FRIENDLY_OUTPUT_ROOT)
    display = recording_output_directory(str(snapshot.get("input_relative", "录播.mp4")), FRIENDLY_OUTPUT_DISPLAY_ROOT)
    return jsonify({"ok": True, "json": str(display / Path(paths["json"]).name), "timeline": str(display / Path(paths["timeline"]).name)})


@app.get("/api/jobs/<job_id>/download/<name>")
def download(job_id: str, name: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or name not in DOWNLOADS:
            abort(404)
        directory = OUTPUT_ROOT / job["run_id"]
    return send_from_directory(directory, name, as_attachment=request.args.get("inline") != "1")


@app.get("/api/jobs/<job_id>/download-work/<name>")
def download_work(job_id: str, name: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or name not in WORK_DOWNLOADS:
            abort(404)
        directory = WORK_ROOT / job["run_id"]
    return send_from_directory(directory, name, as_attachment=request.args.get("inline") != "1")


load_jobs()
threading.Thread(target=worker, daemon=True, name="folia-job-worker").start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), threaded=True)
