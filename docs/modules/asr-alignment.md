# ASR 与逐字对齐

## 入口

- 主 API：`backend/app.py`
- 模型 worker：`backend/worker.py`
- 页面控制：`web/app.js`
- 进度样式：`web/align-progress.css`

## 当前流程

整场录播转录在内部仍用任务 ID 隔离 work 与重试状态，但给用户查看的结果按原录播路径发布到 `folia-asr-mvp/output/recordings/<主播>/<日期>/<录播名>/`。正文文件名为 `<录播名>.txt`，逐句 JSONL 为 `<录播名>.jsonl`，逐字 JSONL 为 `<录播名>_逐字.jsonl`。若 ASR 中途失败但已有逐块断点，则同目录生成 `<录播名>_未完成.txt` 与 `<录播名>_ASR断点.json`；自动歌曲分析还会生成 `<录播名>_歌曲分析.json` 和 `<录播名>_歌曲时间轴.txt`。内部 ID 目录不作为用户查找结果的入口。

1. 选择切片时，新任务会用视频文件名（去掉扩展名）预填歌名；恢复标题为空的旧任务时也会补上文件名，因此可以在识别前直接按歌名搜索标准歌词。
2. `POST /api/jobs/{id}/recognize` 启动识别。
3. 本地模式调用 worker `/recognize`，Faster-Whisper 返回句段和词时间。
4. 标准歌词通过独立 LDDC 服务聚合搜索 QQ、酷狗、网易云和 LRCLIB；LDDC 整体不可用时才回退旧网易云接口。歌名精确匹配优先，歌词片段也可作为查询。
5. 用户选择或粘贴标准歌词，`PUT /api/jobs/{id}/song` 先清除作词、作曲等署名行，再以 ASR 短句及其词时间为主时间轴，按演唱顺序把每段匹配到标准歌词的连续子串。标准歌词只纠正这段已识别内容中的错字或少量漏字，不把一个局部 ASR 片段扩写成完整歌词行。
6. 普通匹配至少需要 2 个原样字符且原样字符覆盖 ASR 正文的 60%。针对演唱中大量同音错字，另有受控的顺序弱匹配：必须已有 4 秒内的前句锚点、只允许匹配下一条标准歌词、最多合并两个连续 ASR 段，并限制正文长度比例；等长长句至少保留 2 个原样字符。这样能纠正“这样霸诊的时间”一类弱识别，同时不能越过 ASR 空白补歌词。一个 ASR 段可以覆盖相邻两行歌词；只识别到半句时保留半句并标记 `partial=true`。
7. `POST /api/jobs/{id}/force-align` 启动 Qwen 对齐。标准歌词时间轴模式的行已经完成最终时间轴，全部直接保留；Qwen 不再改写它们的行框或逐字时间。该接口只对旧的 ASR 推导行和手工粘贴歌词逐条截音频处理，每个已接受的 ASR 片段只在自身 `asr_start_ms` 到 `asr_end_ms` 前后约 300 ms 的音频窗口内细化。
8. worker `/force-align` 返回字符时间，主 API 将时间换回歌曲绝对时间，并统一修复极少量句界重叠。
9. 每句完成后写入 SQLite 的 `alignment.aligner_progress`。

## 标准歌词时间轴模式

- `POST /api/jobs/{id}/standard-timeline/auto` 复用项目中已有的 `asr_segments`，不会重新识别原始文字，但会先调用 `ensure_word_level_asr`（`backend/app.py`）补一次逐字级 ASR：若切片的逐句转录还没有 `timing_source=='qwen-forced-aligner'` 的词，就只对这个歌曲片段运行 Qwen 对齐，再按字符数切回各句段；个别句段可在自身时间窗口内补救。之后才按文件名搜索多源候选，不足时再用 ASR 歌词片段补充搜索。
- 自动流水线的整场 Faster-Whisper 只生成带真实起止时间的逐句 `transcript.jsonl`，不运行整场 Qwen，也不生成空的 `transcript_words.jsonl`。自动切片把整场绝对时间换算为切片相对时间；歌曲片段补 Qwen 字时间，不重复运行整场 ASR。手动转录的原有 Qwen 逐字输出仍按自身选项生成。
- LDDC 逐字候选会用 Qwen 现场字锚点帮助版本评分、计算唯一全曲偏移并生成诊断。选定候选后，最终逐字轴只使用平台原始字时间加这个统一偏移；Qwen 字时间不写回成品时间轴。
- `backend/standard_timeline.py` 解析标准 LRC 的毫秒时间、多时间标签和 `[offset]`；在评分前过滤作词/制作/乐器/录音室等名单、版权提示、平台广告和带已知歌名或歌手的标题横幅。随后通过多个 `ASR 起点 - LRC 起点` 锚点聚类、文字相似度、演唱顺序、时间残差、跨度和标题相似度选择版本。重复副歌由同一偏移聚类和单调顺序消歧。
- **歌名先由音频指纹识别，低置信时再做证据复查**：补齐逐字 ASR 后，正常路径仍用 30 秒窗口 / 25 秒步进寻找 ACRCloud 首个命中，高置信歌曲到此为止。歌词初选低置信时才从下一个未检查窗口继续扫描；两个独立窗口返回同一归一化歌名即确认，扫描过程逐窗记录命中、无匹配和错误。复查还会均衡搜索当前身份和两个 ASR 歌词片段；若异名歌词与 ASR 形成严格强证据（高置信、核心锚点 ≥5、跨度 ≥10 秒、比分领先 ≥40），以 `evidence_consensus` 纠正身份并同步切片名。普通歌词候选仍不能写回身份。两条恢复路径都失败后才进入人声分离补证据。
- 候选选择先看是否逐字版，再看可信度、标题相似度、综合分和锚点数。**同等标题匹配度下逐字版优先**（`choose_best_timeline_candidate`）：逐字版提供可原样平移的标准字级时间，而同名的逐行 DJ/翻录版没有；"标题相似度在最高分 0.05 以内"这个下限防止偏好跨到另一首歌的逐字版上。
- **可信度只由行级证据决定**（`backend/word_timeline.py` 的 `score_provider_timeline`，2026-09-16 起）：行级判据是锚点数`>=3`、跨度`>=10s`、残差p90`<=1.5s`。逐字锚点用于候选排名、全局偏移计算和质量诊断，不参与置信度投票，也不写回最终标准时间轴。此前逐字侧的独立高置信判据实际衡量的是现场翻唱与发行版母带的贴合程度，而不是歌词是否选对。
- **多级补救链**（`auto_standard_timeline_task`）：先跑免费的本地可疑区域探测 `find_suspect_anchor_regions`（`backend/standard_timeline.py`）——即使本地整体判定已经是高置信，个别行也可能因为大段合并、长时间没有锚点等原因单独有问题；再算 `max_anchor_drift_ms`，看有没有哪个锚点偏离整首 shift 超过 `GLOBAL_SHIFT_DRIFT_LIMIT_MS`（2000ms）。**本地判定低置信、探测到可疑区域、单点漂移超限，三者任一成立就需要 AI 介入（`need_ai_help`）**，介入方式统一是把完整真实 ASR 逐字时间轴和完整标准歌词一次性交给 `full_song_deepseek_realign`（见下）做全曲重排，不再有"只打补丁、保留其余本地锚点"的中间方案——2026-09-15 晚间删除了曾经存在的"区域锚点合并"机制（`align_lyrics_deepseek`/`merge_local_and_deepseek_anchors`/`resolve_deepseek_lyric_matches`/`expand_deepseek_matches_to_anchors`），因为它在补丁边界处容易和未改动的行产生时间重叠：真实案例《世界上的另一个我》用区域打补丁方案量出过 30 处行重叠，改用全曲重排后降到 6 处。**`confidence_tier`（`high`/`deepseek`）的唯一判定标准是 `need_ai_help`**——指纹认歌本身不算"AI 辅助对齐时间轴"，换到正确候选后如果本地够格、没有可疑区域、也没有超限漂移，就还是"高置信"；**AI 没能给出可用结果时保留本地时间轴，但 tier 仍然是 `deepseek`，不会因为 AI 补救失败就回退成"高置信"**（这是修复 2026-09-15 深夜发现的一个真实 bug：旧公式在 AI 没有实际贡献锚点时无条件判"高置信"，完全不看本地判断本身是否够格，导致选错候选、且 AI 补救没成功产出结果的《西楼》被误标为高置信直接出片）。**不再有"低置信"这个输出概念**：只要本地够格且没有可疑区域就是高置信；否则一律归入 DeepSeek 版，渲染输出目录第二级从 `低置信` 改名为 `DeepSeek版`；旧的 `低置信` 目录和历史文件不删除、不搬动。零锚点候选不再直接判定为硬失败，也会送进这条补救链；真正的硬失败只剩"连一个候选都搜不到"或者补救链跑完仍然建不出任何时间轴两种情况。
- **整首平移**（`build_shifted_timeline`，2026-09-16 起）：选中有时间 LRC 后，所有行和全部平台逐字时间统一加同一个 `shift_ms`，发行版自身的行间及字间节奏原样保留。锚点只负责选择候选、计算这个偏移、挂接证据和生成诊断，不能移动单独的行或字符。全部与视频相交的标准歌词行进入新时间轴，包含 ASR 漏识别行；带平台逐字时间的行以末字结束时间收尾，没有逐字时间时才使用行距兜底。
- 至少 3 个独立锚点、锚点跨度至少 10 秒且 90 分位残差不超过 1.5 秒才算行级判据达标（这也是唯一的置信度判据，见上）。无时间歌词可按已匹配 ASR 行在锚点间插值并向两端外推，但对应候选仍需经过上面的置信度/补救链判定；完全没有文字锚点的候选不再直接失败，见上面的多级补救链。
- 结果保存在 `alignment.timeline_match`，状态执行中为 `timeline_matching`。旧项目只有主动执行该接口后才进入新模式；手工粘贴纯文本仍沿用 ASR 证据匹配。
- 90 秒以下的切片在进入这一整套流程之前就直接跳过（`auto_standard_timeline_task` 最开始检查 `media_duration`），状态记为 `lyrics_skipped_short_clip`，不搜索候选、不补逐字 ASR、不渲染；自动流水线的整场结束汇总通知（`outputs_completed`）会列出这类跳过的歌曲和归入 `DeepSeek版` 的歌曲，不再逐首单独发通知。

进度字段包括 `status`、`done`、`total`、`succeeded`、`failed`、`percent`、`phase` 和 `current_text`。

## 页面逐字状态

- 只有 `timing_precision=forced-character`、`words` 非空、单字正文与整句正文完全一致且时间有效的行，才显示绿色“逐字 ✓ · N 字”。
- 其他行统一显示黄色“未逐字”；若 `alignment.aligner.failed` 有对应记录，鼠标悬停可查看该行失败原因。
- 完成进度会持续显示逐字成功数与未逐字数；部分失败使用黄色状态，不把任务整体 100% 当作每行均成功。

## 识别纠错语义

- `timing_precision=corrected-character` 表示该行已用 ASR 字符时间投影到标准歌词，但尚不等于 Qwen 强制逐字完成。
- `corrections[]` 保存标准字位置、ASR 原字以及 `replace`/`insert` 来源；对应的 `words[]` 同步保存 `corrected`、`original_text`、`correction_kind`。
- 时间轴和歌词效果预览用黄色显示这些改字，悬停可查看 ASR 原字；黄色只用于人工校对，不进入 ASS 或最终视频。
- 一条 ASR 句段可以连续覆盖多行标准歌词；若片段开头无法匹配，会继续检查片段内部而不是丢弃整个 ASR 段。只识别到标准歌词的一部分时只输出有证据的子串，不补全未识别的前后文。
- 旧的 ASR 证据模式中，没有可靠歌词匹配的聊天或噪声段不进入时间轴，完全没有 ASR 依据的标准歌词也不进入输出。只有已成功执行标准歌词时间轴匹配、并带有 `alignment.timeline_match` 的项目，才允许标准 LRC 中无 `segment_ids` 的已验收行进入预览和渲染。
- 手工改动某行正文后清除该行旧的逐字时间和纠错来源，避免黄色标记错位。

## 时间边界修复

- Qwen 偶尔会给最后一个字符返回零时长；worker 使用本次结果的典型字符时长补齐，不再把最后一个字错误拉到整个搜索窗口末端。
- 标准歌词时间轴模式不再运行逐行 Qwen 回写；平台行时间和逐字时间只做一次统一平移。旧的 ASR 证据模式仍在有界 ASR 窗口内运行 Qwen，并以返回字时间细化对应行。
- 行顺序保护比较相邻行的起点，防止重复副歌抢到前一段或后一段；不会再用上一句最后一个长音强迫下一句后移。收尾标准化只在安全时缩短前一句尾部，允许接唱、叠唱或延音形成的少量真实重叠，不移动可靠的后续起点。
- 不再按“字幕持续时间过长”直接压缩已有逐字结果：延音和间奏无法仅靠时长可靠区分。防止跨间奏的主要约束是 ASR 片段边界和约 300 ms 的 Qwen 搜索窗口。

## 内存策略

- Whisper：CPU/int8，默认 `large-v3-turbo`。
- Qwen：CPU/float32，模型 `Qwen/Qwen3-ForcedAligner-0.6B`。
- 视频工坊 worker 内的 Whisper 与 ForcedAligner 互斥常驻，切换时显式卸载并回收内存。
- 自动整场转录使用现有 `local-worker` 的 Faster-Whisper，启动前先释放该 worker 上闲置的 Qwen/Whisper 模型；转录服务本身不再加载 Qwen3-ASR 或整场 ForcedAligner。切片后才在同一 worker 上加载 Qwen 处理该歌曲，避免两个大模型并存。
- 整场 ASR 每完成一个 180 秒块就原子更新 `work/jobs/<run_id>/asr_chunks.json`。自动任务同时关闭外部分段和 Faster-Whisper 内部的语音 VAD，防止歌声被误删；手动转录任务保持原选项。复用断点还须校验引擎与模型，不能把旧 Qwen 块用作 Whisper 结果。

## 修改后的最低验证

```bash
python -m py_compile backend/app.py backend/asr_matching.py backend/standard_timeline.py backend/word_timeline.py backend/worker.py
python -m unittest discover -s backend -p "test_*.py"
node --check web/app.js
docker compose build studio-api local-worker studio-web
docker compose up -d studio-api local-worker studio-web
docker compose ps
```

真实验证至少要包含“一个 ASR 句段对应两行标准歌词、一个同音错字、一个 ASR 漏字、一个局部歌词和一个完全未唱行”，并检查局部歌词不被补成整行、纠错来源、时间单调性、黄色预览和未唱行不伪装成功。不要用整场录播作为第一次验证。
