# 文档索引

新对话固定先读：

1. 根目录 `AGENTS.md`：协作边界和安全规则。
2. `docs/STATUS.md`：线上现状、最近验证和待办。
3. 只读本次任务对应的模块文档。

| 任务类型 | 应读取文档 | 主要代码 |
| --- | --- | --- |
| ASR、漏字、Qwen、时间戳、进度 | `modules/asr-alignment.md` | `backend/worker.py`、`backend/app.py`、`web/app.js` |
| LDDC、多平台搜索、标准逐字歌词 | `modules/lyrics-sources.md` | `lyrics-service/`、`backend/word_timeline.py` |
| 歌词特效、透明叠加、预览、成片 | `modules/lyrics-preview-render.md` | `folia-renderer/`、`web/`、`backend/folia_native.py` |
| 时间轴文档、批量切歌、中止 | `modules/batch-clips.md` | `web/clips.js`、`backend/app.py` |
| 主播监听、自动判歌、整套自动出片 | `modules/automation-pipeline.md` | `web/automation.js`、`backend/automation.py`、`backend/app.py` |
| 歌曲项目、高置信自动投稿、AI标题、GPT封面、主播模板 | `modules/automatic-publishing.md` | `backend/publish_v2.py`、`backend/title_generation.py`、`web/publish.js`、`backend/publishing.py`、`backend/app.py` |
| 免费本地封面参考帧、区域评分与缓存 | `modules/cover-reference-frames.md` | `backend/cover_frames.py`（V2准备阶段调用） |
| 长篇歌曲单集、同歌去重、响度与首尾转场 | `modules/song-compilations.md` | `ops/compilation-20261018/`（独立任务，不是投稿流水线） |
| Docker、端口、挂载、升级、故障 | `modules/deployment.md` | `compose.yaml`、`backend/*file`、`nginx/` |
| 服务关系、数据流、目录用途 | `ARCHITECTURE.md` | 全局 |
| 接手维护、代码入口、状态域与后续拆分 | `CODE_MAP.md` | 全局 |
| 为什么这样设计 | `DECISIONS.md` | 全局 |
| 分享源码、密钥检查与提交防泄露 | `../SECURITY.md` | `ops/security/`、`.github/workflows/secret-scan.yml` |

`experiments/` 保存 AMLL、lyrics-studio 等上游参考代码。只有在比较或移植上游效果时才读取，日常故障排查不要扫描它。
