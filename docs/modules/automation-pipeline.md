# 主播录播自动流水线

## 入口与边界

- 页面第四工作区“自动流水线”；前端为 `web/automation.js`。
- 编排、SQLite 状态和 API 位于 `backend/app.py`，纯校验和时间投影位于 `backend/automation.py`。
- 主播规则默认停用；保存规则时同时锁定投稿使用的主播显示名，并从 BililiveTool 实时读取视频投稿模板供选择。启用时先把所有现有合格 MP4 记为基线，只处理之后新增的文件。
- 主播选择由 `GET /api/automation/broadcasters` 合并媒体一级目录与录播机身份。主 API 只读挂载 bililive-tools 的 data 目录（含 SQLite WAL），从 `streamer` 和 `record_history` 按平台＋房间号关联录播目录，30 秒缓存；不写录播机配置或数据库。已有规则在唯一匹配时自动绑定，保存 `recorder_identity` 的房间号和历史目录。改名时显示最新录制目录名称，持续监听该身份的新旧目录；手动历史录播也合并查询。无记录或身份不明确的目录继续按目录监听，禁止用名字前缀猜身份。新发现目录中早于规则启用时间的文件进入基线，避免意外重跑历史。页面名单按房间号合并别名，显示绑定房间号；重复锁定同一身份拒绝创建。页面打开时读取一次，有新增时点击“刷新名单”。
- 自动流水线工作区首次打开时读取规则、任务、队列、主播目录及当前主播录播；切走再返回保留已有表单和列表，不重复扫描主播目录和历史录播。页面可见时仅每 15 秒后台刷新任务与队列；规则、主播名单及录播由对应刷新按钮或编辑动作更新。
- UI 的队列概览在桌面放在状态侧栏，手机放在任务列表最前；主播、规则、手动执行和任务记录在手机按单列页面滚动，任务记录默认显示前 10 条并可展开更多。此布局不改变首次加载、返回保留和后台刷新逻辑。
- 页面顶部的真实统计来自 `GET /api/automation/summary`：当前启用的主播规则数、按 NAS 上海日期计算的当日任务数和成功完成数、全局当前排队数。统计查询使用全部 SQLite 记录，不受最近任务列表的分页限制；无任务时显示 0 与空状态。桌面与歌词制作共用左侧导航，流水线主按钮和状态使用绿色。
- 主播选择、规则、当前队列与任务记录各为可折叠卡片。规则列表、任务列表和队列过长时在本卡片内部纵向滚动，标题及其他卡片不随之移动；切换工作区仍沿用首次加载和后台状态刷新行为。
- 已锁定的主播可以通过“手动执行以前的录播”选择历史 MP4。历史文件不受“启用时只监听未来新增文件”的基线限制，也不受自动监听的 1 GiB 门槛限制，但仍必须位于该主播目录、不是 `歌曲切片/`、不是 partial 文件且通过 `ffprobe`。手动任务复用完全相同的串行流水线；同一文件已有活动任务时拒绝重复加入，已结束任务允许再次手动执行。
- 只接收 `.mp4`、至少 1 GiB、连续两次扫描大小不变且 `ffprobe` 成功的录播；永远排除 `歌曲切片/`。

## 串行流程

1. 每 30 秒扫描所有已启用主播目录，并把新录播写入 `automation_runs`。
2. 调用 `folia-video-transcriber` 将整场音频按 180 秒块送入现有 Faster-Whisper worker；关闭语音 VAD 和逐字时间计算，直接取得块内逐句时间并加回源时间 offset。整场不运行 Qwen ForcedAligner，也不发布空的逐字文件。关闭 VAD 避免把歌声误删；转录工作台的手动任务保持原选项。
3. 将逐句转录交给 DeepSeek V4 Flash。模型只能返回歌名与首尾 ASR `segment_id`；后端根据真实句段计算时间，低于规则阈值、重叠、过短、过长或无效 ID 均跳过。
   - 校验后的结果在切片前同时发布到 ASR 的录播名目录：`<录播名>_歌曲分析.json` 保存毫秒时间、segment ID、置信度、理由和未采用候选；`<录播名>_歌曲时间轴.txt` 是可读时间轴。两者用于人工审阅，实际切片仍读取同一份已校验数据写入的数据库批次，避免手工文件被篡改后绕过校验。
4. 使用 FFmpeg 流复制把完整歌曲写入原录播同级 `歌曲切片/`，默认前后 5 秒，不覆盖同名文件。自动模式不使用 `-avoid_negative_ts make_zero`，保留隐藏关键帧预卷，使可见起点对应请求时间。
5. 将整场 ASR 句段减去切片起点后导入歌曲项目，不重复运行 Whisper。切片时长低于 90 秒直接跳过整套歌词渲染流程（状态 `lyrics_skipped_short_clip`），计入结束时的汇总通知，不搜索候选、不补逐字 ASR、不渲染。
6. 每首切片进入标准时间轴匹配时，仅对该歌曲片段补 Qwen 现场逐字时间，再用它与平台逐字歌词评分、对齐并渲染，详见 `docs/modules/asr-alignment.md`。零锚点候选仍进入补救链；只有连候选都搜不到或补救链后仍建不出时间轴才失败。高置信与 `DeepSeek版` 的现有分类保持不变。

所有主播共享一个后台执行队列，避免 Whisper、Qwen 和渲染同时占用内存。一首失败不会阻止同录播中的其他歌曲。

## 成片后投稿准备（Phase 1）

完整 MP4 渲染成功后，API 以项目 ID 幂等创建 `publish_jobs`。投稿任务只快照识别层的 `identified_title`、`identified_artist`、`identity_source`，以及自动规则已经锁定的主播显示名和 BililiveTool preset ID；歌词候选、手工显示标题和 LLM 不得覆盖这些值。旧规则没有选择 preset 时不创建准备任务，避免误用另一位主播的全局默认模板；保存选择后由常驻对账补建。

自动流水线页面通过 `GET /api/publish-presets` 代理 BililiveTool 的 `GET /api/preset/video`，显示模板名称和简介摘要；保存或编辑主播规则时，API 再次读取指定 preset，防止保存不存在的 ID。准备 worker 生成固定标题、tags 与 1920×1080 封面，将 `/output` 和 `/output-legacy` 映射到 BililiveTool 已挂载的 `/app/Folia成片` 和 `/app/历史Folia成片`。简介优先继承所选 preset 的 `config.desc`，通过 BililiveTool 真实的 `POST /api/bili/formatDesc` 展开直播时间等模板变量；preset 没有简介时才使用 Folia 的确定性简介。随后仅覆盖 `title/desc/tag/cover`，持久化不含 PassKey 的完整 payload 快照，再调用 `POST /api/bili/validUploadParams`。成功后停在 `ready`。

payload 一经快照便保持不变：临时网络失败重试同一份快照，后来修改规则或 BililiveTool preset 不会静默改写已经 `ready` 的历史任务。

Phase 1 固定 `AUTO_PUBLISH_ENABLED=0`，代码中不存在 `/api/bili/upload` 调用。BililiveTool 无法访问或 5xx 会按退避时间保留为 `pending`；缺失歌曲身份、封面或参数校验失败为 `failed`。任何这类错误都不改变原自动任务和 MP4 的完成状态。检查接口为 `GET /api/publish-jobs`、`GET /api/publish-jobs/{id}`，准备失败可用 `POST /api/publish-jobs/{id}/retry` 重试。历史验收只能显式调用 `POST /api/publish-jobs/backfill?limit=2`，单次最多补建两个；常驻对账使用 SQLite 持久化水位，不会在每次重启时扫遍历史成片。

整场任务仅在歌曲实际处理失败时记为 `completed_with_errors`。切片短于 90 秒、歌词锚点不足等按规则跳过的歌曲仍逐首保留原因；如果其余歌曲均完成，整场记为 `completed`，页面显示“完成（跳过 N 首）”，不计入失败。转录服务状态查询遇到短暂断线或超时会重试；如果后台任务随后报告 `SIGKILL`，整场错误直接显示“疑似内存不足”及转录服务给出的具体原因。`SIGKILL` 本身不证明内核 OOM，需结合系统日志判断。

## 企业微信通知

自动任务复用转录服务 `.env` 中已有的 `WECOM_WEBHOOK_URL`，在四个阶段发送纯文字通知：开始整场 ASR、逐句 ASR 结果生成、歌曲切片批次完成、整场结束汇总。正文包含主播目录名、录播文件名、结果数量和相应输出目录；切片通知还列出成功文件。**最后一条汇总通知（`outputs_completed`）无条件发送**，正文带成功/失败/跳过三个计数和逐首状态，按"该先看哪首"组织（2026-09-17 通知改版起；更早的"只在全部成功时才发"已不适用）。**一首歌都没检出时同样会发**，正文出现 `🔇 本场未检出歌曲，没有需要查看的成片`——此前这种情况会在 `process_automation_run` 里提前 return，通知永远不触发，读者只看到"开始转写、转写完成"就没有下文，跟任务卡死无法区分。自动任务关闭转录服务原有的通用 ASR 完成通知，避免同一阶段重复发送。通知发送为 best-effort，Webhook 未配置或临时失败不会改变流水线任务状态；每次投递会校验企业微信响应的 `errcode`，失败最多重试 3 次，仍失败时通知接口返回 502，自动流水线把事件名、运行 ID 和异常写入服务日志，避免再次出现“内部 HTTP 200、实际拒收却无证据”的情况。普通转录工作台仍保留原来的 ASR 完成/失败通知。

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

SQLite 表：`automation_profiles`、`automation_seen`、`automation_runs`。运行记录保存转录服务任务 ID、转录、歌曲子任务、视频工坊项目 ID 和输出链接。重试复用已经完成的转录、切片和项目；若切片完成后的路径交接曾中断，会从原批次恢复切片路径。自动任务固定使用 `asr_engine=whisper`、`skip_alignment=true`、`no_vad=true`。整场 ASR 每完成一块即更新 `asr_chunks.json`；缓存按引擎及模型校验，旧 Qwen 块不能被 Whisper 复用。失败重试从已有音频进入 ASR 阶段，不再返回整场逐字对齐阶段。

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
