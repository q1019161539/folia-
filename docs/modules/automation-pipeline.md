# 主播录播自动流水线

## 入口与边界

- 页面第四工作区“自动流水线”；前端为 `web/automation.js`。
- 编排、SQLite 状态和 API 位于 `backend/app.py`，纯校验和时间投影位于 `backend/automation.py`。
- 主播规则默认停用；保存规则时同时锁定投稿使用的主播显示名。投稿模板、封面底图和封面字体不在规则表单里设置，而在第五工作区“投稿管理”按主播设置；规则卡片在未选模板时显示“去投稿管理”。启用时先把所有现有合格 MP4 记为基线，只处理之后新增的文件。
- 主播选择由 `GET /api/automation/broadcasters` 合并媒体一级目录与录播机身份。主 API 只读挂载 bililive-tools 的 data 目录（含 SQLite WAL），从 `streamer` 和 `record_history` 按平台＋房间号关联录播目录，30 秒缓存；不写录播机配置或数据库。已有规则在唯一匹配时自动绑定，保存 `recorder_identity` 的房间号和历史目录。改名时显示最新录制目录名称，持续监听该身份的新旧目录；手动历史录播也合并查询。无记录或身份不明确的目录继续按目录监听，禁止用名字前缀猜身份。新发现目录中早于规则启用时间的文件进入基线，避免意外重跑历史。页面名单按房间号合并别名，显示绑定房间号；重复锁定同一身份拒绝创建。页面打开时读取一次，有新增时点击“刷新名单”。
- 自动流水线工作区首次打开时读取规则、任务、队列、主播目录及当前主播录播；切走再返回保留已有表单和列表，不重复扫描主播目录和历史录播。页面可见时仅每 15 秒后台刷新任务与队列；规则、主播名单及录播由对应刷新按钮或编辑动作更新。
- UI 的队列概览在桌面放在状态侧栏，手机放在任务列表最前；主播、规则、手动执行和任务记录在手机按单列页面滚动，任务记录默认显示前 10 条并可展开更多。此布局不改变首次加载、返回保留和后台刷新逻辑。
- 页面顶部的真实统计来自 `GET /api/automation/summary`：当前启用的主播规则数、按 NAS 上海日期计算的当日任务数和成功完成数、全局当前排队数。统计查询使用全部 SQLite 记录，不受最近任务列表的分页限制；无任务时显示 0 与空状态。桌面与歌词制作共用左侧导航，流水线主按钮和状态使用绿色。
- 主播选择、规则、当前队列与任务记录各为可折叠卡片。规则列表、任务列表和队列过长时在本卡片内部纵向滚动，标题及其他卡片不随之移动；切换工作区仍沿用首次加载和后台状态刷新行为。
- 已锁定的主播可以通过“手动执行以前的录播”选择历史 MP4。历史文件不受“启用时只监听未来新增文件”的基线限制，也不受自动监听的 1 GiB 门槛限制，但仍必须位于该主播目录、不是 `歌曲切片/`、不是 partial 文件且通过 `ffprobe`。手动任务复用完全相同的串行流水线；同一文件已有活动任务时拒绝重复加入，已结束任务允许再次手动执行。
- 只接收 `.mp4`、至少 1 GiB、连续两次扫描大小不变且 `ffprobe` 成功的录播；永远排除 `歌曲切片/`。

## 串行流程

2026-10-08 用户授权本批失败重试一次：外置运维脚本 retry-mang-failed-revisions-once.py（部署根目录 / NAS Git ops），默认只读预检、--execute才执行，目标为当时显式6首而非全库。完成renderer+有效MP4复用原恢复函数，不重渲染；确切终态/404可重新排原队列一次，活动renderer只恢复查询、未知/网络错误不清ID。当前响度skip/已有接受投稿均不重试。app_meta.render_revision_retry_once:<job_id>以事务认领count=1，保存旧ID/错误，重复操作不再排队；行级备份/data/render-retry-backups/20261008-once。当前API仅有投稿交接publish-retry，没有可视化重制重试入口；本次是维护流程，不是新增所有失败自动重试。现行任务不抢占，不改原成片/识别/封面次数。

2026-10-08 最新响度规则覆盖下方历史说明：平均 RMS ≤−30 dB **或**峰值 ≤−15 dB，任一满足即跳过后续流程；环境默认 PERFORMANCE_GATE_MEAN_DB=-30 / PERFORMANCE_GATE_PEAK_DB=-15。quiet-clip-v2-any / settings.logic=any 使旧 AND 缓存失效。保留切片，不修改原历史成品，不运行后续识别/歌词/Qwen/渲染/投稿。已授权芒芒未提交重制队列复查新规则，不取消已接受上传，真实演唱误拦是用户明确接受的取舍。

2026-10-07：automation_profiles.render_output_mode支持fast（旧规则默认）/smooth（逐帧MP4，无MOV）。规则卡片可单独修改默认成片，PUT /api/automation/profiles/{id}/render-output只改这一项，不改歌词效果、模板或监听范围；smooth要求Folia原生效果。process_automation_song在真正开始渲染时读取最新规则，因此已经开始的整场ASR也能使用更新后的默认。芒芒默认smooth，其余主播仍fast。

显式历史重制：POST /api/automation/profiles/{id}/render-revisions {project_ids:[...],enqueue_publish:true}。只复用已完成自动成片的源切片、权威身份与缓存歌词，按同主播同歌排除已接受投稿及重复，不提升置信等级；旧classic效果的副本用主播当前原生效果。独立新项目保存render_revision_parent_id/batch_id，不修改原演唱项目或旧MP4。render_revisions队列单次一首、同主API内存槽位；重启复用成品/查询原render_id，外部渲染器丢失ID时失败而不重新POST。GET /api/render-revisions显示批次、进度和独立投稿交接状态，自动任务卡片显示并链接新版MP4。

明确enqueue_publish的完整高置信新版成品交接到V2 pending；其他版本保留成品、标记ineligible。入队不扩大rollout白名单或打开自动投稿；交接错误只记录publish_status/publish_error，POST /api/render-revisions/{jid}/publish-retry只重试交接，不重新渲染、清空封面或重复提交已接受上传。

2026-10-08 用户恢复芒芒该批逐帧投稿，范围见automatic-publishing.md。render_revisions.priority_at保存原录播开始时间，运行中任务优先恢复、不抢占，pending按priority_at降序、同优先级保留创建顺序；默认0不改其他队列。已完成交接也按新日期优先。重制失败保留，不以旧快速版投稿；本地对齐只重制、低响度未开工克隆跳过，原项目/媒体不删除。

1. 每 30 秒扫描所有已启用主播目录，并把新录播写入 `automation_runs`。
2. 调用 `folia-video-transcriber` 将整场音频按 180 秒块送入现有 Faster-Whisper worker；关闭语音 VAD 和逐字时间计算，直接取得块内逐句时间并加回源时间 offset。整场不运行 Qwen ForcedAligner，也不发布空的逐字文件。关闭 VAD 避免把歌声误删；转录工作台的手动任务保持原选项。
3. 将逐句转录交给标题接口的 `gpt-6.1-sol`，DeepSeek V4 Flash 作为备用（`backend/song_analysis.py`）。主接口连接/超时/HTTP错误/返回格式异常时切备用，各调用一次，无隐藏重试；有效 `songs:[]`、低置信或无效句段候选不触发备用来强行判歌。两个接口均失败则整场分析失败，可用原有重试入口复用 ASR。模型只能返回歌名与首尾 ASR `segment_id`；后端根据真实句段计算时间，低于规则阈值、重叠、过短、过长或无效 ID 均跳过。任务 `timings.song_analysis` 持久化请求模型、provider、备用使用、脱敏错误与耗时；完成记录和歌曲结果原子保存，明确无歌结果重启不再请求。已有分析/切片直接复用，不批量重判历史歌曲。
   - 校验后的结果在切片前同时发布到 ASR 的录播名目录：`<录播名>_歌曲分析.json` 保存毫秒时间、segment ID、置信度、理由和未采用候选；`<录播名>_歌曲时间轴.txt` 是可读时间轴。两者用于人工审阅，实际切片仍读取同一份已校验数据写入的数据库批次，避免手工文件被篡改后绕过校验。
4. 使用 FFmpeg 流复制把完整歌曲写入原录播同级 `歌曲切片/`，默认前后 5 秒，不覆盖同名文件。自动模式不使用 `-avoid_negative_ts make_zero`，保留隐藏关键帧预卷，使可见起点对应请求时间。
5. 先由 `performance_gate.screen_clip` 免费解码切片测电平，平均 RMS ≤−32 dB 且峰值 ≤−18 dB 时标记 `skipped/suspected_quiet_background`，保留切片，直接返回，不创建歌曲项目、不运行指纹/歌词/Qwen/渲染或投稿。保存 `songs[].performance_gate`（版本、输入 stat、配置、两项电平、决定/原因）；缓存只对同版本/同输入/同阈值复用。解码失败/无音轨/90 秒超时停止该首并记 failed，不默认放行。运行环境 `PERFORMANCE_GATE_ENABLED=1`（默认）、`PERFORMANCE_GATE_MEAN_DB=-32`、`PERFORMANCE_GATE_PEAK_DB=-18`；2026-10-08 用户确认没有轻唱后收紧，原档 −38/−25 仅历史记录。阈值变更会使旧配置缓存失效，但已完成/已跳过的历史项目不自动重跑。这是低响度筛查，不证明主播身份，较响原唱可能漏过、整体偏轻的真实演唱可能误拦。通过后将整场 ASR 句段减去切片起点导入歌曲项目，不重复运行 Whisper。切片时长低于 90 秒仍直接跳过整套歌词渲染流程（状态 `lyrics_skipped_short_clip`），计入结束时汇总通知。
6. 每首切片补 Qwen 现场字时间，再对平台歌词版本评分并计算统一偏移。逐字候选无可靠字偏移时先按需分离人声重识别，仍失败则明确报错。最终平台字时间只做全曲统一平移；DeepSeek 全曲重排默认关闭，输出分类为高置信、本地对齐版及显式开启时的 DeepSeek版。详见 `asr-alignment.md`。

所有主播共享一个后台执行队列，避免 Whisper、Qwen 和渲染同时占用内存。一首失败不会阻止同录播中的其他歌曲。

此互斥由主 API 的进程内 ai_slot 实现，不能覆盖外部直接启动的转录工作台任务。`GET /api/automation/health` 返回当前扫描线程是否存活、扫描开始/成功/错误时间、异常类型、最近扫描规则数/合格文件数/入队数、耗时和重任务槽位。超过 120 秒没有新扫描开始标记 stale，仅提示检查，不自动取消任务；没有扫描、线程停止和最近扫描失败分别显示不同状态。诊断计数重启归零，异常正文不进入接口，详细 traceback 仍查日志。`/healthz` 本身不证明扫描成功。

## 成片后投稿准备（Phase 1）

完整 MP4 渲染成功后，API 以项目 ID 幂等创建 `publish_jobs`。投稿任务只快照识别层的 `identified_title`、`identified_artist`、`identity_source`，以及自动规则已经锁定的主播显示名和 BililiveTool preset ID；歌词候选、手工显示标题和 LLM 不得覆盖这些值。规则没有选择 preset 时不创建准备任务，避免误用另一位主播的全局默认模板。常驻对账只处理上次水位之后完成的成片，未选模板期间完成的成片在选好模板后不会自动补建。

### 投稿管理页

2026-10-07起当前行为见[歌曲项目与高置信自动投稿V2](automatic-publishing.md)。以下底图/字体/只停ready说明保留为旧Phase1维护记录，不代表新worker。旧任务隔离，新流程不依赖底图或字体。

第五工作区“投稿管理”（`web/publish.js`、`web/publish.css`）列出所有锁定主播，每位主播一张卡片：

- **投稿模板**：`GET /api/publish-presets` 代理 BililiveTool 的 `GET /api/preset/video`，下拉选择并显示简介摘要；`PUT /api/automation/profiles/{id}/publish` 保存 `bililive_preset_id` 与 `cover_font_id`，API 保存前再次读取 preset，拒绝不存在的 ID，可选“未选择”。任何接口都不回退到 `BILILIVE_PRESET_ID` 全局默认；`default_id` 仅供参考，页面不据此预选。流水线规则的创建/编辑接口不再要求模板：新建为空，编辑未提交时保留原值。
- **封面字体**：默认思源黑体，可选思源宋体或字体库中的上传字体。内置字体使用 Noto CJK 集合中的简体中文字形（索引 2）。保存时实际加载并绘制测试字形，失败返回 400；准备阶段字体已被删除则任务失败并提示重新选择。
- **封面底图**：`GET/POST /api/automation/profiles/{id}/covers`、`GET/DELETE .../covers/{cover_id}`。复用图片库校验（PNG/JPEG/WebP、≤10 MB、≤4000 万像素、长边缩至 2048、按内容去重），存于 `data/cover-templates/<规则 ID>/`。准备任务按“主播+歌名”稳定哈希在该主播自己的底图里选一张；没有底图时任务 `failed`，提示去投稿管理页上传，上传后可重试。旧 `cover_templates/generic/` 占位图不再使用。
- **封面预览**：`POST /api/automation/profiles/{id}/cover-preview`，填试用歌名，可指定某张底图和尚未保存的字体，只写 `data/cache/cover-preview/<规则 ID>.jpg`，不创建任务。
- **字体库**：与歌词效果共用 `/api/fonts`；可上传，`DELETE /api/fonts/{id}` 删除上传字体。内置字体不可删；被歌词项目样式、流水线规则样式或封面设置引用时返回 409 并列出使用位置；正在渲染时拒绝删除。
- **投稿准备任务**：显示最近 20 条 `publish_jobs` 的状态与错误，准备失败的可“重新准备”（`POST /api/publish-jobs/{id}/retry`）。

准备 worker 生成固定标题、tags 与 1920×1080 封面，将 `/output` 和 `/output-legacy` 映射到 BililiveTool 已挂载的 `/app/Folia成片` 和 `/app/历史Folia成片`。简介优先继承所选 preset 的 `config.desc`，通过 BililiveTool 真实的 `POST /api/bili/formatDesc` 展开直播时间等模板变量；preset 没有简介时才使用 Folia 的确定性简介。随后仅覆盖 `title/desc/tag/cover`，持久化不含 PassKey 的完整 payload 快照，再调用 `POST /api/bili/validUploadParams`。成功后停在 `ready`。

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

主接口复用 `TITLE_API_KEY`、`TITLE_API_BASE_URL`、`TITLE_API_PROXY`，不受 `AI_TITLE_ENABLED` 控制；独立 `SONG_ANALYSIS_MODEL=gpt-6.1-sol`、`SONG_ANALYSIS_TIMEOUT_SECONDS=600`（HTTP各阶段等待上限，不是整个操作总时限）。备用沿用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-v4-flash`。主或备用有一个已配置即可启用规则；主缺失会标明缺少密钥并用备用。密钥只在运行环境，不进入数据库/文档/日志。规则页显示主/备用配置，任务记录显示本次实际请求模型（不证明第三方真实后端）。整场 ASR、单曲Qwen、指纹身份以及默认关闭的DeepSeek全曲歌词重排不变。

## 最低验证

```bash
python -m py_compile backend/app.py backend/automation.py
python -m unittest discover -s backend -p "test_*.py"
node --check web/automation.js
node --check web/clips.js
docker compose config
```

上线后确认所有规则默认停用；创建测试规则时应先验证现有 MP4 全部进入基线且不产生自动任务。不得为了测试复制或修改原录播。
