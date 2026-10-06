# 代码维护地图

## 基线与范围

线上目录：/vol1/1000/docker/folia-video-studio；NAS Git 副本：/vol1/1000/docker/folia-git。运行以部署目录和镜像为准；Git 同步必须显式选择源码，不包含 .env、数据库、模型、媒体、任务缓存或备份。不使用宽泛 git add .。

本次只整理文档、统一源码基线、补充只读扫描诊断，不拆大文件、不修改身份/时间轴算法、不修改封面、不实现投稿 Phase 2。

## 按问题找代码

| 问题 | 首先阅读 | 调度/接口入口 |
| --- | --- | --- |
| 自动录播没入队 | automation.py、recorder_identity.py、automation_runtime.py | app.py scan_automation_profile / automation_scan_loop |
| 整场转录/断点 | transcriber/app/pipeline.py、asr.py、outputs.py | transcriber/web.py；app.py ensure_automation_transcript |
| 歌曲切错范围 | automation.py 的本地校验 | app.py detect_songs_deepseek / create_automation_clip_batch |
| 歌名/歌手不对 | song_identity.py、song_identity_diagnostics.py | app.py identify_song_fingerprint / adopt_identified_song |
| 歌词版本或偏移不对 | standard_timeline.py、word_timeline.py、lyrics-service/main.py | app.py auto_standard_timeline_task |
| Qwen 加载或字时间 | worker.py | app.py ensure_word_level_asr / force_align_task_locked |
| 歌词预览/成片 | folia_native.py、folia-renderer/app.py、web/folia-studio-bridge.js | app.py render_task / render_task_locked |
| 投稿准备 | publishing.py、web/publish.js | app.py ensure_publish_job / prepare_publish_job |
| 字体/图片 | font_assets.py、image_assets.py | app.py 素材接口 |
| 排队/重任务冲突 | ai_slot.py | app.py heavy_ai_slot / automation_queue |

## 数据与错误检查

- 扫描检查：GET /api/automation/health；任务结果：/api/automation/runs；当前队列：/api/automation/queue。
- 扫描诊断仅记录异常类型，完整 traceback 留在日志，防止 HTTP 错误文本中的凭据进入检查接口。
- SQLite 主状态、转录任务 JSON、渲染器内存任务是不同状态域。重启不能笼统视为所有阶段都能恢复。
- healthz 部分字段是能力声明，不是对外部服务的实时探测。

## 后续小步维护顺序

1. 先对照当前源码与镜像/文档，保留已有数据和变更。
2. 优先修复可复现的错误；最近 SQLite 锁问题须按真实 traceback 独立诊断。
3. 如拆分 app.py，先提取数据库访问与迁移，保持接口/状态不变，再逐个提取编排模块，每次保留回归测试。
4. 新 Python 模块必须加入 backend/Dockerfile；单实例内存锁不能通过增加 Uvicorn worker 横向扩容。
5. 封面左侧留白、带《》、去主播名是尚未落实的样式需求；当前发布函数仍为居中标题、暗色大底板与主播名。
6. 自动上传 Phase 2 未实现，保持 AUTO_PUBLISH_ENABLED=0；不引入 submit_unknown 或自建 B 站上传器。
