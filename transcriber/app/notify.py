from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


AUTOMATION_NOTIFICATION_TITLES = {
    "asr_started": "Folia 自动流程开始 ASR",
    "asr_completed": "Folia 自动流程 ASR 结果已生成",
    "clips_completed": "Folia 自动流程切片完成",
    "outputs_completed": "Folia 自动流程成品处理完成",
}


def automation_notification(payload: dict[str, object]) -> tuple[str, str]:
    """Format a bounded, human-readable automatic pipeline notification."""
    event = str(payload.get("event", ""))
    if event not in AUTOMATION_NOTIFICATION_TITLES:
        raise ValueError("未知自动流程通知类型")
    broadcaster = str(payload.get("broadcaster") or "未知主播")[:100]
    recording = str(payload.get("recording") or "未知录播")[:200]
    lines = [f"主播：{broadcaster}", f"录播：{recording}"]
    if event == "asr_started":
        lines.append("ASR：已开始（整场固定分块，不使用 VAD）")
    elif event == "asr_completed":
        lines.append(f"逐句结果：已生成，共 {int(payload.get('segment_count') or 0)} 条")
    elif event == "clips_completed":
        lines.append(
            f"切片：成功 {int(payload.get('completed_count') or 0)}，失败 {int(payload.get('failed_count') or 0)}"
        )
        clips = [str(item)[:120] for item in (payload.get("clips") or []) if str(item).strip()][:12]
        if clips:
            lines.append("文件：" + "、".join(clips))
    else:
        completed_count = int(payload.get("completed_count") or 0)
        failed_count = int(payload.get("failed_count") or 0)
        skipped_count = int(payload.get("skipped_count") or 0)
        lines.append(
            f"成品：成功 {completed_count}，失败 {failed_count}，跳过 {skipped_count}"
        )
        outputs = [str(item)[:160] for item in (payload.get("outputs") or []) if str(item).strip()][:12]
        if outputs:
            lines.append("文件：" + "、".join(outputs))
        deepseek_titles = [str(item)[:100] for item in (payload.get("deepseek_titles") or []) if str(item).strip()][:12]
        if deepseek_titles:
            lines.append(f"DeepSeek 版（{len(deepseek_titles)} 首，本地对齐置信度不足，已用 AI 辅助对齐）：" + "、".join(deepseek_titles))
        local_titles = [str(item)[:100] for item in (payload.get("local_titles") or []) if str(item).strip()][:12]
        if local_titles:
            lines.append(f"本地对齐版（{len(local_titles)} 首，本地判定置信度不足，但 AI 全曲重排当前已关闭）：" + "、".join(local_titles))
        suspicious_identity_titles = [str(item)[:100] for item in (payload.get("suspicious_identity_titles") or []) if str(item).strip()][:12]
        if suspicious_identity_titles:
            lines.append(f"⚠️歌曲身份可疑（{len(suspicious_identity_titles)} 首，指纹识别结果和歌词证据对不上，文件名/歌名可能是错的，建议人工核实）：" + "、".join(suspicious_identity_titles))
        short_clip_titles = [str(item)[:100] for item in (payload.get("short_clip_titles") or []) if str(item).strip()][:12]
        if short_clip_titles:
            lines.append(f"跳过（切片时长过短，{len(short_clip_titles)} 首）：" + "、".join(short_clip_titles))
    output_path = str(payload.get("output_path") or "").strip()
    if output_path:
        lines.append(f"输出目录：{output_path[:500]}")
    return AUTOMATION_NOTIFICATION_TITLES[event], "\n".join(lines)


def notify_wecom(title: str, content: str) -> None:
    """Best-effort 企业微信机器人通知；未配置或发送失败不影响任务结果。"""
    url = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
    if not url:
        return
    payload = json.dumps(
        {"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        request = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=8) as response:
            response.read(256)
    except Exception:
        # 通知是附加能力，网络故障不能改变 ASR 任务状态。
        return
