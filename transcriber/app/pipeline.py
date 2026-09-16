from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .aligner import align_chunks, chunk_level_segments
from .asr import transcribe_chunks
from .aliyun_asr import DEFAULT_MODEL as DEFAULT_ALIYUN_MODEL, transcribe_chunks_aliyun
from .audio import detect_voice_regions, extract_pcm, extract_voice_regions, probe_duration, split_audio
from .benchmark import Benchmark
from .outputs import write_json, write_outputs
from .separation import separate_vocals


def load_asr_chunks(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"ASR result does not exist: {path}")
    chunks = json.loads(path.read_text(encoding="utf-8"))
    for chunk in chunks:
        if not Path(chunk["path"]).is_file():
            raise FileNotFoundError(f"ASR audio chunk does not exist: {chunk['path']}")
    return chunks


def require_file(path: Path, stage: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"Run the {stage} stage first; missing: {path}")
    return path


def stage_message(message: str) -> None:
    print(f"[folia] {message}", flush=True)


def progress_message(percent: float, message: str) -> None:
    value = max(0, min(100, round(percent)))
    print(f"[folia-progress] {value} {message}", flush=True)


def run_pipeline(args: Any) -> dict[str, Any]:
    input_path = Path(args.input).resolve()
    work_dir = Path(args.work_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_duration = probe_duration(input_path)
    analysis_duration = min(source_duration, args.test_minutes * 60) if args.test_minutes else source_duration
    selected_stage = getattr(args, "stage", "all")
    alignment_enabled = selected_stage in ("all", "asr", "align") and not args.skip_alignment
    audio_path = work_dir / "audio.wav"
    if selected_stage not in ("all", "extract") and audio_path.is_file():
        analysis_duration = probe_duration(audio_path)
    benchmark = Benchmark()
    benchmark.start()
    started = time.perf_counter()
    error = ""
    segments: list[dict[str, Any]] = []
    asr_chunks: list[dict[str, Any]] = []
    try:
        if selected_stage in ("all", "extract"):
            stage_message("FFmpeg: extracting 16 kHz mono PCM audio")
            progress_message(1 if selected_stage == "all" else 5, "正在提取音频")
            with benchmark.stage("ffmpeg_seconds"):
                extract_pcm(input_path, audio_path, analysis_duration if args.test_minutes else None)
            progress_message(3 if selected_stage == "all" else 100, "音频提取完成")
        else:
            require_file(audio_path, "extract")
            benchmark.stages["ffmpeg_seconds"] = 0.0

        asr_audio = audio_path
        if selected_stage in ("all", "separate") and not args.skip_separation:
            stage_message(f"Separation: running {args.separation_model} on CPU")
            progress_message(4 if selected_stage == "all" else 5, "正在分离人声和伴奏")
            with benchmark.stage("separation_seconds"):
                _, _, asr_audio = separate_vocals(
                    audio_path,
                    work_dir,
                    model=args.separation_model,
                    jobs=args.separation_jobs,
                )
            progress_message(30 if selected_stage == "all" else 100, "人声分离完成")
        elif selected_stage == "all" or selected_stage == "separate":
            benchmark.stages["separation_seconds"] = 0.0

        if selected_stage == "asr":
            source = getattr(args, "asr_source", "auto")
            vocals = work_dir / "vocals_16k.wav"
            if source == "vocals":
                asr_audio = require_file(vocals, "separate")
            elif source == "mix":
                asr_audio = audio_path
            else:
                asr_audio = vocals if vocals.is_file() else audio_path

        if selected_stage in ("all", "asr"):
            stage_message(f"Chunking: splitting ASR input into {args.chunk_seconds}-second blocks")
            progress_message(31 if selected_stage == "all" else 3, "正在切分 ASR 音频")
            with benchmark.stage("chunking_seconds"):
                if not getattr(args, "no_vad", False):
                    stage_message("VAD: skipping long silent regions while preserving source offsets")
                    regions = detect_voice_regions(asr_audio, analysis_duration)
                    chunks = extract_voice_regions(asr_audio, regions, work_dir / "voice-chunks", args.chunk_seconds)
                else:
                    chunks = split_audio(asr_audio, work_dir / "chunks", args.chunk_seconds)

            asr_engine = getattr(args, "asr_engine", "local")
            stage_message(f"ASR: transcribing {len(chunks)} block(s) with {asr_engine}")
            progress_message(
                32 if selected_stage == "all" else 5,
                "正在连接阿里云 ASR" if asr_engine == "aliyun" else "正在加载本地 ASR 模型",
            )
            with benchmark.stage("asr_seconds"):
                def callback(done: int, total: int) -> None:
                    if selected_stage == "all":
                        percent = 32 + 48 * done / total
                    elif alignment_enabled:
                        percent = 5 + 70 * done / total
                    else:
                        percent = 5 + 95 * done / total
                    progress_message(percent, f"ASR 已完成 {done}/{total} 块")
                if asr_engine == "aliyun":
                    asr_chunks = transcribe_chunks_aliyun(
                        chunks,
                        model_name=DEFAULT_ALIYUN_MODEL,
                        language=args.language,
                        progress=callback,
                    )
                else:
                    asr_chunks = transcribe_chunks(
                        chunks,
                        model_name=args.asr_model,
                        language=args.language,
                        max_new_tokens=args.max_new_tokens,
                        progress=callback,
                        checkpoint_path=work_dir / "asr_chunks.json",
                    )
                write_json(work_dir / "asr_chunks.json", asr_chunks)

        if selected_stage == "align":
            asr_chunks = load_asr_chunks(work_dir / "asr_chunks.json")

        if alignment_enabled:
            stage_message(f"Alignment: aligning {len(asr_chunks)} block(s) on CPU")
            align_start = 82 if selected_stage == "all" else (75 if selected_stage == "asr" else 5)
            align_span = 18 if selected_stage == "all" else (25 if selected_stage == "asr" else 95)
            progress_message(align_start, "正在加载时间对齐模型")
            with benchmark.stage("alignment_seconds"):
                segments = align_chunks(
                    asr_chunks,
                    model_name=args.aligner_model,
                    language=args.language,
                    progress=lambda done, total: progress_message(
                        align_start + align_span * done / total,
                        f"时间对齐已完成 {done}/{total} 块",
                    ),
                )
        elif selected_stage in ("all", "asr"):
            benchmark.stages["alignment_seconds"] = 0.0
            segments = chunk_level_segments(asr_chunks)
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        total_seconds = time.perf_counter() - started
        benchmark.stop()
        stats = {
            "status": "failed" if error else "completed",
            "error": error,
            "stage": selected_stage,
            "input": str(input_path),
            "source_duration_seconds": round(source_duration, 3),
            "audio_duration_seconds": round(analysis_duration, 3),
            **{key: round(value, 3) for key, value in benchmark.stages.items()},
            "total_seconds": round(total_seconds, 3),
            "peak_memory_bytes": benchmark.peak_rss_bytes,
            "peak_memory_gib": round(benchmark.peak_rss_bytes / (1024**3), 3),
            "rtf": round(total_seconds / analysis_duration, 4) if analysis_duration else None,
            "estimated_2_5h_seconds": round((total_seconds / analysis_duration) * 9000, 1)
            if analysis_duration
            else None,
            "segments": len(segments),
            "asr_chunks": len(asr_chunks),
            "separation_model": args.separation_model if selected_stage in ("all", "separate") and not args.skip_separation else None,
            "asr_engine": getattr(args, "asr_engine", "local") if selected_stage in ("all", "asr") else None,
            "asr_model": (
                DEFAULT_ALIYUN_MODEL if getattr(args, "asr_engine", "local") == "aliyun" else args.asr_model
            ) if selected_stage in ("all", "asr") else None,
            "aligner_model": args.aligner_model if alignment_enabled else None,
            "chunk_seconds": args.chunk_seconds,
            "vad_enabled": not getattr(args, "no_vad", False),
        }
        if selected_stage in ("all", "asr", "align") and not error:
            write_outputs(output_dir, segments, stats)
        else:
            write_json(output_dir / "stats.json", stats)
        if args.cleanup_work and not error:
            shutil.rmtree(work_dir / "chunks", ignore_errors=True)
            shutil.rmtree(work_dir / "voice-chunks", ignore_errors=True)
    return stats
