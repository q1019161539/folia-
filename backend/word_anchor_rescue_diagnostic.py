"""Diagnostic only -- changes no production alignment, no final subtitles.

Measures how much real Qwen word-level timing evidence sits on ASR segments
that never won a *line-level* anchor at all (never made it into core_chain or
evidence_chain), because word_timeline.score_provider_timeline only ever calls
_line_word_anchors for (lyric_index, asr_index) pairs that evidence_chain
already picked.

Real motivating case (job a6293206..., 云汐/姜姜《离人赋》): a chorus was sung
2-3 times. ASR recognized each repetition with similar (mediocre) accuracy, but
the whole-string line-level text score only cleared the matching threshold for
the *second* repetition -- 54 of 57 lyric lines ended up with zero anchor at
all, forcing the whole song onto one flat shift. This brute-forces every
(lyric_index, asr_index) pair -- cheap at the sizes this pipeline actually sees
(tens of lines x tens of segments) -- and reports, per currently-unanchored
line, whether word-level character matching can find it anyway, and whether it
finds it in one place or several (a repeated occurrence).

See the module's classification fields for exactly what "recoverable" means:
this does NOT decide which occurrence is correct when there is more than one --
distinguishing a real repeat from a mismatch needs the neighboring lines'
already-trusted times as bounds, which is a production-code decision, not a
diagnostic one. This only counts and locates the candidates.
"""
from __future__ import annotations

import statistics
from typing import Any

from standard_timeline import _content_score, mad_ms
from word_timeline import _line_word_anchors

# word_timeline's own bar for "this ASR segment already paired with this lyric
# line vouches for itself" -- fine there because the pair was already chosen by
# the line-level chain, so 2 matching characters are corroborating, not the
# only evidence. Kept here only as a reference constant, not used for gating.
MIN_EXACT_FOR_KNOWN_PAIR = 2

# This diagnostic instead brute-forces EVERY (lyric_index, asr_index) pair with
# no line-level chain to narrow the search first, so a bar of 2 lets common
# Chinese characters (的/你/我/是/一) coincidentally "match" almost anywhere --
# see test_two_incidental_shared_characters_can_pass_the_lenient_occurrence_bar
# for a real example. Real rescues need both enough matched characters AND
# those characters covering a real fraction of the lyric line, not just its
# absolute count -- a lyric_coverage floor is what actually tells corroborating
# and coincidental matches apart at this bar. Thresholds per ChatGPT review
# (2026-09), based on the real 离人赋 job's genuine rescues (e.g. word_anchor=8,
# text_score=0.41) vs its noise (word_anchor=2, from unrelated text); pending
# validation against more songs (heavy-chorus, oversized-segment, poor-ASR
# categories) before any of this feeds a production decision.
MIN_WORD_ANCHORS_FOR_RESCUE_SEARCH = 5
MIN_LYRIC_COVERAGE_FOR_RESCUE_SEARCH = 0.35
OCCURRENCE_GAP_MS = 5000  # hits within this of each other count as the same singing moment


def _valid_lyric_char_count(text: str) -> int:
    """Letters/CJK ideographs only -- punctuation and whitespace don't carry
    matchable identity, so they shouldn't dilute or inflate coverage."""
    return sum(1 for ch in text if ch.isalnum())


def _classify_tier(word_anchor_count: int, lyric_coverage: float, text_score: float) -> str | None:
    """Three confidence tiers over the same base rule (anchor_count>=5 AND
    coverage>=0.35); text_score corroborates but is never a hard gate, since a
    genuine rescue can sit inside a long merged ASR segment whose whole-segment
    text score is diluted by lines it doesn't belong to. WORD_ONLY is kept, not
    discarded -- that dilution is exactly the case it exists to catch."""
    if word_anchor_count >= 6 and lyric_coverage >= 0.40 and text_score >= 0.30:
        return "strong"
    if word_anchor_count >= 5 and lyric_coverage >= 0.35 and text_score >= 0.20:
        return "good"
    if word_anchor_count >= MIN_WORD_ANCHORS_FOR_RESCUE_SEARCH and lyric_coverage >= MIN_LYRIC_COVERAGE_FOR_RESCUE_SEARCH:
        return "word_only"
    return None


def _cluster_occurrences(points: list[tuple[int, dict[str, Any]]], gap_ms: int = OCCURRENCE_GAP_MS) -> list[list[dict[str, Any]]]:
    """Group timestamped hits into occurrences. Same idea as word_timeline's
    _dominant_line_cluster, but returns *every* cluster, not just the largest --
    here the question is how many distinct singing moments a line's evidence
    points at, not which one should win a vote.
    """
    ordered = sorted(points, key=lambda item: item[0])
    clusters: list[list[tuple[int, dict[str, Any]]]] = []
    for time_ms, hit in ordered:
        if clusters and time_ms - clusters[-1][-1][0] <= gap_ms:
            clusters[-1].append((time_ms, hit))
        else:
            clusters.append([(time_ms, hit)])
    return [[hit for _, hit in cluster] for cluster in clusters]


def rescue_diagnostic(
    timed_rows: list[dict[str, Any]],
    asr_segments: list[dict[str, Any]],
    shift_ms: int,
    core_pairs: set[tuple[int, int]],
    evidence_pairs: set[tuple[int, int]],
) -> dict[str, Any]:
    """timed_rows plays both roles score_provider_timeline itself needs: each
    row's own text/start_ms for the line-level text score and expected time,
    and its words[] (when the candidate is verbatim) for word-level matching.
    A line-only candidate has no words[] at all, so every word_anchor_count
    here is correctly 0 -- there is nothing to rescue for it.
    """
    rows: list[dict[str, Any]] = []
    hits_by_line: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for lyric_index, row in enumerate(timed_rows):
        lyric_text = str(row.get("text", ""))
        expected_ms = int(row.get("start_ms", 0)) + shift_ms
        valid_lyric_chars = _valid_lyric_char_count(lyric_text)
        for asr_index, segment in enumerate(asr_segments):
            asr_text = str(segment.get("text", ""))
            text_score, _ = _content_score(asr_text, lyric_text)
            exact = [a for a in _line_word_anchors(lyric_index, asr_index, row, segment) if a["kind"] == "exact"]
            word_anchor_count = len(exact)
            lyric_coverage = round(word_anchor_count / valid_lyric_chars, 4) if valid_lyric_chars else 0.0
            tier = _classify_tier(word_anchor_count, lyric_coverage, text_score)
            record: dict[str, Any] = {
                "lyric_index": lyric_index,
                "lyric_text": lyric_text,
                "expected_ms": expected_ms,
                "asr_index": asr_index,
                "asr_start_ms": segment.get("start_ms"),
                "asr_end_ms": segment.get("end_ms"),
                "line_text_score": round(text_score, 4),
                "in_potentials": text_score > 0,
                "in_core_chain": (lyric_index, asr_index) in core_pairs,
                "in_evidence_chain": (lyric_index, asr_index) in evidence_pairs,
                "word_anchor_count": word_anchor_count,
                "lyric_coverage": lyric_coverage,
                "tier": tier,
            }
            if tier is not None:
                deltas = [a["qwen_start_ms"] - a["provider_start_ms"] for a in exact]
                occurrence_time_ms = round(statistics.median(a["qwen_start_ms"] for a in exact))
                record.update(
                    word_delta_ms=round(statistics.median(deltas)),
                    word_mad_ms=mad_ms(deltas),
                    occurrence_time_ms=occurrence_time_ms,
                    distance_from_expected_ms=abs(occurrence_time_ms - expected_ms),
                )
                hits_by_line.setdefault(lyric_index, []).append((occurrence_time_ms, record))
            # Keep the printed table to a manageable size: only pairs with some
            # signal at all, either level. Zero-signal pairs (the vast majority
            # of the lines x segments grid) are true negatives, not interesting.
            if text_score > 0 or tier is not None:
                rows.append(record)

    unanchored_lines = 0
    recoverable_unanchored_lines = 0
    multi_occurrence_lines = 0
    ambiguous_occurrence_lines = 0
    tier_counts = {"strong": 0, "good": 0, "word_only": 0}
    per_line_summary: dict[int, dict[str, Any]] = {}
    for lyric_index in range(len(timed_rows)):
        already_anchored = any(
            (lyric_index, asr_index) in core_pairs or (lyric_index, asr_index) in evidence_pairs
            for asr_index in range(len(asr_segments))
        )
        if already_anchored:
            continue
        unanchored_lines += 1
        clusters = _cluster_occurrences(hits_by_line.get(lyric_index, []))
        if len(clusters) == 1:
            recoverable_unanchored_lines += 1
            status = "recoverable"
        elif len(clusters) >= 2:
            multi_occurrence_lines += 1
            # Ambiguous unless exactly one cluster sits far closer to the expected
            # time than any other -- a real production disambiguator additionally
            # needs neighboring-line bounds (see module docstring); this diagnostic
            # only flags the ones a distance-to-expected check alone can't settle.
            distances = sorted(
                min(abs(hit["occurrence_time_ms"] - hit["expected_ms"]) for hit in cluster)
                for cluster in clusters
            )
            if len(distances) < 2 or distances[1] - distances[0] < OCCURRENCE_GAP_MS:
                ambiguous_occurrence_lines += 1
                status = "ambiguous_multi_occurrence"
            else:
                status = "multi_occurrence_resolvable"
        else:
            status = "not_recoverable"
        best_tier = None
        for _, hit in hits_by_line.get(lyric_index, []):
            if hit["tier"] and (best_tier is None or ["word_only", "good", "strong"].index(hit["tier"]) > ["word_only", "good", "strong"].index(best_tier)):
                best_tier = hit["tier"]
        if best_tier:
            tier_counts[best_tier] += 1
        per_line_summary[lyric_index] = {"status": status, "occurrence_count": len(clusters), "best_tier": best_tier}

    return {
        "rows": rows,
        "per_line_summary": per_line_summary,
        "unanchored_lines": unanchored_lines,
        "recoverable_unanchored_lines": recoverable_unanchored_lines,
        "multi_occurrence_lines": multi_occurrence_lines,
        "ambiguous_occurrence_lines": ambiguous_occurrence_lines,
        "tier_counts": tier_counts,
    }


def format_report(result: dict[str, Any], timed_rows: list[dict[str, Any]]) -> str:
    def fmt(ms: Any) -> str:
        ms = int(ms or 0)
        sign = "-" if ms < 0 else ""
        ms = abs(ms)
        return "%s%d:%05.2f" % (sign, ms // 60000, (ms % 60000) / 1000.0)

    tc = result.get("tier_counts", {})
    lines = [
        "总行数: %d | 未获得行级锚点: %d | 可字级回收(单一出现): %d | 多次出现: %d (其中歧义: %d)"
        % (
            len(timed_rows), result["unanchored_lines"], result["recoverable_unanchored_lines"],
            result["multi_occurrence_lines"], result["ambiguous_occurrence_lines"],
        ),
        "分级: STRONG=%d GOOD=%d WORD_ONLY=%d" % (tc.get("strong", 0), tc.get("good", 0), tc.get("word_only", 0)),
        "",
    ]
    by_line: dict[int, list[dict[str, Any]]] = {}
    for row in result["rows"]:
        by_line.setdefault(row["lyric_index"], []).append(row)
    for lyric_index in sorted(result["per_line_summary"]):
        summary = result["per_line_summary"][lyric_index]
        candidates = sorted(by_line.get(lyric_index, []), key=lambda r: r.get("word_anchor_count", 0), reverse=True)
        text = timed_rows[lyric_index].get("text", "") if lyric_index < len(timed_rows) else ""
        lines.append("行%d [%s] 预计=%s 状态=%s 出现次数=%d 最佳分级=%s" % (
            lyric_index, text, fmt(candidates[0]["expected_ms"]) if candidates else "?",
            summary["status"], summary["occurrence_count"], summary.get("best_tier") or "-",
        ))
        for c in candidates[:6]:
            marker = {"strong": "★★STRONG", "good": "★GOOD", "word_only": "☆WORD_ONLY"}.get(c["tier"], "·text" if c["in_potentials"] else "")
            occ = fmt(c["occurrence_time_ms"]) if "occurrence_time_ms" in c else "-"
            lines.append("    asr[%2d] %s->%s text_score=%.2f word_anchor=%d coverage=%.2f occurrence=%s %s" % (
                c["asr_index"], fmt(c["asr_start_ms"]), fmt(c["asr_end_ms"]),
                c["line_text_score"], c["word_anchor_count"], c.get("lyric_coverage", 0.0), occ, marker,
            ))
    return "\n".join(lines)


def main() -> None:
    """python word_anchor_rescue_diagnostic.py <job_id> -- run against a real job's
    already-selected candidate and current core/evidence anchors. Read-only: does
    not write anything back to the job."""
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
        chosen_id = tm.get("candidate_id")
        scored = await collect_standard_timeline_candidates({**job, "id": jid}, asr, {})
        chosen = next((item for item in scored if item["candidate"]["candidate_id"] == chosen_id), None)
        if chosen is not None and chosen["timed"]:
            result_meta = chosen["result"]
            core_pairs = {(int(a["lyric_index"]), int(a["asr_index"])) for a in (tm.get("core_anchors") or [])}
            evidence_pairs = {(int(a["lyric_index"]), int(a["asr_index"])) for a in (tm.get("evidence_anchors") or [])}
            shift_ms = int(tm.get("shift_ms") or 0)
        else:
            # The job hasn't committed a winner yet (mid-search, or a stale
            # progress record left over from an interrupted run) -- fall back to
            # picking the same way production itself would, purely for this
            # read-only diagnostic. Never writes anything back to the job.
            print("job 尚未提交最终候选（candidate_id=%r），改用本地重新评分选出的最佳候选" % chosen_id)
            if not scored:
                print("没有可评分的候选")
                return
            chosen = choose_best_timeline_candidate(scored)
            if not chosen["timed"]:
                print("本地选出的最佳候选没有逐字数据（纯行级），无法回收")
                return
            result_meta = chosen["result"]
            core_pairs = {(int(a["lyric_index"]), int(a["asr_index"])) for a in (result_meta.get("core_anchors") or [])}
            evidence_pairs = {(int(a["lyric_index"]), int(a["asr_index"])) for a in (result_meta.get("evidence_anchors") or [])}
            shift_ms = int(result_meta.get("shift_ms") or 0)
        timed_rows = chosen["timed"]
        result = rescue_diagnostic(timed_rows, asr, shift_ms, core_pairs, evidence_pairs)
        print(format_report(result, timed_rows))

    asyncio.run(run())


if __name__ == "__main__":
    main()
