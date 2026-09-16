from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .audio import normalize_pcm


SUPPORTED_MODELS = ("htdemucs", "mdx_q")


def separate_vocals(
    audio_path: Path,
    work_dir: Path,
    *,
    model: str,
    jobs: int = 1,
    overlap: float = 0.1,
) -> tuple[Path, Path, Path]:
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported separation model: {model}")
    separated_root = work_dir / "separated"
    shutil.rmtree(separated_root, ignore_errors=True)
    subprocess.run(
        [
            "python",
            "-m",
            "demucs.separate",
            "--device",
            "cpu",
            "--two-stems",
            "vocals",
            "--name",
            model,
            "--jobs",
            str(jobs),
            "--overlap",
            str(overlap),
            "--out",
            str(separated_root),
            str(audio_path),
        ],
        check=True,
    )
    model_output = separated_root / model / audio_path.stem
    vocals_source = model_output / "vocals.wav"
    instrumental_source = model_output / "no_vocals.wav"
    if not vocals_source.exists() or not instrumental_source.exists():
        raise RuntimeError(f"Demucs did not create expected stems under {model_output}")
    vocals = work_dir / "vocals.wav"
    instrumental = work_dir / "instrumental.wav"
    shutil.move(str(vocals_source), vocals)
    shutil.move(str(instrumental_source), instrumental)
    vocals_16k = work_dir / "vocals_16k.wav"
    normalize_pcm(vocals, vocals_16k)
    return vocals, instrumental, vocals_16k

