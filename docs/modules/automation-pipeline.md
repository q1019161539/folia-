# 主播录播自动流水线

## 入口与边界

- 页面第四工作区“自动流水线”；前端为 `web/automation.js`。
- 编排、SQLite 状态和 API 位于 `backend/app.py`，纯校验和时间投影位于 `backend/automation.py`。
- 主播规则默认停用；启用时先把所有现有合格 MP4 记为基线，只处理之后新增的文件。
- 主播选择由 `GET /api/automation/broadcasters` 动态读取录播根目录下的一级目录；页面使用下拉框，主播名称直接采用目录名。页面打开时读取一次，目录变化后由用户点击“刷新名单”，不做 5 秒轮询。
- 已锁定的主播可以通过“手动执行以前的录播”选择历史 MP4。历史文件不受“启用时只监听未来新增文件”的基线限制，也不受自动监听的 1 GiB 门槛限制，但仍必须位于该主播目录、不是 `歌曲切片/`、不是 partial 文件且通过 `ffprobe`。手动任务复用完全相同的串行流水线；同一文件已有活动任务时拒绝重复加入，已结束任务允许再次手动执行。
- 只接收 `.mp4`、至少 1 GiB、连续两次扫描大小不变且 `ffprobe` 成功的录播；永远排除 `歌曲切片/`。

## 串行流程

1. 每 30 秒扫描所有已启用主播目录，并把新录播写入 `automation_runs`。
2. 调用 `folia-video-transcriber` 完成整场本地 ASR 和 Qwen ForcedAligner；自动任务固定设置 `no_vad=true`，整场音频按 180 秒块顺序送入 ASR，避免语音 VAD 把轻声、拖长音或伴奏中的歌声当成非语音跳过。人声分离关闭，源时间 offset 保持不变。逐句文件保留原始字时间，并另存 `transcript_words.jsonl`。转录工作台的手动任务仍保留 VAD 选项。
3. 将逐句转录交给 DeepSeek V4 Flash。模型只能返回歌名与首尾 ASR `segment_id`；后端根据真实句段计算时间，低于规则阈值、重叠、过短、过长或无效 ID 均跳过。
   - 校验后的结果在切片前同时发布到 ASR 的录播名目录：`<录播名>_歌曲分析.json` 保存毫秒时间、segment ID、置信度、理由和未采用候选；`<录播名>_歌曲时间轴.txt` 是可读时间轴。两者用于人工审阅，实际切片仍读取同一份已校验数据写入的数据库批次，避免手工文件被篡改后绕过校验。
4. 使用 FFmpeg 流复制把完整歌曲写入原录播同级 `歌曲切片/`，默认前后 5 秒，不覆盖同名文件。自动模式不使用 `-avoid_negative_ts make_zero`，保留隐藏关键帧预卷，使可见起点对应请求时间。
5. 将整场 ASR 句段减去切片起点后导入歌曲项目，不重复运行 Whisper。切片时长低于 90 秒直接跳过整套歌词渲染流程（状态 `lyrics_skipped_short_clip`），计入结束时的汇总通知，不搜索候选、不补逐字 ASR、不渲染。
6. 每首依次执行 LDDC 多源标准时间轴匹配、Qwen 现场字与平台逐字融合和完整渲染，详见 `docs/modules/asr-alignment.md` 的"标准歌词时间轴模式"一节（逐字 ASR 前置、行级/逐字级置信度或门、AI 选歌校验+全曲重排的多级补救链）。零锚点候选不再直接跳过，也会送进补救链；只有连候选都搜不到或补救链跑完仍建不出时间轴才是真正的失败。**不再有"低置信照常出片"这一说**：本地够格直接判高置信，AI 帮忙对齐了时间轴（不管本地原本是高是低置信）就归入 `DeepSeek 版`，渲染输出目录第二级相应命名为 `高置信`/`DeepSeek版`（替代旧的 `低置信`，旧目录和历史文件不删除）。已有整场 Qwen 字时间时不为切片重复加载模型。

所有主播共享一个后台执行队列，避免 Whisper、Qwen 和渲染同时占用内存。一首失败不会阻止同录播中的其他歌曲。

## 企业微信通知

自动任务复用转录服务 `.env` 中已有的 `WECOM_WEBHOOK_URL`，在四个阶段发送纯文字通知：开始整场 ASR、逐句 ASR 结果生成、歌曲切片批次完成、全部成品输出成功。正文包含主播目录名、录播文件名、结果数量和相应输出目录；切片及成品通知还列出成功文件。最终成功通知只在本场所有歌曲都完成歌词时间轴、逐字和渲染且确有输出文件时发送，存在跳过或失败歌曲时不发送。自动任务关闭转录服务原有的通用 ASR 完成通知，避免同一阶段重复发送。通知发送为 best-effort，Webhook 未配置或临时失败不会改变流水线任务状态。普通转录工作台仍保留原来的 ASR 完成/失败通知。

2026-09-15 起，最后一条"全部成品输出成功"汇总通知（`outputs_completed`）额外列出两类歌曲，不新增独立的通知事件类型：`DeepSeek 版（N 首）：<歌名列表>`（本地判定低置信、经 AI 辅助对齐时间轴后仍正常渲染的歌曲）、`跳过（切片时长过短，N 首）：<歌名列表>`（低于 90 秒被跳过的切片）。两行只在对应列表非空时输出。`transcriber/app/notify.py` 的 `AUTOMATION_NOTIFICATION_TITLES` 事件白名单未新增条目，只是扩展了 `outputs_completed` 分支的文案。手动单曲项目（不经过自动流水线）不涉及这条汇总通知，结果直接体现在项目状态和 `alignment.timeline_match.confidence_tier` 字段上。

## API 与状态

- `GET/POST /api/automation/profiles`
- `GET /api/automation/broadcasters`
- `GET /api/automation/profiles/{id}/recordings`
- `POST /api/automation/profiles/{id}/run`
- `PUT /api/automation/profiles/{id}`
- `POST /api/automation/profiles/{id}/enable|disable`
- `GET /api/automation/runs`、`GET /api/automation/runs/{id}`
- `POST /api/automation/runs/{id}/cancel|retry`

SQLite 表：`automation_profiles`、`automation_seen`、`automation_runs`。运行记录保存转录服务任务 ID、转录、歌曲子任务、视频工坊项目 ID 和输出链接。重试复用已经完成的转录、切片和项目；若切片完成后的路径交接曾中断，会从原批次恢复内部路径而不重复切片。公开切片响应只在数据副本中移除内部路径，不能修改后台继续处理所需的原批次对象。自动任务的新 ASR 与 ASR 阶段续跑都保持 `no_vad=true`。整场 ASR 每完成一块即更新 `asr_chunks.json`，相同无 VAD 分块可跳过已完成块，全部 ASR 块完成后则只重新执行 align。启动本地整场 ASR 前还会让 `folia-video-ai` 释放闲置 Qwen 模型，避免跨容器内存叠加。

## 安全配置

`DEEPSEEK_API_KEY` 只能放 `.env`。页面和 API 只返回是否已配置及模型名，不返回 Key。默认模型为 `deepseek-v4-flash`，默认地址为 `https://api.deepseek.com`。

## 最低验证

```bash
python -m py_compile backend/app.py backend/automation.py
python -m unittest discover -s backend -p "test_*.py"
node --check web/automation.js
node --check web/clips.js
docker compose config
```

上线后确认所有规则默认停用；创建测试规则时应先验证现有 MP4 全部进入基线且不产生自动任务。不得为了测试复制或修改原录播。
