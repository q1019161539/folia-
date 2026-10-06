# 架构说明

当前实现基线：2026-10-06。历史改动与验收记录见 STATUS.md，不应把历史规则当成当前规则。

## 服务关系

```text
浏览器 :18081 → studio-web（Nginx + Basic Auth）
                  ├─ /api → studio-api（FastAPI、SQLite、任务编排）
                  ├─ /transcriber → transcriber（Flask、子进程、断点文件）
                  └─ /folia-native → folia-renderer（Chromium、SSE、FFmpeg）
studio-api
  ├─ local-worker：Faster-Whisper CPU/int8、Qwen ForcedAligner CPU/float32
  ├─ lyrics-service：LDDC，QQ/酷狗/网易云/LRCLIB
  ├─ transcriber：整场 ASR、按需人声分离重识别、结果与通知
  ├─ folia-renderer：原生预览与三种成片输出
  ├─ DeepSeek：歌曲范围分析；全曲时间轴重排默认关闭
  ├─ ACRCloud（默认）/Shazam：歌曲指纹身份
  └─ BililiveTool：读取 preset、格式化简介、校验投稿参数；不自动上传
```

## 自动数据流

录播稳定性检查 → 整场 180 秒块 Whisper ASR（无 VAD、无整场 Qwen）
→ DeepSeek 返回首尾句段 ID → 本地校验并计算毫秒 → FFmpeg 流复制切片
→ 导入切片相对 ASR → 单曲 Qwen 逐字证据 → 指纹认歌
→ 标准歌词版本评分 → 唯一全曲偏移 → 渲染完整 MP4 → 独立投稿准备 → ready。

标准逐字成品轴使用平台原始字时间加同一个偏移；Qwen 只提供定位证据，不能逐字回写平台节奏。逐字证据不足先按需分离人声重识别，仍不可靠则明确失败，不静默退为逐句偏移。

手动歌词制作、手动时间轴批量切歌、转录工作台可独立使用，不必经过自动队列。

## 数据与所有权

- SQLite `/data/studio.db`：jobs、clip_batches、automation_profiles、automation_seen、automation_runs、publish_jobs、app_meta。
- jobs 的 identified_* 是识别身份，matched_* 位于歌词报告，manual_* 是人工搜索信息。普通候选不得覆盖识别身份；严格 evidence_consensus 恢复属于识别流程。
- 转录服务任务 JSON、音频、分块断点保存在既有 folia-asr-mvp 的 work/output；不是主 SQLite 的副本。
- 原生渲染任务及预览会话主要在渲染器内存中，重启后不能直接恢复原 render ID。
- 投稿独立持久化且以 source_job_id 唯一约束去重；payload 校验前冻结，ready 不提交。

## 文件边界

- `/media/bililive` 与转录器 `/input`：统一新旧录播视图，只读。
- `/media-output`：新盘录播根，只写歌曲切片，不改原录播。
- `/output`：`/vol2/1000/video/Folia成片`；`/output-legacy`：旧盘成片，只读。
- 模型、数据库、字体、图片、封面底图和工作目录仍位于第一块盘。
- BililiveTool 将新旧成片分别读取为 `/app/Folia成片`、`/app/历史Folia成片`，不复制 MP4。

## 调度与检查

主 API 单进程后台线程扫描并串行消费自动队列。ai_slot 串行保护经主 API 发起的重任务；worker 另有模型锁，渲染器另有渲染锁。ai_slot 不是跨进程锁，直接在转录工作台启动任务不能据此假定与 API 全局互斥。

`/healthz` 是进程/基础配置检查，不证明外部服务或后台扫描成功。`GET /api/automation/health` 补充当前进程扫描时间、错误类型、扫描/入队计数、线程状态及重任务槽位。诊断计数在 API 重启后重置，不是业务任务数据库。

代码入口和维护顺序见 CODE_MAP.md；挂载与升级见 modules/deployment.md。
