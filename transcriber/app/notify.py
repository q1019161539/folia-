from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen


AUTOMATION_NOTIFICATION_TITLES = {
    "asr_started": "🎙 Folia 开始转写",
    "asr_completed": "✅ Folia 转写完成",
    "clips_completed": "✂️ Folia 切片完成",
    "render_queue_waiting": "⏳ Folia 渲染排队中",
    "outputs_completed": "🎬 Folia 成片处理完成",
}

# Sent as plain text, not markdown: a text message is readable in ordinary
# WeChat, while markdown only renders inside the WeCom app. So the structure has
# to come from ordering, blank lines, numbering and emoji rather than from bold
# or colour.
MAX_NOTIFICATION_BYTES = 1800

BEIJING = timezone(timedelta(hours=8))

# Wording lives here; the thresholds that decide when each code applies live in
# the backend's quality assessment. Adjusting a threshold must not mean editing
# a notification template.
REASON_TEXT = {
    "song_identity_suspicious": "歌曲身份可疑：识别结果和歌词证据对不上",
    "timing_model_conflict": "字幕时间轴存在冲突，建议先看有没有闪句、重叠",
    "weak_anchor_evidence": "时间轴证据偏弱：可对上的地方少",
    "anchor_consistency_poor": "时间轴一致性较差：各处对齐结果不统一",
    "line_timing_only": "这份歌词只有整行时间，没有逐字时间",
    "render_failed": "成片生成失败",
    "clip_too_short": "切片时长过短，已跳过",
}


def _clip(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _minutes(seconds: float) -> str:
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分钟"
    hours, rest = divmod(seconds, 3600)
    return f"{hours} 小时 {rest // 60} 分" if rest >= 60 else f"{hours} 小时"


def _eta_line(label: str, eta: object) -> str:
    """A range of clock times, never a single moment: the spread between a
    typical run and a slow one is real, and a single figure reads as a promise.
    With too little history the estimate says so instead of inventing one."""
    if not isinstance(eta, dict):
        return ""
    if not eta.get("reliable"):
        return f"{label}：历史样本不足，暂时估不准"
    now = datetime.now(BEIJING)
    low = (now + timedelta(seconds=int(eta.get("low_seconds") or 0))).strftime("%H:%M")
    high = (now + timedelta(seconds=int(eta.get("high_seconds") or 0))).strftime("%H:%M")
    return f"{label}：约 {low}～{high}" if low != high else f"{label}：约 {low}"


def _reason_line(reason: dict[str, object]) -> str:
    code = str(reason.get("code") or "")
    text = REASON_TEXT.get(code, code)
    facts = reason.get("facts") if isinstance(reason.get("facts"), dict) else {}
    if code == "song_identity_suspicious" and facts:
        heard, lyric = facts.get("primary_title"), facts.get("lyric_title")
        if heard and lyric:
            extra = f"识别为《{_clip(heard, 40)}》，歌词更像《{_clip(lyric, 40)}》"
            return f"{text}\n  {extra}"
    if code == "timing_model_conflict" and facts.get("model_delta_ms"):
        seconds = int(facts["model_delta_ms"]) / 1000.0
        return f"{text}\n  两套时间轴结果相差约 {seconds:.1f} 秒"
    if code == "weak_anchor_evidence" and facts:
        count = int(facts.get("anchor_count") or 0)
        span = int(facts.get("anchor_span_ms") or 0) // 1000
        return f"{text}\n  仅 {count} 处可靠对应，覆盖约 {span} 秒"
    return text


def _song_block(index: int, song: dict[str, object]) -> list[str]:
    """One song, and at most the single worst thing found about it. Printing
    every diagnostic would bury the songs that actually need opening."""
    block = [f"{index}.《{_clip(song.get('title'), 60) or '未命名'}》"]
    reasons = [r for r in (song.get("review_reasons") or []) if isinstance(r, dict)]
    if reasons:
        block.extend("  " + line.strip() for line in _reason_line(reasons[0]).split("\n"))
    return block


def _outputs_body(payload: dict[str, object]) -> list[list[str]]:
    """Blocks in descending order of how much they matter, so that trimming from
    the end never removes a problem the reader needs to act on."""
    songs = [s for s in (payload.get("songs") or []) if isinstance(s, dict)]
    critical = [s for s in songs if s.get("review_level") == "critical"]
    warning = [s for s in songs if s.get("review_level") == "warning"]
    normal = [s for s in songs if s.get("review_level") not in ("critical", "warning")
              and s.get("state") == "completed"]
    missing = [s for s in songs if s.get("state") in ("failed", "skipped")]

    completed = int(payload.get("completed_count") or 0)
    failed = int(payload.get("failed_count") or 0)
    skipped = int(payload.get("skipped_count") or 0)
    head = [
        f"主播：{_clip(payload.get('broadcaster'), 60) or '未知主播'}",
        f"录播：{_clip(payload.get('recording'), 120) or '未知录播'}",
        f"结果：成功 {completed}｜失败 {failed}｜跳过 {skipped}",
    ]
    if critical or warning:
        head.append(f"需要看的：🔴 {len(critical)}｜🟡 {len(warning)}｜✅ {len(normal)}")
    elapsed = payload.get("elapsed_seconds")
    if elapsed:
        head.append(f"总耗时：{_minutes(float(elapsed))}")
    waited = float(payload.get("render_wait_seconds") or 0)
    if waited >= 60:
        head.append(f"其中渲染排队：{_minutes(waited)}")

    blocks = [head]
    if critical:
        block = [f"🔴 优先检查 {len(critical)} 首"]
        for i, song in enumerate(critical, 1):
            block.extend(_song_block(i, song))
        blocks.append(block)
    if warning:
        block = [f"🟡 建议抽查 {len(warning)} 首"]
        for i, song in enumerate(warning[:3], 1):
            block.extend(_song_block(i, song))
        rest = warning[3:]
        if rest:
            block.append("另有 %d 首：%s" % (
                len(rest), "、".join(_clip(s.get("title"), 40) for s in rest)))
        blocks.append(block)
    if missing:
        block = [f"⏭ 未产出 {len(missing)} 首"]
        for song in missing:
            reason = REASON_TEXT.get(str(song.get("reason") or ""), _clip(song.get("reason"), 60))
            block.append(f"《{_clip(song.get('title'), 50)}》：{reason or '未说明原因'}")
        blocks.append(block)
    if normal:
        blocks.append([f"✅ 其余 {len(normal)} 首未发现明显风险"])
    if not songs and not completed and not failed and not skipped:
        # A recording with no singing in it used to end in silence: the pipeline
        # returned early and this message was never sent, so the reader saw
        # "transcribing started", "transcribing done", and then nothing at all --
        # indistinguishable from a run that hung.
        blocks.append(["🔇 本场未检出歌曲，没有需要查看的成片"])
    output_path = _clip(payload.get("output_path"), 400)
    if output_path:
        blocks.append([f"📁 {output_path}"])
    return blocks


def _fit(blocks: list[list[str]], limit: int) -> str:
    """Drop whole blocks from the least important end until it fits.

    Never a blind slice of the finished string: the output directory and the
    reasons a song failed sit at the end, and those are exactly what the reader
    needs. Blocks are ordered by importance, and the last optional one goes
    first. Measured in UTF-8 bytes, since the text is Chinese.
    """
    kept = list(blocks)
    # The head and the 🔴 block are never dropped; the directory line is pinned
    # to the end because it is what the reader opens.
    pinned_tail = kept.pop() if kept and kept[-1] and kept[-1][0].startswith("📁") else None
    while True:
        parts = kept + ([pinned_tail] if pinned_tail else [])
        text = "\n\n".join("\n".join(block) for block in parts)
        if len(text.encode("utf-8")) <= limit or len(kept) <= 2:
            return text
        kept.pop()


def automation_notification(payload: dict[str, object]) -> tuple[str, str]:
    """Format a bounded, plain-text notification for one pipeline stage."""
    event = str(payload.get("event", ""))
    if event not in AUTOMATION_NOTIFICATION_TITLES:
        raise ValueError("未知自动流程通知类型")
    broadcaster = _clip(payload.get("broadcaster"), 100) or "未知主播"
    recording = _clip(payload.get("recording"), 200) or "未知录播"

    if event == "outputs_completed":
        return AUTOMATION_NOTIFICATION_TITLES[event], _fit(
            _outputs_body(payload), MAX_NOTIFICATION_BYTES)

    lines = [f"主播：{broadcaster}", f"录播：{recording}"]
    if event == "asr_started":
        duration = payload.get("audio_duration_sec")
        if duration:
            lines.append(f"录播时长：{_minutes(float(duration))}")
        eta = _eta_line("预计转写完成", payload.get("asr_eta"))
        if eta:
            lines.append(eta)
    elif event == "asr_completed":
        lines.append(f"逐句结果：{int(payload.get('segment_count') or 0)} 条")
        elapsed = payload.get("elapsed_seconds")
        if elapsed:
            lines.append(f"转写耗时：{_minutes(float(elapsed))}")
    elif event == "clips_completed":
        lines.append(
            f"切片：成功 {int(payload.get('completed_count') or 0)}"
            f"，失败 {int(payload.get('failed_count') or 0)}"
        )
        elapsed = payload.get("elapsed_seconds")
        if elapsed:
            lines.append(f"切片耗时：{_minutes(float(elapsed))}")
        failed = [_clip(item, 60) for item in (payload.get("failed_titles") or []) if _clip(item, 60)]
        if failed:
            lines.append("失败：" + "、".join(failed[:8]))
        eta = _eta_line("预计全部完成", payload.get("songs_eta"))
        if eta:
            lines.append(eta + ("（渲染排队会顺延）" if "约" in eta else ""))
    elif event == "render_queue_waiting":
        done = int(payload.get("completed_count") or 0)
        total = int(payload.get("total_count") or 0)
        lines.append(f"进度：已完成 {done} / {total} 首")
        title = _clip(payload.get("song_title"), 60)
        if title:
            lines.append(f"《{title}》已就绪，正在等待渲染资源")
        lines.append(f"已等待：{_minutes(float(payload.get('wait_seconds') or 0))}")
        lines.append("前面还有其他渲染在跑，流程没有卡住。")

    output_path = _clip(payload.get("output_path"), 400)
    if output_path and event != "render_queue_waiting":
        lines.append(f"📁 {output_path}")
    return AUTOMATION_NOTIFICATION_TITLES[event], "\n".join(lines)


def notify_wecom(title: str, content: str) -> dict[str, object]:
    """发送企业微信机器人通知，并返回可观测的投递结果。"""
    url = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
    if not url:
        return {"ok": False, "status": "not_configured", "attempts": 0}
    payload = json.dumps(
        {"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
        ensure_ascii=False,
    ).encode("utf-8")
    last_error = "unknown error"
    for attempt in range(1, 4):
        try:
            request = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=8) as response:
                result = json.loads(response.read(1024).decode("utf-8"))
            if result.get("errcode") == 0:
                return {"ok": True, "status": "sent", "attempts": attempt}
            last_error = f"WeCom errcode={result.get('errcode')}: {result.get('errmsg', '')}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < 3:
            time.sleep(attempt)
    # 通知是附加能力，投递失败不能改变 ASR 任务状态；调用方负责记录结果。
    return {"ok": False, "status": "failed", "attempts": 3, "error": last_error}
