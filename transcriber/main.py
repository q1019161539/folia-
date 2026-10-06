from __future__ import annotations

import argparse
import json

from app.aligner import DEFAULT_MODEL as DEFAULT_ALIGNER_MODEL
from app.asr import DEFAULT_MODEL as DEFAULT_ASR_MODEL
from app.pipeline import run_pipeline
from app.separation import SUPPORTED_MODELS


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="CPU-only recording transcription MVP")
    value.add_argument("input", help="Input recording, for example /input/test.mp4")
    value.add_argument(
        "--stage",
        choices=("all", "extract", "separate", "asr", "align"),
        default="all",
        help="Run the complete pipeline or one reusable stage",
    )
    value.add_argument("--test-minutes", type=float, help="Only analyze the first N minutes")
    separation = value.add_mutually_exclusive_group()
    separation.add_argument(
        "--skip-separation",
        dest="skip_separation",
        action="store_true",
        help="Skip Demucs separation (default)",
    )
    separation.add_argument(
        "--with-separation",
        dest="skip_separation",
        action="store_false",
        help="Explicitly enable Demucs vocal separation; uses substantial RAM",
    )
    value.set_defaults(skip_separation=True)
    value.add_argument("--skip-alignment", action="store_true")
    value.add_argument("--separation-model", choices=SUPPORTED_MODELS, default="htdemucs")
    value.add_argument("--separation-jobs", type=int, default=1)
    value.add_argument("--chunk-seconds", type=int, default=180, choices=range(30, 181), metavar="30..180")
    value.add_argument("--no-vad", action="store_true", help="Disable silence skipping; source timestamps remain unchanged when VAD is enabled")
    value.add_argument("--language", default="Chinese")
    value.add_argument("--asr-engine", choices=("local", "aliyun", "whisper"), default="local")
    value.add_argument("--asr-model", default=DEFAULT_ASR_MODEL)
    value.add_argument("--aligner-model", default=DEFAULT_ALIGNER_MODEL)
    value.add_argument("--max-new-tokens", type=int, default=1024)
    value.add_argument(
        "--asr-source",
        choices=("auto", "mix", "vocals"),
        default="auto",
        help="Audio used by a standalone ASR stage",
    )
    value.add_argument("--work-dir", default="/work")
    value.add_argument("--output-dir", default="/output")
    value.add_argument("--cleanup-work", action="store_true")
    return value


if __name__ == "__main__":
    arguments = parser().parse_args()
    stats = run_pipeline(arguments)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
