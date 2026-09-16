"""Compare Qwen live word timings with provider verbatim lyrics and merge them."""
from __future__ import annotations

import difflib
import math
import statistics
from typing import Any, Callable

from standard_timeline import clamp_forced_words, interpolated_shift_ms, normalized, score_timeline


def normalize_provider_rows(
    rows: list[dict[str, Any]],
    metadata_filter: Callable[[str], bool] | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source_index, raw in enumerate(rows or []):
        text = str(raw.get("text", "")).strip()
        start = raw.get("start_ms")
        if not text or (metadata_filter and metadata_filter(text)):
            continue
        words = []
        for word in raw.get("words") or []:
            value = str(word.get("text", ""))
            if not value:
                continue
            begin, end = word.get("start_ms"), word.get("end_ms")
            words.append({
                "text": value,
                "start_ms": int(begin) if begin is not None else None,
                "end_ms": int(end) if end is not None else None,
            })
        output.append({
            "text": text,
            "start_ms": int(start) if start is not None else None,
            "end_ms": int(raw["end_ms"]) if raw.get("end_ms") is not None else None,
            "words": words,
            "source_index": source_index,
        })
    return output


def timed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("start_ms") is not None]


def _char_units(text: str, start_ms: int | None, end_ms: int | None) -> list[dict[str, Any]]:
    characters = list(str(text or ""))
    if not characters:
        return []
    duration = max(1, int(end_ms or 0) - int(start_ms or 0)) if start_ms is not None and end_ms is not None else 0
    output = []
    for index, character in enumerate(characters):
        value = normalized(character)
        if not value:
            continue
        begin = int(start_ms) + round(duration * index / len(characters)) if duration else None
        finish = int(start_ms) + round(duration * (index + 1) / len(characters)) if duration else None
        for unit in value:
            output.append({"char": unit, "start_ms": begin, "end_ms": finish, "source_char_index": index})
    return output


def _provider_chars(row: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    text_cursor = 0
    for word in row.get("words") or []:
        units = _char_units(word.get("text", ""), word.get("start_ms"), word.get("end_ms"))
        for unit in units:
            unit["source_char_index"] += text_cursor
            output.append(unit)
        text_cursor += len(str(word.get("text", "")))
    return output


def _qwen_chars(segment: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for word in segment.get("words") or []:
        if word.get("timing_source") != "qwen-forced-aligner":
            continue
        start = word.get("start_ms")
        end = word.get("end_ms")
        if start is None:
            start = round(float(word.get("start", 0)) * 1000)
        if end is None:
            end = round(float(word.get("end", word.get("start", 0))) * 1000)
        output.extend(_char_units(str(word.get("text", word.get("word", ""))), int(start), int(end)))
    return output


def _line_word_anchors(
    lyric_index: int,
    asr_index: int,
    row: dict[str, Any],
    segment: dict[str, Any],
) -> list[dict[str, Any]]:
    provider, qwen = _provider_chars(row), _qwen_chars(segment)
    if not provider or not qwen:
        return []
    provider_text = "".join(item["char"] for item in provider)
    qwen_text = "".join(item["char"] for item in qwen)
    matcher = difflib.SequenceMatcher(None, qwen_text, provider_text, autojunk=False)
    anchors: list[dict[str, Any]] = []
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            qitem, pitem = qwen[block.a + offset], provider[block.b + offset]
            if None in (qitem["start_ms"], qitem["end_ms"], pitem["start_ms"], pitem["end_ms"]):
                continue
            anchors.append({
                "asr_index": asr_index,
                "lyric_index": lyric_index,
                "standard_char_index": pitem["source_char_index"],
                "qwen_char": qitem["char"],
                "lyric_char": pitem["char"],
                "qwen_start_ms": int(qitem["start_ms"]),
                "qwen_end_ms": int(qitem["end_ms"]),
                "provider_start_ms": int(pitem["start_ms"]),
                "provider_end_ms": int(pitem["end_ms"]),
                "kind": "exact",
            })
    anchors.sort(key=lambda item: (item["qwen_start_ms"], item["standard_char_index"]))
    # A one-to-one ASR substitution between adjacent exact characters may use
    # the live Qwen span, but never infer insertions or reorder lyrics.
    additions = []
    for left, right in zip(anchors, anchors[1:]):
        if left["asr_index"] != right["asr_index"] or left["lyric_index"] != right["lyric_index"]:
            continue
        q_gap = [item for item in qwen if left["qwen_end_ms"] <= int(item.get("start_ms") or -1) and int(item.get("end_ms") or -1) <= right["qwen_start_ms"]]
        p_gap = [item for item in provider if left["standard_char_index"] < item["source_char_index"] < right["standard_char_index"]]
        if 0 < len(q_gap) == len(p_gap) <= 2:
            for qitem, pitem in zip(q_gap, p_gap):
                if None in (qitem["start_ms"], qitem["end_ms"], pitem["start_ms"], pitem["end_ms"]):
                    continue
                additions.append({
                    "asr_index": asr_index,
                    "lyric_index": lyric_index,
                    "standard_char_index": pitem["source_char_index"],
                    "qwen_char": qitem["char"],
                    "lyric_char": pitem["char"],
                    "qwen_start_ms": int(qitem["start_ms"]),
                    "qwen_end_ms": int(qitem["end_ms"]),
                    "provider_start_ms": int(pitem["start_ms"]),
                    "provider_end_ms": int(pitem["end_ms"]),
                    "kind": "corrected",
                })
    return sorted(anchors + additions, key=lambda item: (item["qwen_start_ms"], item["standard_char_index"]))


def score_provider_timeline(
    rows: list[dict[str, Any]],
    asr_segments: list[dict[str, Any]],
    *,
    title_score: float = 0.0,
) -> dict[str, Any]:
    timed = timed_rows(rows)
    line_result = score_timeline(timed, asr_segments, title_score=title_score)
    if not line_result.get("anchors"):
        return {**line_result, "word_anchors": [], "word_anchor_count": 0, "word_coverage": 0.0}
    word_anchors: list[dict[str, Any]] = []
    for anchor in line_result["anchors"]:
        lyric_index, asr_index = int(anchor["lyric_index"]), int(anchor["asr_index"])
        if lyric_index >= len(timed) or asr_index >= len(asr_segments):
            continue
        word_anchors.extend(_line_word_anchors(lyric_index, asr_index, timed[lyric_index], asr_segments[asr_index]))
    center = int(line_result.get("shift_ms", 0))
    accepted_word_anchors = []
    for item in word_anchors:
        delta = item["qwen_start_ms"] - item["provider_start_ms"]
        expected = interpolated_shift_ms(
            item["provider_start_ms"], line_result.get("anchors"), center
        )
        if abs(delta - expected) <= 1800:
            accepted_word_anchors.append({**item, "delta_ms": delta})
    word_anchors = accepted_word_anchors
    exact = [item for item in word_anchors if item["kind"] == "exact"]
    word_lines = {item["lyric_index"] for item in exact}
    shift_ms = center
    p90 = None
    span_ms = 0
    if len(exact) >= 5 and len(word_lines) >= 2:
        shift_ms = round(statistics.median(item["delta_ms"] for item in exact))
        residuals = sorted(abs(item["delta_ms"] - shift_ms) for item in exact)
        p90 = residuals[min(len(residuals) - 1, math.ceil(len(residuals) * 0.9) - 1)]
        span_ms = max(item["qwen_start_ms"] for item in exact) - min(item["qwen_start_ms"] for item in exact)
    lyric_characters = sum(len(normalized(row.get("text", ""))) for row in timed)
    coverage = len({(item["lyric_index"], item["standard_char_index"]) for item in exact}) / max(1, lyric_characters)
    # Confidence is decided by line-level evidence alone. Word-level anchors stay
    # as timing material (they drive the hybrid per-character merge) and as a
    # ranking bonus, but they no longer vote on confidence: a live cover drifts
    # away from a studio release character by character, so the word-level verdict
    # swung on how closely this particular performance tracked that particular
    # master rather than on whether the lyrics were the right ones, which made the
    # reported confidence read wrong in both directions.
    low_confidence = bool(line_result.get("low_confidence", True))
    score = float(line_result.get("score", 0)) + min(25, len(exact) / 2) + min(8, span_ms / 10000)
    if p90 is not None:
        score -= p90 / 200
    return {
        **line_result,
        "score": round(score, 3),
        "shift_ms": shift_ms,
        "word_anchors": word_anchors,
        "word_anchor_count": len(exact),
        "word_anchor_lines": len(word_lines),
        "word_anchor_span_ms": span_ms,
        "word_residual_p90_ms": p90,
        "word_coverage": round(coverage, 4),
        "low_confidence": low_confidence,
        "confidence": "low" if low_confidence else "high",
    }


def _provider_character_times(row: dict[str, Any], start_ms: int, end_ms: int, shift_ms: int) -> list[dict[str, Any]]:
    text = str(row.get("text", ""))
    characters = list(text)
    duration = max(1, end_ms - start_ms)
    output = [
        {
            "text": character,
            "start_ms": start_ms + round(duration * index / max(1, len(characters))),
            "end_ms": start_ms + round(duration * (index + 1) / max(1, len(characters))),
            "timing_source": "interpolated",
        }
        for index, character in enumerate(characters)
    ]
    cursor = 0
    for word in row.get("words") or []:
        value = str(word.get("text", ""))
        begin, finish = word.get("start_ms"), word.get("end_ms")
        if begin is not None and finish is not None and int(finish) > int(begin):
            for offset, _ in enumerate(value):
                index = cursor + offset
                if index >= len(output):
                    break
                output[index].update({
                    "start_ms": int(begin) + shift_ms + round((int(finish) - int(begin)) * offset / max(1, len(value))),
                    "end_ms": int(begin) + shift_ms + round((int(finish) - int(begin)) * (offset + 1) / max(1, len(value))),
                    "timing_source": "lddc-standard",
                })
        cursor += len(value)
    return output


def apply_hybrid_words(
    timeline: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    word_anchors: list[dict[str, Any]],
    shift_ms: int,
) -> dict[str, int]:
    anchors_by_line: dict[int, dict[int, dict[str, Any]]] = {}
    for anchor in word_anchors:
        line = int(anchor["lyric_index"])
        index = int(anchor["standard_char_index"])
        current = anchors_by_line.setdefault(line, {}).get(index)
        if current is None or (current.get("kind") == "corrected" and anchor.get("kind") == "exact"):
            anchors_by_line[line][index] = anchor
    counts = {"qwen_exact": 0, "qwen_corrected": 0, "lddc_standard": 0, "interpolated": 0, "rejected": 0}
    for line in timeline:
        index = int(line.get("standard_line_index", -1))
        if not 0 <= index < len(rows):
            continue
        line_anchors = anchors_by_line.get(index, {})
        exact_anchors = [anchor for anchor in line_anchors.values() if anchor.get("kind") == "exact"]
        local_shift = int(line.get("local_shift_ms", shift_ms))
        if len(exact_anchors) >= 2:
            local_shift = round(statistics.median(
                int(anchor["qwen_start_ms"]) - int(anchor["provider_start_ms"])
                for anchor in exact_anchors
            ))
        standard_start = int(line.get("standard_start_ms", rows[index].get("start_ms", 0) or 0))
        standard_end = int(line.get("standard_end_ms", rows[index].get("end_ms", standard_start + 1) or standard_start + 1))
        start, end = standard_start + local_shift, standard_end + local_shift
        if line_anchors:
            start = min(start, min(int(anchor["qwen_start_ms"]) for anchor in line_anchors.values()))
            end = max(end, max(int(anchor["qwen_end_ms"]) for anchor in line_anchors.values()))
        start, end = max(0, start), max(max(0, start) + 1, end)
        words = _provider_character_times(rows[index], start, end, local_shift)
        for char_index, anchor in line_anchors.items():
            if not 0 <= char_index < len(words):
                counts["rejected"] += 1
                continue
            qstart, qend = int(anchor["qwen_start_ms"]), int(anchor["qwen_end_ms"])
            if qend <= qstart:
                counts["rejected"] += 1
                continue
            source = "qwen-exact" if anchor.get("kind") == "exact" else "qwen-corrected"
            words[char_index].update({"start_ms": qstart, "end_ms": qend, "timing_source": source})
        words = clamp_forced_words(words, start, end)
        if not words or "".join(item["text"] for item in words) != line.get("text", ""):
            line["words"] = []
            line["anchors"] = []
            counts["rejected"] += len(str(line.get("text", "")))
            continue
        for word in words:
            counts[word["timing_source"].replace("-", "_")] += 1
        line["words"] = words
        line["anchors"] = [word for word in words if word["timing_source"].startswith("qwen-")]
        line["start_ms"] = words[0]["start_ms"]
        line["end_ms"] = words[-1]["end_ms"]
        line["local_shift_ms"] = local_shift
        line["timing_precision"] = "forced-character"
        line["word_timing_source"] = "qwen-lddc-hybrid"
        line["aligner_model"] = "Qwen3-ForcedAligner-0.6B + LDDC"
    return counts
