"""Diagnostic only -- proposes where an oversized ASR segment should be cut,
and changes nothing: no production alignment, no subtitles, no segment records.

The problem this measures: Whisper merges several sung lyric lines into one
oversized segment (the real 《很任性》 case is 12-16s / 35 chars holding four
chorus lines, caused by "很任性的" being heard as "人人心的"). Line-level matching
then treats "when this lyric line was sung" as "when the whole segment started",
which put one line 9 seconds off. Cutting such a segment at the right places
fixes the timing WITHOUT correcting the ASR text at all -- the Qwen
per-character times inside the segment already say where each line sits.

The unit of evidence here is deliberately NOT (lyric_index, asr_index). A
chorus written four times in the standard lyrics produces four lyric_index
values that all match the same sung moment, and deciding which repeat this is
requires the neighbouring lines' trusted times -- a problem a cut does not need
to solve, since the boundary sits at the same millisecond either way. So this
works in (normalized_lyric_text, occurrence_time) and emits canonical text plus
a time span, never a lyric_index assignment. Attribution stays downstream.

What keeps a cut safe is the combination rule, not any single score: individual
evidence is allowed to be a bit weaker than the word-level rescue bar, but a
segment must be corroborated by two independent lyric texts at clearly separate
times before anything is cut at all. Short lines (<=7 chars, where a corrupted
ASR reading leaves only 3 matching characters) can join as supplementary
occurrences but can never trigger a split on their own.
"""
from __future__ import annotations

import math
from typing import Any

from standard_timeline import _content_score
from word_anchor_rescue_diagnostic import _valid_lyric_char_count
from word_timeline import _line_word_anchors, _qwen_chars

# Normal evidence: scaled to the lyric line's own length, so a 6-char line is
# not asked for the 83% coverage a flat bar of 5 would demand, while a long
# line still has to bring real evidence. Capped so very long lines stay reachable.
NORMAL_MIN_COVERAGE = 0.35
NORMAL_ANCHOR_FLOOR = 4
NORMAL_ANCHOR_CEILING = 8
NORMAL_ANCHOR_RATIO = 0.35

# Short-line bridge: a 6-char line whose ASR reading is corrupted may only have
# 3 characters left to match. That is too weak to justify a cut by itself, but
# once the segment is already proven to hold two other lyric texts, it is
# reasonable supplementary structure rather than a coincidence.
BRIDGE_MAX_CHARS = 7
BRIDGE_MIN_ANCHORS = 3
BRIDGE_MIN_COVERAGE = 0.50
MIN_NORMAL_OCCURRENCES_FOR_BRIDGE = 2

# Two occurrences count as distinct sung moments either by being far apart, or
# by not overlapping at all with a real gap between them.
OCCURRENCE_CENTER_SEPARATION_MS = 700
OCCURRENCE_SPAN_GAP_MS = 200

# A pause counts as an observed boundary from here up; below it the cut still
# has to land somewhere, but the report says it was a midpoint guess.
CLEAR_GAP_MS = 300
STRONG_GAP_MS = 500

MIN_OCCURRENCES_FOR_SPLIT = 2


def normalize_lyric_text(text: str) -> str:
    """Two lyric rows are the same line when their letters/CJK agree -- spacing
    and punctuation differ between lyric providers and carry no identity."""
    return "".join(ch for ch in str(text) if ch.isalnum())


def required_anchors(valid_lyric_chars: int) -> int:
    return min(NORMAL_ANCHOR_CEILING,
               max(NORMAL_ANCHOR_FLOOR, math.ceil(valid_lyric_chars * NORMAL_ANCHOR_RATIO)))


def _strength(anchor_count: int, coverage: float, valid_chars: int) -> str | None:
    if anchor_count >= required_anchors(valid_chars) and coverage >= NORMAL_MIN_COVERAGE:
        return "normal"
    if (valid_chars <= BRIDGE_MAX_CHARS and anchor_count >= BRIDGE_MIN_ANCHORS
            and coverage >= BRIDGE_MIN_COVERAGE):
        return "bridge"
    return None


def _separated(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Whether two hits of the SAME lyric text are two different sung moments
    rather than one. Being far apart in the middle is enough here, since the
    question is identity, not where a boundary would go."""
    if right["center_ms"] - left["center_ms"] >= OCCURRENCE_CENTER_SEPARATION_MS:
        return True
    return right["first_ms"] - left["last_ms"] >= OCCURRENCE_SPAN_GAP_MS


def _cuttable(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Whether a boundary between two occurrences is even defined. Centre
    distance is not enough: an occurrence whose matched characters are scattered
    across the whole segment can sit 700ms away by its midpoint while its span
    still swallows the other one, and there is no moment where one line ends and
    the next begins. Cutting on those produced overlapping, even negative-length
    pseudo-segments on real songs, so the span itself has to clear."""
    return right["first_ms"] - left["last_ms"] >= OCCURRENCE_SPAN_GAP_MS


def collect_occurrences(
    timed_rows: list[dict[str, Any]],
    asr_segments: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """Per ASR segment, the distinct lyric texts found inside it and when.

    Every lyric row is searched against every segment: a line production already
    anchored elsewhere may still prove "this text was sung here", which is all a
    cut needs. What it must never do is claim this position IS that lyric_index
    -- so the producing rows are recorded only as candidates, for inspection.
    """
    found: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for lyric_index, row in enumerate(timed_rows):
        text = str(row.get("text", ""))
        canonical = normalize_lyric_text(text)
        valid_chars = _valid_lyric_char_count(text)
        if not canonical:
            continue
        for asr_index, segment in enumerate(asr_segments):
            exact = [a for a in _line_word_anchors(lyric_index, asr_index, row, segment)
                     if a["kind"] == "exact"]
            if not exact:
                continue
            coverage = len(exact) / valid_chars if valid_chars else 0.0
            strength = _strength(len(exact), coverage, valid_chars)
            if strength is None:
                continue
            first = min(a["qwen_start_ms"] for a in exact)
            last = max(a["qwen_end_ms"] for a in exact)
            text_score, _ = _content_score(str(segment.get("text", "")), text)
            found.setdefault(asr_index, {}).setdefault(canonical, []).append({
                "canonical_text": canonical,
                "lyric_text": text,
                "candidate_lyric_indexes": [lyric_index],
                "asr_index": asr_index,
                "strength": strength,
                "anchor_count": len(exact),
                "coverage": round(coverage, 4),
                "text_score": round(text_score, 4),
                "first_ms": first,
                "last_ms": last,
                "center_ms": (first + last) // 2,
            })

    # Fold the repeats: identical text hitting the same moment is one occurrence
    # with several possible lyric_index owners, not several pieces of evidence.
    occurrences: dict[int, list[dict[str, Any]]] = {}
    for asr_index, by_text in found.items():
        merged: list[dict[str, Any]] = []
        for canonical, hits in by_text.items():
            hits.sort(key=lambda h: h["center_ms"])
            clusters: list[list[dict[str, Any]]] = []
            for hit in hits:
                if clusters and not _separated(clusters[-1][-1], hit):
                    clusters[-1].append(hit)
                else:
                    clusters.append([hit])
            for cluster in clusters:
                best = max(cluster, key=lambda h: h["anchor_count"])
                merged.append({**best, "candidate_lyric_indexes":
                               sorted(i for h in cluster for i in h["candidate_lyric_indexes"])})
        occurrences[asr_index] = sorted(merged, key=lambda o: o["center_ms"])
    return occurrences


def _boundary_between(qwen_chars: list[dict[str, Any]], prev_end_ms: int, next_start_ms: int) -> dict[str, Any]:
    """Pick the cut point between two occurrences: the widest silence between
    them if there is a real one, otherwise the midpoint. Reports the gap it
    found either way, so a reviewer can see what the choice rested on. Callers
    must pass occurrences that clear _cuttable, so the interval is non-empty."""
    inside = [c for c in qwen_chars
              if c["start_ms"] is not None and c["end_ms"] is not None
              and c["start_ms"] >= prev_end_ms and c["end_ms"] <= next_start_ms]
    # Silences run from the end of one covered span to the start of the next.
    # With no characters in between at all that is simply the whole interval,
    # which is exactly the common case of a clean pause between two sung lines.
    span_ends = [prev_end_ms] + [c["end_ms"] for c in inside]
    span_starts = [c["start_ms"] for c in inside] + [next_start_ms]
    best_gap, best_mid = -1, None
    for gap_start, gap_end in zip(span_ends, span_starts):
        if gap_end - gap_start > best_gap:
            best_gap, best_mid = gap_end - gap_start, (gap_start + gap_end) // 2
    if best_gap >= CLEAR_GAP_MS and best_mid is not None:
        return {
            "boundary_ms": best_mid,
            "gap_ms": best_gap,
            "method": "gap_strong" if best_gap >= STRONG_GAP_MS else "gap",
        }
    return {
        "boundary_ms": (prev_end_ms + next_start_ms) // 2,
        "gap_ms": max(best_gap, 0),
        "method": "midpoint",
    }


def _accept_occurrences(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """Which occurrences may structure this segment. Bridges only ride along
    once two normal-strength occurrences of different texts already agree that
    the segment holds more than one line."""
    normals = [o for o in candidates if o["strength"] == "normal"]
    kept_normals: list[dict[str, Any]] = []
    for occurrence in normals:
        if kept_normals and not _cuttable(kept_normals[-1], occurrence):
            continue
        if any(o["canonical_text"] == occurrence["canonical_text"] for o in kept_normals):
            continue
        kept_normals.append(occurrence)
    if len(kept_normals) < MIN_NORMAL_OCCURRENCES_FOR_BRIDGE:
        return [], "not_enough_normal_occurrences"
    accepted = list(kept_normals)
    for occurrence in candidates:
        if occurrence["strength"] != "bridge":
            continue
        if any(o["canonical_text"] == occurrence["canonical_text"] for o in accepted):
            continue
        accepted.append(occurrence)
    accepted.sort(key=lambda o: o["center_ms"])
    final: list[dict[str, Any]] = []
    for occurrence in accepted:
        if final and not _cuttable(final[-1], occurrence):
            continue
        final.append(occurrence)
    if len(final) < MIN_OCCURRENCES_FOR_SPLIT:
        return [], "no_separated_pair"
    return final, None


def resplit_diagnostic(
    timed_rows: list[dict[str, Any]],
    asr_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    occurrences = collect_occurrences(timed_rows, asr_segments)
    proposals: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for asr_index, segment in enumerate(asr_segments):
        candidates = occurrences.get(asr_index) or []
        if not candidates:
            continue
        accepted, reason = _accept_occurrences(candidates)
        if reason is not None:
            rejected.append({"asr_index": asr_index, "reason": reason, "candidates": candidates})
            continue
        qwen_chars = _qwen_chars(segment)
        cuts = [_boundary_between(qwen_chars, left["last_ms"], right["first_ms"])
                for left, right in zip(accepted, accepted[1:])]
        seg_start, seg_end = int(segment.get("start_ms", 0)), int(segment.get("end_ms", 0))
        edges = [seg_start] + [c["boundary_ms"] for c in cuts] + [seg_end]
        proposals.append({
            "asr_index": asr_index,
            "segment_start_ms": seg_start,
            "segment_end_ms": seg_end,
            "segment_text": str(segment.get("text", "")),
            "occurrences": accepted,
            "cuts": cuts,
            "pseudo_segments": [
                {"start_ms": edges[i], "end_ms": edges[i + 1],
                 "canonical_text": accepted[i]["canonical_text"],
                 "lyric_text": accepted[i]["lyric_text"],
                 "strength": accepted[i]["strength"],
                 "anchor_count": accepted[i]["anchor_count"],
                 "candidate_lyric_indexes": accepted[i]["candidate_lyric_indexes"]}
                for i in range(len(accepted))
            ],
        })
    return {
        "proposals": proposals,
        "rejected": rejected,
        "proposed_segment_count": len(proposals),
        "proposed_cut_count": sum(len(p["cuts"]) for p in proposals),
        "occurrence_count": sum(len(v) for v in occurrences.values()),
        "bridge_used_count": sum(1 for p in proposals for o in p["occurrences"]
                                 if o["strength"] == "bridge"),
    }


def format_report(result: dict[str, Any], asr_segments: list[dict[str, Any]]) -> str:
    def fmt(ms: Any) -> str:
        ms = int(ms or 0)
        sign = "-" if ms < 0 else ""
        ms = abs(ms)
        return "%s%d:%05.2f" % (sign, ms // 60000, (ms % 60000) / 1000.0)

    lines = ["可切分段落=%d 切点总数=%d 出现总数=%d 其中短句桥接=%d" % (
        result["proposed_segment_count"], result["proposed_cut_count"],
        result["occurrence_count"], result["bridge_used_count"]), ""]
    for p in result["proposals"]:
        lines.append("asr[%d] %s->%s (%.1fs, %d字) %s" % (
            p["asr_index"], fmt(p["segment_start_ms"]), fmt(p["segment_end_ms"]),
            (p["segment_end_ms"] - p["segment_start_ms"]) / 1000.0,
            len(p["segment_text"]), p["segment_text"][:44]))
        for i, ps in enumerate(p["pseudo_segments"]):
            occurrence = p["occurrences"][i]
            lines.append("    伪段%d %s->%s  [%s] (%s, %d锚点, cov=%.2f, 候选行%s)" % (
                i + 1, fmt(ps["start_ms"]), fmt(ps["end_ms"]), ps["lyric_text"],
                ps["strength"], ps["anchor_count"], occurrence["coverage"],
                ps["candidate_lyric_indexes"][:4]))
            if i < len(p["cuts"]):
                c = p["cuts"][i]
                lines.append("      切点 %s (%s, 间隔%dms)" % (fmt(c["boundary_ms"]), c["method"], c["gap_ms"]))
    if result["rejected"]:
        lines.append("")
        lines.append("未提出切分的段落:")
        for r in result["rejected"][:15]:
            seg = asr_segments[r["asr_index"]] if r["asr_index"] < len(asr_segments) else {}
            texts = "/".join(o["lyric_text"][:8] for o in r["candidates"][:3])
            lines.append("  asr[%-2d] %s->%s -- %s (出现%d处: %s)" % (
                r["asr_index"], fmt(seg.get("start_ms")), fmt(seg.get("end_ms")),
                r["reason"], len(r["candidates"]), texts))
    return "\n".join(lines)


def main() -> None:
    """python segment_resplit_diagnostic.py <job_id> -- read-only, writes nothing back."""
    import asyncio
    import json
    import sys
    import urllib.request

    sys.path.insert(0, "/app")
    from app import collect_standard_timeline_candidates
    from standard_timeline import choose_best_timeline_candidate

    jid = sys.argv[1]
    api = "http://127.0.0.1:8000"

    async def run() -> None:
        job = json.load(urllib.request.urlopen(f"{api}/api/jobs/{jid}", timeout=30))
        al = job.get("alignment") or {}
        asr = al.get("asr_segments") or []
        tm = al.get("timeline_match") or {}
        scored = await collect_standard_timeline_candidates({**job, "id": jid}, asr, {})
        if not scored:
            print("没有候选歌词")
            return
        chosen = next((i for i in scored if i["candidate"]["candidate_id"] == tm.get("candidate_id")), None)
        if chosen is None or not chosen["timed"]:
            print("job 尚未提交最终候选，改用本地重新评分选出的最佳候选")
            chosen = choose_best_timeline_candidate(scored)
            if not chosen["timed"]:
                print("最佳候选是纯行级，无逐字数据")
                return
        result = resplit_diagnostic(chosen["timed"], asr)
        print(format_report(result, asr))

    asyncio.run(run())


if __name__ == "__main__":
    main()
