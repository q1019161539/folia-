"""Compare Qwen live word timings with provider verbatim lyrics and merge them."""
from __future__ import annotations

import difflib
import math
import statistics
from typing import Any, Callable

from standard_timeline import clamp_forced_words, interpolated_shift_ms, mad_ms, normalized, score_timeline

# A word-vs-line disagreement past this point is only ever a warning: it is a
# *consistency* signal (do the two models even agree?), not a *quality* one --
# see cross_model_conflict below. It is deliberately far more sensitive than
# MAX_WORD_VS_LINE_SHIFT_DIFF_MS, which stays the hard veto on promoting a word
# cluster to the global shift. The two must not be merged: a real segmentation
# bias (~2600-4000ms, see the bootstrap docstring) should warn without being
# vetoed, and 1500ms was considered and rejected as too eager with no bad
# sample yet to justify it.
WORD_LINE_CONFLICT_WARN_MS = 2000


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


def provider_char_count(rows: list[dict[str, Any]]) -> int:
    """How many characters the aligner can actually match on.

    Deliberately the same units the matcher consumes, rather than len(text): a
    second counting rule would measure a different song than the one being
    aligned.
    """
    return sum(len(_provider_chars(row)) for row in rows)


def word_anchor_coverage(word_anchor_count: int, rows: list[dict[str, Any]]) -> float | None:
    """Share of the release's characters that found a live counterpart."""
    total = provider_char_count(rows)
    if not total:
        return None
    return max(0, int(word_anchor_count)) / total


def separation_retry_needed(
    timing_type: str,
    word_anchor_count: int,
    rows: list[dict[str, Any]],
    threshold: float,
) -> bool:
    """Would re-reading this clip from separated vocals be worth ~9 GiB and a quarter hour?

    Only for a word-timed release -- a line-only sheet has no character times to
    match against, so a cleaner ASR would change nothing about its anchors.

    Coverage across 37 finished verbatim songs ran min 0%, median 10.3%, max
    28.9%, and the starved ones sat far below: 《心之火》 1.6% (7 anchors out of
    432 characters) against 《读心术》 17.4% (78 of 449). 《心之火》 re-read from
    separated vocals went from 95 recognised characters to 767, and from 7 word
    anchors to 80, with the word residual median dropping 158ms -> 46ms.
    """
    if str(timing_type) != "verbatim" or threshold <= 0:
        return False
    coverage = word_anchor_coverage(word_anchor_count, rows)
    return coverage is not None and coverage < threshold


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _line_delta_stats(exact_by_line: dict[int, list[int]]) -> dict[int, dict[str, Any]]:
    """Per-line median/MAD of character deltas used to vote on one global shift."""
    return {
        line: {"median": statistics.median(deltas), "mad": mad_ms(deltas), "count": len(deltas)}
        for line, deltas in exact_by_line.items()
        if len(deltas) >= 2
    }


def _dominant_line_cluster(line_stats: dict[int, dict[str, Any]], gap_ms: int = 1500) -> list[int]:
    """Group per-line shift votes (one line, one vote) into offset clusters and
    return the lines in the largest one.

    A merged ASR segment biases every line it touches by roughly the same
    lead-in, so segmentation artefacts show up as their own tight cluster
    sitting seconds away from the real offset -- exactly the ~2600ms split
    found on 《和你一样》. This only needs to find the largest tight group, not
    classify every line; anything left out simply isn't part of it.
    """
    ordered = sorted(line_stats.items(), key=lambda item: item[1]["median"])
    clusters: list[list[int]] = []
    for line, stat in ordered:
        if clusters:
            cluster_median = statistics.median(line_stats[member]["median"] for member in clusters[-1])
            if abs(stat["median"] - cluster_median) <= gap_ms:
                clusters[-1].append(line)
                continue
        clusters.append([line])
    return max(clusters, key=len) if clusters else []


# How far a unanimous word-level cluster may sit from the line-level shift and
# still be trusted to override it. A real case measured ~9000ms of disagreement
# from a chorus repeated three times inside one oversized, ASR-garbled segment
# (line-level anchored to the segment's own start, word-level correctly landing
# on the actual matched substring deep inside it) -- likely closer to the truth
# than the line-level number it was compared against, but nothing here can tell
# the two apart automatically, and refusing costs nothing but a missed
# correction (fall back to the line shift, same as before this bootstrap
# existed). 2000-3000ms is the largest disagreement seen on a genuinely good
# match, so this sits with real margin below the ~9000ms failure and real
# margin above that: neither edge is razor-thin.
MAX_WORD_VS_LINE_SHIFT_DIFF_MS = 5000


def _bootstrap_word_shift(exact_anchors: list[dict[str, Any]], center: int) -> dict[str, Any]:
    """Find a global word-level shift from line votes, with the safety valves a
    single mis-timed segment needs to be kept from swinging the whole song.

    The old approach filtered every character against a *line-level* expected
    offset, which is exactly backwards when the line-level numbers are the ones
    carrying the ASR segmentation bias (see standard_timeline's anchor_trend_stats
    docstring for the mechanism): 《和你一样》 lost 94% of its correct word anchors
    that way, because their true offset disagreed with a line-level `expected`
    that was itself wrong by ~2600ms. Voting one line at a time instead of one
    character at a time also stops a single 20-character mismatched line from
    outvoting several short correct ones.
    """
    exact_by_line: dict[int, list[int]] = {}
    for item in exact_anchors:
        exact_by_line.setdefault(int(item["lyric_index"]), []).append(item["qwen_start_ms"] - item["provider_start_ms"])
    line_stats = _line_delta_stats(exact_by_line)
    result: dict[str, Any] = {
        "line_stats": line_stats,
        "cluster_lines": [],
        # word_model_shift_ms is the word level's own candidate -- reported whenever
        # a dominant cluster exists, whether or not it clears the safety valves below.
        # word_shift_ms is that same candidate promoted to the *global* shift, which
        # only happens once it does. Keeping both lets a caller tell "the word model
        # disagreed with the line shift" apart from "the word model itself is no
        # good": on a real song a chorus repeated three times inside one oversized,
        # ASR-garbled segment produced a word_model_shift_ms tight and self-consistent
        # across four lines, sitting ~9000ms from the line shift -- and it was likely
        # the *line* shift that was wrong there (see standard_timeline's
        # anchor_trend_stats docstring for the segment-boundary mechanism, at an
        # extreme most segments never reach). The valve below still refuses to
        # promote a cluster that far away, because nothing here can tell that case
        # apart from a genuinely bad one automatically -- but the candidate itself
        # is worth keeping visible either way.
        "word_model_shift_ms": None,
        "word_shift_ms": None,
        "status": "insufficient_lines",
    }
    if len(line_stats) < 3:
        return result
    cluster = _dominant_line_cluster(line_stats)
    result["cluster_lines"] = cluster
    coverage = len(cluster) / len(line_stats)
    cluster_median = statistics.median(line_stats[line]["median"] for line in cluster)
    result["word_model_shift_ms"] = round(cluster_median)
    if coverage < 0.6:
        result["status"] = "no_dominant_cluster"
        return result
    if abs(cluster_median - center) > MAX_WORD_VS_LINE_SHIFT_DIFF_MS:
        result["status"] = "far_from_line_shift"
        return result
    result.update(word_shift_ms=round(cluster_median), status="accepted")
    return result


def _timing_confidence(
    eligible: int, dominant: int, coverage: float | None, model_medabs: int | None, model_mad: int | None, inlier500: float | None
) -> str:
    """How much to trust the word-level timing model on its own -- deliberately
    orthogonal to match_confidence (see standard_timeline.score_timeline): a
    wrong lyric match can still produce a perfectly self-consistent local timing
    model on a repeated phrase ("我爱你我爱你", "以为自己"), so a clean word model
    must never be read as evidence the lyrics were the right ones.

    Structural gates (eligible/dominant/coverage) need no bad sample to justify
    them; the numeric guardrails below do, and are provisional on purpose --
    see the module-level comment on WORD_LINE_CONFLICT_WARN_MS. Only eligible<3
    or an uncomputable model means *no evidence*: eligible>=3 with a scattered
    or low-coverage result is a real, informative negative (there is data, it
    just does not agree with itself), so that reads "low", not "unavailable".
    """
    if eligible < 3 or model_medabs is None or coverage is None:
        return "unavailable"
    inlier = inlier500 or 0.0
    if (
        eligible >= 4 and dominant >= 4 and coverage >= 0.75
        and model_medabs <= 250 and (model_mad or 0) <= 400 and inlier >= 0.80
    ):
        return "high"
    if (
        eligible >= 3 and dominant >= 3 and coverage >= 0.60
        and model_medabs <= 500 and (model_mad or 0) <= 800 and inlier >= 0.60
    ):
        return "medium"
    return "low"


def score_provider_timeline(
    rows: list[dict[str, Any]],
    asr_segments: list[dict[str, Any]],
    *,
    title_score: float = 0.0,
) -> dict[str, Any]:
    timed = timed_rows(rows)
    line_result = score_timeline(timed, asr_segments, title_score=title_score)
    if not line_result.get("core_anchors"):
        return {**line_result, "word_anchors": [], "word_anchor_count": 0, "word_coverage": 0.0, "timing_confidence": "unavailable"}
    # Harvesting is evidence work, so it reads the evidence chain -- every extra
    # lyric line it reaches is more per-character material to vote with below.
    # (Confidence and drift read core_anchors alone -- see standard_timeline.)
    word_anchors: list[dict[str, Any]] = []
    for anchor in line_result.get("evidence_anchors") or line_result["core_anchors"]:
        lyric_index, asr_index = int(anchor["lyric_index"]), int(anchor["asr_index"])
        if lyric_index >= len(timed) or asr_index >= len(asr_segments):
            continue
        word_anchors.extend(_line_word_anchors(lyric_index, asr_index, timed[lyric_index], asr_segments[asr_index]))
    center = int(line_result.get("shift_ms", 0))
    raw_exact = [item for item in word_anchors if item["kind"] == "exact"]
    bootstrap = _bootstrap_word_shift(raw_exact, center)
    line_stats, cluster_lines = bootstrap["line_stats"], set(bootstrap["cluster_lines"])
    cluster_mad = mad_ms([line_stats[line]["median"] for line in cluster_lines]) if cluster_lines else 0
    # Filtering is independent of whether the global bootstrap succeeded. These
    # anchors are evidence for candidate ranking, the single whole-song shift and
    # diagnostics only; they are never written into the selected lyric sheet.
    accepted_word_anchors = []
    for item in word_anchors:
        delta = item["qwen_start_ms"] - item["provider_start_ms"]
        line = int(item["lyric_index"])
        stat = line_stats.get(line)
        if stat is not None:
            expected, window = stat["median"], _clamp(3 * stat["mad"], 500, 2000)
        elif bootstrap["status"] == "accepted":
            expected, window = bootstrap["word_shift_ms"], _clamp(3 * cluster_mad, 500, 2000)
        else:
            expected = interpolated_shift_ms(item["provider_start_ms"], line_result.get("evidence_anchors"), center)
            window = 1800
        if abs(delta - expected) <= window:
            accepted_word_anchors.append({**item, "delta_ms": delta})
    # Watch the accept/reject split across runs -- this is how a systematic
    # rejection problem like 《和你一样》's (94% of its correct word anchors gone)
    # becomes visible again if some future change reintroduces one.
    raw_word_anchor_count = len(word_anchors)
    word_anchors = accepted_word_anchors
    exact = [item for item in word_anchors if item["kind"] == "exact"]
    word_lines = {item["lyric_index"] for item in exact}
    accepted_exact_counts: dict[int, int] = {}
    for item in exact:
        accepted_exact_counts[item["lyric_index"]] = accepted_exact_counts.get(item["lyric_index"], 0) + 1
    # Lines with at least two exact characters can cast one vote in the global
    # word model. The count remains diagnostic; it does not authorize a local
    # shift or a character-level rewrite.
    local_shift_lines = {line for line, count in accepted_exact_counts.items() if count >= 2}
    shift_source = "word" if bootstrap["status"] == "accepted" else "line"
    shift_ms = bootstrap["word_shift_ms"] if shift_source == "word" else center
    word_model_shift_ms = bootstrap["word_model_shift_ms"]
    # word_vs_line_shift_diff_ms is a *safety/consistency* signal, not a quality one:
    # how much the word model disagrees with the line model, regardless of who is
    # right. word_median_abs_residual_ms/word_mad_ms stay the pre-existing *effective*
    # residual (against whatever shift actually ends up used -- unchanged meaning,
    # what the score penalty below and existing callers already rely on).
    # word_model_median_abs_residual_ms/word_model_mad_ms are new: the word anchors'
    # residual against the word model's *own* candidate, which is what a future
    # confidence stage should read as *word quality*. On a chorus repeated three
    # times inside one oversized ASR segment, effective residual read ~9000ms (it
    # was compared against the line shift the safety valve fell back to) while the
    # word anchors were tightly self-consistent around their own candidate -- two
    # very different facts the old single field could not tell apart.
    word_vs_line_shift_diff_ms = abs(word_model_shift_ms - center) if word_model_shift_ms is not None else None
    cross_model_conflict = word_vs_line_shift_diff_ms is not None and word_vs_line_shift_diff_ms > WORD_LINE_CONFLICT_WARN_MS
    p90 = None
    span_ms = 0
    word_median_abs, word_mad = 0, 0
    if exact:
        residuals_signed = [item["delta_ms"] - shift_ms for item in exact]
        residuals = sorted(abs(value) for value in residuals_signed)
        p90 = residuals[min(len(residuals) - 1, math.ceil(len(residuals) * 0.9) - 1)]
        span_ms = max(item["qwen_start_ms"] for item in exact) - min(item["qwen_start_ms"] for item in exact)
        word_median_abs = round(statistics.median(residuals))
        word_mad = mad_ms(residuals_signed)
    # word_model_median_abs_residual_ms/mad/inlier_ratio_500 are the *confidence*
    # signals, so they read structural_word_anchors -- every raw exact character
    # harvested from a line with enough of its own to vouch for itself (>=2),
    # deliberately *before* the +-window residual filter above runs. Computing a
    # quality signal from anchors that filter already kept would be circular:
    # reject the bad points, then point at how clean what is left looks.
    structural_word_anchors = [item for item in raw_exact if int(item["lyric_index"]) in line_stats]
    word_model_median_abs, word_model_mad, word_model_inlier_ratio_500 = None, None, None
    if word_model_shift_ms is not None and structural_word_anchors:
        model_deltas = [item["qwen_start_ms"] - item["provider_start_ms"] for item in structural_word_anchors]
        model_residuals_signed = [delta - word_model_shift_ms for delta in model_deltas]
        model_residuals_abs = sorted(abs(value) for value in model_residuals_signed)
        word_model_median_abs = round(statistics.median(model_residuals_abs))
        word_model_mad = mad_ms(model_residuals_signed)
        word_model_inlier_ratio_500 = round(sum(1 for value in model_residuals_abs if value <= 500) / len(model_residuals_abs), 4)
    word_model_coverage_ratio = round(len(cluster_lines) / len(line_stats), 4) if line_stats else None
    timing_confidence = _timing_confidence(
        len(line_stats), len(cluster_lines), word_model_coverage_ratio,
        word_model_median_abs, word_model_mad, word_model_inlier_ratio_500,
    )
    lyric_characters = sum(len(normalized(row.get("text", ""))) for row in timed)
    coverage = len({(item["lyric_index"], item["standard_char_index"]) for item in exact}) / max(1, lyric_characters)
    timing_model = f"{shift_source}_global"
    # Confidence is decided by line-level evidence alone. Word-level anchors may
    # choose the one global shift, contribute a ranking bonus and remain visible
    # in diagnostics, but never replace timestamps in the selected lyric sheet.
    low_confidence = bool(line_result.get("low_confidence", True))
    score = float(line_result.get("score", 0)) + min(25, len(exact) / 2) + min(8, span_ms / 10000)
    if p90 is not None:
        score -= p90 / 200
    return {
        **line_result,
        "score": round(score, 3),
        "shift_ms": shift_ms,
        "line_shift_ms": center,
        "effective_shift_ms": shift_ms,
        "shift_source": shift_source,
        "timing_model": timing_model,
        "word_bootstrap_status": bootstrap["status"],
        "word_eligible_line_count": len(line_stats),
        "word_dominant_cluster_line_count": len(cluster_lines),
        "word_local_shift_line_count": len(local_shift_lines),
        "word_anchors": word_anchors,
        "word_anchor_count": len(exact),
        "word_anchor_raw_count": raw_word_anchor_count,
        "word_anchor_accepted_count": len(word_anchors),
        "word_anchor_rejected_count": raw_word_anchor_count - len(word_anchors),
        "word_anchor_lines": len(word_lines),
        "word_anchor_span_ms": span_ms,
        "word_residual_p90_ms": p90,
        "word_median_abs_residual_ms": word_median_abs,
        "word_mad_ms": word_mad,
        "word_model_shift_ms": word_model_shift_ms,
        "word_model_median_abs_residual_ms": word_model_median_abs,
        "word_model_mad_ms": word_model_mad,
        "word_model_inlier_ratio_500": word_model_inlier_ratio_500,
        "word_model_coverage_ratio": word_model_coverage_ratio,
        "word_vs_line_shift_diff_ms": word_vs_line_shift_diff_ms,
        "cross_model_conflict": cross_model_conflict,
        "timing_confidence": timing_confidence,
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


def apply_shifted_provider_words(
    timeline: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    shift_ms: int,
) -> dict[str, int]:
    """Attach the provider character timeline using exactly one global shift.

    Qwen/ASR character timestamps are evidence for selecting a candidate and
    calculating ``shift_ms``. Once a standard verbatim lyric is selected, its
    internal line and character rhythm is authoritative: every provider timestamp
    receives the same offset and no live character timestamp is copied into it.
    """
    counts = {"qwen_exact": 0, "qwen_corrected": 0, "lddc_standard": 0, "interpolated": 0, "rejected": 0}
    for line in timeline:
        index = int(line.get("standard_line_index", -1))
        if not 0 <= index < len(rows):
            continue
        start, end = int(line["start_ms"]), int(line["end_ms"])
        words = _provider_character_times(rows[index], start, end, shift_ms)
        if not words or "".join(item["text"] for item in words) != line.get("text", ""):
            line["words"] = []
            line["anchors"] = []
            counts["rejected"] += len(str(line.get("text", "")))
            continue
        for word in words:
            counts[word["timing_source"].replace("-", "_")] += 1
        line["words"] = words
        line["anchors"] = []
        line["local_shift_ms"] = shift_ms
        line["timing_precision"] = "forced-character"
        line["word_timing_source"] = "provider-global-shift"
        line["aligner_model"] = "LDDC standard timeline"
    return counts
