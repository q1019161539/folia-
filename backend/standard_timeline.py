"""Parse and place a standard lyric timeline using timestamped ASR anchors."""
from __future__ import annotations

import difflib
import math
import re
import statistics
from typing import Any


TIME_TAG = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:\.\d{1,3})?)\]")
OFFSET_TAG = re.compile(r"\[offset\s*:\s*([+-]?\d+)\]", re.I)
META_TAG = re.compile(r"^\[(?:ar|ti|al|by|re|ve)\s*:", re.I)
ROLE_LINE = re.compile(
    r"^\s*(?:作词|作曲|词|曲|编曲|制作人|监制|制作|MIDI(?:程序|编写)?|口哨|混音(?:棚|工程师|工程室|工作室|室)?|录音(?:棚|工程师|工程室|工作室|室)?|"
    r"母带(?:工程师|工作室)?|吉他|木吉他|电吉他|贝斯|鼓|古筝|小提琴|大提琴|二胡|琵琶|笛子|键盘|配唱(?:制作人)?|人声(?:编辑|录音师)?|"
    r"和声(?:演唱|编写)?|合声(?:演唱|编写)?|合音|和音|弦乐(?:编写)?|录音师|音乐总监|乐队统筹|项目统筹|统筹|灯光设计|舞美设计|"
    r"企划|企宣|策划|宣发|发行(?:人)?|出品(?:人|方)?|版权|演唱|原唱|翻唱|主唱|歌手|艺人统筹|OP|SP)\s*[:：]",
    re.I,
)
NOTICE_LINE = re.compile(
    r"(?:未经.{0,12}(?:许可|授权).{0,12}(?:使用|翻唱|翻录)|版权所有|著作权人|"
    r"AI作歌|未音APP|Vemus|本歌曲.{0,8}(?:来自|由)|https?://|www\.)",
    re.I,
)


def normalized(text: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", str(text or "").lower().replace("臺", "台"))


def is_lyric_metadata(text: str, title: str = "", artist: str = "") -> bool:
    """Recognize provider credits, notices, ads and title banners, not sung lyrics."""
    value = str(text or "").strip()
    if not value or ROLE_LINE.match(value) or NOTICE_LINE.search(value):
        return True
    # Providers often insert a timed ``song - artist`` banner. Only treat a
    # hyphenated row as a banner when it also contains the known song title or
    # artist, so ordinary lyric punctuation remains untouched.
    if re.search(r"\s[-–—]\s", value):
        compact = normalized(value)
        known = [normalized(title)]
        known.extend(normalized(part) for part in re.split(r"[/,&，、]", artist or ""))
        if any(len(item) >= 2 and item in compact for item in known):
            return True
    return False


def find_suspect_anchor_regions(
    local_anchors: list[dict[str, Any]],
    lrc_lines: list[dict[str, Any]],
    asr_segments: list[dict[str, Any]],
    *,
    char_ms_threshold: int = 650,
    gap_line_threshold: int = 4,
    max_regions: int = 5,
) -> list[dict[str, Any]]:
    """Flag spots worth a human look. Reporting only -- it must not judge a song.

    This was a veto on the whole song and could not carry that weight. The
    `sparse_gap` rule measures whether anchors happen to cover every four lyric
    lines, not whether those four lines are timed wrong -- and a 40-line song
    matched by 6~16 core anchors is normally sparse, so it fired on essentially
    every song and became a second blanket "low confidence" switch after the
    residual threshold was removed. `long_duration` has the same weakness for a
    different reason: it divides the whole ASR *segment* span by the lyric's
    character count, and a segment padded with filler words, breaths or a merged
    neighbouring line inflates that number without anything being misaligned.

    Both are still worth surfacing as warnings, and `long_duration` may earn a
    verdict back once anchors carry real word-level spans instead of segment
    boundaries. Until then callers log these regions and route on confidence
    alone. Reviving "a local anomaly downgrades the song" should mean designing
    that judgement deliberately, not re-reading this function.
    """
    ordered = sorted(local_anchors, key=lambda a: int(a["lyric_index"]))
    regions: list[dict[str, Any]] = []
    for position, anchor in enumerate(ordered):
        lyric_index = int(anchor["lyric_index"])
        text = str(anchor.get("lyric_text") or lrc_lines[lyric_index]["text"])
        chars = max(1, len(normalized(text)))
        span_ms = int(anchor.get("asr_end_ms", 0)) - int(anchor.get("asr_start_ms", 0))
        if span_ms / chars <= char_ms_threshold:
            continue
        next_lyric = int(ordered[position + 1]["lyric_index"]) if position + 1 < len(ordered) else len(lrc_lines)
        segment_end = int(anchor["asr_index"])
        if segment_end + 1 < len(asr_segments):
            next_anchor_start = ordered[position + 1].get("asr_start_ms") if position + 1 < len(ordered) else None
            if next_anchor_start is None or int(asr_segments[segment_end + 1].get("start_ms", 0)) < int(next_anchor_start):
                segment_end += 1
        regions.append(
            {
                "lyric_start": lyric_index,
                "lyric_end": next_lyric,
                "segment_start": int(anchor["asr_index"]),
                "segment_end": segment_end,
                "reason": "long_duration",
            }
        )
    for this_anchor, next_anchor in zip(ordered, ordered[1:]):
        this_lyric, next_lyric = int(this_anchor["lyric_index"]), int(next_anchor["lyric_index"])
        if next_lyric - this_lyric - 1 < gap_line_threshold:
            continue
        this_segment, next_segment = int(this_anchor["asr_index"]), int(next_anchor["asr_index"])
        if next_segment - this_segment - 1 <= 0:
            continue
        regions.append(
            {
                "lyric_start": this_lyric + 1,
                "lyric_end": next_lyric,
                "segment_start": this_segment + 1,
                "segment_end": next_segment - 1,
                "reason": "sparse_gap",
            }
        )
    regions.sort(key=lambda r: r["lyric_end"] - r["lyric_start"], reverse=True)
    return regions[:max_regions]


def max_anchor_drift_ms(anchors: list[dict[str, Any]] | None, shift_ms: int) -> int:
    """Diagnostic only: how far the worst anchor sits from the whole-song shift.

    This used to gate DeepSeek at a 2000ms limit and was wrong twice over. It was
    fed the evidence chain, which is admitted with a tolerance window of seconds,
    so it was comparing a deliberately loose chain against a tight threshold. And
    a maximum is precisely the statistic a single mis-matched anchor can dominate,
    so it re-admitted through the back door the outliers the median was chosen to
    reject: songs whose residual p90 was 473~1109ms were handed to DeepSeek over a
    lone 4300ms anchor. It survives only as a logged number for comparing runs --
    nothing may branch on it. Judge systematic drift from a robust trend slope
    over long baselines instead.
    """
    deltas = [int(anchor["delta_ms"]) for anchor in anchors or [] if anchor.get("delta_ms") is not None]
    return max((abs(delta - int(shift_ms)) for delta in deltas), default=0)


def mad_ms(values: list[float]) -> int:
    """Median absolute deviation, scaled to compare with a standard deviation.

    Public so word_timeline's own line-vote bootstrap can reuse the same robust
    spread measure instead of duplicating it.
    """
    if not values:
        return 0
    center = statistics.median(values)
    return round(1.4826 * statistics.median([abs(value - center) for value in values]))


def anchor_residual_stats(anchors: list[dict[str, Any]] | None, shift_ms: int) -> dict[str, int]:
    """Robust spread of the anchor residuals around one whole-song shift.

    p90 is reported but must not be judged on: at the anchor counts this pipeline
    actually sees, `ceil(n*0.9)-1` lands on the last element for every n <= 9, so
    "the 90th percentile" silently *is* the worst anchor until a song reaches ten
    anchors. median_abs and MAD carry the same intent without that cliff.
    """
    signed = [int(item["delta_ms"]) - int(shift_ms) for item in anchors or [] if item.get("delta_ms") is not None]
    if not signed:
        return {"median_abs_residual_ms": 0, "mad_ms": 0, "residual_p90_ms": 0}
    absolute = sorted(abs(value) for value in signed)
    return {
        "median_abs_residual_ms": round(statistics.median(absolute)),
        "mad_ms": mad_ms(signed),
        "residual_p90_ms": absolute[min(len(absolute) - 1, math.ceil(len(absolute) * 0.9) - 1)],
    }


def anchor_trend_stats(anchors: list[dict[str, Any]] | None, shift_ms: int) -> dict[str, Any]:
    """Whether the residual spread is a steady drift or just scatter. Diagnostic only.

    MAD says how scattered the residuals are; it cannot say why, because it does
    not look at their order in time. A clean ramp (-1500 .. +1500 across a song)
    and a jitter (+1300, -1600, +800, -1400) give the same MAD and mean opposite
    things -- the first is a performance drifting steadily against the studio
    master, which one stretch factor would absorb; the second is anchors that are
    simply mis-matched, which no amount of stretching will fix. So fit a robust
    slope and report how much of the spread it actually explains
    (`mad_improvement_ratio`), alongside how consistently the long baselines agree
    on its direction (`direction_support`).

    Only pairs at least `max(20s, 20% of span)` apart contribute a slope: two
    anchors three seconds apart with a 400ms difference imply an absurd rate.

    Nothing may branch on these numbers yet, and `drift_over_span_ms` must never
    gate anything on its own -- a drift figure used as a threshold is exactly how
    max_anchor_drift_ms went wrong. Anchors here are still ASR segment starts,
    which carry a lead-in of their own, so part of any trend measured now is an
    artefact of segmentation rather than of the singing.
    """
    empty: dict[str, Any] = {
        "long_baseline_pairs": 0,
        "drift_over_span_ms": 0,
        "direction_support": 0.0,
        "affine_mad_ms": 0,
        "mad_improvement_ratio": 0.0,
    }
    points = sorted(
        (int(item["lrc_start_ms"]), int(item["delta_ms"]))
        for item in anchors or []
        if item.get("lrc_start_ms") is not None and item.get("delta_ms") is not None
    )
    if len(points) < 3:
        return empty
    span_ms = points[-1][0] - points[0][0]
    min_baseline_ms = max(20_000, round(span_ms * 0.20))
    slopes = [
        (later_delta - delta) / (later_time - time_ms)
        for index, (time_ms, delta) in enumerate(points)
        for later_time, later_delta in points[index + 1:]
        if later_time - time_ms >= min_baseline_ms
    ]
    if not slopes:
        return empty
    slope = statistics.median(slopes)
    agreeing = sum(1 for value in slopes if (value >= 0) == (slope >= 0))
    center_ms = statistics.median(time_ms for time_ms, _ in points)
    intercept = statistics.median(delta - slope * (time_ms - center_ms) for time_ms, delta in points)
    trend_residuals = [delta - (intercept + slope * (time_ms - center_ms)) for time_ms, delta in points]
    shift_mad = mad_ms([delta - int(shift_ms) for _, delta in points])
    affine_mad = mad_ms(trend_residuals)
    return {
        "long_baseline_pairs": len(slopes),
        "drift_over_span_ms": round(slope * span_ms),
        "direction_support": round(agreeing / len(slopes), 3),
        "affine_mad_ms": affine_mad,
        "mad_improvement_ratio": round((shift_mad - affine_mad) / shift_mad, 3) if shift_mad else 0.0,
    }


def is_high_confidence(result: dict[str, Any]) -> bool:
    return not bool(result.get("low_confidence", True))


def resolve_deepseek_full_realign(
    payload: dict[str, Any],
    lrc_lines: list[dict[str, Any]],
    asr_min_ms: int,
    asr_max_ms: int,
) -> list[dict[str, Any]]:
    """Validate a full-song DeepSeek realignment response.

    This is the terminal step of the confidence remediation chain (see
    auto_standard_timeline_task): once local scoring plus the song-identity
    recheck still can't reach high confidence, DeepSeek is handed the complete
    real ASR word timeline and the complete standard lyric text and asked to
    return an adjusted timed lyric file directly. Its output is taken as final
    without further content-based vetoing (no shift-consistency rejection), so
    validation here is limited to structural sanity -- real lyric index, sane
    text/ordering -- and clamping every time into the real ASR-covered window,
    which is the one hard physical boundary: nothing can be timed earlier or
    later than the video's real ASR-recognized speech/singing range.
    """
    raw_lines = payload.get("lines") if isinstance(payload, dict) else None
    if not isinstance(raw_lines, list):
        return []
    resolved: list[dict[str, Any]] = []
    for raw in raw_lines:
        if not isinstance(raw, dict):
            continue
        try:
            index = int(raw.get("index"))
            start_ms = int(raw.get("start_ms"))
            end_ms = int(raw.get("end_ms"))
        except (TypeError, ValueError):
            continue
        if not (0 <= index < len(lrc_lines)):
            continue
        text = str(raw.get("text") or lrc_lines[index]["text"]).strip()
        if not text:
            continue
        start_ms = max(asr_min_ms, min(asr_max_ms, start_ms))
        end_ms = max(asr_min_ms, min(asr_max_ms, end_ms))
        if end_ms <= start_ms:
            end_ms = min(asr_max_ms, start_ms + 1)
        if end_ms <= start_ms:
            continue
        resolved.append({"standard_line_index": index, "text": text, "start_ms": start_ms, "end_ms": end_ms})
    resolved.sort(key=lambda item: item["start_ms"])
    return resolved


def choose_best_timeline_candidate(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer a trustworthy alignment over a slightly higher raw match score.

    Among the versions that match the song title equally well, a verbatim
    (word-timed) release wins outright: it carries per-character times the whole
    hybrid pipeline is built on, while a line-only DJ/remix upload of the same
    title carries none. A live cover's line-level residuals can read worse
    against the original studio release than against a remix whose pacing
    happens to sit closer, which previously handed the pick to the remix -- the
    title-similarity floor keeps that preference from reaching across to a
    verbatim release of a different song.
    """
    if not items:
        raise ValueError("没有可用歌词候选")
    best_similarity = max(float(item.get("title_similarity", 0)) for item in items)
    return max(
        items,
        key=lambda item: (
            str(item.get("candidate", {}).get("timing_type", "")) == "verbatim"
            and float(item.get("title_similarity", 0)) >= best_similarity - 0.05,
            not bool(item.get("result", {}).get("low_confidence", True)),
            float(item.get("title_similarity", 0)),
            float(item.get("result", {}).get("score", 0)),
            len(item.get("result", {}).get("core_anchors") or []),
        ),
    )


def _timestamp_ms(minutes: str, seconds: str) -> int:
    return round((int(minutes) * 60 + float(seconds)) * 1000)


def parse_lrc(value: str) -> list[dict[str, Any]]:
    """Return unique, ordered lyric rows while honoring the LRC offset tag."""
    offset_match = OFFSET_TAG.search(value or "")
    offset_ms = int(offset_match.group(1)) if offset_match else 0
    rows: list[dict[str, Any]] = []
    for source_index, raw in enumerate(str(value or "").splitlines()):
        tags = TIME_TAG.findall(raw)
        if not tags or META_TAG.match(raw.strip()):
            continue
        text = TIME_TAG.sub("", OFFSET_TAG.sub("", raw)).strip()
        if is_lyric_metadata(text):
            continue
        for minutes, seconds in tags:
            rows.append(
                {
                    "text": text,
                    "start_ms": max(0, _timestamp_ms(minutes, seconds) + offset_ms),
                    "source_index": source_index,
                }
            )
    rows.sort(key=lambda row: (row["start_ms"], row["source_index"]))
    # Parallel translations and duplicated platform rows must not create
    # overlapping single-line subtitle events. Keep the first original row.
    result: list[dict[str, Any]] = []
    seen_times: set[int] = set()
    for row in rows:
        if row["start_ms"] in seen_times:
            continue
        seen_times.add(row["start_ms"])
        result.append(row)
    return result


def plain_lyric_lines(value: str) -> list[str]:
    """Extract lyric text even when a provider did not supply timestamps."""
    rows: list[str] = []
    for raw in str(value or "").splitlines():
        if META_TAG.match(raw.strip()) or OFFSET_TAG.fullmatch(raw.strip()):
            continue
        text = TIME_TAG.sub("", raw).strip()
        if text and not is_lyric_metadata(text):
            rows.append(text)
    return rows


def _content_score(heard: str, target: str) -> tuple[float, int]:
    heard, target = normalized(heard), normalized(target)
    if not heard or not target:
        return 0.0, 0
    matcher = difflib.SequenceMatcher(None, heard, target, autojunk=False)
    exact = sum(block.size for block in matcher.get_matching_blocks())
    ratio = matcher.ratio()
    coverage = max(exact / len(heard), exact / len(target))
    if exact < 2 or (ratio < 0.42 and coverage < 0.60):
        return 0.0, exact
    length_penalty = abs(len(heard) - len(target)) / max(len(heard), len(target))
    return max(0.0, ratio + 0.25 * coverage - 0.15 * length_penalty), exact


def _potential_anchors(
    lrc_lines: list[dict[str, Any]], asr_segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    potentials: list[dict[str, Any]] = []
    for asr_index, segment in enumerate(asr_segments):
        heard = normalized(segment.get("text", ""))
        if len(heard) < 2:
            continue
        asr_start = int(segment.get("start_ms", 0))
        asr_end = max(asr_start + 1, int(segment.get("end_ms", asr_start + 1)))
        for lyric_index, line in enumerate(lrc_lines):
            score, exact = _content_score(heard, line["text"])
            if not score:
                continue
            lrc_start = int(line["start_ms"])
            potentials.append(
                {
                    "asr_index": asr_index,
                    "lyric_index": lyric_index,
                    "asr_start_ms": asr_start,
                    "asr_end_ms": asr_end,
                    "lrc_start_ms": lrc_start,
                    "delta_ms": asr_start - lrc_start,
                    "text_score": round(score, 4),
                    "exact": exact,
                    "asr_text": str(segment.get("text", "")),
                    "lyric_text": str(line["text"]),
                }
            )
    return potentials


def _best_monotonic_chain(
    potentials: list[dict[str, Any]], center: int, tolerance_ms: int
) -> list[dict[str, Any]]:
    selected = [p for p in potentials if abs(p["delta_ms"] - center) <= tolerance_ms]
    selected.sort(key=lambda p: (p["asr_index"], p["lyric_index"], -p["text_score"]))
    if not selected:
        return []
    scores: list[float] = []
    previous: list[int] = []
    for index, item in enumerate(selected):
        residual_bonus = max(0.0, 1 - abs(item["delta_ms"] - center) / tolerance_ms)
        best_score = item["text_score"] * 4 + residual_bonus
        best_previous = -1
        for before in range(index):
            prior = selected[before]
            if prior["asr_index"] >= item["asr_index"] or prior["lyric_index"] >= item["lyric_index"]:
                continue
            candidate = scores[before] + item["text_score"] * 4 + residual_bonus
            if candidate > best_score:
                best_score, best_previous = candidate, before
        scores.append(best_score)
        previous.append(best_previous)
    cursor = max(range(len(scores)), key=scores.__getitem__)
    chain: list[dict[str, Any]] = []
    while cursor >= 0:
        chain.append(selected[cursor])
        cursor = previous[cursor]
    return list(reversed(chain))


def score_timeline(
    lrc_lines: list[dict[str, Any]],
    asr_segments: list[dict[str, Any]],
    *,
    title_score: float = 0.0,
    tolerance_ms: int = 1800,
) -> dict[str, Any]:
    """Find a monotonic anchor chain, allowing smooth/local timing drift."""
    potentials = _potential_anchors(lrc_lines, asr_segments)
    if not potentials:
        return {"score": 0.0, "core_anchors": [], "evidence_anchors": [], "reason": "没有歌词文字锚点"}
    centers = sorted({round(item["delta_ms"] / 500) * 500 for item in potentials})
    best_chain: list[dict[str, Any]] = []
    best_key: tuple[float, int, float] | None = None
    for center in centers:
        chain = _best_monotonic_chain(potentials, center, tolerance_ms)
        if not chain:
            continue
        median_delta = round(statistics.median(item["delta_ms"] for item in chain))
        residuals = [abs(item["delta_ms"] - median_delta) for item in chain]
        value = len(chain) * 20 + sum(item["text_score"] for item in chain) * 6
        value += min(10, (chain[-1]["asr_start_ms"] - chain[0]["asr_start_ms"]) / 3000)
        value += max(0.0, min(1.0, title_score)) * 5 - statistics.median(residuals) / 250
        key = (value, len(chain), -statistics.median(residuals))
        if best_key is None or key > best_key:
            best_key, best_chain = key, chain
    if not best_chain:
        return {"score": 0.0, "core_anchors": [], "evidence_anchors": [], "reason": "歌词锚点无法形成同一整体偏移"}
    # Two chains with two different jobs, and they must never be confused again.
    # core_chain is the tight one: it is the clock, and every timing and quality
    # judgement reads it alone. evidence_chain additionally admits very strong
    # text matches under a tolerance window of seconds, purely so more lyric rows
    # can carry their ASR evidence; a window that wide cannot calibrate anything.
    # Returning both under one "anchors" key is what let a 8000ms-tolerance chain
    # be measured against a 2000ms drift limit (see max_anchor_drift_ms).
    core_chain = best_chain
    shift_ms = round(statistics.median(item["delta_ms"] for item in core_chain))
    reliable_potentials = list(core_chain)
    reliable_potentials.extend(
        item for item in potentials if item["text_score"] >= 0.8 and item not in core_chain
    )
    expanded_chain = _best_monotonic_chain(
        reliable_potentials, shift_ms, max(8000, tolerance_ms * 4)
    )
    evidence_chain = expanded_chain if len(expanded_chain) >= len(core_chain) else list(core_chain)
    stats = anchor_residual_stats(core_chain, shift_ms)
    trend = anchor_trend_stats(core_chain, shift_ms)
    span_ms = evidence_chain[-1]["asr_start_ms"] - evidence_chain[0]["asr_start_ms"]
    confidence_span_ms = core_chain[-1]["asr_start_ms"] - core_chain[0]["asr_start_ms"]
    # The residual thresholds are deliberately absent. A live cover sits 1500~2700ms
    # off the studio master as a matter of course, and the old `p90 > 1500` rejected
    # every song in a 13-song batch on that alone -- while for anything under ten
    # anchors that p90 was the single worst anchor. Residual spread is logged here
    # and judged once the anchors themselves are word-level (they are still ASR
    # segment starts, which carry a lead-in of their own).
    low_confidence = len(core_chain) < 3 or confidence_span_ms < 10000
    return {
        "score": round(best_key[0], 3) if best_key else 0.0,
        "shift_ms": shift_ms,
        "shift_min_ms": min(item["delta_ms"] for item in core_chain),
        "shift_max_ms": max(item["delta_ms"] for item in core_chain),
        "shift_range_ms": max(item["delta_ms"] for item in core_chain) - min(item["delta_ms"] for item in core_chain),
        "core_anchors": core_chain,
        "evidence_anchors": evidence_chain,
        "core_anchor_count": len(core_chain),
        "evidence_anchor_count": len(evidence_chain),
        "evidence_added_count": len(evidence_chain) - len(core_chain),
        "core_span_ms": confidence_span_ms,
        "anchor_span_ms": span_ms,
        "max_anchor_drift_ms": max_anchor_drift_ms(core_chain, shift_ms),
        **stats,
        **trend,
        "low_confidence": low_confidence,
        "confidence": "low" if low_confidence else "high",
        # match_confidence names the same line/core-evidence judgement under a
        # name that says what it actually measures: whether the standard lyric
        # text matched well enough, structurally, to trust which song and which
        # lines this is. It says nothing about word-level timing quality (see
        # word_timeline.score_provider_timeline's timing_confidence for that) --
        # deliberately kept orthogonal, since a wrong lyric can still produce a
        # perfectly self-consistent local timing model on repeated phrases.
        "match_confidence": "low" if low_confidence else "high",
        "reason": "核心锚点太少或跨度太短" if low_confidence else "多个歌词锚点支持同一整体偏移",
    }


def candidate_pool_quality(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """How much independent lyric-text evidence the whole candidate pool found.

    A wrong upstream song identity (fingerprint false positive, or a stale
    automation guess) poisons every candidate before this point -- every
    searched version of the wrong title gets scored, and none of them is the
    real song, so the whole pool tends to score badly together. That reads
    differently from "the right song, a mediocre lyric version" (one weak
    candidate among otherwise-reasonable ones): it shows up as most of the pool
    matching nothing at all -- real case, 8 of 12 -- and even the best of that
    bad lot barely clearing a handful of anchors -- real case, 1.

    Each `scored` item is expected to carry a "result" dict shaped like
    score_timeline's or score_provider_timeline's output (a "core_anchors" list)
    or, for an untimed lyric sheet, align_standard_lyrics's own shape (an
    "anchor_count" int and no "core_anchors" key).
    """
    if not scored:
        return {"candidate_count": 0, "zero_score_count": 0, "zero_score_ratio": 0.0, "best_anchor_count": 0}
    counts = [
        len(item["result"]["core_anchors"]) if item["result"].get("core_anchors") is not None
        else int(item["result"].get("anchor_count", 0) or 0)
        for item in scored
    ]
    zero = sum(1 for count in counts if count == 0)
    return {
        "candidate_count": len(scored),
        "zero_score_count": zero,
        "zero_score_ratio": round(zero / len(scored), 4),
        "best_anchor_count": max(counts),
    }


def song_identity_suspicious(
    pool_quality: dict[str, Any],
    *,
    min_anchor_count: int = 3,
    max_zero_score_ratio: float = 0.5,
) -> bool:
    """Flag a candidate pool that looks like it was searched under the wrong
    song title entirely, distinct from "the right song, weak lyric evidence".
    """
    return (
        pool_quality["candidate_count"] > 0
        and pool_quality["best_anchor_count"] < min_anchor_count
        and pool_quality["zero_score_ratio"] >= max_zero_score_ratio
    )


def interpolated_shift_ms(
    standard_ms: int,
    anchors: list[dict[str, Any]] | None,
    fallback_shift_ms: int,
) -> int:
    """Interpolate a local LRC shift between reliable monotonic ASR anchors."""
    points: list[tuple[int, int]] = []
    for anchor in anchors or []:
        if anchor.get("lrc_start_ms") is None or anchor.get("delta_ms") is None:
            continue
        points.append((int(anchor["lrc_start_ms"]), int(anchor["delta_ms"])))
    if not points:
        return int(fallback_shift_ms)
    points.sort()
    collapsed: list[tuple[int, int]] = []
    for position in sorted({point[0] for point in points}):
        deltas = [delta for current, delta in points if current == position]
        collapsed.append((position, round(statistics.median(deltas))))
    if standard_ms <= collapsed[0][0]:
        return collapsed[0][1]
    if standard_ms >= collapsed[-1][0]:
        return collapsed[-1][1]
    for (left_ms, left_shift), (right_ms, right_shift) in zip(collapsed, collapsed[1:]):
        if left_ms <= standard_ms <= right_ms:
            ratio = (standard_ms - left_ms) / max(1, right_ms - left_ms)
            return round(left_shift + (right_shift - left_shift) * ratio)
    return int(fallback_shift_ms)


def build_shifted_timeline(
    lrc_lines: list[dict[str, Any]],
    shift_ms: int,
    duration_ms: int,
    *,
    anchors: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not lrc_lines or duration_ms <= 0:
        return []
    gaps = [
        int(b["start_ms"]) - int(a["start_ms"])
        for a, b in zip(lrc_lines, lrc_lines[1:])
        if int(b["start_ms"]) > int(a["start_ms"])
    ]
    tail = max(1500, min(8000, round(statistics.median(gaps)) if gaps else 4000))
    # The whole lyric sheet moves by one shift. A release's internal rhythm is
    # already correct, so preserving it exactly is the safest thing to do with it;
    # interpolating a per-section shift between anchors instead let a single
    # mis-attributed anchor bend everything around it, and every anchor carries
    # the text-matching uncertainty of one ASR line. A section that genuinely
    # drifts away from this one shift is not patched locally here either; that
    # belongs to a robust whole-song stretch, once the anchors are word-level.
    # `anchors` here is the evidence chain -- it only attaches ASR rows to lyric
    # lines and never moves a single time.
    evidence: dict[int, list[dict[str, Any]]] = {}
    for anchor in anchors or []:
        evidence.setdefault(int(anchor["lyric_index"]), []).append(anchor)
    output: list[dict[str, Any]] = []
    for index, line in enumerate(lrc_lines):
        standard_start = int(line["start_ms"])
        explicit_end = line.get("end_ms")
        if explicit_end is not None and int(explicit_end) > standard_start:
            standard_end = int(explicit_end)
        elif index + 1 < len(lrc_lines):
            standard_end = int(lrc_lines[index + 1]["start_ms"])
        else:
            standard_end = standard_start + tail
        # Do not hold a line through a clearly exceptional instrumental gap; use
        # this version's typical row interval as the inferred display duration.
        # This has to cover a verbatim release's own end_ms too, not just the
        # inferred one: the last line before an interlude is routinely published
        # with an end that runs to the next sung line, which left one line of
        # 《坏女孩》on screen for 32 seconds straight through the break.
        if standard_end - standard_start > tail * 1.5:
            standard_end = standard_start + tail
        shifted_start, shifted_end = standard_start + shift_ms, standard_end + shift_ms
        start, end = max(0, shifted_start), min(duration_ms, shifted_end)
        if end <= start:
            continue
        line_evidence = evidence.get(index, [])
        segment_ids = sorted({int(item["asr_index"]) for item in line_evidence})
        asr_starts = [int(item["asr_start_ms"]) for item in line_evidence if item.get("asr_start_ms") is not None]
        asr_ends = [int(item["asr_end_ms"]) for item in line_evidence if item.get("asr_end_ms") is not None]
        if output and start < int(output[-1]["end_ms"]):
            output[-1]["end_ms"] = max(int(output[-1]["start_ms"]) + 1, start)
        output.append(
            {
                "line_id": len(output),
                "text": line["text"],
                "start_ms": start,
                "end_ms": end,
                "standard_start_ms": standard_start,
                "standard_end_ms": standard_end,
                "local_shift_ms": shift_ms,
                "standard_line_index": index,
                "status": "standard_timeline",
                "timing_precision": "standard-line",
                "timing_source": "standard-lrc",
                "fixed_timeline": True,
                "segment_ids": segment_ids,
                "words": [],
                "anchors": [],
                "confidence": 1.0 if segment_ids else 0.5,
                **({"asr_start_ms": min(asr_starts)} if asr_starts else {}),
                **({"asr_end_ms": max(asr_ends)} if asr_ends else {}),
            }
        )
    return output


def estimate_untimed_timeline(
    lyrics: list[str], evidence_rows: list[dict[str, Any]], duration_ms: int
) -> list[dict[str, Any]]:
    """Fill an untimed lyric sheet around real ASR-backed line anchors."""
    if not lyrics or duration_ms <= 0:
        return []
    anchors: dict[int, int] = {}
    evidence_ids: dict[int, list[int]] = {}
    for row in evidence_rows:
        index = row.get("standard_line_index")
        if not isinstance(index, int) or not 0 <= index < len(lyrics):
            continue
        anchors[index] = int(row.get("asr_start_ms", row.get("start_ms", 0)))
        evidence_ids[index] = [int(value) for value in row.get("segment_ids", [])]
    if not anchors:
        raise ValueError("没有歌词文字锚点，无法估算整首时间轴")
    points = sorted(anchors.items())
    starts = [0] * len(lyrics)

    def distribute(left_index: int, right_index: int, left_time: int, right_time: int) -> None:
        weights = [max(2, len(normalized(lyrics[i]))) for i in range(left_index, right_index)]
        total = max(1, sum(weights))
        elapsed = 0
        for offset, index in enumerate(range(left_index, right_index)):
            starts[index] = left_time + round((right_time - left_time) * elapsed / total)
            elapsed += weights[offset]
        starts[right_index] = right_time

    first_index, first_time = points[0]
    distribute(0, first_index, 0, max(0, min(duration_ms, first_time)))
    for (left_index, left_time), (right_index, right_time) in zip(points, points[1:]):
        distribute(left_index, right_index, left_time, max(left_time + 1, right_time))
    last_index, last_time = points[-1]
    distribute(last_index, len(lyrics) - 1, last_time, max(last_time + 1, duration_ms - 1200))
    for index, value in anchors.items():
        starts[index] = max(0, min(duration_ms - 1, value))
    starts = [max(0, min(duration_ms - 1, value)) for value in starts]
    for index in range(1, len(starts)):
        starts[index] = max(starts[index - 1] + 1, starts[index])
    output: list[dict[str, Any]] = []
    for index, text in enumerate(lyrics):
        start = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else duration_ms
        if end <= start:
            continue
        output.append(
            {
                "line_id": len(output),
                "text": text,
                "start_ms": start,
                "end_ms": end,
                "standard_line_index": index,
                "status": "standard_timeline",
                "timing_precision": "estimated-line",
                "timing_source": "estimated-full",
                "fixed_timeline": True,
                "segment_ids": evidence_ids.get(index, []),
                "words": [],
                "anchors": [],
                "confidence": 0.35,
            }
        )
    return output


def clamp_forced_words(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    """Keep Qwen character timing inside an immutable standard-LRC row."""
    if not words or end_ms - start_ms < len(words):
        return []
    output: list[dict[str, Any]] = []
    cursor = start_ms
    for index, word in enumerate(words):
        remaining = len(words) - index - 1
        start = max(cursor, min(end_ms - remaining - 1, int(word.get("start_ms", cursor))))
        end = max(start + 1, min(end_ms - remaining, int(word.get("end_ms", start + 1))))
        output.append({**word, "start_ms": start, "end_ms": end})
        cursor = end
    for current, nxt in zip(output, output[1:]):
        current["end_ms"] = max(current["start_ms"] + 1, min(current["end_ms"], nxt["start_ms"]))
    output[-1]["end_ms"] = min(end_ms, max(output[-1]["start_ms"] + 1, output[-1]["end_ms"]))
    return output


def lyric_render_window(rows: list[dict[str, Any]], duration_ms: int, padding_ms: int = 5000) -> tuple[int, int]:
    """Bound a final video to the first/last lyric with available edge padding."""
    duration_ms = max(0, int(duration_ms))
    valid = [row for row in rows if int(row.get("end", 0)) > int(row.get("start", 0))]
    if not valid:
        return 0, duration_ms
    first = min(int(row["start"]) for row in valid)
    last = max(int(row["end"]) for row in valid)
    return max(0, first - max(0, padding_ms)), min(duration_ms, last + max(0, padding_ms))
