# ASR 与逐字对齐

当前基线：2026-10-06。旧版混合时间轴、DeepSeek 重排和旧残差阈值的历史记录见 STATUS.md；不要从历史记录推导当前行为。

## 代码入口

- backend/worker.py：模型推理与 `/recognize`、`/force-align`、`/unload`。
- transcriber/app/pipeline.py、asr.py：分块 ASR、断点、独立阶段与输出。
- backend/app.py：ensure_word_level_asr、auto_standard_timeline_task、force_align_task_locked。
- backend/standard_timeline.py、word_timeline.py：候选、证据、偏移及字时间。
- backend/song_identity.py：识别身份与人工搜索信息分离。

## 自动整场与单曲

自动整场固定使用 Faster-Whisper large-v3-turbo、CPU/int8、180 秒块、无 VAD、skip_alignment=true。每块落盘，断点按引擎/模型和块参数校验；不运行整场 Qwen，也不生成空逐字文件。DeepSeek 只返回歌曲范围的 ASR segment ID，本地校验后换算时间。

切片减去起点导入已有逐句 ASR，不重复整场识别。短于 90 秒的歌曲跳过歌词渲染。进入标准匹配时补单曲 Qwen 现场字时间，个别句段可局部补救，然后做指纹识别和标准歌词搜索。默认 ACRCloud，可配置切换 Shazam；低置信时继续独立窗口/ASR 证据复查，严格条件下允许 evidence_consensus 纠正身份。

手动转录工作台仍有 local Qwen ASR、Whisper 和云端等独立选项，不能将自动路径等同于所有手动路径。

## 标准时间轴

1. 解析并过滤标准歌词制作名单、广告和标题横幅。
2. 使用句锚点与有效 Qwen 字锚点评分版本；同名或合理短标题的真实逐字版优先，指纹歌手提供有限同分优势。
3. 核心锚点用于时钟/置信度，证据锚点用于对应关系；可疑区域与部分残差指标仅作诊断，不能套用历史 max drift/P90 硬失败规则。
4. 逐字版需有可用且可靠的字偏移；覆盖不足或模型不稳定时按需分离人声并重识别，失败后明确报错。
5. 最终行和平台字时间统一增加同一个 shift_ms；Qwen 不覆盖成品字节奏。无时间文本沿用估计轴并标记相应置信度。
6. DEEPSEEK_FULL_REALIGN 默认关闭；confidence_tier 为 high/local/deepseek，目录映射到高置信/本地对齐版/DeepSeek版。历史 mode='standard-piecewise' 不代表当前一定在做分段拉伸。

标准行带 fixed_timeline 等标识时，后续 `/force-align` 保留行框和平台字时间。旧 ASR 推导行与粘贴歌词仍可在受限音频窗口逐句运行 Qwen。

## 身份与编辑

identified_title、identified_artist、identity_source 由识别流程写入。普通歌词候选仅进入 matched_*；manual_title/manual_artist 可优先影响后续搜索，不覆盖数据库识别身份，投稿也不采用人工或候选字段兜底。

页面的最终预览读取保存后的 alignment.lines；正文或时间被手工修改时清除不再有效的旧字时间。纠错黄色只供校对，不进入最终成片。

## 离线与内存

worker 在依赖导入前固定 HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1；Compose 与 Workerfile 同步设置。仓库名通过 snapshot_download(local_files_only=True) 解析缓存快照，再把目录传给 Qwen，覆盖内部独立 processor 加载。支持 ALIGNER_MODEL 指定目录；关键文件缺失明确失败，不运行时下载。

Whisper 与 ForcedAligner 切换时显式卸载。经主 API 发起的识别、整场转录、分离、对齐和渲染共用 ai_slot；它是单进程锁，不覆盖所有外部直接调用。新离线修复针对 worker ForcedAligner，不应宣称所有手动 Qwen ASR 路径都已验证离线。

## 输出与验证

用户结果发布到转录服务 output/recordings/<主播>/<日期>/<录播名>/，内部任务 ID 保留作隔离、日志和断点。主项目的结果与进度在 jobs.alignment 内保存。

最小检查：相关 Python 编译、backend 匹配测试、worker 离线缓存测试、对应服务健康；真实验证只用短片段或现有项目副本，不以整场大录播作为首次测试。离线可用性不等于歌词文本、每个字时间或完整歌曲质量已验收。
