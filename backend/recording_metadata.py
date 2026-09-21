"""Keep the recording metadata that bililive-tools needs after Folia cuts a clip."""

from __future__ import annotations

import os
import re
from pathlib import Path


METADATA_BLOCK = re.compile(r"<metadata(?:\s[^>]*)?>.*?</metadata>", re.IGNORECASE | re.DOTALL)


def copy_recording_metadata_sidecar(source_video: Path, output_video: Path) -> Path | None:
    """Write a small XML sidecar beside a clip using its source recording metadata.

    bililive-tools looks for an XML file with the same stem as the selected video.
    Keeping only the metadata block avoids duplicating the source recording's full
    danmaku file for every song clip.
    """

    source_xml = source_video.with_suffix(".xml")
    if not source_xml.is_file():
        return None

    with source_xml.open("r", encoding="utf-8-sig", errors="replace") as handle:
        head = handle.read(128 * 1024)
    match = METADATA_BLOCK.search(head)
    if not match:
        return None

    target = output_video.with_suffix(".xml")
    temporary = target.with_name(target.name + ".partial")
    temporary.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<i>\n'
        + match.group(0).strip()
        + "\n</i>\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target
