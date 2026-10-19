# 代码维护地图

## 基线与范围

线上目录：/vol1/1000/docker/folia-video-studio；NAS Git 副本：/vol1/1000/docker/folia-git。运行以部署目录和镜像为准；Git 同步必须显式选择源码，不包含 .env、数据库、模型、媒体、任务缓存或备份。不使用宽泛 git add .。

维护拆分保持小步，不改身份/时间轴算法。2026-10-07新增歌曲级投稿V2，当前上线范围及验收阻塞见STATUS.md；原单次演唱与成片不合并、不删除。

## 按问题找代码

| 问题 | 首先阅读 | 调度/接口入口 |
| --- | --- | --- |
| 自动录播没入队 | automation.py、recorder_identity.py、automation_runtime.py | app.py scan_automation_profile / automation_scan_loop |
| 整场转录/断点 | transcriber/app/pipeline.py、asr.py、outputs.py | transcriber/web.py；app.py ensure_automation_transcript |
| 歌曲切错范围 | song_analysis.py 的主/备用调用、automation.py 的本地校验 | app.py process_automation_run / create_automation_clip_batch |
| 明显很轻的背景音乐被当成演唱 | performance_gate.py 的 RMS/峰值筛查（不是声纹检测） | app.py process_automation_song，先于创建项目/歌词/Qwen |
| 歌名/歌手不对 | song_identity.py、song_identity_diagnostics.py | app.py identify_song_fingerprint / adopt_identified_song |
| 歌词版本或偏移不对 | standard_timeline.py、word_timeline.py、lyrics-service/main.py | app.py auto_standard_timeline_task |
| Qwen 加载或字时间 | worker.py | app.py ensure_word_level_asr / force_align_task_locked |
| 歌词预览/成片 | folia_native.py、folia-renderer/app.py、web/folia-studio-bridge.js | app.py render_task / render_task_locked |
| 主播默认逐帧、缓存歌词历史重制 | automation.py render_output_mode、render_revisions.py、web/automation.js | app.py update_profile_render_output / render_revision_loop / enqueue_render_revision |
| 歌曲项目、AI标题、GPT封面、投稿/审核状态 | publish_v2.py、title_generation.py、publishing.py、cover_frames.py、web/publish.js | app.py ensure_publish_job / publish_worker_loop；旧prepare_publish_job仅遗留兼容、不由新worker调用 |
| 字体/图片 | font_assets.py、image_assets.py | app.py 素材接口 |
| 排队/重任务冲突 | ai_slot.py | app.py heavy_ai_slot / automation_queue |

## 数据与错误检查

- 投稿合集：publishing.py collection_capabilities/collection_job、publish_v2.py poll_collection、web/publish.js publishCollectionInfo；BililiveTool固定镜像适配源/精确补丁与测试在ops/bililive-season-fix-20261013，仅新opt-in，不补加旧稿。

- SQLite 锁/提交恢复：backend/sqlite_runtime.py、app.py db()；投稿外部响应恢复与锁失败修复：publish_v2.py checkpoint/recover_responses/recover_database_failures。不得为数据库锁重放整个上传或 AI 请求。

- 扫描检查：GET /api/automation/health；任务结果：/api/automation/runs；当前队列：/api/automation/queue。
- 扫描诊断仅记录异常类型，完整 traceback 留在日志，防止 HTTP 错误文本中的凭据进入检查接口。
- SQLite 主状态、转录任务 JSON、渲染器内存任务是不同状态域。重启不能笼统视为所有阶段都能恢复。
- healthz 部分字段是能力声明，不是对外部服务的实时探测。

## 后续小步维护顺序

1. 先对照当前源码与镜像/文档，保留已有数据和变更。
2. 优先修复可复现的错误；最近 SQLite 锁问题须按真实 traceback 独立诊断。
3. 如拆分 app.py，先提取数据库访问与迁移，保持接口/状态不变，再逐个提取编排模块，每次保留回归测试。
4. 新 Python 模块必须加入 backend/Dockerfile；单实例内存锁不能通过增加 Uvicorn worker 横向扩容。
5. 投稿V2采用GPT完整封面，人物右侧、左侧完整《歌名》、不加主播名；旧本地叠字仅遗留预览，不作为失败兜底。AI文字没有自动视觉核验。
6. BililiveTool真实上传已实现并完成三首验收，但当前仍acceptance白名单；投稿页现可启用/暂停新成片自动投稿，首次水位和暂停区间持久化，不补投历史或暂停期间成片。部署开关不等于自动启用；不引入submit_unknown或自建B站上传器。
